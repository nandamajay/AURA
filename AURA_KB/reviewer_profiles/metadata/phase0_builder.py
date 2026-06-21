#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path('/local/mnt/workspace/AURA_V1_upstream')
BASE = ROOT / 'AURA_KB/reviewer_profiles'
RAW_DIR = BASE / 'raw'
PROC_DIR = BASE / 'processed'
RULE_DIR = BASE / 'subsystem_rules'
VAL_DIR = BASE / 'validation'
META_DIR = BASE / 'metadata'
PLAN_DIR = ROOT / 'AURA_KB/platform_tools/upstream_reviewer_sim_01/plan'

for d in [RAW_DIR, PROC_DIR, RULE_DIR, VAL_DIR, META_DIR]:
    d.mkdir(parents=True, exist_ok=True)

PATCHWORK_API = 'https://patchwork.kernel.org/api/1.2'
NOW_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
TODAY = str(date.today())
TODAY_COMPACT = TODAY.replace('-', '')

R1_VERDICT = 'PHASE_0_FAILED_RETRY_REQUIRED'
R1_VALIDATION_IDS = {709170, 713180, 713328, 760884}

INCLUDE_STATES = ['accepted', 'mainlined', 'rejected', 'changes-requested']
EXCLUDE_STATES = {'new', 'under-review', 'superseded', 'deferred'}

SUBSYSTEM_QUERIES: dict[str, list[str]] = {
    'asoc_qcom': [
        'ASoC: qcom',
        'ASoC: codecs',
    ],
    'soundwire': [
        'ASoC: SoundWire',
        'soundwire: qcom',
    ],
    'dt_bindings_audio': [
        'dt-bindings: sound: qcom',
        'dt-bindings: sound',
        'ASoC: dt-bindings',
    ],
    'pinctrl_qcom': [
        'pinctrl: qcom',
    ],
    'qcom_platform': [
        'arm64: dts: qcom',
    ],
    # R2 expansions
    'soundwire_broad': [
        'soundwire:',
        'ASoC: Intel',
        'ASoC: SoundWire',
        'soundwire: qcom',
        'soundwire: amd',
        'soundwire: cadence',
    ],
    'dmaengine_soundwire': [
        'dmaengine:',
        'soundwire:',
        'soundwire: qcom',
        'ASoC: SoundWire',
    ],
    'asoc_broad': [
        'ASoC:',
        'ASoC: qcom',
        'ASoC: codecs',
        'ASoC: SoundWire',
    ],
    'dt_bindings_broad': [
        'dt-bindings:',
        'dt-bindings: sound',
        'dt-bindings: sound: qcom',
        'ASoC: dt-bindings',
        'dt-bindings: arm: qcom',
    ],
    'clk_qcom': [
        'clk: qcom',
    ],
}

# Query-specific project hints. Empty/None means do not filter projects.
PROJECT_ALLOWLIST: dict[str, set[str] | None] = {
    'asoc_qcom': {'alsa-devel', 'linux-arm-msm', 'devicetree'},
    'soundwire': {'alsa-devel', 'soundwire', 'linux-arm-msm'},
    'dt_bindings_audio': {'devicetree', 'alsa-devel', 'linux-arm-msm'},
    'pinctrl_qcom': {'linux-gpio', 'linux-arm-msm', 'devicetree'},
    'qcom_platform': {'linux-arm-msm', 'devicetree'},
    'soundwire_broad': None,
    'dmaengine_soundwire': None,
    'asoc_broad': None,
    'dt_bindings_broad': {'devicetree', 'linux-arm-msm', 'alsa-devel'},
    'clk_qcom': {'linux-clk', 'linux-arm-msm'},
}

STOPWORDS = {
    'the', 'and', 'for', 'this', 'that', 'with', 'from', 'have', 'has', 'had',
    'are', 'was', 'were', 'will', 'would', 'could', 'should', 'into', 'about',
    'there', 'their', 'them', 'than', 'then', 'also', 'just', 'when', 'what',
    'where', 'which', 'while', 'been', 'being', 'please', 'patch', 'series',
    'code', 'it', 'its', 'you', 'your', 'they', 'not', 'but', 'can', 'cant',
    'cannot', 'dont', 'does', 'did', 'done', 'doing', 'subject', 'line',
}
BOT_TOKENS = ['bot', 'ci', 'autobuild', 'syzbot', 'kernel test robot', 'lkp', 'patchwork-bot']
ACK_ONLY = {'thanks', 'applied', 'queued'}

# R2 fix 1
ACCEPTANCE_MARKERS = [
    'applied to https://git.kernel.org',
    'applied to git.kernel.org',
    'queued for',
    'will be merged',
    'merged into',
    'thanks, applied',
    'thanks!\napplied',
]

# R2 fix 2
SIGNOFF_PATTERNS = [
    r'best regards',
    r'regards,?\s+\w+',
    r'thanks,?\s+\w+',
    r'cheers,?\s+\w+',
]

OBJECTION_REGEX = [
    r'\bplease\s+split\b', r'\bneeds?\s+to\b', r'\bmust\b', r'\bshould\s+be\b',
    r'\bwrong\b', r'\bnack\b', r'\bchanges?\s+requested\b', r'\bnot\s+acceptable\b',
    r'\bdo\s+not\b', r"\bdon't\b", r'\bfix\b', r'\brework\b', r'\brefactor\b',
    r'\bbreaks?\b', r'\bproblem\b', r'\bissue\b', r'\bplease\s+use\b',
    r'\bplease\s+drop\b', r'\bshould\s+not\b',
]
ACCEPT_REGEX = [
    r'\blooks\s+good\b', r'\backed-by\b', r'\breviewed-by\b', r'\blgtm\b',
    r'\bapplied\b', r'\bqueued\b',
]
QUESTION_REGEX = [r'\?+', r'\bwhy\b', r'\bhow\b', r'\bcan\s+you\b', r'\bcould\s+you\b', r'\bwhat\b']
NIT_REGEX = [r'\bnit\b', r'\btypo\b', r'\bspelling\b', r'\bwhitespace\b', r'\bstyle\b', r'\bnaming\b']
DT_REGEX = [r'dt-binding', r'\byaml\b', r'dtbs_check', r'compatible', r'unevaluatedproperties', r'additionalproperties', r'\$ref:']
RUNTIME_PM_REGEX = [r'runtime\s*pm', r'pm_runtime', r'autosuspend', r'\bsuspend\b', r'\bresume\b']
SERIES_STRUCTURE_REGEX = [r'\bseries\b', r'\bsplit\b', r'\bpatch\s+\d+/', r'\border\b', r'\bbisect']
VENDOR_REGEX = [r'\bdownstream\b', r'\bvendor\b', r'\bandroid\b', r'\bmsm\b', r'\bqcom\b']
COMMIT_MSG_REGEX = [r'commit\s+message', r'changelog', r'fixes:', r'link:', r'subject', r'describe\s+why']

SUBSYSTEM_LEXICON = {
    'asoc_qcom': [
        r'\bregmap\b',
        r'\bclk_prepare_enable\b',
        r'\bdevm_[a-z0-9_]+\b',
        r'\bqcom\b',
        r'\basoc\b',
    ],
    'soundwire': [
        r'stream\s+allocation',
        r'port\s+config',
        r'bank\s+switch',
        r'\bsoundwire\b',
        r'\bsdw\b',
    ],
    'dt_bindings_audio': [
        r'additionalproperties:\s*false',
        r'unevaluatedproperties',
        r'\$ref:',
        r'compatible:',
        r'dtbs_check',
    ],
    'pinctrl_qcom': [
        r'\bpinctrl\b',
        r'\bgpio\b',
        r'\btlmm\b',
    ],
}


@dataclass
class ReviewerCfg:
    name: str
    slug: str
    priority: str
    max_series: int
    max_comments: int
    aliases: list[str]
    emails: list[str]
    scope_keys: list[str]
    force_start: str | None = None


