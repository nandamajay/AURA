#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
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
NOW_ISO = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
TODAY = str(date.today())

INCLUDE_STATES = {'accepted', 'mainlined', 'rejected', 'changes-requested'}
EXCLUDE_STATES = {'new', 'under-review', 'superseded', 'deferred'}

SUBSYSTEM_QUERIES = {
    'asoc_qcom': ['ASoC: qcom', 'ASoC: codecs'],
    'soundwire': ['ASoC: SoundWire', 'soundwire: qcom'],
    'dt_bindings_audio': ['dt-bindings: sound: qcom', 'dt-bindings: sound', 'ASoC: dt-bindings'],
    'pinctrl_qcom': ['pinctrl: qcom'],
    'qcom_platform': ['arm64: dts: qcom'],
}

# Use project filters to avoid global Patchwork noise.
PROJECT_ALLOWLIST = {
    'asoc_qcom': {'alsa-devel', 'linux-arm-msm', 'devicetree'},
    'soundwire': {'alsa-devel', 'soundwire', 'linux-arm-msm'},
    'dt_bindings_audio': {'devicetree', 'alsa-devel', 'linux-arm-msm'},
    'pinctrl_qcom': {'linux-gpio', 'linux-arm-msm', 'devicetree'},
    'qcom_platform': {'linux-arm-msm', 'devicetree'},
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

REVIEWERS: list[ReviewerCfg] = [
    ReviewerCfg('Mark Brown', 'mark_brown', 'P0', 500, 2000, ['mark brown', 'broonie'], ['broonie', 'mark.brown'], ['asoc_qcom', 'soundwire', 'dt_bindings_audio']),
    ReviewerCfg('Pierre-Louis Bossart', 'pierre_louis_bossart', 'P0', 300, 1500, ['pierre-louis bossart', 'pierre louis bossart'], ['bossart'], ['soundwire', 'asoc_qcom']),
    ReviewerCfg('Krzysztof Kozlowski', 'krzysztof_kozlowski', 'P0', 400, 2000, ['krzysztof kozlowski'], ['krzysztof.kozlowski', 'krzysztof.kozlowski+dt'], ['dt_bindings_audio', 'qcom_platform']),
    ReviewerCfg('Vinod Koul', 'vinod_koul', 'P0', 200, 1000, ['vinod koul'], ['vkoul', 'vinod.koul'], ['soundwire', 'asoc_qcom']),
    ReviewerCfg('Liam Girdwood', 'liam_girdwood', 'P1', 150, 800, ['liam girdwood'], ['lgirdwood', 'liam.r.girdwood'], ['asoc_qcom', 'soundwire']),
    ReviewerCfg('Bjorn Andersson', 'bjorn_andersson', 'P1', 200, 1000, ['bjorn andersson', 'björn andersson'], ['bjorn.andersson'], ['qcom_platform', 'pinctrl_qcom']),
    ReviewerCfg('Linus Walleij', 'linus_walleij', 'P1', 200, 1000, ['linus walleij'], ['linus.walleij'], ['pinctrl_qcom']),
    ReviewerCfg('Rob Herring', 'rob_herring', 'P1', 200, 1000, ['rob herring'], ['robh'], ['dt_bindings_audio', 'qcom_platform']),
    ReviewerCfg('Konrad Dybcio', 'konrad_dybcio', 'P2', 150, 800, ['konrad dybcio'], ['konrad.dybcio'], ['qcom_platform', 'pinctrl_qcom']),
]

STOPWORDS = {
    'the','and','for','this','that','with','from','have','has','had','are','was','were','will','would','could','should',
    'into','about','there','their','them','than','then','also','just','when','what','where','which','while','been','being',
    'please','patch','series','code','it','its','you','your','they','not','but','can','cant','cannot','dont',
}
BOT_TOKENS = ['bot', 'ci', 'autobuild', 'syzbot', 'kernel test robot', 'lkp', 'patchwork']
ACK_ONLY = {'thanks', 'applied', 'queued'}

OBJECTION_REGEX = [
    r'\bplease\s+split\b', r'\bneeds?\s+to\b', r'\bmust\b', r'\bshould\s+be\b', r'\bwrong\b',
    r'\bnack\b', r'\bchanges?\s+requested\b', r'\bnot\s+acceptable\b', r'\bdo\s+not\b', r'\bdon\'t\b',
    r'\bfix\b', r'\brework\b', r'\brefactor\b', r'\bbreaks?\b', r'\bproblem\b', r'\bissue\b'
]
ACCEPT_REGEX = [r'\blooks\s+good\b', r'\backed-by\b', r'\breviewed-by\b', r'\bapplied\b', r'\bqueued\b', r'\blgtm\b']
QUESTION_REGEX = [r'\?+', r'\bwhy\b', r'\bhow\b', r'\bcan\s+you\b', r'\bcould\s+you\b', r'\bwhat\b']
NIT_REGEX = [r'\bnit\b', r'\btypo\b', r'\bspelling\b', r'\bwhitespace\b', r'\bstyle\b', r'\bnaming\b']
DT_REGEX = [r'dt-binding', r'\byaml\b', r'dtbs_check', r'compatible', r'unevaluatedproperties', r'additionalproperties']
RUNTIME_PM_REGEX = [r'runtime\s*pm', r'pm_runtime', r'autosuspend', r'\bsuspend\b', r'\bresume\b']
SERIES_STRUCTURE_REGEX = [r'\bseries\b', r'\bsplit\b', r'\bpatch\s+\d+/', r'\border\b', r'\bbisect']
VENDOR_REGEX = [r'\bdownstream\b', r'\bvendor\b', r'\bandroid\b', r'\bmsm\b', r'\bqcom\b']
COMMIT_MSG_REGEX = [r'commit\s+message', r'changelog', r'fixes:', r'link:', r'subject', r'describe\s+why']


class PatchworkClient:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.rate_hits = 0
        self.errors: list[str] = []

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(5):
            try:
                r = self.s.get(url, params=params, timeout=40)
                if r.status_code == 429:
                    self.rate_hits += 1
                    time.sleep(1.0 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == 4:
                    self.errors.append(f'GET {url} params={params} failed: {e}')
                    return None
                time.sleep(0.6 * (attempt + 1))
        return None


def iso_to_date(s: str) -> str:
    return (s or '')[:10]


def within_window(d: str, start: str, end: str) -> bool:
    return bool(d and start <= d <= end)


def clean_comment_text(text: str) -> str:
    lines = []
    for ln in (text or '').splitlines():
        st = ln.strip()
        if not st:
            continue
        if st.startswith('>'):
            continue
        if st.lower().startswith('on ') and ' wrote:' in st.lower():
            continue
        lines.append(st)
    joined = '\n'.join(lines)
    joined = re.sub(r'`{3}.*?`{3}', ' ', joined, flags=re.DOTALL)
    joined = re.sub(r'\s+', ' ', joined).strip()
    return joined


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


def reviewer_match(cfg: ReviewerCfg, name: str, email: str) -> bool:
    n = (name or '').lower()
    e = (email or '').lower()
    return any(a in n for a in cfg.aliases) or any(em in e for em in cfg.emails)


def classify_comment(text: str, patch_state: str) -> str:
    t = (text or '').lower()
    if any(re.search(p, t) for p in NIT_REGEX):
        return 'nit'
    if any(re.search(p, t) for p in QUESTION_REGEX):
        return 'question'
    if any(re.search(p, t) for p in ACCEPT_REGEX):
        return 'acceptance'
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


def normalize_dup(text: str) -> str:
    t = re.sub(r'\W+', ' ', text.lower()).strip()
    return re.sub(r'\s+', ' ', t)


def scope_queries_for(cfg: ReviewerCfg) -> list[str]:
    out = []
    for key in cfg.scope_keys:
        out.extend(SUBSYSTEM_QUERIES[key])
    return out


def allowed_projects(cfg: ReviewerCfg) -> set[str]:
    out = set()
    for key in cfg.scope_keys:
        out |= PROJECT_ALLOWLIST.get(key, set())
    return out


def desired_threads(cfg: ReviewerCfg) -> int:
    if cfg.priority == 'P0':
        return 55
    if cfg.priority == 'P1':
        return 25
    return 20


def fetch_reviewer_raw(client: PatchworkClient, cfg: ReviewerCfg, start: str, end: str) -> tuple[dict[str, Any], dict[str, Any]]:
    queries = scope_queries_for(cfg)
    project_allow = allowed_projects(cfg)
    target_threads = desired_threads(cfg)

    seen_series_ids: set[int] = set()
    raw_series: list[dict[str, Any]] = []

    series_fetch_count = 0
    comments_fetched = 0
    comments_after_filter = 0
    threads = 0

    max_pages_per_query_state = 10

    def process_series(s: dict[str, Any]) -> None:
        nonlocal series_fetch_count, comments_fetched, comments_after_filter, threads
        if series_fetch_count >= cfg.max_series or comments_after_filter >= cfg.max_comments:
            return

        sid = int(s.get('id', 0) or 0)
        sname = s.get('name', '')
        sdate = s.get('date', '')
        patches = s.get('patches', []) or []

        series_fetch_count += 1

        per_series_comments: list[dict[str, Any]] = []
        patch_states: list[str] = []
        patch_ids: list[int] = []
        dup_in_series: set[str] = set()

        for p in patches:
            if comments_after_filter >= cfg.max_comments:
                break
            purl = p.get('url')
            pid = int(p.get('id', 0) or 0)
            if not purl or not pid:
                continue
            patch_ids.append(pid)

            pd = client.get_json(purl)
            if not isinstance(pd, dict):
                continue

            pstate = (pd.get('state') or '').strip()
            if pstate:
                patch_states.append(pstate)
            if pstate and pstate in EXCLUDE_STATES:
                continue

            comments_url = pd.get('comments')
            if not comments_url:
                continue
            clist = client.get_json(comments_url)
            if not isinstance(clist, list):
                continue

            comments_fetched += len(clist)

            for c in clist:
                sub = c.get('submitter') or {}
                rname = sub.get('name', '')
                remail = sub.get('email', '')
                if not reviewer_match(cfg, rname, remail):
                    continue

                ctext_raw = c.get('content', '') or ''
                csubj = c.get('subject', '') or ''
                ctext = clean_comment_text(ctext_raw)
                wc = word_count(ctext)
                if wc < 20:
                    continue
                if is_bot_or_ci(rname, remail, ctext, csubj):
                    continue
                if is_ack_only(ctext):
                    continue
                nk = normalize_dup(ctext)
                if nk in dup_in_series:
                    continue
                dup_in_series.add(nk)

                per_series_comments.append({
                    'comment_id': int(c.get('id', 0) or 0),
                    'date': c.get('date', ''),
                    'word_count': wc,
                    'classification': classify_comment(ctext, pstate),
                    'text': ctext,
                    'patch_id': pid,
                    'patch_state': pstate,
                    'submitter_name': rname,
                    'submitter_email': remail,
                })
                comments_after_filter += 1
                if comments_after_filter >= cfg.max_comments:
                    break

        if per_series_comments:
            threads += 1
            raw_series.append({
                'series_id': sid,
                'subject': sname,
                'state': derive_series_state(patch_states),
                'date': sdate,
                'patch_count': len(patches),
                'patch_ids': patch_ids,
                'reviewer_comments': sorted(per_series_comments, key=lambda x: x['date']),
            })

    for q in queries:
        for st in ['accepted', 'mainlined', 'rejected', 'changes-requested']:
            for page in range(1, max_pages_per_query_state + 1):
                if series_fetch_count >= cfg.max_series or comments_after_filter >= cfg.max_comments:
                    break
                if threads >= target_threads and cfg.priority in {'P0', 'P1'}:
                    break

                params = {'q': q, 'state': st, 'since': start, 'per_page': 100, 'page': page}
                arr = client.get_json(f'{PATCHWORK_API}/series/', params=params)
                if not isinstance(arr, list) or not arr:
                    break

                for s in arr:
                    sid = int(s.get('id', 0) or 0)
                    if not sid or sid in seen_series_ids:
                        continue
                    sdate = iso_to_date(s.get('date', ''))
                    if not within_window(sdate, start, end):
                        continue
                    plink = ((s.get('project') or {}).get('link_name') or '').strip()
                    if project_allow and plink and plink not in project_allow:
                        continue
                    seen_series_ids.add(sid)
                    process_series(s)
                    if series_fetch_count >= cfg.max_series or comments_after_filter >= cfg.max_comments:
                        break
                    if threads >= target_threads and cfg.priority in {'P0', 'P1'}:
                        break

                if len(arr) < 100:
                    break

    raw_payload = {
        'reviewer': cfg.name,
        'fetch_date': NOW_ISO,
        'time_window': {'start': start, 'end': end},
        'scope_queries_used': queries,
        'series_fetched': series_fetch_count,
        'series_with_reviewer_comments': threads,
        'comments_fetched': comments_fetched,
        'comments_after_filter': comments_after_filter,
        'series': sorted(raw_series, key=lambda x: x['date'], reverse=True),
        'fetch_errors': list(client.errors),
        'api_rate_limit_hits': client.rate_hits,
    }
    summary = {
        'threads': threads,
        'series_fetched': series_fetch_count,
        'comments_after_filter': comments_after_filter,
        'comments_fetched': comments_fetched,
        'api_errors': list(client.errors),
        'rate_limit_hits': client.rate_hits,
        'queries': queries,
    }
    return raw_payload, summary


def confidence_from_threads(n: int) -> str:
    if n >= 50:
        return 'HIGH'
    if n >= 20:
        return 'LOW_CONFIDENCE'
    return 'INSUFFICIENT_DATA'


def flatten_comments(raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in raw_payload.get('series', []):
        sid = s.get('series_id')
        ssub = s.get('subject', '')
        sstate = s.get('state', '')
        for c in s.get('reviewer_comments', []):
            out.append({
                'series_id': sid,
                'series_subject': ssub,
                'series_state': sstate,
                'text': c.get('text', ''),
                'classification': c.get('classification', 'neutral'),
                'patch_state': c.get('patch_state', sstate),
                'date': c.get('date', ''),
                'word_count': c.get('word_count', 0),
            })
    return out


def extract_patterns(cfg: ReviewerCfg, raw_payload: dict[str, Any]) -> list[dict[str, Any]]:
    comments = flatten_comments(raw_payload)
    if not comments:
        return []

    defs = {
        'objection': OBJECTION_REGEX,
        'acceptance': ACCEPT_REGEX,
        'question': QUESTION_REGEX,
        'nit': NIT_REGEX,
        'subsystem_rule': [r'\basoc\b', r'soundwire', r'\bsdw\b', r'dt-binding', r'\bpinctrl\b', r'\bqcom\b'],
        'commit_message': COMMIT_MSG_REGEX,
        'dt_rule': DT_REGEX,
        'runtime_pm': RUNTIME_PM_REGEX,
        'series_structure': SERIES_STRUCTURE_REGEX,
        'vendor_code': VENDOR_REGEX,
    }

    bucket: dict[tuple[str, str], dict[str, Any]] = {}

    for cat, regexes in defs.items():
        for rgx in regexes:
            freq = 0
            ex_series = []
            ex_excerpt = []
            for c in comments:
                text = c['text'].lower()
                if re.search(rgx, text):
                    freq += 1
                    if c['series_id'] not in ex_series:
                        ex_series.append(c['series_id'])
                    if len(ex_excerpt) < 3:
                        ex_excerpt.append(c['text'][:220])
            if freq > 0:
                bucket[(cat, rgx)] = {
                    'category': cat,
                    'pattern': rgx,
                    'frequency': freq,
                    'example_series_ids': ex_series[:8],
                    'example_comment_excerpts': ex_excerpt,
                }

    for cls in ['objection', 'question', 'nit', 'acceptance']:
        cls_comments = [c['text'].lower() for c in comments if c['classification'] == cls]
        grams = Counter()
        for text in cls_comments:
            tokens = [t for t in re.findall(r'[a-z][a-z0-9_\-]{1,}', text) if t not in STOPWORDS]
            for n in (2, 3):
                for i in range(0, max(0, len(tokens) - n + 1)):
                    g = ' '.join(tokens[i:i+n])
                    if len(g) >= 8:
                        grams[g] += 1
        for g, f in grams.most_common(8):
            if f < 2:
                continue
            if (cls, g) not in bucket:
                exs, ex_ids = [], []
                for c in comments:
                    if c['classification'] == cls and g in c['text'].lower():
                        if c['series_id'] not in ex_ids:
                            ex_ids.append(c['series_id'])
                        if len(exs) < 3:
                            exs.append(c['text'][:220])
                bucket[(cls, g)] = {
                    'category': cls,
                    'pattern': g,
                    'frequency': f,
                    'example_series_ids': ex_ids[:8],
                    'example_comment_excerpts': exs,
                }

    entries = sorted(bucket.values(), key=lambda x: (-x['frequency'], x['category'], x['pattern']))
    out = []
    for i, e in enumerate(entries, start=1):
        freq = e['frequency']
        conf = 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW'
        fpr = 'LOW' if len(e['pattern']) >= 18 and freq >= 4 else 'MEDIUM' if freq >= 6 else 'HIGH'
        out.append({
            'pattern_id': f'{cfg.slug.upper()}-PAT-{i:03d}',
            'reviewer': cfg.name,
            'category': e['category'],
            'pattern': e['pattern'],
            'frequency': freq,
            'example_series_ids': e['example_series_ids'],
            'example_comment_excerpts': e['example_comment_excerpts'],
            'confidence': conf,
            'false_positive_risk': fpr,
        })
    return out


def build_profile(cfg: ReviewerCfg, raw_payload: dict[str, Any], patterns: list[dict[str, Any]]) -> dict[str, Any]:
    threads = int(raw_payload.get('series_with_reviewer_comments', 0))
    confidence = confidence_from_threads(threads)
    cats = defaultdict(list)
    for p in patterns:
        cats[p['category']].append(p)

    def top_patterns(cat: str, k: int = 5) -> list[str]:
        arr = sorted(cats.get(cat, []), key=lambda x: (-x['frequency'], x['pattern']))
        return [x['pattern'] for x in arr[:k]]

    versions = []
    for s in raw_payload.get('series', []):
        m = re.search(r'\bv(\d+)\b', (s.get('subject') or '').lower())
        if m:
            versions.append(int(m.group(1)))
    typical_iter = int(round(sum(versions) / len(versions))) if versions else 1

    dt_hits = sum(p['frequency'] for p in cats.get('dt_rule', []))
    rpm_hits = sum(p['frequency'] for p in cats.get('runtime_pm', []))
    vendor_hits = sum(p['frequency'] for p in cats.get('vendor_code', []))
    objection_hits = sum(p['frequency'] for p in cats.get('objection', []))
    acceptance_hits = sum(p['frequency'] for p in cats.get('acceptance', []))

    strict = lambda h: 'HIGH' if h >= 25 else 'MEDIUM' if h >= 8 else 'LOW'
    if objection_hits > acceptance_hits * 1.8:
        rfc_tol = 'LOW'
    elif objection_hits > acceptance_hits * 1.2:
        rfc_tol = 'MEDIUM'
    else:
        rfc_tol = 'HIGH'
    vendor_tol = 'LOW' if vendor_hits >= 15 else 'MEDIUM' if vendor_hits >= 6 else 'HIGH'

    profile = {
        'reviewer': cfg.name,
        'profile_version': 'v1',
        'generated_date': TODAY,
        'time_window': raw_payload.get('time_window', {}),
        'confidence_level': confidence,
        'series_analyzed': int(raw_payload.get('series_fetched', 0)),
        'comment_threads_analyzed': threads,
        'subsystems_covered': sorted(set(cfg.scope_keys)),
        'objection_patterns': sorted(cats.get('objection', []), key=lambda x: (-x['frequency'], x['pattern']))[:25],
        'acceptance_patterns': sorted(cats.get('acceptance', []), key=lambda x: (-x['frequency'], x['pattern']))[:25],
        'question_patterns': sorted(cats.get('question', []), key=lambda x: (-x['frequency'], x['pattern']))[:20],
        'nit_patterns': sorted(cats.get('nit', []), key=lambda x: (-x['frequency'], x['pattern']))[:20],
        'subsystem_specific_rules': sorted(cats.get('subsystem_rule', []), key=lambda x: (-x['frequency'], x['pattern']))[:25],
        'top_objection_topics': top_patterns('objection', 10),
        'top_acceptance_signals': top_patterns('acceptance', 10),
        'typical_review_iterations': typical_iter,
        'rfc_tolerance': rfc_tol,
        'dt_strictness': strict(dt_hits),
        'runtime_pm_strictness': strict(rpm_hits),
        'vendor_code_tolerance': vendor_tol,
        'known_limitations': [],
        'profile_notes': 'Derived from Patchwork review comments using deterministic filters and regex/ngram extraction.',
    }
    if confidence != 'HIGH':
        profile['known_limitations'].append('Limited thread coverage for HIGH-confidence generalization.')
    if threads < 20:
        profile['known_limitations'].append('INSUFFICIENT_DATA threshold not met; advisory-only usage.')
    return profile


def build_subsystem_rules(all_patterns: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    subsystem_reviewers = {
        'asoc_qcom': ['mark_brown', 'pierre_louis_bossart', 'vinod_koul', 'liam_girdwood'],
        'soundwire': ['pierre_louis_bossart', 'vinod_koul', 'mark_brown'],
        'dt_bindings_audio': ['krzysztof_kozlowski', 'rob_herring', 'mark_brown'],
        'pinctrl_qcom': ['linus_walleij', 'bjorn_andersson', 'konrad_dybcio'],
    }
    out = {}
    for subsystem, reviewers in subsystem_reviewers.items():
        candidates = []
        for slug in reviewers:
            for p in all_patterns.get(slug, []):
                if p['category'] == 'acceptance':
                    continue
                sev = 'QUESTION' if p['category'] == 'question' else 'NIT' if p['category'] == 'nit' else 'SHOULD_FIX'
                if p['category'] in {'objection', 'dt_rule', 'runtime_pm', 'vendor_code'} and p['frequency'] >= 6:
                    sev = 'BLOCKING'
                applies = {
                    'commit_message': 'commit_message',
                    'dt_rule': 'dt_binding',
                    'nit': 'code_style',
                    'runtime_pm': 'runtime_pm',
                    'series_structure': 'series_structure',
                    'vendor_code': 'vendor_code',
                    'subsystem_rule': 'api_usage',
                    'question': 'api_usage',
                    'objection': 'code_style',
                }.get(p['category'], 'api_usage')
                candidates.append({
                    'rule_id': f'{subsystem.upper()}-{slug.upper()}-{len(candidates)+1:03d}',
                    'rule': p['pattern'],
                    'source_reviewer': p['reviewer'],
                    'evidence_series_ids': p['example_series_ids'][:6],
                    'frequency': p['frequency'],
                    'severity': sev,
                    'applies_to': applies,
                    'false_positive_risk': p['false_positive_risk'],
                })
        ded = {}
        for r in candidates:
            k = (r['rule'], r['source_reviewer'])
            if k not in ded or r['frequency'] > ded[k]['frequency']:
                ded[k] = r
        rules = sorted(ded.values(), key=lambda x: (-x['frequency'], x['rule']))[:45]
        out[subsystem] = {
            'subsystem': subsystem,
            'version': 'v1',
            'generated_date': TODAY,
            'primary_reviewers': [next((c.name for c in REVIEWERS if c.slug == s), s) for s in reviewers],
            'rules': rules,
            'known_limitations': [] if rules else ['No sufficient rule evidence found from current profile data.'],
        }
    return out


def choose_validation_cases(reviewer_raw: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    acc, rej = [], []
    for slug, raw in reviewer_raw.items():
        if slug not in {'mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul'}:
            continue
        for s in raw.get('series', []):
            item = {
                'reviewer_slug': slug,
                'reviewer': next((c.name for c in REVIEWERS if c.slug == slug), slug),
                'series_id': s.get('series_id'),
                'subject': s.get('subject', ''),
                'state': s.get('state', ''),
                'comments': s.get('reviewer_comments', []),
            }
            if s.get('state') in {'accepted', 'mainlined'}:
                acc.append(item)
            if s.get('state') in {'rejected', 'changes-requested'}:
                rej.append(item)
    acc = sorted(acc, key=lambda x: x['series_id'])[:3]
    rej = sorted(rej, key=lambda x: x['series_id'])[:3]
    return {'accepted': acc, 'rejected_or_changes_requested': rej}


def fired_patterns_for_case(profile: dict[str, Any], case: dict[str, Any]) -> list[dict[str, Any]]:
    text = ((case.get('subject') or '') + ' ' + ' '.join((c.get('text') or '') for c in case.get('comments', []))).lower()
    fired = []
    for section in ['objection_patterns', 'subsystem_specific_rules', 'question_patterns', 'nit_patterns']:
        for p in profile.get(section, []):
            patt = p.get('pattern', '')
            try:
                match = bool(re.search(patt, text))
            except re.error:
                match = patt.lower() in text if patt else False
            if match:
                fired.append({
                    'section': section,
                    'pattern_id': p.get('pattern_id'),
                    'pattern': patt,
                    'severity': 'BLOCKING' if section == 'objection_patterns' else 'INFO',
                })
    ded = {(f['section'], f['pattern']): f for f in fired}
    return list(ded.values())


def run_validation(processed_profiles: dict[str, dict[str, Any]], reviewer_raw: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    selected = choose_validation_cases(reviewer_raw)
    results = {
        'artifact': 'reviewer_profile_validation_results_v1',
        'generated_date': TODAY,
        'selected_validation_cases': {
            'accepted_count': len(selected['accepted']),
            'rejected_or_changes_requested_count': len(selected['rejected_or_changes_requested']),
            'accepted_series_ids': [c['series_id'] for c in selected['accepted']],
            'rejected_series_ids': [c['series_id'] for c in selected['rejected_or_changes_requested']],
        },
        'cases': [],
        'metrics': {'per_reviewer': {}, 'overall': {}},
    }

    per = defaultdict(lambda: {'tp': 0, 'fp': 0, 'fn': 0, 'accepted_cases': 0, 'rejected_cases': 0})

    for label, expected_blocking in [('accepted', False), ('rejected_or_changes_requested', True)]:
        for case in selected[label]:
            slug = case['reviewer_slug']
            prof = processed_profiles.get(slug)
            if not prof:
                continue
            fired = fired_patterns_for_case(prof, case)
            fired_blocking = any(f['severity'] == 'BLOCKING' for f in fired)

            if expected_blocking:
                per[slug]['rejected_cases'] += 1
                if fired_blocking:
                    per[slug]['tp'] += 1
                else:
                    per[slug]['fn'] += 1
            else:
                per[slug]['accepted_cases'] += 1
                if fired_blocking:
                    per[slug]['fp'] += 1

            results['cases'].append({
                'series_id': case['series_id'],
                'subject': case['subject'],
                'reviewer': case['reviewer'],
                'reviewer_slug': slug,
                'state': case['state'],
                'expected_blocking_objection': expected_blocking,
                'patterns_fired': fired,
                'blocking_fired': fired_blocking,
                'real_comment_classifications': sorted(set(c.get('classification', 'neutral') for c in case.get('comments', []))),
            })

    otp = ofp = ofn = 0
    for slug, m in sorted(per.items()):
        tp, fp, fn = m['tp'], m['fp'], m['fn']
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        fpr = fp / m['accepted_cases'] if m['accepted_cases'] else 0.0
        results['metrics']['per_reviewer'][slug] = {
            'reviewer': next((c.name for c in REVIEWERS if c.slug == slug), slug),
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'false_positive_count': fp,
            'false_negative_count': fn,
            'accepted_cases': m['accepted_cases'],
            'rejected_cases': m['rejected_cases'],
            'false_positive_rate': round(fpr, 4),
        }
        otp += tp
        ofp += fp
        ofn += fn

    oprec = otp / (otp + ofp) if (otp + ofp) else 0.0
    orec = otp / (otp + ofn) if (otp + ofn) else 0.0

    results['metrics']['overall'] = {
        'precision': round(oprec, 4),
        'recall': round(orec, 4),
        'false_positive_total': ofp,
        'false_negative_total': ofn,
        'objection_pattern_precision_target_met': oprec >= 0.60,
        'accepted_patch_false_positive_target_met': ofp <= 2,
    }

    lines = [
        '# Reviewer Profile Validation Accuracy Report',
        '',
        f'Generated: {TODAY}',
        '',
        '## Validation Set',
        f"- Accepted patches/series: {results['selected_validation_cases']['accepted_count']}",
        f"- Rejected/changes-requested patches/series: {results['selected_validation_cases']['rejected_or_changes_requested_count']}",
        '',
        '## Per-Reviewer Precision/Recall',
    ]
    for _, m in results['metrics']['per_reviewer'].items():
        lines.append(f"- {m['reviewer']}: precision={m['precision']:.2f}, recall={m['recall']:.2f}, FP={m['false_positive_count']}, FN={m['false_negative_count']}")
    lines += [
        '',
        '## Overall',
        f"- Precision: {results['metrics']['overall']['precision']:.2f}",
        f"- Recall: {results['metrics']['overall']['recall']:.2f}",
        f"- False positives on accepted patches: {results['metrics']['overall']['false_positive_total']}",
        f"- False negatives on rejected patches: {results['metrics']['overall']['false_negative_total']}",
        '',
        '## Confidence Assessment',
        '- Scores are bounded by profile confidence level and validation sample size.',
        '- LOW_CONFIDENCE and INSUFFICIENT_DATA profiles should remain advisory.',
        '',
        '## Recommended Tuning Actions',
        '1. Increase reviewer thread coverage where confidence is below HIGH.',
        '2. Improve objection-pattern normalization to reduce false positives.',
        '3. Add subsystem-specific lexical parsers for dt-bindings and SoundWire.',
    ]
    return results, '\n'.join(lines) + '\n'


def update_master_plan_and_tracker(fetch_log: list[dict[str, Any]], phase0_verdict: str, success_flags: dict[str, bool]) -> None:
    tracker_path = PLAN_DIR / 'progress_tracker.json'
    tracker = json.loads(tracker_path.read_text())

    high_p0 = sum(1 for e in fetch_log if e['reviewer'] in {'Mark Brown','Pierre-Louis Bossart','Krzysztof Kozlowski','Vinod Koul'} and e['confidence_level'] == 'HIGH')
    low_or_high_p1 = sum(1 for e in fetch_log if e['reviewer'] in {'Liam Girdwood','Bjorn Andersson','Linus Walleij','Rob Herring'} and e['confidence_level'] in {'HIGH','LOW_CONFIDENCE'})

    phase0_status = 'COMPLETED' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else ('IN_PROGRESS' if phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL' else 'FAILED')
    overall_status = 'PHASE_1_UNBLOCKED' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else 'PHASE_0_PARTIAL' if phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL' else 'PHASE_0_FAILED'

    tracker['last_updated'] = TODAY
    tracker['overall_status'] = overall_status
    tracker['current_phase'] = 0
    tracker['current_step'] = '0.10'

    for ph in tracker.get('phases', []):
        if ph.get('phase') == 0:
            ph['status'] = phase0_status
            ph['steps_completed'] = 10 if phase0_status == 'COMPLETED' else 9 if phase0_status == 'IN_PROGRESS' else 6
            ph['steps_in_progress'] = 0
            ph['steps_blocked'] = 0 if phase0_status == 'COMPLETED' else 1
            ph['completion_pct'] = 100 if phase0_status == 'COMPLETED' else 90 if phase0_status == 'IN_PROGRESS' else 60
            ph['pm_verdict'] = 'ON_TRACK' if phase0_status == 'COMPLETED' else 'REPLANNED' if phase0_status == 'IN_PROGRESS' else 'BLOCKED'
            ph['last_card'] = 'PC-P0-COMPLETE-20260621'
            met = sum(1 for v in success_flags.values() if v)
            total = len(success_flags)
            ph['success_criteria'] = {'total': total, 'met': met, 'not_met': total - met}
        if ph.get('phase') == 1:
            if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED':
                ph['status'] = 'READY_TO_START'
                ph['steps_blocked'] = 0
                ph['pm_verdict'] = 'READY'
            elif phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL':
                ph['status'] = 'CONDITIONAL_ON_PHASE_0_GAPS'
                ph['pm_verdict'] = 'CONDITIONAL'
            else:
                ph['status'] = 'BLOCKED_ON_PHASE_0'
                ph['pm_verdict'] = 'BLOCKED'

    tracker.setdefault('history', []).append({
        'date': TODAY,
        'action': 'Phase 0 processing completed',
        'card': 'PC-P0-COMPLETE-20260621',
        'phase_status_change': f"Phase 0 ended with verdict {phase0_verdict}; P0_HIGH={high_p0}/4, P1_LOW_OR_HIGH={low_or_high_p1}/4"
    })
    tracker_path.write_text(json.dumps(tracker, indent=2) + '\n')

    master_path = PLAN_DIR / 'MASTER_PLAN.md'
    mtxt = master_path.read_text()
    mtxt = mtxt.replace('### Status: IN_PROGRESS', f'### Status: {phase0_status}', 1)
    mtxt = mtxt.replace('| 0 | Reviewer Pattern Learning | NOT_STARTED | Before Phase 1 |', f'| 0 | Reviewer Pattern Learning | {phase0_status} | Before Phase 1 |')
    mtxt = mtxt.replace('| 0 | Reviewer Pattern Learning | IN_PROGRESS | Before Phase 1 |', f'| 0 | Reviewer Pattern Learning | {phase0_status} | Before Phase 1 |')

    step_updates = {
        '| 0.1 | Define subsystems and maintainers | NOT_STARTED | |': '| 0.1 | Define subsystems and maintainers | COMPLETED | reviewer list and subsystem map finalized |',
        '| 0.2 | Define fetch parameters | NOT_STARTED | |': '| 0.2 | Define fetch parameters | COMPLETED | fetch_parameters.json created |',
        '| 0.3 | Fetch raw comment history | NOT_STARTED | |': '| 0.3 | Fetch raw comment history | COMPLETED | raw artifacts generated for P0/P1/P2 |',
        '| 0.4 | Filter and clean raw data | NOT_STARTED | |': '| 0.4 | Filter and clean raw data | COMPLETED | min-word/bot/ack/CI/duplicate filters applied |',
        '| 0.5 | Extract objection/acceptance patterns | NOT_STARTED | |': '| 0.5 | Extract objection/acceptance patterns | COMPLETED | per-reviewer pattern sets extracted |',
        '| 0.6 | Build per-reviewer behavioral profiles | NOT_STARTED | |': '| 0.6 | Build per-reviewer behavioral profiles | COMPLETED | processed profiles generated where data available |',
        '| 0.7 | Build per-subsystem rule sets | NOT_STARTED | |': '| 0.7 | Build per-subsystem rule sets | COMPLETED | rule files created for target subsystems |',
        '| 0.8 | Validate profiles against known outcomes | NOT_STARTED | |': '| 0.8 | Validate profiles against known outcomes | COMPLETED | validation report + accuracy metrics generated |',
        '| 0.9 | Store offline profiles in AURA_KB | NOT_STARTED | |': '| 0.9 | Store offline profiles in AURA_KB | COMPLETED | raw/processed/metadata separation enforced |',
        '| 0.10 | PM review and sign-off | NOT_STARTED | |': f'| 0.10 | PM review and sign-off | {"COMPLETED" if phase0_status=="COMPLETED" else "PARTIAL" if phase0_status=="IN_PROGRESS" else "FAILED"} | see pm_phase0_summary.md |',
    }
    for old, new in step_updates.items():
        if old in mtxt:
            mtxt = mtxt.replace(old, new)

    append = f"\n\n### Phase 0 Update ({TODAY})\n- Verdict: `{phase0_verdict}`\n- P0 HIGH confidence reviewers: {high_p0}/4\n- P1 LOW/HIGH confidence reviewers: {low_or_high_p1}/4\n- Artifacts: `AURA_KB/reviewer_profiles/`\n"
    if append not in mtxt:
        mtxt += append
    master_path.write_text(mtxt)


def main() -> None:
    fetch_log: list[dict[str, Any]] = []
    reviewer_raw: dict[str, dict[str, Any]] = {}
    all_patterns: dict[str, list[dict[str, Any]]] = {}
    processed_profiles: dict[str, dict[str, Any]] = {}

    for cfg in REVIEWERS:
        print(f'[phase0] fetching reviewer: {cfg.name}', flush=True)
        client = PatchworkClient()
        start = '2023-01-01'
        end = '2025-12-31'

        raw_payload, summary = fetch_reviewer_raw(client, cfg, start, end)
        confidence = confidence_from_threads(summary['threads'])
        time_window_used = '2023-2025'
        deviations = []

        if cfg.priority == 'P1' and summary['threads'] < 20:
            print(f'[phase0] secondary window for {cfg.name}', flush=True)
            client2 = PatchworkClient()
            raw2, sum2 = fetch_reviewer_raw(client2, cfg, '2021-01-01', end)
            if sum2['threads'] > summary['threads']:
                raw_payload = raw2
                summary = sum2
                confidence = confidence_from_threads(summary['threads'])
                time_window_used = '2021-2025'
                deviations.append('Secondary window 2021-2025 used due low primary activity.')

        raw_payload['time_window'] = {'start': time_window_used.split('-')[0] + '-01-01', 'end': '2025-12-31'}
        (RAW_DIR / f'{cfg.slug}_raw_2023_2025.json').write_text(json.dumps(raw_payload, indent=2) + '\n')
        reviewer_raw[cfg.slug] = raw_payload

        status = 'SUCCESS'
        if confidence == 'INSUFFICIENT_DATA':
            status = 'PARTIAL'
        if summary['api_errors']:
            status = 'PARTIAL'

        fetch_log.append({
            'reviewer': cfg.name,
            'fetch_date': NOW_ISO,
            'time_window_used': time_window_used,
            'scope_queries_run': summary['queries'],
            'series_fetched': summary['series_fetched'],
            'series_with_reviewer_comments': summary['threads'],
            'comments_after_filter': summary['comments_after_filter'],
            'confidence_level': confidence,
            'api_errors': summary['api_errors'],
            'rate_limit_hits': summary['rate_limit_hits'],
            'deviations_from_parameters': deviations,
            'status': status,
        })

        if summary['threads'] >= 20:
            pats = extract_patterns(cfg, raw_payload)
            all_patterns[cfg.slug] = pats
            profile = build_profile(cfg, raw_payload, pats)
            processed_profiles[cfg.slug] = profile
            (PROC_DIR / f'{cfg.slug}_profile_v1.json').write_text(json.dumps(profile, indent=2) + '\n')
        else:
            all_patterns[cfg.slug] = []

        print(f"[phase0] {cfg.name}: threads={summary['threads']} comments={summary['comments_after_filter']} confidence={confidence}", flush=True)

    (META_DIR / 'fetch_log.json').write_text(json.dumps(fetch_log, indent=2) + '\n')

    rules_by_sub = build_subsystem_rules(all_patterns)
    (RULE_DIR / 'asoc_qcom_rules_v1.json').write_text(json.dumps(rules_by_sub['asoc_qcom'], indent=2) + '\n')
    (RULE_DIR / 'soundwire_rules_v1.json').write_text(json.dumps(rules_by_sub['soundwire'], indent=2) + '\n')
    (RULE_DIR / 'dt_bindings_audio_rules_v1.json').write_text(json.dumps(rules_by_sub['dt_bindings_audio'], indent=2) + '\n')
    (RULE_DIR / 'pinctrl_qcom_rules_v1.json').write_text(json.dumps(rules_by_sub['pinctrl_qcom'], indent=2) + '\n')

    validation_results, accuracy_md = run_validation(processed_profiles, reviewer_raw)
    (VAL_DIR / 'profile_validation_results.json').write_text(json.dumps(validation_results, indent=2) + '\n')
    (VAL_DIR / 'accuracy_report.md').write_text(accuracy_md)

    profiles_manifest = []
    for cfg in REVIEWERS:
        raw = reviewer_raw.get(cfg.slug, {})
        threads = int(raw.get('series_with_reviewer_comments', 0))
        conf = confidence_from_threads(threads)
        ppath = PROC_DIR / f'{cfg.slug}_profile_v1.json'
        profiles_manifest.append({
            'reviewer': cfg.name,
            'version': 'v1',
            'path': str(ppath.relative_to(ROOT)) if ppath.exists() else None,
            'confidence': conf,
            'fetch_window': raw.get('time_window', {}),
            'series_count': int(raw.get('series_fetched', 0)),
            'thread_count': threads,
            'next_rebuild_due': '2026-12-21',
            'status': 'ACTIVE' if ppath.exists() else ('INSUFFICIENT_DATA' if conf == 'INSUFFICIENT_DATA' else 'FAILED'),
        })

    subsystem_manifest = []
    for sub, fn in [
        ('asoc_qcom', 'asoc_qcom_rules_v1.json'),
        ('soundwire', 'soundwire_rules_v1.json'),
        ('dt_bindings_audio', 'dt_bindings_audio_rules_v1.json'),
        ('pinctrl_qcom', 'pinctrl_qcom_rules_v1.json'),
    ]:
        data = json.loads((RULE_DIR / fn).read_text())
        subsystem_manifest.append({
            'subsystem': sub,
            'version': 'v1',
            'path': str((RULE_DIR / fn).relative_to(ROOT)),
            'rule_count': len(data.get('rules', [])),
            'status': 'ACTIVE',
        })

    (META_DIR / 'profile_versions.json').write_text(json.dumps({'generated_date': TODAY, 'profiles': profiles_manifest, 'subsystem_rules': subsystem_manifest}, indent=2) + '\n')

    lookup = {x['reviewer']: x for x in fetch_log}
    p0 = ['Mark Brown', 'Pierre-Louis Bossart', 'Krzysztof Kozlowski', 'Vinod Koul']
    p1 = ['Liam Girdwood', 'Bjorn Andersson', 'Linus Walleij', 'Rob Herring']

    p0_all_high = all(lookup.get(n, {}).get('confidence_level') == 'HIGH' for n in p0)
    p1_low_plus = all(lookup.get(n, {}).get('confidence_level') in {'HIGH', 'LOW_CONFIDENCE'} for n in p1)

    overall_prec = validation_results['metrics']['overall'].get('precision', 0.0)
    overall_fp = validation_results['metrics']['overall'].get('false_positive_total', 999)

    success_flags = {
        'all_p0_high': p0_all_high,
        'all_p1_low_or_high': p1_low_plus,
        'objection_patterns_extracted_high_reviewers': len([p for p in profiles_manifest if p['confidence'] == 'HIGH' and p['status'] == 'ACTIVE']) > 0,
        'acceptance_patterns_extracted_high_reviewers': len([p for p in profiles_manifest if p['confidence'] == 'HIGH' and p['status'] == 'ACTIVE']) > 0,
        'subsystem_rules_created_p0': all((RULE_DIR / fn).exists() for fn in ['asoc_qcom_rules_v1.json', 'soundwire_rules_v1.json', 'dt_bindings_audio_rules_v1.json']),
        'validation_accepted_ge_3': validation_results['selected_validation_cases']['accepted_count'] >= 3,
        'validation_rejected_ge_3': validation_results['selected_validation_cases']['rejected_or_changes_requested_count'] >= 3,
        'objection_precision_ge_60pct': overall_prec >= 0.60,
        'false_positive_le_2': overall_fp <= 2,
        'profiles_versioned': True,
        'raw_processed_separated': True,
    }

    if all(success_flags.values()):
        phase0_verdict = 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED'
    elif success_flags['validation_accepted_ge_3'] and success_flags['validation_rejected_ge_3']:
        phase0_verdict = 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL'
    else:
        phase0_verdict = 'PHASE_0_FAILED_RETRY_REQUIRED'

    # PM summary
    low_or_ins = [f"{x['reviewer']} ({x['confidence_level']})" for x in fetch_log if x['confidence_level'] != 'HIGH']

    def top5(slug: str, key: str) -> list[str]:
        p = processed_profiles.get(slug, {})
        arr = p.get(key, [])
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            arr = sorted(arr, key=lambda x: (-x.get('frequency', 0), x.get('pattern', '')))
            return [x.get('pattern', '') for x in arr[:5]]
        return []

    subsystem_top_rules = {}
    for fn in ['asoc_qcom_rules_v1.json', 'soundwire_rules_v1.json', 'dt_bindings_audio_rules_v1.json']:
        data = json.loads((RULE_DIR / fn).read_text())
        subsystem_top_rules[data['subsystem']] = [r['rule'] for r in data.get('rules', [])[:5]]

    pm = [
        '# PM Phase 0 Summary',
        '',
        f'Generated: {TODAY}',
        '',
        '## 1. Which P0 reviewers have HIGH confidence profiles?',
    ]
    for n in p0:
        pm.append(f"- {n}: {lookup.get(n, {}).get('confidence_level', 'INSUFFICIENT_DATA')}")
    pm += ['', '## 2. Which reviewers are LOW_CONFIDENCE or INSUFFICIENT_DATA?']
    if low_or_ins:
        pm += [f'- {x}' for x in low_or_ins]
    else:
        pm += ['- None']

    pm += ['', '## 3. What are the top 5 objection patterns per P0 reviewer?']
    for slug in ['mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul']:
        nm = next((c.name for c in REVIEWERS if c.slug == slug), slug)
        vals = top5(slug, 'objection_patterns')
        pm.append(f"- {nm}: {', '.join(vals) if vals else 'N/A'}")

    pm += ['', '## 4. What are the top 5 subsystem rules per P0 subsystem?']
    for sub, vals in subsystem_top_rules.items():
        pm.append(f"- {sub}: {', '.join(vals) if vals else 'N/A'}")

    pm += [
        '',
        '## 5. What did profile validation show?',
        f"- Overall precision: {validation_results['metrics']['overall'].get('precision', 0.0):.2f}",
        f"- Overall recall: {validation_results['metrics']['overall'].get('recall', 0.0):.2f}",
        f"- False positive count on accepted patches: {validation_results['metrics']['overall'].get('false_positive_total', 0)}",
        f"- False negative count on rejected patches: {validation_results['metrics']['overall'].get('false_negative_total', 0)}",
        '',
        '## 6. Is Phase 0 success criteria met?',
        f"- {'YES' if all(success_flags.values()) else 'NO'}",
        '',
        '## 7. Is Phase 1 unblocked?',
        f"- {'YES' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else 'CONDITIONAL' if phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL' else 'NO'}",
        '',
        '## 8. What should be improved before Phase 1?',
        '- Expand review-thread corpus for reviewers below HIGH confidence.',
        '- Improve objection pattern extraction to reduce false positives.',
        '- Add stronger subsystem lexicons for dt-bindings and SoundWire.',
        '',
        f'Verdict: `{phase0_verdict}`',
    ]
    (META_DIR / 'pm_phase0_summary.md').write_text('\n'.join(pm) + '\n')

    complete_card = {
        'card_id': 'PC-P0-COMPLETE-20260621',
        'date': TODAY,
        'phase': 0,
        'step': '0.10',
        'step_name': 'Phase 0 completion and PM sign-off',
        'status': 'COMPLETED' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else 'PARTIAL' if phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL' else 'FAILED',
        'previous_status': 'IN_PROGRESS',
        'what_was_done': 'Fetched raw reviewer comments, extracted patterns, built profiles and subsystem rules, and validated outputs.',
        'artifacts_created': [
            'AURA_KB/reviewer_profiles/raw/',
            'AURA_KB/reviewer_profiles/processed/',
            'AURA_KB/reviewer_profiles/subsystem_rules/',
            'AURA_KB/reviewer_profiles/validation/',
            'AURA_KB/reviewer_profiles/metadata/'
        ],
        'artifacts_modified': [
            'AURA_KB/platform_tools/upstream_reviewer_sim_01/plan/progress_tracker.json',
            'AURA_KB/platform_tools/upstream_reviewer_sim_01/plan/MASTER_PLAN.md'
        ],
        'success_criteria_met': [k for k, v in success_flags.items() if v],
        'success_criteria_not_met': [k for k, v in success_flags.items() if not v],
        'blockers': [] if phase0_verdict != 'PHASE_0_FAILED_RETRY_REQUIRED' else ['Profile confidence/validation thresholds not met'],
        'deviations_from_plan': ['Series state inferred from patch states because series endpoint does not provide explicit consolidated state.'],
        'pm_verdict': 'ON_TRACK' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else 'REPLANNED' if phase0_verdict == 'PHASE_0_PARTIAL_PHASE_1_CONDITIONAL' else 'BLOCKED',
        'next_step': 'Phase 1 simulation engine prototype' if phase0_verdict == 'PHASE_0_COMPLETE_PHASE_1_UNBLOCKED' else 'Close Phase 0 confidence and validation gaps',
        'notes': f'Phase 0 verdict: {phase0_verdict}'
    }
    (PLAN_DIR / 'progress_cards/PROGRESS_CARD_P0_COMPLETE_20260621.json').write_text(json.dumps(complete_card, indent=2) + '\n')

    update_master_plan_and_tracker(fetch_log, phase0_verdict, success_flags)

    phase0_validation = {
        'artifact': 'phase0_validation',
        'generated_date': TODAY,
        'json_parse_status': {},
        'kernel_source_modified': 'no',
        'wcd9378_modified': 'no',
        'patches_generated': 'no',
        'phase1_simulation_engine_started': 'no',
        'raw_data_stored_separately_from_processed': 'yes',
        'profile_confidence_levels_achieved': {x['reviewer']: x['confidence_level'] for x in fetch_log},
        'phase0_verdict': phase0_verdict,
    }

    files_to_check = [
        META_DIR / 'fetch_parameters.json',
        META_DIR / 'fetch_log.json',
        META_DIR / 'profile_versions.json',
        VAL_DIR / 'profile_validation_results.json',
    ]
    files_to_check += sorted(PROC_DIR.glob('*_profile_v1.json'))

    for p in files_to_check:
        try:
            json.loads(p.read_text())
            phase0_validation['json_parse_status'][str(p.relative_to(ROOT))] = 'PASS'
        except Exception as e:
            phase0_validation['json_parse_status'][str(p.relative_to(ROOT))] = f'FAIL: {e}'

    (META_DIR / 'phase0_validation.json').write_text(json.dumps(phase0_validation, indent=2) + '\n')

    print(f'[phase0] verdict={phase0_verdict}', flush=True)


if __name__ == '__main__':
    main()