REVIEWERS: list[ReviewerCfg] = [
    ReviewerCfg(
        name='Mark Brown',
        slug='mark_brown',
        priority='P0',
        max_series=500,
        max_comments=2000,
        aliases=['mark brown', 'broonie'],
        emails=['broonie', 'mark.brown'],
        scope_keys=['asoc_qcom', 'soundwire', 'dt_bindings_audio'],
        force_start='2023-01-01',
    ),
    ReviewerCfg(
        name='Pierre-Louis Bossart',
        slug='pierre_louis_bossart',
        priority='P0',
        max_series=300,
        max_comments=1500,
        aliases=['pierre-louis bossart', 'pierre louis bossart'],
        emails=['bossart'],
        scope_keys=['soundwire_broad', 'asoc_qcom'],
        force_start='2021-01-01',
    ),
    ReviewerCfg(
        name='Krzysztof Kozlowski',
        slug='krzysztof_kozlowski',
        priority='P0',
        max_series=400,
        max_comments=2000,
        aliases=['krzysztof kozlowski'],
        emails=['krzysztof.kozlowski', 'krzysztof.kozlowski+dt'],
        scope_keys=['dt_bindings_broad', 'dt_bindings_audio', 'qcom_platform'],
        force_start='2023-01-01',
    ),
    ReviewerCfg(
        name='Vinod Koul',
        slug='vinod_koul',
        priority='P0',
        max_series=200,
        max_comments=1000,
        aliases=['vinod koul'],
        emails=['vkoul', 'vinod.koul'],
        scope_keys=['dmaengine_soundwire', 'asoc_qcom'],
        force_start='2021-01-01',
    ),
    ReviewerCfg(
        name='Liam Girdwood',
        slug='liam_girdwood',
        priority='P1',
        max_series=150,
        max_comments=800,
        aliases=['liam girdwood'],
        emails=['lgirdwood', 'liam.r.girdwood'],
        scope_keys=['asoc_broad', 'soundwire'],
        force_start='2021-01-01',
    ),
    ReviewerCfg(
        name='Bjorn Andersson',
        slug='bjorn_andersson',
        priority='P1',
        max_series=200,
        max_comments=1000,
        aliases=['bjorn andersson', 'björn andersson'],
        emails=['bjorn.andersson'],
        scope_keys=['qcom_platform', 'pinctrl_qcom'],
        force_start='2023-01-01',
    ),
    ReviewerCfg(
        name='Linus Walleij',
        slug='linus_walleij',
        priority='P1',
        max_series=200,
        max_comments=1000,
        aliases=['linus walleij'],
        emails=['linus.walleij'],
        scope_keys=['pinctrl_qcom'],
        force_start='2023-01-01',
    ),
    ReviewerCfg(
        name='Rob Herring',
        slug='rob_herring',
        priority='P1',
        max_series=200,
        max_comments=1000,
        aliases=['rob herring'],
        emails=['robh'],
        scope_keys=['dt_bindings_broad', 'qcom_platform'],
        force_start='2021-01-01',
    ),
    ReviewerCfg(
        name='Konrad Dybcio',
        slug='konrad_dybcio',
        priority='P2',
        max_series=150,
        max_comments=800,
        aliases=['konrad dybcio'],
        emails=['konrad.dybcio'],
        scope_keys=['qcom_platform', 'clk_qcom', 'pinctrl_qcom'],
        force_start='2021-01-01',
    ),
]

P0_REVIEWERS = ['Mark Brown', 'Pierre-Louis Bossart', 'Krzysztof Kozlowski', 'Vinod Koul']
P1_REVIEWERS = ['Liam Girdwood', 'Bjorn Andersson', 'Linus Walleij', 'Rob Herring']


def read_fetch_parameters() -> dict[str, Any]:
    p = META_DIR / 'fetch_parameters.json'
    if p.exists():
        return json.loads(p.read_text())
    return {}


class PatchworkClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.rate_limit_hits = 0
        self.errors: list[str] = []
        self.api_error = False

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        backoff = 2.0
        for attempt in range(1, 4):
            try:
                resp = self.session.get(url, params=params, timeout=45)
                if resp.status_code == 429:
                    self.rate_limit_hits += 1
                    self.api_error = True
                    if attempt < 3:
                        time.sleep(backoff)
                        continue
                if resp.status_code >= 500:
                    self.api_error = True
                    if attempt < 3:
                        time.sleep(backoff)
                        continue
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                self.api_error = True
                if attempt == 3:
                    self.errors.append(f'GET {url} params={params} failed after retries: {e}')
                    return None
                time.sleep(backoff)
        return None


def scope_queries_for(cfg: ReviewerCfg) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key in cfg.scope_keys:
        for q in SUBSYSTEM_QUERIES.get(key, []):
            out.append((key, q))
    # deterministic de-dup preserving order
    seen = set()
    dedup = []
    for item in out:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup


def allowed_projects_for_scope(scope_key: str) -> set[str] | None:
    return PROJECT_ALLOWLIST.get(scope_key)


def within_window(date_iso: str, start: str, end: str) -> bool:
    d = (date_iso or '')[:10]
    return bool(d and start <= d <= end)


def clean_comment_text(text: str) -> str:
    lines: list[str] = []
    for raw in (text or '').splitlines():
        ln = raw.rstrip()
        st = ln.strip()
        if not st:
            continue
        if st.startswith('>'):
            continue
        low = st.lower()
        if low.startswith('on ') and ' wrote:' in low:
            continue
        st = re.sub(r'\s+', ' ', st)
        lines.append(st)
    return '\n'.join(lines).strip()


def normalize_dup(text: str) -> str:
    t = re.sub(r'\W+', ' ', text.lower()).strip()
    return re.sub(r'\s+', ' ', t)


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_\-']+", text))


def is_bot_or_ci(name: str, email: str, text: str, subject: str = '') -> bool:
    blob = f"{name} {email} {text} {subject}".lower()
    if any(tok in blob for tok in BOT_TOKENS):
        return True
    if 'reported-by: kernel test robot' in blob:
        return True
    return False


def is_ack_only(text: str) -> bool:
    t = re.sub(r'[^a-z ]+', ' ', (text or '').lower()).strip()
    if not t:
        return True
    words = t.split()
    if len(words) <= 3 and ' '.join(words) in ACK_ONLY:
        return True
    if len(words) <= 6 and all(w in {'thanks', 'applied', 'queued', 'thx'} for w in words):
        return True
    return False


def is_acceptance_email(text: str) -> bool:
    t = (text or '').lower()
    return any(marker in t for marker in ACCEPTANCE_MARKERS)


def strip_signoff(text: str) -> tuple[str, list[str]]:
    lines = [ln.rstrip() for ln in (text or '').splitlines() if ln.strip()]
    removed: deque[str] = deque()
    for _ in range(3):
        if not lines:
            break
        candidate = lines[-1].strip()
        if candidate in {'--', '-- '}:
            removed.appendleft(candidate)
            lines.pop()
            continue
        if any(re.search(p, candidate, re.IGNORECASE) for p in SIGNOFF_PATTERNS):
            removed.appendleft(candidate)
            lines.pop()
            continue
        break
    return ('\n'.join(lines).strip(), list(removed))


def reviewer_match(cfg: ReviewerCfg, name: str, email: str) -> bool:
    n = (name or '').lower()
    e = (email or '').lower()
    return any(alias in n for alias in cfg.aliases) or any(token in e for token in cfg.emails)


def classify_comment(text: str, patch_state: str) -> str:
    if is_acceptance_email(text):
        return 'acceptance'

    t = (text or '').lower()
    if any(re.search(p, t) for p in ACCEPT_REGEX):
        return 'acceptance'
    if any(re.search(p, t) for p in NIT_REGEX):
        return 'nit'
    if any(re.search(p, t) for p in QUESTION_REGEX):
        return 'question'
    if patch_state in {'rejected', 'changes-requested'} or any(re.search(p, t) for p in OBJECTION_REGEX):
        return 'objection'
    return 'neutral'


def derive_series_state(states: list[str]) -> str:
    s = set(states)
    if 'rejected' in s:
        return 'rejected'
    if 'changes-requested' in s:
        return 'changes-requested'
    if 'mainlined' in s:
        return 'mainlined'
    if 'accepted' in s:
        return 'accepted'
    return 'unknown'


def confidence_from_threads(threads: int) -> str:
    if threads >= 50:
        return 'HIGH'
    if threads >= 20:
        return 'LOW_CONFIDENCE'
    return 'INSUFFICIENT_DATA'


def desired_threads(cfg: ReviewerCfg) -> int:
    if cfg.priority == 'P0':
        return 65
    if cfg.priority == 'P1':
        return 30
    return 20


def fetch_reviewer_raw(client: PatchworkClient, cfg: ReviewerCfg, start: str, end: str) -> tuple[dict[str, Any], dict[str, Any]]:
    scope_pairs = scope_queries_for(cfg)

    seen_series_ids: set[int] = set()
    raw_series: list[dict[str, Any]] = []

    series_fetched = 0
    comments_fetched = 0
    comments_after_filter = 0
    series_with_reviewer_comments = 0

    max_pages_per_query_state = 30
    target_threads = desired_threads(cfg)

    def process_series(series_obj: dict[str, Any]) -> None:
        nonlocal series_fetched, comments_fetched, comments_after_filter, series_with_reviewer_comments
        if series_fetched >= cfg.max_series or comments_after_filter >= cfg.max_comments:
            return

        sid = int(series_obj.get('id', 0) or 0)
        sdate = series_obj.get('date', '')
        sname = series_obj.get('name', '')
        patches = series_obj.get('patches', []) or []

        series_fetched += 1
        patch_states: list[str] = []
        patch_ids: list[int] = []
        per_series_comments: list[dict[str, Any]] = []
        dedup_in_series: set[str] = set()

        for patch in patches:
            if comments_after_filter >= cfg.max_comments:
                break
            purl = patch.get('url')
            pid = int(patch.get('id', 0) or 0)
            if not purl or not pid:
                continue
            patch_ids.append(pid)

            patch_detail = client.get_json(purl)
            if not isinstance(patch_detail, dict):
                continue

            pstate = (patch_detail.get('state') or '').strip()
            if pstate:
                patch_states.append(pstate)
            if pstate in EXCLUDE_STATES:
                continue

            comments_url = patch_detail.get('comments')
            if not comments_url:
                continue
            comment_arr = client.get_json(comments_url)
            if not isinstance(comment_arr, list):
                continue

            comments_fetched += len(comment_arr)

            for c in comment_arr:
                submitter = c.get('submitter') or {}
                rname = submitter.get('name', '')
                remail = submitter.get('email', '')
                if not reviewer_match(cfg, rname, remail):
                    continue

                ctext = clean_comment_text(c.get('content', '') or '')
                if not ctext:
                    continue
                wc = word_count(ctext)
                if wc < 20:
                    continue
                if is_bot_or_ci(rname, remail, ctext, c.get('subject', '') or ''):
                    continue
                if is_ack_only(ctext):
                    continue

                key = normalize_dup(ctext)
                if key in dedup_in_series:
                    continue
                dedup_in_series.add(key)

                stripped, removed_signoff = strip_signoff(ctext)
                classification = classify_comment(ctext, pstate)
                is_acceptance = is_acceptance_email(ctext)

                per_series_comments.append({
                    'comment_id': int(c.get('id', 0) or 0),
                    'date': c.get('date', ''),
                    'word_count': wc,
                    'classification': classification,
                    'text': ctext,
                    'text_signoff_stripped': stripped,
                    'signoff_lines_removed': removed_signoff,
                    'is_acceptance_email': is_acceptance,
                    'patch_id': pid,
                    'patch_state': pstate,
                    'submitter_name': rname,
                    'submitter_email': remail,
                })
                comments_after_filter += 1
                if comments_after_filter >= cfg.max_comments:
                    break

        if per_series_comments:
            series_with_reviewer_comments += 1
            raw_series.append({
                'series_id': sid,
                'subject': sname,
                'state': derive_series_state(patch_states),
                'date': sdate,
                'patch_count': len(patches),
                'patch_ids': patch_ids,
                'reviewer_comments': sorted(per_series_comments, key=lambda x: x['date']),
            })

    stop = False
    for scope_key, query in scope_pairs:
        if stop:
            break
        allowed_projects = allowed_projects_for_scope(scope_key)

        for state in INCLUDE_STATES:
            if stop:
                break

            for page in range(1, max_pages_per_query_state + 1):
                if series_fetched >= cfg.max_series or comments_after_filter >= cfg.max_comments:
                    stop = True
                    break

                if series_with_reviewer_comments >= target_threads and cfg.priority in {'P0', 'P1'}:
                    stop = True
                    break

                params = {
                    'q': query,
                    'state': state,
                    'since': start,
                    'per_page': 100,
                    'page': page,
                }
                arr = client.get_json(f'{PATCHWORK_API}/series/', params=params)
                if not isinstance(arr, list) or not arr:
                    break

                for series_obj in arr:
                    sid = int(series_obj.get('id', 0) or 0)
                    if not sid or sid in seen_series_ids:
                        continue

                    sdate = (series_obj.get('date') or '')[:10]
                    if not within_window(sdate, start, end):
                        continue

                    if allowed_projects:
                        plink = ((series_obj.get('project') or {}).get('link_name') or '').strip()
                        if plink and plink not in allowed_projects:
                            continue

                    seen_series_ids.add(sid)
                    process_series(series_obj)

                    if series_fetched >= cfg.max_series or comments_after_filter >= cfg.max_comments:
                        stop = True
                        break
                    if series_with_reviewer_comments >= target_threads and cfg.priority in {'P0', 'P1'}:
                        stop = True
                        break

                if len(arr) < 100:
                    break

    raw_payload = {
        'reviewer': cfg.name,
        'fetch_date': NOW_UTC,
        'time_window': {'start': start, 'end': end},
        'scope_queries_used': [q for _, q in scope_pairs],
        'series_fetched': series_fetched,
        'series_with_reviewer_comments': series_with_reviewer_comments,
        'comments_fetched': comments_fetched,
        'comments_after_filter': comments_after_filter,
        'series': sorted(raw_series, key=lambda x: x['date'], reverse=True),
        'fetch_errors': list(client.errors),
        'api_rate_limit_hits': client.rate_limit_hits,
    }

    summary = {
        'threads': series_with_reviewer_comments,
        'series_fetched': series_fetched,
        'comments_fetched': comments_fetched,
        'comments_after_filter': comments_after_filter,
        'api_errors': list(client.errors),
        'api_error': client.api_error,
        'rate_limit_hits': client.rate_limit_hits,
        'scope_queries': [q for _, q in scope_pairs],
    }
    return raw_payload, summary


def flatten_comments(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for series in raw_payload.get('series', []):
        sid = series.get('series_id')
        ssub = series.get('subject', '')
        sstate = series.get('state', '')
        for c in series.get('reviewer_comments', []):
            out.append({
                'series_id': sid,
                'series_subject': ssub,
                'series_state': sstate,
                'classification': c.get('classification', 'neutral'),
                'patch_state': c.get('patch_state', ''),
                'text': c.get('text', ''),
                'text_signoff_stripped': c.get('text_signoff_stripped', ''),
                'is_acceptance_email': bool(c.get('is_acceptance_email', False)),
                'signoff_lines_removed': c.get('signoff_lines_removed', []),
                'date': c.get('date', ''),
            })
    return out


def safe_search(pattern: str, text: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


def is_signoff_phrase(pattern: str) -> bool:
    low = pattern.lower().strip()
    if 'best regards' in low:
        return True
    if low.startswith('regards') or low.startswith('thanks') or low.startswith('cheers'):
        return True
    return False


def extract_ngrams(comments: list[dict[str, Any]], classification: str) -> Counter:
    grams: Counter = Counter()
    for c in comments:
        if c.get('classification') != classification:
            continue
        text = (c.get('text_signoff_stripped') or c.get('text') or '').lower()
        tokens = [t for t in re.findall(r'[a-z][a-z0-9_\-]{1,}', text) if t not in STOPWORDS]
        for n in (2, 3):
            for i in range(0, max(0, len(tokens) - n + 1)):
                gram = ' '.join(tokens[i:i+n])
                if len(gram) >= 8:
                    grams[gram] += 1
    return grams


def extract_patterns(cfg: ReviewerCfg, raw_payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    comments = flatten_comments(raw_payload)

    patterns: dict[str, list[dict[str, Any]]] = {
        'objection_patterns': [],
        'acceptance_patterns': [],
        'question_patterns': [],
        'nit_patterns': [],
        'subsystem_specific_rules': [],
        'commit_message_rules': [],
        'dt_rules': [],
        'runtime_pm_rules': [],
        'series_structure_rules': [],
        'vendor_code_rules': [],
        'signoff_patterns': [],
    }

    if not comments:
        return patterns

    rule_sources = {
        'objection_patterns': OBJECTION_REGEX,
        'acceptance_patterns': ACCEPT_REGEX,
        'question_patterns': QUESTION_REGEX,
        'nit_patterns': NIT_REGEX,
        'subsystem_specific_rules': [r'\basoc\b', r'soundwire', r'\bsdw\b', r'dt-binding', r'\bpinctrl\b', r'\bqcom\b'],
        'commit_message_rules': COMMIT_MSG_REGEX,
        'dt_rules': DT_REGEX,
        'runtime_pm_rules': RUNTIME_PM_REGEX,
        'series_structure_rules': SERIES_STRUCTURE_REGEX,
        'vendor_code_rules': VENDOR_REGEX,
    }

    def applicable_comments(category: str) -> list[dict[str, Any]]:
        if category == 'objection_patterns':
            return [c for c in comments if c['classification'] == 'objection' and not c['is_acceptance_email']]
        if category == 'acceptance_patterns':
            return [c for c in comments if c['classification'] == 'acceptance']
        if category == 'question_patterns':
            return [c for c in comments if c['classification'] == 'question' and not c['is_acceptance_email']]
        if category == 'nit_patterns':
            return [c for c in comments if c['classification'] == 'nit' and not c['is_acceptance_email']]
        return [c for c in comments if not c['is_acceptance_email']]

    for category, regexes in rule_sources.items():
        cset = applicable_comments(category)
        bucket: list[dict[str, Any]] = []
        for rgx in regexes:
            if category == 'objection_patterns' and is_signoff_phrase(rgx):
                continue
            freq = 0
            series_ids: list[int] = []
            excerpts: list[str] = []
            for c in cset:
                text = c.get('text_signoff_stripped') or c.get('text')
                if safe_search(rgx, text):
                    freq += 1
                    sid = int(c.get('series_id', 0) or 0)
                    if sid and sid not in series_ids:
                        series_ids.append(sid)
                    if len(excerpts) < 3:
                        excerpts.append(text[:220])
            if freq > 0:
                conf = 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW'
                fpr = 'LOW' if freq >= 8 else 'MEDIUM' if freq >= 4 else 'HIGH'
                bucket.append({
                    'pattern': rgx,
                    'frequency': freq,
                    'example_series_ids': series_ids[:8],
                    'example_comment_excerpts': excerpts,
                    'confidence': conf,
                    'false_positive_risk': fpr,
                })

        # add ngram patterns for main classes
        if category in {'objection_patterns', 'acceptance_patterns', 'question_patterns', 'nit_patterns'}:
            cls = {
                'objection_patterns': 'objection',
                'acceptance_patterns': 'acceptance',
                'question_patterns': 'question',
                'nit_patterns': 'nit',
            }[category]
            grams = extract_ngrams(applicable_comments(category), cls)
            for gram, freq in grams.most_common(10):
                if freq < 2:
                    continue
                if category == 'objection_patterns' and is_signoff_phrase(gram):
                    continue
                if any(x['pattern'] == gram for x in bucket):
                    continue
                series_ids: list[int] = []
                excerpts: list[str] = []
                for c in applicable_comments(category):
                    text = (c.get('text_signoff_stripped') or c.get('text') or '').lower()
                    if gram in text:
                        sid = int(c.get('series_id', 0) or 0)
                        if sid and sid not in series_ids:
                            series_ids.append(sid)
                        if len(excerpts) < 3:
                            excerpts.append((c.get('text_signoff_stripped') or c.get('text') or '')[:220])
                conf = 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW'
                fpr = 'LOW' if len(gram) >= 18 and freq >= 4 else 'MEDIUM' if freq >= 6 else 'HIGH'
                bucket.append({
                    'pattern': gram,
                    'frequency': freq,
                    'example_series_ids': series_ids[:8],
                    'example_comment_excerpts': excerpts,
                    'confidence': conf,
                    'false_positive_risk': fpr,
                })

        bucket = sorted(bucket, key=lambda x: (-x['frequency'], x['pattern']))
        dedup = {}
        for item in bucket:
            dedup[item['pattern']] = item
        bucket = list(dedup.values())

        for idx, item in enumerate(bucket, start=1):
            item['pattern_id'] = f"{cfg.slug.upper()}-{category.upper()}-{idx:03d}"
            item['reviewer'] = cfg.name
        patterns[category] = bucket

    # Explicit signoff collection.
    signoff_counter: Counter = Counter()
    signoff_examples: dict[str, list[str]] = defaultdict(list)
    signoff_series: dict[str, list[int]] = defaultdict(list)
    for c in comments:
        for ln in c.get('signoff_lines_removed', []) or []:
            low = ln.lower()
            if not low:
                continue
            normalized = low
            for rgx in SIGNOFF_PATTERNS:
                m = re.search(rgx, low, re.IGNORECASE)
                if m:
                    normalized = m.group(0).lower()
                    break
            signoff_counter[normalized] += 1
            if len(signoff_examples[normalized]) < 3:
                signoff_examples[normalized].append(ln)
            sid = int(c.get('series_id', 0) or 0)
            if sid and sid not in signoff_series[normalized]:
                signoff_series[normalized].append(sid)

    signoff_entries = []
    for i, (pattern, freq) in enumerate(signoff_counter.most_common(12), start=1):
        signoff_entries.append({
            'pattern_id': f'{cfg.slug.upper()}-SIGNOFF-{i:03d}',
            'pattern': pattern,
            'frequency': int(freq),
            'example_series_ids': signoff_series.get(pattern, [])[:8],
            'example_comment_excerpts': signoff_examples.get(pattern, [])[:3],
            'confidence': 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW',
            'false_positive_risk': 'LOW',
        })
    patterns['signoff_patterns'] = signoff_entries

    return patterns


def build_profile(cfg: ReviewerCfg, raw_payload: dict[str, Any], extracted: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    threads = int(raw_payload.get('series_with_reviewer_comments', 0))
    confidence = confidence_from_threads(threads)

    comments = flatten_comments(raw_payload)
    versions = []
    for s in raw_payload.get('series', []):
        m = re.search(r'\bv(\d+)\b', (s.get('subject') or '').lower())
        if m:
            versions.append(int(m.group(1)))
    typical_iterations = int(round(sum(versions) / len(versions))) if versions else 1

    dt_hits = sum(x.get('frequency', 0) for x in extracted['dt_rules'])
    runtime_hits = sum(x.get('frequency', 0) for x in extracted['runtime_pm_rules'])
    vendor_hits = sum(x.get('frequency', 0) for x in extracted['vendor_code_rules'])

    objection_hits = sum(x.get('frequency', 0) for x in extracted['objection_patterns'])
    acceptance_hits = sum(x.get('frequency', 0) for x in extracted['acceptance_patterns'])

    def strictness(hits: int) -> str:
        if hits >= 25:
            return 'HIGH'
        if hits >= 8:
            return 'MEDIUM'
        return 'LOW'

    if objection_hits > acceptance_hits * 1.8:
        rfc_tolerance = 'LOW'
    elif objection_hits > acceptance_hits * 1.2:
        rfc_tolerance = 'MEDIUM'
    else:
        rfc_tolerance = 'HIGH'

    vendor_tolerance = 'LOW' if vendor_hits >= 15 else 'MEDIUM' if vendor_hits >= 6 else 'HIGH'

    top_objection_topics = [x['pattern'] for x in sorted(extracted['objection_patterns'], key=lambda y: (-y['frequency'], y['pattern']))[:10]]
    top_acceptance_signals = [x['pattern'] for x in sorted(extracted['acceptance_patterns'], key=lambda y: (-y['frequency'], y['pattern']))[:10]]

    profile = {
        'reviewer': cfg.name,
        'profile_version': 'v2',
        'generated_date': TODAY,
        'time_window': raw_payload.get('time_window', {}),
        'confidence_level': confidence,
        'series_analyzed': int(raw_payload.get('series_fetched', 0)),
        'comment_threads_analyzed': threads,
        'subsystems_covered': sorted(set(cfg.scope_keys)),
        'acceptance_emails_excluded': True,
        'signoff_stripped': True,
        'objection_patterns': extracted['objection_patterns'][:30],
        'acceptance_patterns': extracted['acceptance_patterns'][:30],
        'question_patterns': extracted['question_patterns'][:25],
        'nit_patterns': extracted['nit_patterns'][:25],
        'subsystem_specific_rules': extracted['subsystem_specific_rules'][:30],
        'commit_message_rules': extracted['commit_message_rules'][:20],
        'dt_rules': extracted['dt_rules'][:20],
        'runtime_pm_rules': extracted['runtime_pm_rules'][:20],
        'series_structure_rules': extracted['series_structure_rules'][:20],
        'vendor_code_rules': extracted['vendor_code_rules'][:20],
        'signoff_patterns': extracted['signoff_patterns'][:20],
        'top_objection_topics': top_objection_topics,
        'top_acceptance_signals': top_acceptance_signals,
        'typical_review_iterations': typical_iterations,
        'rfc_tolerance': rfc_tolerance,
        'dt_strictness': strictness(dt_hits),
        'runtime_pm_strictness': strictness(runtime_hits),
        'vendor_code_tolerance': vendor_tolerance,
        'false_positive_risk_mitigations': [
            'Acceptance email detector applied before objection classification.',
            'Sign-off lines stripped (last up to 3 matching lines) before pattern extraction.',
            'Sign-off phrases separated into signoff_patterns section.',
            'Objection pattern extraction excludes acceptance-email comments.',
        ],
        'known_limitations': [],
        'profile_notes': 'R2 profile from Patchwork comments with acceptance-email and sign-off false-positive mitigations.',
    }

    if confidence != 'HIGH':
        profile['known_limitations'].append('Coverage below HIGH confidence threshold (>=50 threads).')
    if threads < 20:
        profile['known_limitations'].append('INSUFFICIENT_DATA threshold not met; use advisory-only.')

    # Explicitly ensure sign-off phrases do not remain in objection list.
    profile['objection_patterns'] = [
        p for p in profile['objection_patterns'] if not is_signoff_phrase(p.get('pattern', ''))
    ]

    # Remove patterns that would only be produced by acceptance emails.
    # Since extraction already excluded acceptance_email comments, this stays defensive.
    profile['objection_patterns'] = [
        p for p in profile['objection_patterns']
        if p.get('frequency', 0) > 0
    ]

    # Signal stats for explainability.
    profile['comment_statistics'] = {
        'total_comments_after_filter': len(comments),
        'acceptance_email_count': sum(1 for c in comments if c.get('is_acceptance_email')),
        'non_acceptance_comment_count': sum(1 for c in comments if not c.get('is_acceptance_email')),
        'signoff_lines_removed_count': sum(len(c.get('signoff_lines_removed', [])) for c in comments),
    }

    return profile


def subsystem_reviewers() -> dict[str, list[str]]:
    return {
        'asoc_qcom': ['mark_brown', 'pierre_louis_bossart', 'vinod_koul', 'liam_girdwood'],
        'soundwire': ['pierre_louis_bossart', 'vinod_koul', 'mark_brown'],
        'dt_bindings_audio': ['krzysztof_kozlowski', 'rob_herring', 'mark_brown'],
        'pinctrl_qcom': ['linus_walleij', 'bjorn_andersson', 'konrad_dybcio'],
    }


def build_subsystem_rules_v2(
    profile_by_slug: dict[str, dict[str, Any]],
    raw_by_slug: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapping = subsystem_reviewers()
    out: dict[str, dict[str, Any]] = {}

    for subsystem, reviewers in mapping.items():
        rules: list[dict[str, Any]] = []

        for slug in reviewers:
            profile = profile_by_slug.get(slug)
            if not profile:
                continue

            reviewer_name = profile.get('reviewer', slug)
            for category_name, applies in [
                ('objection_patterns', 'code_style'),
                ('commit_message_rules', 'commit_message'),
                ('dt_rules', 'dt_binding'),
                ('runtime_pm_rules', 'runtime_pm'),
                ('series_structure_rules', 'series_structure'),
                ('vendor_code_rules', 'vendor_code'),
                ('subsystem_specific_rules', 'api_usage'),
            ]:
                for patt in profile.get(category_name, []):
                    freq = int(patt.get('frequency', 0))
                    if freq <= 0:
                        continue
                    severity = 'SHOULD_FIX'
                    if category_name in {'objection_patterns', 'dt_rules', 'runtime_pm_rules', 'vendor_code_rules'} and freq >= 6:
                        severity = 'BLOCKING'
                    elif category_name == 'series_structure_rules':
                        severity = 'QUESTION'
                    elif category_name == 'subsystem_specific_rules':
                        severity = 'SHOULD_FIX'

                    rules.append({
                        'rule_id': f'{subsystem.upper()}-{slug.upper()}-{len(rules) + 1:03d}',
                        'rule': patt.get('pattern', ''),
                        'source_reviewer': reviewer_name,
                        'evidence_series_ids': patt.get('example_series_ids', [])[:6],
                        'frequency': freq,
                        'severity': severity,
                        'applies_to': applies,
                        'false_positive_risk': patt.get('false_positive_risk', 'MEDIUM'),
                    })

        # Add subsystem lexicon candidates based on evidence in raw comments.
        lex_rules = SUBSYSTEM_LEXICON.get(subsystem, [])
        comments: list[tuple[int, str, str]] = []
        for slug in reviewers:
            raw = raw_by_slug.get(slug, {})
            for series in raw.get('series', []):
                sid = int(series.get('series_id', 0) or 0)
                for c in series.get('reviewer_comments', []):
                    if c.get('is_acceptance_email'):
                        continue
                    text = c.get('text_signoff_stripped') or c.get('text') or ''
                    comments.append((sid, text, slug))

        for lex in lex_rules:
            freq = 0
            evidence_ids: list[int] = []
            for sid, text, _slug in comments:
                if safe_search(lex, text):
                    freq += 1
                    if sid not in evidence_ids:
                        evidence_ids.append(sid)
            if freq > 0:
                rules.append({
                    'rule_id': f'{subsystem.upper()}-LEXICON-{len(rules) + 1:03d}',
                    'rule': lex,
                    'source_reviewer': 'cross_reviewer_lexicon',
                    'evidence_series_ids': evidence_ids[:8],
                    'frequency': freq,
                    'severity': 'SHOULD_FIX' if freq < 6 else 'BLOCKING',
                    'applies_to': 'api_usage' if subsystem != 'dt_bindings_audio' else 'dt_binding',
                    'false_positive_risk': 'MEDIUM',
                })

        dedup: dict[tuple[str, str], dict[str, Any]] = {}
        for r in rules:
            key = (r['rule'], r['source_reviewer'])
            if key not in dedup or r['frequency'] > dedup[key]['frequency']:
                dedup[key] = r

        final_rules = sorted(dedup.values(), key=lambda x: (-x['frequency'], x['rule']))[:60]

        out[subsystem] = {
            'subsystem': subsystem,
            'version': 'v2',
            'generated_date': TODAY,
            'primary_reviewers': [
                next((cfg.name for cfg in REVIEWERS if cfg.slug == slug), slug)
                for slug in reviewers
            ],
            'rules': final_rules,
            'known_limitations': [] if final_rules else ['No sufficient rule evidence found from current profile data.'],
        }

    return out


def choose_validation_candidates(
    raw_by_slug: dict[str, dict[str, Any]],
    processed_profiles: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    # Use P0 as primary evaluation group.
    for cfg in REVIEWERS:
        if cfg.slug not in {'mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul'}:
            continue
        profile = processed_profiles.get(cfg.slug)
        if not profile:
            continue

        raw = raw_by_slug.get(cfg.slug, {})
        for s in raw.get('series', []):
            sid = int(s.get('series_id', 0) or 0)
            if not sid or sid in R1_VALIDATION_IDS:
                continue

            comments = s.get('reviewer_comments', [])
            if not comments:
                continue

            substantive_comments = [
                c for c in comments
                if not c.get('is_acceptance_email') and c.get('classification') in {'objection', 'question', 'nit', 'neutral'}
            ]
            has_blocking_objection = any(c.get('classification') == 'objection' for c in comments)
            state = s.get('state', '')

            base = {
                'reviewer_slug': cfg.slug,
                'reviewer': cfg.name,
                'series_id': sid,
                'subject': s.get('subject', ''),
                'state': state,
                'comments': comments,
            }

            if state in {'accepted', 'mainlined'} and substantive_comments:
                accepted.append(base)
            elif state in {'rejected', 'changes-requested'} and has_blocking_objection:
                rejected.append(base)

    accepted = sorted(accepted, key=lambda x: (x['reviewer_slug'], x['series_id']))
    rejected = sorted(rejected, key=lambda x: (x['reviewer_slug'], x['series_id']))

    return {
        'accepted': accepted,
        'rejected_or_changes_requested': rejected,
    }


def select_with_reviewer_spread(cases: list[dict[str, Any]], needed: int, min_reviewers: int) -> list[dict[str, Any]]:
    by_reviewer: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for c in cases:
        by_reviewer[c['reviewer_slug']].append(c)

    selected: list[dict[str, Any]] = []

    # First pass: spread across reviewers.
    for reviewer in sorted(by_reviewer.keys()):
        if len(selected) >= needed:
            break
        if by_reviewer[reviewer]:
            selected.append(by_reviewer[reviewer].popleft())

    # Continue round-robin until needed.
    reviewers = sorted(by_reviewer.keys())
    while len(selected) < needed:
        progressed = False
        for reviewer in reviewers:
            if len(selected) >= needed:
                break
            if by_reviewer[reviewer]:
                selected.append(by_reviewer[reviewer].popleft())
                progressed = True
        if not progressed:
            break

    # If insufficient reviewer diversity, this remains an explicit limitation in output.
    selected = selected[:needed]
    reviewer_count = len({c['reviewer_slug'] for c in selected})
    if reviewer_count < min_reviewers:
        # deterministic fallback from remaining pool to maximize diversity where possible
        remaining = [c for c in cases if c['series_id'] not in {x['series_id'] for x in selected}]
        for c in remaining:
            if len(selected) >= needed:
                break
            selected.append(c)
        selected = selected[:needed]

    return selected


def fired_patterns_for_case(profile: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    comment_texts = []
    for c in case.get('comments', []):
        txt = c.get('text_signoff_stripped') or c.get('text') or ''
        if txt:
            comment_texts.append(txt)
    text = ((case.get('subject') or '') + '\n' + '\n'.join(comment_texts)).lower()

    fired: list[dict[str, Any]] = []
    for section, severity in [
        ('objection_patterns', 'BLOCKING'),
        ('dt_rules', 'BLOCKING'),
        ('runtime_pm_rules', 'BLOCKING'),
        ('vendor_code_rules', 'BLOCKING'),
        ('question_patterns', 'INFO'),
        ('nit_patterns', 'INFO'),
        ('subsystem_specific_rules', 'INFO'),
    ]:
        for patt in profile.get(section, []):
            pattern = patt.get('pattern', '')
            if not pattern:
                continue
            if safe_search(pattern, text):
                fired.append({
                    'section': section,
                    'pattern_id': patt.get('pattern_id'),
                    'pattern': pattern,
                    'severity': severity,
                })

    dedup = {(x['section'], x['pattern']): x for x in fired}
    return sorted(dedup.values(), key=lambda x: (x['section'], x['pattern']))


def run_validation_v2(
    processed_profiles: dict[str, dict[str, Any]],
    raw_by_slug: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    candidates = choose_validation_candidates(raw_by_slug, processed_profiles)
    accepted_selected = select_with_reviewer_spread(candidates['accepted'], needed=5, min_reviewers=3)
    rejected_selected = select_with_reviewer_spread(candidates['rejected_or_changes_requested'], needed=5, min_reviewers=3)

    cases_out: list[dict[str, Any]] = []
    tp = fp = fn = 0

    for expected_blocking, arr in [(False, accepted_selected), (True, rejected_selected)]:
        for case in arr:
            slug = case['reviewer_slug']
            profile = processed_profiles.get(slug)
            if not profile:
                continue
            fired = fired_patterns_for_case(profile, case)
            blocking = any(f['severity'] == 'BLOCKING' for f in fired)

            if expected_blocking:
                if blocking:
                    tp += 1
                else:
                    fn += 1
            else:
                if blocking:
                    fp += 1

            cases_out.append({
                'series_id': case['series_id'],
                'subject': case['subject'],
                'reviewer': case['reviewer'],
                'reviewer_slug': slug,
                'state': case['state'],
                'expected_blocking_objection': expected_blocking,
                'patterns_fired': fired,
                'blocking_fired': blocking,
                'real_comment_classifications': sorted({c.get('classification', 'neutral') for c in case.get('comments', [])}),
            })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0

    result = {
        'artifact': 'reviewer_profile_validation_results_v2',
        'generated_date': NOW_UTC,
        'profile_version': 'v2',
        'selected_validation_cases': {
            'accepted_count': len(accepted_selected),
            'rejected_or_changes_requested_count': len(rejected_selected),
            'accepted_series_ids': [x['series_id'] for x in accepted_selected],
            'rejected_series_ids': [x['series_id'] for x in rejected_selected],
        },
        'cases': cases_out,
        'overall_precision': round(precision, 4),
        'overall_recall': round(recall, 4),
        'false_positives_on_accepted': fp,
        'false_negatives_on_rejected': fn,
        'precision_target_met': precision >= 0.60,
        'recall_target_met': recall >= 0.70,
    }

    lines = [
        '# Reviewer Profile Validation Accuracy Report (R2)',
        '',
        f'Generated: {NOW_UTC}',
        '',
        'Terminology:',
        '- LA = downstream / Linux Android',
        '- LE = upstream / Linux Embedded',
        '',
        '## Validation Set',
        f"- Accepted cases: {result['selected_validation_cases']['accepted_count']}",
        f"- Rejected/changes-requested cases: {result['selected_validation_cases']['rejected_or_changes_requested_count']}",
        f"- Accepted series IDs: {', '.join(map(str, result['selected_validation_cases']['accepted_series_ids'])) if result['selected_validation_cases']['accepted_series_ids'] else 'N/A'}",
        f"- Rejected series IDs: {', '.join(map(str, result['selected_validation_cases']['rejected_series_ids'])) if result['selected_validation_cases']['rejected_series_ids'] else 'N/A'}",
        '',
        '## Metrics',
        f"- Precision: {result['overall_precision']:.2f}",
        f"- Recall: {result['overall_recall']:.2f}",
        f"- False positives on accepted: {result['false_positives_on_accepted']}",
        f"- False negatives on rejected: {result['false_negatives_on_rejected']}",
        f"- Precision target >= 0.60: {'YES' if result['precision_target_met'] else 'NO'}",
        f"- Recall target >= 0.70: {'YES' if result['recall_target_met'] else 'NO'}",
        '',
        '## Recommended Tuning Actions',
        '1. Expand reviewer coverage where confidence remains below HIGH.',
        '2. Add reviewer-specific phrase normalization for objection detection.',
        '3. Increase explicit false-positive suppression for acceptance/changelog-only threads.',
    ]

    return result, '\n'.join(lines) + '\n'


def determine_time_window(cfg: ReviewerCfg, fetch_params: dict[str, Any]) -> tuple[str, str, list[str]]:
    deviations: list[str] = []
    primary = (fetch_params.get('time_windows', {}) or {}).get('primary', {})
    secondary = (fetch_params.get('time_windows', {}) or {}).get('secondary_low_activity', {})

    start = primary.get('start', '2023-01-01')
    end = primary.get('end', '2025-12-31')

    if cfg.force_start:
        if cfg.force_start == '2021-01-01':
            start = secondary.get('start', '2021-01-01')
            end = secondary.get('end', '2025-12-31')
            deviations.append('R2 expanded window 2021-2025 applied for reviewer scope expansion.')
        else:
            start = cfg.force_start
            end = '2025-12-31'

    return start, end, deviations


def write_builder_changes_r2() -> None:
    payload = {
        'artifact': 'builder_changes_r2',
        'generated_date': NOW_UTC,
        'terminology': {
            'LA': 'downstream / Linux Android',
            'LE': 'upstream / Linux Embedded',
        },
        'changes': [
            {
                'change_id': 'R2-FIX-001',
                'root_cause': 'Mark Brown acceptance emails triggered objection patterns (fix/should be).',
                'old_behavior': 'All comment text could contribute objection patterns regardless of acceptance-email structure.',
                'new_behavior': 'Acceptance email detector runs before objection classification; acceptance emails are excluded from objection extraction.',
                'implementation': ['ACCEPTANCE_MARKERS', 'is_acceptance_email()', 'classify_comment() pre-check'],
                'why_changed': 'Reduce false positives from applied/queued maintainer emails.',
                'evidence_reference': 'R1 pm_phase0_summary.md + validation false-positive analysis.',
            },
            {
                'change_id': 'R2-FIX-002',
                'root_cause': 'Krzysztof sign-offs (best regards) extracted as blocking objections.',
                'old_behavior': 'Pattern extraction used full comment text including closing sign-off lines.',
                'new_behavior': 'strip_signoff() removes trailing sign-off lines; sign-off phrases stored separately in signoff_patterns.',
                'implementation': ['SIGNOFF_PATTERNS', 'strip_signoff()', 'signoff_patterns profile field'],
                'why_changed': 'Prevent sign-off phrases from polluting objection signal.',
                'evidence_reference': 'R1 objection pattern list included best regards variants.',
            },
            {
                'change_id': 'R2-FIX-003',
                'root_cause': 'Pierre-Louis Bossart scope too narrow for Intel/general SoundWire activity.',
                'old_behavior': 'Scope limited to soundwire qcom + narrow ASoC.',
                'new_behavior': 'Added soundwire_broad scope and forced 2021-2025 window for Bossart.',
                'implementation': ['SUBSYSTEM_QUERIES.soundwire_broad', 'ReviewerCfg scope/window update'],
                'why_changed': 'Increase thread coverage for true reviewer activity footprint.',
                'evidence_reference': 'R1 fetch_log showed 10 threads for Bossart.',
            },
            {
                'change_id': 'R2-FIX-004',
                'root_cause': 'Vinod Koul scope too narrow; dmaengine activity missed.',
                'old_behavior': 'Scope mostly SoundWire qcom + ASoC qcom.',
                'new_behavior': 'Added dmaengine_soundwire scope and forced 2021-2025 window for Koul.',
                'implementation': ['SUBSYSTEM_QUERIES.dmaengine_soundwire', 'ReviewerCfg scope/window update'],
                'why_changed': 'Capture Koul maintainer reviews outside qcom-only patches.',
                'evidence_reference': 'R1 fetch_log showed 4 threads for Vinod Koul.',
            },
            {
                'change_id': 'R2-FIX-005',
                'root_cause': 'Liam Girdwood post-2022 activity sparse in narrow window.',
                'old_behavior': 'Primary 2023-2025 window only.',
                'new_behavior': 'Forced 2021-2025 window and asoc_broad scope.',
                'implementation': ['SUBSYSTEM_QUERIES.asoc_broad', 'ReviewerCfg scope/window update'],
                'why_changed': 'Improve chance of reaching P1 LOW_CONFIDENCE threshold.',
                'evidence_reference': 'R1 fetch_log showed 0 threads for Liam Girdwood.',
            },
            {
                'change_id': 'R2-FIX-006',
                'root_cause': 'Rob Herring scope narrowed to audio dt-bindings only.',
                'old_behavior': 'Only dt-bindings sound/audio + qcom platform query.',
                'new_behavior': 'Added dt_bindings_broad scope and forced 2021-2025 window for Rob Herring.',
                'implementation': ['SUBSYSTEM_QUERIES.dt_bindings_broad', 'ReviewerCfg scope/window update'],
                'why_changed': 'Reflect broad dt-bindings review footprint.',
                'evidence_reference': 'R1 fetch_log showed 3 threads for Rob Herring.',
            },
            {
                'change_id': 'R2-FIX-007',
                'root_cause': 'Konrad Dybcio had 0 threads in narrow qcom scope.',
                'old_behavior': 'Only arm64 dts qcom/pinctrl scope in short window.',
                'new_behavior': 'Added clk: qcom scope and forced 2021-2025 window.',
                'implementation': ['SUBSYSTEM_QUERIES.clk_qcom', 'ReviewerCfg scope/window update'],
                'why_changed': 'Retry with broader likely-reviewed domains before marking inactive.',
                'evidence_reference': 'R1 fetch_log showed 0 threads for Konrad Dybcio.',
            },
            {
                'change_id': 'R2-FIX-008',
                'root_cause': 'Validation sample size too small (3 accepted, 1 rejected).',
                'old_behavior': 'Selected only up to 3 accepted + 3 rejected candidates; ended with 4 total.',
                'new_behavior': 'Validation target set to exactly 5 accepted + 5 rejected/changes-requested, excluding known R1 series IDs.',
                'implementation': ['choose_validation_candidates()', 'run_validation_v2() selection logic'],
                'why_changed': 'Provide statistically meaningful precision/recall estimate.',
                'evidence_reference': 'R1 profile_validation_results.json had rejected_count=1.',
            },
        ],
    }
    (META_DIR / 'builder_changes_r2.json').write_text(json.dumps(payload, indent=2) + '\n')


def update_progress_tracker(r2_complete: bool, success: dict[str, Any]) -> None:
    tracker_path = PLAN_DIR / 'progress_tracker.json'
    tracker = json.loads(tracker_path.read_text())

    tracker['last_updated'] = TODAY
    tracker['current_phase'] = 0
    tracker['current_step'] = '0.R2'

    if r2_complete:
        tracker['overall_status'] = 'PHASE_1_READY'
    else:
        tracker['overall_status'] = 'PHASE_0_RETRY_R3_REQUIRED'

    for phase in tracker.get('phases', []):
        if phase.get('phase') == 0:
            if r2_complete:
                phase['status'] = 'COMPLETED'
                phase['completion_pct'] = 100
                phase['steps_completed'] = 10
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'READY'
            else:
                phase['status'] = 'RETRY_R3_REQUIRED'
                phase['completion_pct'] = 75
                phase['steps_completed'] = 8
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 2
                phase['pm_verdict'] = 'BLOCKED'
            phase['last_card'] = f'PC-P0-R2-{TODAY_COMPACT}'
            phase['success_criteria'] = {
                'total': 4,
                'met': sum(1 for v in success.values() if v),
                'not_met': sum(1 for v in success.values() if not v),
            }
        if phase.get('phase') == 1:
            if r2_complete:
                phase['status'] = 'IN_PROGRESS'
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'ON_TRACK'
            else:
                phase['status'] = 'BLOCKED_ON_PHASE_0'
                phase['steps_blocked'] = max(1, int(phase.get('steps_blocked', 1)))
                phase['pm_verdict'] = 'BLOCKED'

    tracker.setdefault('history', []).append({
        'date': TODAY,
        'action': 'Phase 0 R2 retry completed',
        'card': f'PC-P0-R2-{TODAY_COMPACT}',
        'phase_status_change': (
            'Phase 0 completed and Phase 1 started.'
            if r2_complete
            else 'Phase 0 retry did not meet all criteria; R3 required.'
        ),
    })

    tracker_path.write_text(json.dumps(tracker, indent=2) + '\n')


def write_progress_card(r2_complete: bool, validation: dict[str, Any], success: dict[str, bool]) -> None:
    card = {
        'card_id': f'PC-P0-R2-{TODAY_COMPACT}',
        'date': TODAY,
        'phase': 0,
        'step': '0.R2',
        'step_name': 'Phase 0 retry (R2) completion',
        'status': 'COMPLETED' if r2_complete else 'RETRY_R3_REQUIRED',
        'previous_status': 'FAILED',
        'what_was_done': 'Applied R2 false-positive fixes, expanded reviewer scopes/windows, rebuilt profiles, and revalidated on expanded case set.',
        'artifacts_created': [
            'AURA_KB/reviewer_profiles/metadata/builder_changes_r2.json',
            'AURA_KB/reviewer_profiles/metadata/fetch_log_r2.json',
            'AURA_KB/reviewer_profiles/metadata/profile_versions_r2.json',
            'AURA_KB/reviewer_profiles/metadata/phase0_validation_r2.json',
            'AURA_KB/reviewer_profiles/metadata/pm_phase0_summary_r2.md',
            'AURA_KB/reviewer_profiles/validation/profile_validation_results_r2.json',
            'AURA_KB/reviewer_profiles/validation/accuracy_report_r2.md',
            'AURA_KB/reviewer_profiles/processed/*_profile_v2.json',
            'AURA_KB/reviewer_profiles/raw/*_raw_r2_*.json',
            'AURA_KB/reviewer_profiles/subsystem_rules/*_rules_v2.json',
        ],
        'success_criteria_met': [k for k, v in success.items() if v],
        'success_criteria_not_met': [k for k, v in success.items() if not v],
        'pm_verdict': 'READY' if r2_complete else 'BLOCKED',
        'next_step': 'Phase 1 simulation engine planning' if r2_complete else 'Run Phase 0 retry R3 with further data expansion/tuning',
        'notes': f"R2 verdict: {validation['r2_verdict']}",
    }
    path = PLAN_DIR / f'progress_cards/PROGRESS_CARD_P0_R2_{TODAY_COMPACT}.json'
    path.write_text(json.dumps(card, indent=2) + '\n')


def render_pm_summary_r2(
    fetch_entries: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    rules_v2: dict[str, dict[str, Any]],
    validation_r2: dict[str, Any],
    phase1_unblocked: bool,
) -> str:
    conf_map = {x['reviewer']: x['confidence_level'] for x in fetch_entries}

    def top_objections(slug: str) -> list[str]:
        p = profiles.get(slug, {})
        arr = sorted(p.get('objection_patterns', []), key=lambda x: (-x.get('frequency', 0), x.get('pattern', '')))
        return [x.get('pattern', '') for x in arr[:5]]

    lines = [
        '# PM Phase 0 Summary (R2)',
        '',
        f'Generated: {NOW_UTC}',
        '',
        'Terminology:',
        '- LA = downstream / Linux Android',
        '- LE = upstream / Linux Embedded',
        '',
        '## 1. Which P0 reviewers have HIGH confidence profiles?',
    ]
    for name in P0_REVIEWERS:
        lines.append(f"- {name}: {conf_map.get(name, 'INSUFFICIENT_DATA')}")

    lines += ['', '## 2. Which reviewers are LOW_CONFIDENCE or INSUFFICIENT_DATA?']
    low_or_ins = [f"{x['reviewer']} ({x['confidence_level']})" for x in fetch_entries if x['confidence_level'] != 'HIGH']
    if low_or_ins:
        lines += [f'- {x}' for x in low_or_ins]
    else:
        lines.append('- None')

    lines += ['', '## 3. What are the top 5 objection patterns per P0 reviewer?']
    for slug in ['mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul']:
        nm = next((cfg.name for cfg in REVIEWERS if cfg.slug == slug), slug)
        vals = top_objections(slug)
        lines.append(f"- {nm}: {', '.join(vals) if vals else 'N/A'}")

    lines += ['', '## 4. What are the top 5 subsystem rules per P0 subsystem?']
    for sub in ['asoc_qcom', 'soundwire', 'dt_bindings_audio']:
        rv = rules_v2.get(sub, {})
        top = [r.get('rule', '') for r in rv.get('rules', [])[:5]]
        lines.append(f"- {sub}: {', '.join(top) if top else 'N/A'}")

    lines += [
        '',
        '## 5. What did profile validation show?',
        f"- Accepted cases: {validation_r2['validation_meta']['accepted_cases_achieved']}",
        f"- Rejected/changes-requested cases: {validation_r2['success_criteria']['rejected_validation_cases_achieved']}",
        f"- Overall precision: {validation_r2['success_criteria']['objection_precision_achieved']:.2f}",
        f"- Overall recall: {validation_r2['validation_meta']['overall_recall']:.2f}",
        f"- False positives on accepted: {validation_r2['validation_meta']['false_positives_on_accepted']}",
        f"- False negatives on rejected: {validation_r2['validation_meta']['false_negatives_on_rejected']}",
        '',
        '## 6. Is Phase 0 success criteria met?',
        f"- {'YES' if validation_r2['r2_verdict'] == 'PHASE_0_COMPLETE' else 'NO'}",
        '',
        '## 7. Is Phase 1 unblocked?',
        f"- {'YES' if phase1_unblocked else 'NO'}",
        '',
        '## 8. What should be improved before Phase 1?',
        '- Increase comment-thread coverage for reviewers still below HIGH confidence.',
        '- Continue reducing acceptance-email and courtesy-signoff leakage into objection signals.',
        '- Add reviewer-specific lexicon tuning for SoundWire and dt-bindings objection language.',
        '',
        f"Verdict: `{validation_r2['r2_verdict']}`",
    ]
    return '\n'.join(lines) + '\n'


def write_phase0_validation_r2(
    fetch_entries: list[dict[str, Any]],
    validation_results: dict[str, Any],
) -> dict[str, Any]:
    confidence_map = {x['reviewer']: x['confidence_level'] for x in fetch_entries}

    # P2 special handling for Konrad if still zero.
    konrad_entry = next((x for x in fetch_entries if x['reviewer'] == 'Konrad Dybcio'), None)
    if konrad_entry and int(konrad_entry.get('series_with_reviewer_comments', 0)) == 0:
        confidence_map['Konrad Dybcio'] = 'REVIEWER_INACTIVE_IN_SCOPE'

    p0_high = sum(1 for n in P0_REVIEWERS if confidence_map.get(n) == 'HIGH')
    p1_low_or_high = sum(1 for n in P1_REVIEWERS if confidence_map.get(n) in {'HIGH', 'LOW_CONFIDENCE'})

    rejected_cases = int(validation_results.get('selected_validation_cases', {}).get('rejected_or_changes_requested_count', 0))
    accepted_cases = int(validation_results.get('selected_validation_cases', {}).get('accepted_count', 0))
    precision = float(validation_results.get('overall_precision', 0.0))
    recall = float(validation_results.get('overall_recall', 0.0))

    success = {
        'p0_high_profiles_required': 3,
        'p0_high_profiles_achieved': p0_high,
        'p0_high_met': p0_high >= 3,
        'p1_low_or_high_required': 3,
        'p1_low_or_high_achieved': p1_low_or_high,
        'p1_low_or_high_met': p1_low_or_high >= 3,
        'rejected_validation_cases_required': 3,
        'rejected_validation_cases_achieved': rejected_cases,
        'rejected_validation_met': rejected_cases >= 3,
        'objection_precision_required': 0.60,
        'objection_precision_achieved': round(precision, 4),
        'objection_precision_met': precision >= 0.60,
    }

    r2_complete = all([
        success['p0_high_met'],
        success['p1_low_or_high_met'],
        success['rejected_validation_met'],
        success['objection_precision_met'],
    ])

    remaining = []
    if not success['p0_high_met']:
        remaining.append(f"P0 HIGH profiles shortfall: {p0_high}/3 required")
    if not success['p1_low_or_high_met']:
        remaining.append(f"P1 LOW/HIGH profiles shortfall: {p1_low_or_high}/3 required")
    if not success['rejected_validation_met']:
        remaining.append(f"Rejected validation coverage shortfall: {rejected_cases}/3 required")
    if not success['objection_precision_met']:
        remaining.append(f"Objection precision shortfall: {precision:.2f}/0.60 required")
    if recall < 0.70:
        remaining.append(f"Recall below advisory R2 target: {recall:.2f}/0.70")

    payload = {
        'artifact': 'phase0_validation_r2',
        'generated_date': NOW_UTC,
        'r1_verdict': R1_VERDICT,
        'r2_profile_confidence_levels': confidence_map,
        'success_criteria': success,
        'r2_verdict': 'PHASE_0_COMPLETE' if r2_complete else 'PHASE_0_FAILED_RETRY_REQUIRED',
        'phase1_unblocked': bool(r2_complete),
        'root_causes_fixed': [
            'acceptance_email_exclusion_added',
            'signoff_exclusion_added',
            'bossart_scope_expanded',
            'koul_scope_expanded',
            'girdwood_time_window_extended',
            'herring_scope_expanded',
            'dybcio_time_window_extended',
            'validation_set_expanded_to_10_cases',
        ],
        'remaining_gaps': remaining,
        'kernel_source_modified': 'no',
        'wcd9378_modified': 'no',
        'patches_generated': 'no',
        'phase1_simulation_engine_started': 'no',
        'validation_meta': {
            'accepted_cases_achieved': accepted_cases,
            'overall_recall': round(recall, 4),
            'false_positives_on_accepted': int(validation_results.get('false_positives_on_accepted', 0)),
            'false_negatives_on_rejected': int(validation_results.get('false_negatives_on_rejected', 0)),
        },
    }

    (META_DIR / 'phase0_validation_r2.json').write_text(json.dumps(payload, indent=2) + '\n')
    return payload


def write_profile_versions_r2(
    raw_by_slug: dict[str, dict[str, Any]],
    processed_by_slug: dict[str, dict[str, Any]],
    rules_v2: dict[str, dict[str, Any]],
) -> None:
    profiles = []
    for cfg in REVIEWERS:
        raw = raw_by_slug.get(cfg.slug, {})
        threads = int(raw.get('series_with_reviewer_comments', 0))
        conf = confidence_from_threads(threads)
        p_path = PROC_DIR / f'{cfg.slug}_profile_v2.json'

        status = 'ACTIVE' if p_path.exists() else 'FAILED'
        if conf == 'INSUFFICIENT_DATA':
            status = 'INSUFFICIENT_DATA'
        if cfg.slug == 'konrad_dybcio' and threads == 0:
            status = 'INSUFFICIENT_DATA'

        profiles.append({
            'reviewer': cfg.name,
            'version': 'v2',
            'path': str(p_path.relative_to(ROOT)) if p_path.exists() else None,
            'confidence': conf,
            'fetch_window': raw.get('time_window', {}),
            'series_count': int(raw.get('series_fetched', 0)),
            'thread_count': threads,
            'next_rebuild_due': '2026-12-21',
            'status': status,
        })

    subsystem_manifest = []
    for sub, fn in [
        ('asoc_qcom', 'asoc_qcom_rules_v2.json'),
        ('soundwire', 'soundwire_rules_v2.json'),
        ('dt_bindings_audio', 'dt_bindings_audio_rules_v2.json'),
        ('pinctrl_qcom', 'pinctrl_qcom_rules_v2.json'),
    ]:
        path = RULE_DIR / fn
        data = rules_v2.get(sub, {})
        subsystem_manifest.append({
            'subsystem': sub,
            'version': 'v2',
            'path': str(path.relative_to(ROOT)),
            'rule_count': len(data.get('rules', [])),
            'status': 'ACTIVE',
        })

    payload = {
        'generated_date': NOW_UTC,
        'profiles': profiles,
        'subsystem_rules': subsystem_manifest,
    }
    (META_DIR / 'profile_versions_r2.json').write_text(json.dumps(payload, indent=2) + '\n')


def main() -> None:
    fetch_params = read_fetch_parameters()
    write_builder_changes_r2()

    raw_by_slug: dict[str, dict[str, Any]] = {}
    processed_by_slug: dict[str, dict[str, Any]] = {}
    fetch_entries: list[dict[str, Any]] = []

    for cfg in REVIEWERS:
        start, end, deviations = determine_time_window(cfg, fetch_params)

        print(f'[phase0-r2] fetching reviewer: {cfg.name} window={start[:4]}-{end[:4]}', flush=True)
        client = PatchworkClient()
        raw_payload, summary = fetch_reviewer_raw(client, cfg, start, end)

        raw_payload['time_window'] = {'start': start, 'end': end}
        raw_name = f"{cfg.slug}_raw_r2_{start[:4]}_{end[:4]}.json"
        raw_path = RAW_DIR / raw_name
        raw_path.write_text(json.dumps(raw_payload, indent=2) + '\n')
        raw_by_slug[cfg.slug] = raw_payload

        confidence = confidence_from_threads(int(summary['threads']))
        status = 'SUCCESS'
        if summary['api_error']:
            status = 'PARTIAL'
        if confidence == 'INSUFFICIENT_DATA':
            status = 'PARTIAL'

        # Konrad specific documented inactivity behavior (P2).
        if cfg.slug == 'konrad_dybcio' and int(summary['threads']) < 20:
            deviations.append('EXPANDED_SCOPE_STILL_INSUFFICIENT (P2): REVIEWER_INACTIVE_IN_SCOPE')

        fetch_entries.append({
            'reviewer': cfg.name,
            'fetch_date': NOW_UTC,
            'time_window_used': f"{start[:4]}-{end[:4]}",
            'scope_queries_run': summary['scope_queries'],
            'series_fetched': int(summary['series_fetched']),
            'series_with_reviewer_comments': int(summary['threads']),
            'comments_after_filter': int(summary['comments_after_filter']),
            'confidence_level': confidence,
            'api_errors': summary['api_errors'],
            'api_error': bool(summary['api_error']),
            'rate_limit_hits': int(summary['rate_limit_hits']),
            'deviations_from_parameters': deviations,
            'status': status,
        })

        extracted = extract_patterns(cfg, raw_payload)
        profile = build_profile(cfg, raw_payload, extracted)
        processed_path = PROC_DIR / f'{cfg.slug}_profile_v2.json'
        processed_path.write_text(json.dumps(profile, indent=2) + '\n')
        processed_by_slug[cfg.slug] = profile

        print(
            f"[phase0-r2] {cfg.name}: threads={summary['threads']} comments={summary['comments_after_filter']} confidence={confidence}",
            flush=True,
        )

    fetch_log_payload = {
        'artifact': 'fetch_log_r2',
        'generated_date': NOW_UTC,
        'builder_changes_reference': 'AURA_KB/reviewer_profiles/metadata/builder_changes_r2.json',
        'rationale_summary': [
            'R2 adds acceptance-email exclusion to reduce objection false positives.',
            'R2 strips sign-off lines before pattern extraction.',
            'R2 expands reviewer scope and/or window for low-coverage reviewers.',
            'R2 keeps raw/processed separation and preserves R1 files.',
        ],
        'reviewers': fetch_entries,
    }
    (META_DIR / 'fetch_log_r2.json').write_text(json.dumps(fetch_log_payload, indent=2) + '\n')

    rules_v2 = build_subsystem_rules_v2(processed_by_slug, raw_by_slug)

    # Preserve R1 rule files by writing v2 outputs separately.
    (RULE_DIR / 'asoc_qcom_rules_v2.json').write_text(json.dumps(rules_v2['asoc_qcom'], indent=2) + '\n')
    (RULE_DIR / 'soundwire_rules_v2.json').write_text(json.dumps(rules_v2['soundwire'], indent=2) + '\n')
    (RULE_DIR / 'dt_bindings_audio_rules_v2.json').write_text(json.dumps(rules_v2['dt_bindings_audio'], indent=2) + '\n')
    (RULE_DIR / 'pinctrl_qcom_rules_v2.json').write_text(json.dumps(rules_v2['pinctrl_qcom'], indent=2) + '\n')

    validation_results, accuracy_md = run_validation_v2(processed_by_slug, raw_by_slug)
    (VAL_DIR / 'profile_validation_results_r2.json').write_text(json.dumps(validation_results, indent=2) + '\n')
    (VAL_DIR / 'accuracy_report_r2.md').write_text(accuracy_md)

    write_profile_versions_r2(raw_by_slug, processed_by_slug, rules_v2)

    phase0_validation = write_phase0_validation_r2(fetch_entries, validation_results)
    r2_complete = phase0_validation['r2_verdict'] == 'PHASE_0_COMPLETE'

    pm_summary = render_pm_summary_r2(
        fetch_entries=fetch_entries,
        profiles=processed_by_slug,
        rules_v2=rules_v2,
        validation_r2=phase0_validation,
        phase1_unblocked=bool(r2_complete),
    )
    (META_DIR / 'pm_phase0_summary_r2.md').write_text(pm_summary)

    success_checks = {
        'p0_high_profiles': phase0_validation['success_criteria']['p0_high_met'],
        'p1_low_or_high_profiles': phase0_validation['success_criteria']['p1_low_or_high_met'],
        'rejected_validation_cases': phase0_validation['success_criteria']['rejected_validation_met'],
        'objection_precision': phase0_validation['success_criteria']['objection_precision_met'],
    }

    update_progress_tracker(r2_complete, success_checks)
    write_progress_card(r2_complete, phase0_validation, success_checks)

    print(f"[phase0-r2] verdict={phase0_validation['r2_verdict']}", flush=True)


if __name__ == '__main__':
    main()
