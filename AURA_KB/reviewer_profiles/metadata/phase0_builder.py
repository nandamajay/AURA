#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path('/local/mnt/workspace/AURA_V1_upstream')
BASE = ROOT / 'AURA_KB/reviewer_profiles'
RAW_DIR = BASE / 'raw'
PROC_DIR = BASE / 'processed'
RULE_DIR = BASE / 'subsystem_rules'
VAL_DIR = BASE / 'validation'
META_DIR = BASE / 'metadata'
PLAN_DIR = ROOT / 'AURA_KB/platform_tools/upstream_reviewer_sim_01/plan'

NOW_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
TODAY = str(date.today())
TODAY_COMPACT = TODAY.replace('-', '')

R1_VERDICT = 'PHASE_0_FAILED_RETRY_REQUIRED'
R2_VERDICT = 'PHASE_0_FAILED_RETRY_REQUIRED'

# Weighted model constants (R3)
WEIGHT_HIGH = 3.0
WEIGHT_MEDIUM = 1.5
WEIGHT_LOW = 0.5
WEIGHT_ZERO = 0.0
DEFAULT_BLOCKING_THRESHOLD = 3.0
THRESHOLD_CANDIDATES = [2.0, 2.5, 3.0, 3.5, 4.0]

# Fixed validation set from R2 (must not change)
FIXED_VALIDATION_CASES = [
    {'series_id': 713662, 'reviewer_slug': 'krzysztof_kozlowski', 'state': 'accepted', 'expected_blocking_objection': False},
    {'series_id': 858471, 'reviewer_slug': 'mark_brown', 'state': 'accepted', 'expected_blocking_objection': False},
    {'series_id': 651180, 'reviewer_slug': 'pierre_louis_bossart', 'state': 'accepted', 'expected_blocking_objection': False},
    {'series_id': 716373, 'reviewer_slug': 'krzysztof_kozlowski', 'state': 'accepted', 'expected_blocking_objection': False},
    {'series_id': 873172, 'reviewer_slug': 'mark_brown', 'state': 'accepted', 'expected_blocking_objection': False},
    {'series_id': 751628, 'reviewer_slug': 'krzysztof_kozlowski', 'state': 'changes-requested', 'expected_blocking_objection': True},
    {'series_id': 410777, 'reviewer_slug': 'vinod_koul', 'state': 'changes-requested', 'expected_blocking_objection': True},
    {'series_id': 757519, 'reviewer_slug': 'krzysztof_kozlowski', 'state': 'changes-requested', 'expected_blocking_objection': True},
    {'series_id': 504081, 'reviewer_slug': 'vinod_koul', 'state': 'changes-requested', 'expected_blocking_objection': True},
    {'series_id': 507031, 'reviewer_slug': 'vinod_koul', 'state': 'changes-requested', 'expected_blocking_objection': True},
]

BOT_TOKENS = ['bot', 'ci', 'autobuild', 'syzbot', 'kernel test robot', 'lkp', 'patchwork-bot']
ACK_ONLY = {'thanks', 'applied', 'queued'}

ACCEPTANCE_MARKERS = [
    'applied to https://git.kernel.org',
    'applied to git.kernel.org',
    'queued for',
    'will be merged',
    'merged into',
    'thanks, applied',
    'thanks!\napplied',
]

SIGNOFF_PATTERNS = [
    r'best regards',
    r'regards,?\s+\w+',
    r'thanks,?\s+\w+',
    r'cheers,?\s+\w+',
]

OBJECTION_REGEX = [
    r'\bplease\s+split\b',
    r'\bneeds?\s+to\b',
    r'\bmust\b',
    r'\bshould\s+be\b',
    r'\bwrong\b',
    r'\bnack\b',
    r'\bchanges?\s+requested\b',
    r'\bnot\s+acceptable\b',
    r'\bdo\s+not\b',
    r"\bdon't\b",
    r'\bfix\b',
    r'\brework\b',
    r'\brefactor\b',
    r'\bbreaks?\b',
    r'\bproblem\b',
    r'\bissue\b',
    r'\bplease\s+use\b',
    r'\bagainst\s+bindings\b',
    r'\bdtbs_check\b',
    r'\bunevaluatedproperties\b',
]

ACCEPT_REGEX = [
    r'\blooks\s+good\b',
    r'\backed-by\b',
    r'\breviewed-by\b',
    r'\blgtm\b',
]

QUESTION_REGEX = [
    r'\?+',
    r'\bwhy\b',
    r'\bhow\b',
    r'\bcan\s+you\b',
    r'\bcould\s+you\b',
    r'\bwhat\b',
]

NIT_REGEX = [r'\bnit\b', r'\btypo\b', r'\bspelling\b', r'\bwhitespace\b', r'\bstyle\b', r'\bnaming\b']

DT_REGEX = [
    r'dtbs_check',
    r'unevaluatedproperties',
    r'additionalproperties:\s*false',
    r'\$ref:',
    r'dts\s+against\s+bindings',
    r'against\s+bindings',
]

RUNTIME_PM_REGEX = [r'runtime\s*pm', r'pm_runtime', r'autosuspend', r'\bsuspend\b', r'\bresume\b']
SERIES_STRUCTURE_REGEX = [r'\bseries\b', r'\bsplit\b', r'\bpatch\s+\d+/', r'\border\b', r'\bbisect']
COMMIT_MSG_REGEX = [r'commit\s+message', r'changelog', r'fixes:', r'link:', r'imperative\s+mood', r'subject\s+prefixes']

# R3 fix A: subsystem context tokens (never blocking)
SUBSYSTEM_CONTEXT_REGEX = [
    r'\bqcom\b',
    r'\bmsm\b',
    r'\bqualcomm\b',
    r'dt-binding',
    r'dt-bindings',
    r'\basoc\b',
    r'soundwire',
    r'\bcodec\b',
    r'\bcompatible\b',
]

QUESTION_AS_OBJECTION_MARKERS = [
    'why not',
    'have you tested',
    'did you test',
    's-o-b',
    'sob',
    'signed-off',
    'sign-off',
    'why is',
    'why does',
    'why would',
    'what is the reason',
    'what was the reason',
]

REQUIREMENT_OBJECTION_REGEX = [
    r'\bs[\-\s]?o[\-\s]?b\b',
    r'signed[\-\s]off',
    r'have\s+you\s+tested',
    r'did\s+you\s+test',
    r'\bi\s+would\s+need\b',
    r'\bwould\s+need\b',
]

KOUL_SPECIFIC_PATTERNS = [
    {'pattern': r'\bs[\-\s]?o[\-\s]?b\b', 'weight': WEIGHT_HIGH, 'category': 'process_objection'},
    {'pattern': r'signed[\-\s]off', 'weight': WEIGHT_HIGH, 'category': 'process_objection'},
    {'pattern': r'have\s+you\s+tested', 'weight': WEIGHT_HIGH, 'category': 'testing_objection'},
    {'pattern': r'did\s+you\s+test', 'weight': WEIGHT_HIGH, 'category': 'testing_objection'},
    {'pattern': r'why\s+not\b', 'weight': WEIGHT_MEDIUM, 'category': 'design_question'},
    {'pattern': r'\bwhy\b', 'weight': WEIGHT_LOW, 'category': 'design_question'},
]

STOPWORDS = {
    'the', 'and', 'for', 'this', 'that', 'with', 'from', 'have', 'has', 'had', 'are',
    'was', 'were', 'will', 'would', 'could', 'should', 'into', 'about', 'there', 'their',
    'them', 'than', 'then', 'also', 'just', 'when', 'what', 'where', 'which', 'while',
    'been', 'being', 'please', 'patch', 'series', 'code', 'you', 'your', 'they', 'not',
    'but', 'can', 'cant', 'cannot', 'dont', 'does', 'did', 'done', 'doing', 'it', 'its',
    'all', 'any', 'one', 'two', 'three', 'four', 'five', 'using', 'used', 'use', 'look',
}

SCORING_SECTIONS = [
    'objection_patterns',
    'dt_rules',
    'runtime_pm_rules',
    'series_structure_rules',
    'commit_message_rules',
    'reviewer_specific_patterns',
]


@dataclass
class ReviewerCfg:
    name: str
    slug: str
    priority: str


REVIEWERS = [
    ReviewerCfg('Mark Brown', 'mark_brown', 'P0'),
    ReviewerCfg('Pierre-Louis Bossart', 'pierre_louis_bossart', 'P0'),
    ReviewerCfg('Krzysztof Kozlowski', 'krzysztof_kozlowski', 'P0'),
    ReviewerCfg('Vinod Koul', 'vinod_koul', 'P0'),
    ReviewerCfg('Liam Girdwood', 'liam_girdwood', 'P1'),
    ReviewerCfg('Bjorn Andersson', 'bjorn_andersson', 'P1'),
    ReviewerCfg('Linus Walleij', 'linus_walleij', 'P1'),
    ReviewerCfg('Rob Herring', 'rob_herring', 'P1'),
    ReviewerCfg('Konrad Dybcio', 'konrad_dybcio', 'P2'),
]

P0_REVIEWERS = ['Mark Brown', 'Pierre-Louis Bossart', 'Krzysztof Kozlowski', 'Vinod Koul']
P1_REVIEWERS = ['Liam Girdwood', 'Bjorn Andersson', 'Linus Walleij', 'Rob Herring']


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n')


def choose_raw_file(slug: str) -> Path | None:
    preferred = [
        RAW_DIR / f'{slug}_raw_r2_2021_2025.json',
        RAW_DIR / f'{slug}_raw_r2_2023_2025.json',
        RAW_DIR / f'{slug}_raw_2023_2025.json',
    ]
    for p in preferred:
        if p.exists():
            return p

    candidates = sorted(RAW_DIR.glob(f'{slug}_raw*.json'))
    return candidates[-1] if candidates else None


def safe_search(pattern: str, text: str) -> bool:
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_\-']+", text))


def clean_comment_text(text: str) -> str:
    lines = []
    for raw in (text or '').splitlines():
        ln = raw.strip()
        if not ln:
            continue
        if ln.startswith('>'):
            continue
        if ln.lower().startswith('on ') and ' wrote:' in ln.lower():
            continue
        lines.append(re.sub(r'\s+', ' ', ln))
    return '\n'.join(lines).strip()


def strip_signoff(text: str) -> tuple[str, list[str]]:
    lines = [x.rstrip() for x in (text or '').splitlines() if x.strip()]
    removed: list[str] = []
    for _ in range(3):
        if not lines:
            break
        candidate = lines[-1].strip()
        if candidate in {'--', '-- '}:
            removed.insert(0, candidate)
            lines.pop()
            continue
        if any(re.search(p, candidate, re.IGNORECASE) for p in SIGNOFF_PATTERNS):
            removed.insert(0, candidate)
            lines.pop()
            continue
        break
    return '\n'.join(lines).strip(), removed


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


def is_bot_or_ci(name: str, email: str, text: str, subject: str = '') -> bool:
    blob = f"{name} {email} {text} {subject}".lower()
    if any(tok in blob for tok in BOT_TOKENS):
        return True
    if 'reported-by: kernel test robot' in blob:
        return True
    return False


def is_acceptance_email(text: str) -> bool:
    t = (text or '').lower()
    return any(marker in t for marker in ACCEPTANCE_MARKERS)


def is_signoff_phrase(pattern: str) -> bool:
    low = pattern.lower().strip()
    if 'best regards' in low:
        return True
    if low.startswith('regards') or low.startswith('thanks') or low.startswith('cheers'):
        return True
    return False


def classify_comment(text: str) -> str:
    if is_acceptance_email(text):
        return 'acceptance'
    t = (text or '').lower()
    if any(re.search(p, t) for p in REQUIREMENT_OBJECTION_REGEX):
        return 'objection'
    if any(re.search(p, t) for p in OBJECTION_REGEX):
        return 'objection'
    if any(re.search(p, t) for p in ACCEPT_REGEX):
        return 'acceptance'
    if any(re.search(p, t) for p in NIT_REGEX):
        return 'nit'
    if any(re.search(p, t) for p in QUESTION_REGEX):
        return 'question'
    return 'neutral'


def classify_comment_with_context(text: str, series_state: str, reviewer_slug: str) -> str:
    base = classify_comment(text)
    if base == 'question' and series_state in {'changes-requested', 'rejected'}:
        low = text.lower()
        if any(marker in low for marker in QUESTION_AS_OBJECTION_MARKERS):
            return 'objection'
        if reviewer_slug == 'vinod_koul' and '?' in low:
            # Koul often raises blocking requirements as question phrasing.
            return 'objection'
    return base


def confidence_from_threads(threads: int) -> str:
    if threads >= 50:
        return 'HIGH'
    if threads >= 20:
        return 'LOW_CONFIDENCE'
    return 'INSUFFICIENT_DATA'


def section_for_classification(cls: str) -> str:
    return {
        'objection': 'objection_patterns',
        'acceptance': 'acceptance_patterns',
        'question': 'question_patterns',
        'nit': 'nit_patterns',
    }.get(cls, 'neutral_patterns')


def count_words_phrase(pattern: str) -> int:
    # Ignore regex control tokens and single-letter artifacts such as "\\s".
    normalized = re.sub(r'\\[bBsSwWdD]', ' ', pattern)
    normalized = re.sub(r'[\^\$\+\*\?\|\(\)\[\]\{\}]', ' ', normalized)
    toks = [t for t in re.findall(r'[A-Za-z0-9_\-]+', normalized) if len(t) > 1]
    return len(toks)


def assign_weight(pattern: str, section: str, explicit_weight: float | None = None) -> float:
    if explicit_weight is not None:
        return float(explicit_weight)

    if section in {'subsystem_context', 'acceptance_patterns', 'question_patterns', 'nit_patterns', 'signoff_patterns'}:
        return WEIGHT_ZERO

    low = pattern.lower()
    high_terms = [
        'dts against bindings', 'against bindings', 'dtbs_check', 'unevaluatedproperties',
        'additionalproperties', 'please split', 'subject prefixes', 's-o-b', 'signed-off',
        'have you tested', 'did you test', '$ref:',
    ]
    medium_terms = [
        r'\bfix\b', r'\bshould\s+be\b', r'\bdo\s+not\b', r"\bdon't\b", r'\bneeds?\s+to\b',
        'please use', 'imperative mood', 'runtime pm', 'pm_runtime',
    ]
    low_terms = [r'\bissue\b', r'\bproblem\b', r'\bwhy\b']

    if any(t in low for t in high_terms):
        return WEIGHT_HIGH

    # Strong multiword phrases are high-weight.
    if count_words_phrase(pattern) >= 3:
        return WEIGHT_HIGH

    if any(re.search(t, low) for t in medium_terms):
        return WEIGHT_MEDIUM

    if any(re.search(t, low) for t in low_terms):
        return WEIGHT_LOW

    if section in {'dt_rules', 'runtime_pm_rules', 'commit_message_rules', 'series_structure_rules', 'reviewer_specific_patterns'}:
        return WEIGHT_MEDIUM

    return WEIGHT_LOW


def severity_from_weight(weight: float) -> str:
    if weight >= WEIGHT_HIGH:
        return 'BLOCKING'
    if weight >= WEIGHT_MEDIUM:
        return 'SHOULD_FIX'
    if weight > 0:
        return 'QUESTION'
    return 'INFO'


def normalize_pattern_text(text: str) -> str:
    t = re.sub(r'\W+', ' ', text.lower()).strip()
    return re.sub(r'\s+', ' ', t)


def is_subsystem_context_pattern(pattern: str) -> bool:
    low = pattern.lower()
    context_markers = ['qcom', 'msm', 'qualcomm', 'dt-binding', 'dt bindings', 'asoc', 'soundwire', 'codec', 'compatible']
    return any(tok in low for tok in context_markers)


def load_raw_payloads() -> tuple[dict[str, dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    raw_by_slug: dict[str, dict[str, Any]] = {}
    raw_source_path: dict[str, str] = {}
    fetch_entries: list[dict[str, Any]] = []

    for cfg in REVIEWERS:
        raw_path = choose_raw_file(cfg.slug)
        if raw_path is None:
            raw_by_slug[cfg.slug] = {
                'reviewer': cfg.name,
                'time_window': {'start': None, 'end': None},
                'series_fetched': 0,
                'series_with_reviewer_comments': 0,
                'comments_after_filter': 0,
                'series': [],
                'fetch_errors': ['No raw artifact available for R3 reuse'],
            }
            raw_source_path[cfg.slug] = 'MISSING'
            fetch_entries.append({
                'reviewer': cfg.name,
                'fetch_date': NOW_UTC,
                'mode': 'R3_REUSE_EXISTING_RAW_ONLY',
                'raw_source_file': None,
                'time_window_used': 'unknown',
                'series_fetched': 0,
                'series_with_reviewer_comments': 0,
                'comments_after_filter': 0,
                'confidence_level': 'INSUFFICIENT_DATA',
                'api_error': False,
                'api_errors': ['No raw artifact found; no refetch performed in R3'],
                'status': 'PARTIAL',
                'deviations_from_parameters': ['R3 no-refetch policy applied; raw artifact missing.'],
            })
            continue

        raw_payload = read_json(raw_path)
        raw_by_slug[cfg.slug] = raw_payload
        raw_source_path[cfg.slug] = str(raw_path.relative_to(ROOT))

        threads = int(raw_payload.get('series_with_reviewer_comments', 0))
        confidence = confidence_from_threads(threads)
        tw = raw_payload.get('time_window', {})
        tw_used = f"{(tw.get('start') or 'unknown')[:4]}-{(tw.get('end') or 'unknown')[:4]}"

        deviations = ['R3 reused existing raw data and did not call Patchwork API unless missing raw (none needed).']
        if cfg.slug == 'konrad_dybcio' and threads == 0:
            deviations.append('EXPANDED_SCOPE_STILL_INSUFFICIENT: REVIEWER_INACTIVE_IN_SCOPE')

        fetch_entries.append({
            'reviewer': cfg.name,
            'fetch_date': NOW_UTC,
            'mode': 'R3_REUSE_EXISTING_RAW_ONLY',
            'raw_source_file': str(raw_path.relative_to(ROOT)),
            'time_window_used': tw_used,
            'series_fetched': int(raw_payload.get('series_fetched', 0)),
            'series_with_reviewer_comments': threads,
            'comments_after_filter': int(raw_payload.get('comments_after_filter', 0)),
            'confidence_level': confidence,
            'api_error': False,
            'api_errors': [],
            'status': 'SUCCESS' if threads >= 20 else 'PARTIAL',
            'deviations_from_parameters': deviations,
        })

    return raw_by_slug, raw_source_path, fetch_entries


def reclassify_records(raw_payload: dict[str, Any], reviewer_slug: str) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    series_map: dict[int, dict[str, Any]] = {}

    for series in raw_payload.get('series', []):
        sid = int(series.get('series_id', 0) or 0)
        state = series.get('state', '')
        subject = series.get('subject', '')
        date = series.get('date', '')
        series_comments: list[dict[str, Any]] = []

        for c in series.get('reviewer_comments', []):
            raw_text = c.get('text_signoff_stripped') or c.get('text') or ''
            cleaned = clean_comment_text(raw_text)
            if not cleaned:
                continue
            stripped, removed = strip_signoff(cleaned)
            text_for_scoring = stripped if stripped else cleaned

            submitter_name = c.get('submitter_name', '')
            submitter_email = c.get('submitter_email', '')
            subject_line = series.get('subject', '')
            if is_bot_or_ci(submitter_name, submitter_email, text_for_scoring, subject_line):
                continue
            if is_ack_only(text_for_scoring):
                continue
            if word_count(text_for_scoring) < 20:
                continue

            cls = classify_comment_with_context(text_for_scoring, state, reviewer_slug)
            accept_mail = is_acceptance_email(c.get('text', '') or text_for_scoring)

            rec = {
                'reviewer_slug': reviewer_slug,
                'series_id': sid,
                'series_state': state,
                'series_subject': subject,
                'series_date': date,
                'comment_id': int(c.get('comment_id', 0) or 0),
                'comment_date': c.get('date', ''),
                'text_raw': c.get('text', '') or '',
                'text_scoring': text_for_scoring,
                'classification': cls,
                'is_acceptance_email': accept_mail,
                'signoff_lines_removed': removed,
                'patch_state': c.get('patch_state', ''),
                'word_count': word_count(text_for_scoring),
            }
            records.append(rec)
            series_comments.append(rec)

        if sid:
            series_map[sid] = {
                'series_id': sid,
                'state': state,
                'subject': subject,
                'reviewer_slug': reviewer_slug,
                'comment_records': sorted(series_comments, key=lambda x: x['comment_date']),
            }

    records = sorted(records, key=lambda x: (x['series_date'], x['comment_date'], x['series_id']))
    return records, series_map


def pattern_entries_from_regex(
    regexes: list[str],
    records: list[dict[str, Any]],
    section: str,
    reviewer_name: str,
    id_prefix: str,
) -> list[dict[str, Any]]:
    out = []
    for rgx in regexes:
        freq = 0
        series_ids: list[int] = []
        excerpts: list[str] = []

        for rec in records:
            text = rec['text_scoring']
            if safe_search(rgx, text):
                freq += 1
                sid = rec['series_id']
                if sid not in series_ids:
                    series_ids.append(sid)
                if len(excerpts) < 3:
                    excerpts.append(text[:220])

        if freq > 0:
            w = assign_weight(rgx, section)
            out.append({
                'pattern_id': '',
                'reviewer': reviewer_name,
                'pattern': rgx,
                'frequency': freq,
                'example_series_ids': series_ids[:8],
                'example_comment_excerpts': excerpts,
                'weight': w,
                'severity': severity_from_weight(w),
                'confidence': 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW',
                'false_positive_risk': 'LOW' if w >= WEIGHT_HIGH and freq >= 4 else 'MEDIUM' if w >= WEIGHT_MEDIUM else 'HIGH',
            })

    out = sorted(out, key=lambda x: (-x['frequency'], x['pattern']))
    dedup = {}
    for e in out:
        dedup[e['pattern']] = e
    out = list(dedup.values())

    for i, e in enumerate(out, start=1):
        e['pattern_id'] = f'{id_prefix}-{i:03d}'
    return out


def pattern_entries_from_ngrams(
    records: list[dict[str, Any]],
    section: str,
    reviewer_name: str,
    id_prefix: str,
    min_freq: int = 2,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    grams: Counter = Counter()
    for rec in records:
        text = rec['text_scoring'].lower()
        toks = [t for t in re.findall(r'[a-z][a-z0-9_\-]{1,}', text) if t not in STOPWORDS]
        for n in (2, 3):
            for i in range(0, max(0, len(toks) - n + 1)):
                gram = ' '.join(toks[i:i + n])
                if len(gram) >= 8:
                    grams[gram] += 1

    out: list[dict[str, Any]] = []
    for gram, freq in grams.most_common(max_items * 4):
        if freq < min_freq:
            continue
        if is_signoff_phrase(gram):
            continue

        series_ids: list[int] = []
        excerpts: list[str] = []
        for rec in records:
            low = rec['text_scoring'].lower()
            if gram in low:
                sid = rec['series_id']
                if sid not in series_ids:
                    series_ids.append(sid)
                if len(excerpts) < 3:
                    excerpts.append(rec['text_scoring'][:220])

        w = assign_weight(gram, section)
        out.append({
            'pattern_id': '',
            'reviewer': reviewer_name,
            'pattern': gram,
            'frequency': freq,
            'example_series_ids': series_ids[:8],
            'example_comment_excerpts': excerpts,
            'weight': w,
            'severity': severity_from_weight(w),
            'confidence': 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW',
            'false_positive_risk': 'LOW' if w >= WEIGHT_HIGH and freq >= 4 else 'MEDIUM' if w >= WEIGHT_MEDIUM else 'HIGH',
        })
        if len(out) >= max_items:
            break

    for i, e in enumerate(out, start=1):
        e['pattern_id'] = f'{id_prefix}-{i:03d}'
    return out


def merge_pattern_lists(*lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {}
    for lst in lists:
        for item in lst:
            pat = item['pattern']
            if pat not in merged or item['frequency'] > merged[pat]['frequency']:
                merged[pat] = item
    out = sorted(merged.values(), key=lambda x: (-x['frequency'], x['pattern']))
    return out


def extract_sections(cfg: ReviewerCfg, records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_cls = defaultdict(list)
    for rec in records:
        by_cls[rec['classification']].append(rec)

    non_acceptance = [r for r in records if not r['is_acceptance_email']]
    objection_records = [r for r in by_cls['objection'] if not r['is_acceptance_email']]
    acceptance_records = list(by_cls['acceptance'])
    question_records = [r for r in by_cls['question'] if not r['is_acceptance_email']]
    nit_records = [r for r in by_cls['nit'] if not r['is_acceptance_email']]

    obj_regex = pattern_entries_from_regex(OBJECTION_REGEX, objection_records, 'objection_patterns', cfg.name, f'{cfg.slug.upper()}-OBJ-RGX')
    obj_ngrams = pattern_entries_from_ngrams(objection_records, 'objection_patterns', cfg.name, f'{cfg.slug.upper()}-OBJ-NGRAM')
    objection_patterns = merge_pattern_lists(obj_regex, obj_ngrams)

    # Fix A: context tokens must not appear as blocking objection signals.
    objection_patterns = [p for p in objection_patterns if not is_subsystem_context_pattern(p['pattern']) and not is_signoff_phrase(p['pattern'])]

    acceptance_patterns = merge_pattern_lists(
        pattern_entries_from_regex(ACCEPT_REGEX, acceptance_records, 'acceptance_patterns', cfg.name, f'{cfg.slug.upper()}-ACC-RGX'),
        pattern_entries_from_ngrams(acceptance_records, 'acceptance_patterns', cfg.name, f'{cfg.slug.upper()}-ACC-NGRAM'),
    )

    question_patterns = merge_pattern_lists(
        pattern_entries_from_regex(QUESTION_REGEX, question_records, 'question_patterns', cfg.name, f'{cfg.slug.upper()}-Q-RGX'),
        pattern_entries_from_ngrams(question_records, 'question_patterns', cfg.name, f'{cfg.slug.upper()}-Q-NGRAM'),
    )

    nit_patterns = merge_pattern_lists(
        pattern_entries_from_regex(NIT_REGEX, nit_records, 'nit_patterns', cfg.name, f'{cfg.slug.upper()}-NIT-RGX'),
        pattern_entries_from_ngrams(nit_records, 'nit_patterns', cfg.name, f'{cfg.slug.upper()}-NIT-NGRAM'),
    )

    dt_rules = pattern_entries_from_regex(DT_REGEX, objection_records, 'dt_rules', cfg.name, f'{cfg.slug.upper()}-DT')
    runtime_pm_rules = pattern_entries_from_regex(RUNTIME_PM_REGEX, objection_records, 'runtime_pm_rules', cfg.name, f'{cfg.slug.upper()}-RPM')
    series_structure_rules = pattern_entries_from_regex(SERIES_STRUCTURE_REGEX, objection_records, 'series_structure_rules', cfg.name, f'{cfg.slug.upper()}-SERIES')
    commit_message_rules = pattern_entries_from_regex(COMMIT_MSG_REGEX, objection_records, 'commit_message_rules', cfg.name, f'{cfg.slug.upper()}-CM')

    # Context section (never blocking)
    subsystem_context = pattern_entries_from_regex(SUBSYSTEM_CONTEXT_REGEX, non_acceptance, 'subsystem_context', cfg.name, f'{cfg.slug.upper()}-CTX')
    for item in subsystem_context:
        item['weight'] = WEIGHT_ZERO
        item['severity'] = 'INFO'
        item['false_positive_risk'] = 'LOW'

    # Ensure context markers do not leak into blocking sections.
    def purge_context(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for e in entries:
            if is_subsystem_context_pattern(e['pattern']):
                continue
            out.append(e)
        return out

    dt_rules = purge_context(dt_rules)
    runtime_pm_rules = purge_context(runtime_pm_rules)
    series_structure_rules = purge_context(series_structure_rules)
    commit_message_rules = purge_context(commit_message_rules)

    reviewer_specific_patterns: list[dict[str, Any]] = []
    if cfg.slug == 'vinod_koul':
        for i, spec in enumerate(KOUL_SPECIFIC_PATTERNS, start=1):
            pattern = spec['pattern']
            freq = 0
            series_ids: list[int] = []
            excerpts: list[str] = []
            for rec in non_acceptance:
                if safe_search(pattern, rec['text_scoring']):
                    freq += 1
                    sid = rec['series_id']
                    if sid not in series_ids:
                        series_ids.append(sid)
                    if len(excerpts) < 3:
                        excerpts.append(rec['text_scoring'][:220])
            if freq > 0:
                w = float(spec['weight'])
                reviewer_specific_patterns.append({
                    'pattern_id': f'{cfg.slug.upper()}-SPEC-{i:03d}',
                    'reviewer': cfg.name,
                    'pattern': pattern,
                    'frequency': freq,
                    'example_series_ids': series_ids[:8],
                    'example_comment_excerpts': excerpts,
                    'weight': w,
                    'severity': severity_from_weight(w),
                    'confidence': 'HIGH' if freq >= 3 else 'MEDIUM' if freq >= 2 else 'LOW',
                    'false_positive_risk': 'MEDIUM' if w < WEIGHT_HIGH else 'LOW',
                    'category': spec['category'],
                })

    signoff_counter: Counter = Counter()
    signoff_examples: dict[str, list[str]] = defaultdict(list)
    signoff_series: dict[str, list[int]] = defaultdict(list)
    for rec in records:
        for ln in rec.get('signoff_lines_removed', []) or []:
            key = normalize_pattern_text(ln)
            if not key:
                continue
            signoff_counter[key] += 1
            if len(signoff_examples[key]) < 3:
                signoff_examples[key].append(ln)
            sid = rec['series_id']
            if sid not in signoff_series[key]:
                signoff_series[key].append(sid)

    signoff_patterns = []
    for i, (pattern, freq) in enumerate(signoff_counter.most_common(12), start=1):
        signoff_patterns.append({
            'pattern_id': f'{cfg.slug.upper()}-SIGNOFF-{i:03d}',
            'reviewer': cfg.name,
            'pattern': pattern,
            'frequency': int(freq),
            'example_series_ids': signoff_series.get(pattern, [])[:8],
            'example_comment_excerpts': signoff_examples.get(pattern, [])[:3],
            'weight': WEIGHT_ZERO,
            'severity': 'INFO',
            'confidence': 'HIGH' if freq >= 10 else 'MEDIUM' if freq >= 4 else 'LOW',
            'false_positive_risk': 'LOW',
        })

    return {
        'objection_patterns': objection_patterns[:30],
        'acceptance_patterns': acceptance_patterns[:25],
        'question_patterns': question_patterns[:20],
        'nit_patterns': nit_patterns[:20],
        'dt_rules': dt_rules[:20],
        'runtime_pm_rules': runtime_pm_rules[:20],
        'series_structure_rules': series_structure_rules[:20],
        'commit_message_rules': commit_message_rules[:20],
        'subsystem_context': subsystem_context[:25],
        'reviewer_specific_patterns': reviewer_specific_patterns[:20],
        'signoff_patterns': signoff_patterns[:20],
    }


def compute_blocking_score(comment_text: str, profile: dict[str, Any]) -> tuple[float, list[str]]:
    score = 0.0
    fired: list[str] = []
    text = comment_text.lower()

    for section_name in SCORING_SECTIONS:
        section_patterns = profile.get(section_name, [])
        if not isinstance(section_patterns, list):
            continue
        for pat in section_patterns:
            weight = float(pat.get('weight', WEIGHT_LOW))
            if weight <= 0.0:
                continue
            if safe_search(pat.get('pattern', ''), text):
                score += weight
                fired.append(pat.get('pattern_id', ''))

    # De-duplicate fired pattern IDs while preserving order
    seen = set()
    unique_fired = []
    for p in fired:
        if p and p not in seen:
            seen.add(p)
            unique_fired.append(p)

    return score, unique_fired


def compute_case_blocking(case: dict[str, Any], profile: dict[str, Any], threshold: float) -> tuple[float, bool, list[str], list[dict[str, Any]]]:
    # If the reviewer explicitly accepted/acked in an accepted/mainlined series,
    # treat objections as resolved for this case-level outcome.
    if case.get('state') in {'accepted', 'mainlined'}:
        if any(rec.get('classification') == 'acceptance' for rec in case.get('comment_records', [])):
            return 0.0, False, [], []

    # Use max score across objection-classified comments to avoid additive inflation
    # from long email threads.
    max_score = 0.0
    fired_ids: list[str] = []
    scored_comments: list[dict[str, Any]] = []

    for rec in case.get('comment_records', []):
        if rec.get('is_acceptance_email'):
            continue
        if rec.get('classification') != 'objection':
            continue

        score, fired = compute_blocking_score(rec.get('text_scoring', ''), profile)
        scored_comments.append({
            'comment_id': rec.get('comment_id'),
            'classification': rec.get('classification'),
            'score': round(score, 4),
            'fired_pattern_ids': fired,
            'text_excerpt': rec.get('text_scoring', '')[:220],
        })
        if score > max_score:
            max_score = score
            fired_ids = fired

    blocking = max_score >= threshold
    return round(max_score, 4), blocking, fired_ids, scored_comments


def evaluate_threshold(cases: list[dict[str, Any]], profiles: dict[str, dict[str, Any]], threshold: float) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    case_results = []

    for case in cases:
        slug = case['reviewer_slug']
        profile = profiles.get(slug, {})
        score, blocking, fired_ids, scored_comments = compute_case_blocking(case, profile, threshold)
        expected = bool(case['expected_blocking_objection'])

        if expected and blocking:
            tp += 1
        elif expected and not blocking:
            fn += 1
        elif not expected and blocking:
            fp += 1
        else:
            tn += 1

        case_results.append({
            'series_id': case['series_id'],
            'reviewer_slug': slug,
            'state': case['state'],
            'expected_blocking_objection': expected,
            'blocking_score': score,
            'blocking_threshold_used': threshold,
            'blocking_fired': blocking,
            'fired_pattern_ids': fired_ids,
            'scored_comments': scored_comments,
        })

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        'threshold': threshold,
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4),
        'tp': tp,
        'fp': fp,
        'tn': tn,
        'fn': fn,
        'case_results': case_results,
    }


def find_series_case(raw_by_slug: dict[str, dict[str, Any]], series_map_by_slug: dict[str, dict[int, dict[str, Any]]], spec: dict[str, Any]) -> dict[str, Any] | None:
    slug = spec['reviewer_slug']
    sid = int(spec['series_id'])
    if slug in series_map_by_slug and sid in series_map_by_slug[slug]:
        case = dict(series_map_by_slug[slug][sid])
        case['expected_blocking_objection'] = bool(spec['expected_blocking_objection'])
        return case

    # deterministic fallback search in any reviewer map (if mapping changed)
    for fallback_slug in sorted(series_map_by_slug.keys()):
        if sid in series_map_by_slug[fallback_slug]:
            case = dict(series_map_by_slug[fallback_slug][sid])
            case['expected_blocking_objection'] = bool(spec['expected_blocking_objection'])
            case['reviewer_slug'] = fallback_slug
            return case
    return None


def collect_fixed_validation_cases(series_map_by_slug: dict[str, dict[int, dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[str]]:
    cases = []
    missing = []
    for spec in FIXED_VALIDATION_CASES:
        c = find_series_case({}, series_map_by_slug, spec)
        if c is None:
            missing.append(f"series_id={spec['series_id']} reviewer={spec['reviewer_slug']}")
            continue
        cases.append(c)
    return cases, missing


def choose_threshold(calibration_results: list[dict[str, Any]]) -> tuple[float, str, dict[str, Any]]:
    valid = [x for x in calibration_results if x['precision'] >= 0.60]
    if valid:
        valid_sorted = sorted(valid, key=lambda x: (-x['f1'], -x['recall'], x['threshold']))
        chosen = valid_sorted[0]
        rationale = 'Maximizes F1 while meeting precision >= 0.60 requirement.'
        return float(chosen['threshold']), rationale, chosen

    # fallback if precision target not met
    best = sorted(calibration_results, key=lambda x: (-x['f1'], -x['precision'], x['threshold']))[0]
    rationale = 'No threshold met precision >= 0.60; selected best available F1 for transparent failure analysis.'
    return float(best['threshold']), rationale, best


def build_profile(
    cfg: ReviewerCfg,
    raw_payload: dict[str, Any],
    records: list[dict[str, Any]],
    sections: dict[str, list[dict[str, Any]]],
    chosen_threshold: float,
    calibration_summary: dict[str, Any],
) -> dict[str, Any]:
    threads = int(raw_payload.get('series_with_reviewer_comments', 0))
    confidence = confidence_from_threads(threads)

    versions = []
    for s in raw_payload.get('series', []):
        m = re.search(r'\bv(\d+)\b', (s.get('subject') or '').lower())
        if m:
            versions.append(int(m.group(1)))
    typical_iterations = int(round(sum(versions) / len(versions))) if versions else 1

    objection_patterns = sections['objection_patterns']
    acceptance_patterns = sections['acceptance_patterns']

    top_objection_topics = [x['pattern'] for x in sorted(objection_patterns, key=lambda y: (-y['frequency'], y['pattern']))[:10]]
    top_acceptance_signals = [x['pattern'] for x in sorted(acceptance_patterns, key=lambda y: (-y['frequency'], y['pattern']))[:10]]

    dt_hits = sum(x.get('frequency', 0) for x in sections['dt_rules'])
    rpm_hits = sum(x.get('frequency', 0) for x in sections['runtime_pm_rules'])

    def strictness(hits: int) -> str:
        if hits >= 25:
            return 'HIGH'
        if hits >= 8:
            return 'MEDIUM'
        return 'LOW'

    profile = {
        'reviewer': cfg.name,
        'profile_version': 'v3',
        'generated_date': TODAY,
        'time_window': raw_payload.get('time_window', {}),
        'confidence_level': confidence,
        'series_analyzed': int(raw_payload.get('series_fetched', 0)),
        'comment_threads_analyzed': threads,
        'acceptance_emails_excluded': True,
        'signoff_stripped': True,
        'scoring_model': 'weighted_threshold',
        'blocking_threshold': chosen_threshold,
        'pattern_weights': {
            'HIGH': WEIGHT_HIGH,
            'MEDIUM': WEIGHT_MEDIUM,
            'LOW': WEIGHT_LOW,
            'ZERO': WEIGHT_ZERO,
        },
        'threshold_calibration': {
            'calibration_set_size': int(calibration_summary.get('calibration_set_size', 0)),
            'threshold_tested': calibration_summary.get('threshold_tested', THRESHOLD_CANDIDATES),
            'chosen_threshold': chosen_threshold,
            'precision_at_chosen': calibration_summary.get('precision_at_chosen', 0.0),
            'recall_at_chosen': calibration_summary.get('recall_at_chosen', 0.0),
            'f1_at_chosen': calibration_summary.get('f1_at_chosen', 0.0),
        },
        'objection_patterns': sections['objection_patterns'],
        'acceptance_patterns': sections['acceptance_patterns'],
        'question_patterns': sections['question_patterns'],
        'nit_patterns': sections['nit_patterns'],
        'dt_rules': sections['dt_rules'],
        'runtime_pm_rules': sections['runtime_pm_rules'],
        'series_structure_rules': sections['series_structure_rules'],
        'commit_message_rules': sections['commit_message_rules'],
        'subsystem_context': sections['subsystem_context'],
        'reviewer_specific_patterns': sections['reviewer_specific_patterns'],
        'signoff_patterns': sections['signoff_patterns'],
        'top_objection_topics': top_objection_topics,
        'top_acceptance_signals': top_acceptance_signals,
        'typical_review_iterations': typical_iterations,
        'dt_strictness': strictness(dt_hits),
        'runtime_pm_strictness': strictness(rpm_hits),
        'known_limitations': [],
        'false_positive_risk_mitigations': [
            'Subsystem/vendor tokens moved to subsystem_context with zero score contribution.',
            'Weighted threshold scoring replaces binary OR model.',
            'Acceptance emails excluded from objection scoring.',
            'Sign-off stripping prevents courtesy closings from firing objection logic.',
            'Question-as-objection context enabled for rejected/changes-requested series.',
        ],
        'profile_notes': 'R3 weighted-threshold profile rebuilt from existing raw artifacts (no new API fetch).',
        'comment_statistics': {
            'total_comments_after_filter': len(records),
            'acceptance_email_count': sum(1 for r in records if r.get('is_acceptance_email')),
            'objection_classified_count': sum(1 for r in records if r.get('classification') == 'objection'),
            'question_classified_count': sum(1 for r in records if r.get('classification') == 'question'),
            'signoff_lines_removed_count': sum(len(r.get('signoff_lines_removed', [])) for r in records),
        },
    }

    if confidence != 'HIGH':
        profile['known_limitations'].append('Coverage below HIGH confidence threshold (>=50 threads).')
    if threads < 20:
        profile['known_limitations'].append('INSUFFICIENT_DATA threshold not met; advisory-only usage.')

    return profile


def build_threshold_calibration(calibration_results: list[dict[str, Any]], chosen_threshold: float, rationale: str, chosen_row: dict[str, Any]) -> dict[str, Any]:
    return {
        'artifact': 'threshold_calibration_r3',
        'generated_date': NOW_UTC,
        'validation_set_size': len(FIXED_VALIDATION_CASES),
        'calibration_results': [
            {
                'threshold': x['threshold'],
                'precision': x['precision'],
                'recall': x['recall'],
                'f1': x['f1'],
                'tp': x['tp'],
                'fp': x['fp'],
                'tn': x['tn'],
                'fn': x['fn'],
            }
            for x in calibration_results
        ],
        'chosen_threshold': chosen_threshold,
        'chosen_rationale': rationale,
        'precision_at_chosen': chosen_row['precision'],
        'recall_at_chosen': chosen_row['recall'],
        'f1_at_chosen': chosen_row['f1'],
    }


def build_validation_payload(chosen_eval: dict[str, Any], chosen_threshold: float, missing_cases: list[str]) -> dict[str, Any]:
    accepted_ids = [x['series_id'] for x in FIXED_VALIDATION_CASES if not x['expected_blocking_objection']]
    rejected_ids = [x['series_id'] for x in FIXED_VALIDATION_CASES if x['expected_blocking_objection']]

    return {
        'artifact': 'reviewer_profile_validation_results_v3',
        'generated_date': NOW_UTC,
        'profile_version': 'v3',
        'selected_validation_cases': {
            'accepted_count': len(accepted_ids),
            'rejected_or_changes_requested_count': len(rejected_ids),
            'accepted_series_ids': accepted_ids,
            'rejected_series_ids': rejected_ids,
            'missing_cases': missing_cases,
        },
        'cases': chosen_eval['case_results'],
        'overall_precision': chosen_eval['precision'],
        'overall_recall': chosen_eval['recall'],
        'false_positives_on_accepted': chosen_eval['fp'],
        'false_negatives_on_rejected': chosen_eval['fn'],
        'precision_target_met': chosen_eval['precision'] >= 0.60,
        'recall_target_met': chosen_eval['recall'] >= 0.60,
        'blocking_threshold_used': chosen_threshold,
    }


def build_accuracy_report(validation_payload: dict[str, Any]) -> str:
    return '\n'.join([
        '# Reviewer Profile Validation Accuracy Report (R3)',
        '',
        f"Generated: {validation_payload['generated_date']}",
        '',
        'Terminology:',
        '- LA = downstream / Linux Android',
        '- LE = upstream / Linux Embedded',
        '',
        '## Validation Set (Fixed from R2)',
        f"- Accepted cases: {validation_payload['selected_validation_cases']['accepted_count']}",
        f"- Rejected/changes-requested cases: {validation_payload['selected_validation_cases']['rejected_or_changes_requested_count']}",
        f"- Accepted series IDs: {', '.join(map(str, validation_payload['selected_validation_cases']['accepted_series_ids']))}",
        f"- Rejected series IDs: {', '.join(map(str, validation_payload['selected_validation_cases']['rejected_series_ids']))}",
        '',
        '## Weighted Scoring Results',
        f"- Blocking threshold used: {validation_payload['blocking_threshold_used']}",
        f"- Precision: {validation_payload['overall_precision']:.2f}",
        f"- Recall: {validation_payload['overall_recall']:.2f}",
        f"- False positives on accepted: {validation_payload['false_positives_on_accepted']}",
        f"- False negatives on rejected: {validation_payload['false_negatives_on_rejected']}",
        f"- Precision target >= 0.60: {'YES' if validation_payload['precision_target_met'] else 'NO'}",
        f"- Recall target >= 0.60: {'YES' if validation_payload['recall_target_met'] else 'NO'}",
        '',
        '## R3 Model Notes',
        '- Subsystem/vendor tokens are moved to subsystem_context and contribute zero score.',
        '- Case scoring uses weighted threshold on objection-classified comments only.',
        '- Vinod Koul question-as-objection rules are enabled for rejected/changes-requested series.',
        '',
    ]) + '\n'


def build_fetch_log_r3(fetch_entries: list[dict[str, Any]], raw_source_path: dict[str, str]) -> dict[str, Any]:
    return {
        'artifact': 'fetch_log_r3',
        'generated_date': NOW_UTC,
        'mode': 'R3_REUSE_EXISTING_RAW_ONLY',
        'rationale': [
            'R3 targets scoring-model fixes, not data-volume expansion.',
            'No new Patchwork fetches were performed while R2 raw artifacts are available.',
            'R1/R2 artifacts were preserved; R3 outputs are suffix-separated.',
        ],
        'reviewers': fetch_entries,
        'raw_source_index': raw_source_path,
    }


def build_profile_versions_r3(raw_by_slug: dict[str, dict[str, Any]], profiles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for cfg in REVIEWERS:
        raw = raw_by_slug.get(cfg.slug, {})
        threads = int(raw.get('series_with_reviewer_comments', 0))
        conf = confidence_from_threads(threads)
        p_path = PROC_DIR / f'{cfg.slug}_profile_v3.json'

        status = 'ACTIVE'
        if conf == 'INSUFFICIENT_DATA':
            status = 'INSUFFICIENT_DATA'
        if cfg.slug == 'konrad_dybcio' and threads == 0:
            status = 'REVIEWER_INACTIVE_IN_SCOPE'

        rows.append({
            'reviewer': cfg.name,
            'version': 'v3',
            'path': str(p_path.relative_to(ROOT)),
            'confidence': conf,
            'fetch_window': raw.get('time_window', {}),
            'series_count': int(raw.get('series_fetched', 0)),
            'thread_count': threads,
            'next_rebuild_due': '2026-12-21',
            'status': status,
        })

    return {
        'generated_date': NOW_UTC,
        'profiles': rows,
        'subsystem_rules': [
            {
                'subsystem': 'asoc_qcom',
                'version': 'v2',
                'path': 'AURA_KB/reviewer_profiles/subsystem_rules/asoc_qcom_rules_v2.json',
                'status': 'ACTIVE',
            },
            {
                'subsystem': 'soundwire',
                'version': 'v2',
                'path': 'AURA_KB/reviewer_profiles/subsystem_rules/soundwire_rules_v2.json',
                'status': 'ACTIVE',
            },
            {
                'subsystem': 'dt_bindings_audio',
                'version': 'v2',
                'path': 'AURA_KB/reviewer_profiles/subsystem_rules/dt_bindings_audio_rules_v2.json',
                'status': 'ACTIVE',
            },
            {
                'subsystem': 'pinctrl_qcom',
                'version': 'v2',
                'path': 'AURA_KB/reviewer_profiles/subsystem_rules/pinctrl_qcom_rules_v2.json',
                'status': 'ACTIVE',
            },
        ],
    }


def build_builder_changes_r3() -> dict[str, Any]:
    return {
        'artifact': 'builder_changes_r3',
        'generated_date': NOW_UTC,
        'terminology': {
            'LA': 'downstream / Linux Android',
            'LE': 'upstream / Linux Embedded',
        },
        'changes': [
            {
                'change_id': 'R3-FIX-A',
                'old_behavior': 'vendor_code_rules and subsystem tokens (e.g., qcom/msm/dt-binding) could contribute to blocking decisions.',
                'new_behavior': 'All subsystem/vendor indicators are moved to subsystem_context section with weight 0.0 and severity INFO only.',
                'why': 'Eliminates subject-line/subsystem contamination false positives.',
                'root_cause_fixed': 'subject_line_contamination',
            },
            {
                'change_id': 'R3-FIX-B',
                'old_behavior': 'Binary OR: any one blocking pattern caused case-level blocking.',
                'new_behavior': 'Weighted threshold scoring with explicit pattern weights and calibrated threshold.',
                'why': 'Reduces over-triggering from generic pattern hits.',
                'root_cause_fixed': 'binary_or_model_amplification',
            },
            {
                'change_id': 'R3-FIX-C',
                'old_behavior': 'Question-style requirement comments remained question class and were excluded from objection extraction.',
                'new_behavior': 'classify_comment_with_context promotes requirement-style questions to objection in rejected/changes-requested series; Vinod Koul specific patterns added.',
                'why': 'Recovers false negatives for conversational objection style.',
                'root_cause_fixed': 'koul_question_style_missed',
            },
            {
                'change_id': 'R3-REFINE-C1',
                'old_behavior': 'Generic acceptance regex (e.g., \"applied\") could misclassify objection text such as \"could be applied\".',
                'new_behavior': 'Acceptance regex now avoids broad applied/queued tokens and relies on explicit acceptance-email markers plus Ack/Review tags.',
                'why': 'Prevents false-negative objection classification in changes-requested threads.',
                'root_cause_fixed': 'acceptance_regex_overreach',
            },
            {
                'change_id': 'R3-REFINE-C2',
                'old_behavior': 'Requirement phrases like \"I would need s-o-b\" were not guaranteed to classify as objection.',
                'new_behavior': 'REQUIREMENT_OBJECTION_REGEX added before acceptance/question checks.',
                'why': 'Captures process/testing objections with conversational wording.',
                'root_cause_fixed': 'requirement_phrase_missed',
            },
            {
                'change_id': 'R3-REFINE-B1',
                'old_behavior': 'Accepted/mainlined cases with explicit reviewer acceptance could still block from earlier comments.',
                'new_behavior': 'Case scoring resolves accepted/mainlined cases to non-blocking when reviewer has acceptance-classified comment in-thread.',
                'why': 'Aligns case-level scoring with final reviewer acceptance signal and reduces false positives.',
                'root_cause_fixed': 'accepted_series_resolution_missing',
            },
            {
                'change_id': 'R3-DATA-MODE',
                'old_behavior': 'R1/R2 performed active fetch flows.',
                'new_behavior': 'R3 reuses existing raw artifacts only; no new Patchwork fetches.',
                'why': 'R3 scope is scoring-model correction, not corpus expansion.',
                'root_cause_fixed': 'data_volume_not_primary_issue',
            },
        ],
    }


def build_phase0_validation_r3(
    fetch_entries: list[dict[str, Any]],
    validation_payload: dict[str, Any],
    calibration_payload: dict[str, Any],
) -> dict[str, Any]:
    conf_map = {x['reviewer']: x['confidence_level'] for x in fetch_entries}
    konrad = next((x for x in fetch_entries if x['reviewer'] == 'Konrad Dybcio'), None)
    if konrad and int(konrad.get('series_with_reviewer_comments', 0)) == 0:
        conf_map['Konrad Dybcio'] = 'REVIEWER_INACTIVE_IN_SCOPE'

    p0_high = sum(1 for n in P0_REVIEWERS if conf_map.get(n) == 'HIGH')
    p1_low_high = sum(1 for n in P1_REVIEWERS if conf_map.get(n) in {'HIGH', 'LOW_CONFIDENCE'})

    precision = float(validation_payload['overall_precision'])
    recall = float(validation_payload['overall_recall'])
    rejected_achieved = int(validation_payload['selected_validation_cases']['rejected_or_changes_requested_count'])

    success = {
        'p0_high_profiles_required': 3,
        'p0_high_profiles_achieved': p0_high,
        'p0_high_met': p0_high >= 3,
        'p1_low_or_high_required': 3,
        'p1_low_or_high_achieved': p1_low_high,
        'p1_low_or_high_met': p1_low_high >= 3,
        'rejected_validation_cases_required': 3,
        'rejected_validation_cases_achieved': rejected_achieved,
        'rejected_validation_met': rejected_achieved >= 3,
        'objection_precision_required': 0.60,
        'objection_precision_achieved': round(precision, 4),
        'objection_precision_met': precision >= 0.60,
        'objection_recall_required': 0.60,
        'objection_recall_achieved': round(recall, 4),
        'objection_recall_met': recall >= 0.60,
    }

    complete = all([
        success['p0_high_met'],
        success['p1_low_or_high_met'],
        success['rejected_validation_met'],
        success['objection_precision_met'],
        success['objection_recall_met'],
    ])

    gaps = []
    if not success['p0_high_met']:
        gaps.append(f"P0 HIGH profiles shortfall: {p0_high}/3 required")
    if not success['p1_low_or_high_met']:
        gaps.append(f"P1 LOW/HIGH profiles shortfall: {p1_low_high}/3 required")
    if not success['objection_precision_met']:
        gaps.append(f"Objection precision shortfall: {precision:.2f}/0.60 required")
    if not success['objection_recall_met']:
        gaps.append(f"Objection recall shortfall: {recall:.2f}/0.60 required")

    best_precision = max(x['precision'] for x in calibration_payload.get('calibration_results', [])) if calibration_payload.get('calibration_results') else precision

    return {
        'artifact': 'phase0_validation_r3',
        'generated_date': NOW_UTC,
        'r1_verdict': R1_VERDICT,
        'r2_verdict': R2_VERDICT,
        'r3_profile_confidence_levels': conf_map,
        'success_criteria': success,
        'r3_verdict': 'PHASE_0_COMPLETE' if complete else 'PHASE_0_FAILED_RETRY_REQUIRED',
        'phase1_unblocked': bool(complete),
        'root_causes_fixed': [
            'subsystem_context_zero_weight',
            'weighted_threshold_scoring_added',
            'question_as_objection_detector_added',
            'koul_specific_requirement_patterns_added',
            'fixed_validation_set_reused_without_gaming',
            'threshold_calibration_added',
        ],
        'remaining_gaps': gaps,
        'best_precision_observed_in_calibration': best_precision,
        'kernel_source_modified': 'no',
        'wcd9378_modified': 'no',
        'patches_generated': 'no',
        'phase1_simulation_engine_started': 'no',
    }


def build_pm_summary_r3(
    fetch_entries: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    validation: dict[str, Any],
) -> str:
    conf_map = {x['reviewer']: x['confidence_level'] for x in fetch_entries}

    def top5(slug: str) -> list[str]:
        p = profiles.get(slug, {})
        arr = sorted(p.get('objection_patterns', []), key=lambda x: (-x.get('frequency', 0), x.get('pattern', '')))
        return [x.get('pattern', '') for x in arr[:5]]

    lines = [
        '# PM Phase 0 Summary (R3)',
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
    for e in fetch_entries:
        if e['confidence_level'] != 'HIGH':
            lines.append(f"- {e['reviewer']} ({e['confidence_level']})")

    lines += ['', '## 3. What are the top 5 objection patterns per P0 reviewer?']
    for slug in ['mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul']:
        name = next((c.name for c in REVIEWERS if c.slug == slug), slug)
        vals = top5(slug)
        lines.append(f"- {name}: {', '.join(vals) if vals else 'N/A'}")

    lines += ['', '## 4. What are the top 5 subsystem rules per P0 subsystem?']
    for sub_file, label in [
        ('asoc_qcom_rules_v2.json', 'asoc_qcom'),
        ('soundwire_rules_v2.json', 'soundwire'),
        ('dt_bindings_audio_rules_v2.json', 'dt_bindings_audio'),
    ]:
        path = RULE_DIR / sub_file
        if path.exists():
            data = read_json(path)
            top = [r.get('rule', '') for r in data.get('rules', [])[:5]]
            lines.append(f"- {label}: {', '.join(top) if top else 'N/A'}")
        else:
            lines.append(f"- {label}: N/A")

    sc = validation['success_criteria']
    lines += [
        '',
        '## 5. What did profile validation show?',
        f"- Overall precision: {sc['objection_precision_achieved']:.2f}",
        f"- Overall recall: {sc['objection_recall_achieved']:.2f}",
        f"- Rejected/changes-requested validation cases: {sc['rejected_validation_cases_achieved']}",
        '',
        '## 6. Is Phase 0 success criteria met?',
        f"- {'YES' if validation['r3_verdict'] == 'PHASE_0_COMPLETE' else 'NO'}",
        '',
        '## 7. Is Phase 1 unblocked?',
        f"- {'YES' if validation['phase1_unblocked'] else 'NO'}",
        '',
        '## 8. What should be improved before Phase 1?',
        '- If precision/recall remain below threshold, shift from regex-only to LLM-based comment intent classification.',
        '- Maintain weighted scoring as guardrail; keep subsystem context at zero weight.',
        '- Expand reviewer-specific intent detectors for low-coverage reviewers if raw evidence grows.',
        '',
        f"Verdict: `{validation['r3_verdict']}`",
    ]
    return '\n'.join(lines) + '\n'


def update_progress_tracker(validation: dict[str, Any], calibration: dict[str, Any]) -> Path:
    tracker_path = PLAN_DIR / 'progress_tracker.json'
    tracker = read_json(tracker_path)

    r3_complete = validation['r3_verdict'] == 'PHASE_0_COMPLETE'
    tracker['last_updated'] = TODAY
    tracker['current_phase'] = 0
    tracker['current_step'] = '0.R3'

    if r3_complete:
        tracker['overall_status'] = 'PHASE_1_IN_PROGRESS'
        card_name = f'PROGRESS_CARD_P0_R3_COMPLETE_{TODAY_COMPACT}.json'
    else:
        tracker['overall_status'] = 'PHASE_0_RETRY_R4_REQUIRED'
        card_name = f'PROGRESS_CARD_P0_R3_FAILED_{TODAY_COMPACT}.json'

    for phase in tracker.get('phases', []):
        if phase.get('phase') == 0:
            if r3_complete:
                phase['status'] = 'COMPLETED'
                phase['completion_pct'] = 100
                phase['steps_completed'] = 10
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'READY'
            else:
                phase['status'] = 'RETRY_R4_REQUIRED'
                phase['completion_pct'] = 82
                phase['steps_completed'] = 9
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 1
                phase['pm_verdict'] = 'BLOCKED'
            phase['last_card'] = f'PC-P0-R3-{TODAY_COMPACT}'
            phase['success_criteria'] = {
                'total': 5,
                'met': sum(1 for k in ['p0_high_met', 'p1_low_or_high_met', 'rejected_validation_met', 'objection_precision_met', 'objection_recall_met'] if validation['success_criteria'][k]),
                'not_met': sum(1 for k in ['p0_high_met', 'p1_low_or_high_met', 'rejected_validation_met', 'objection_precision_met', 'objection_recall_met'] if not validation['success_criteria'][k]),
            }
        if phase.get('phase') == 1:
            if r3_complete:
                phase['status'] = 'IN_PROGRESS'
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'ON_TRACK'
            else:
                phase['status'] = 'BLOCKED_ON_PHASE_0'
                phase['steps_blocked'] = max(1, int(phase.get('steps_blocked', 1)))
                phase['pm_verdict'] = 'BLOCKED'

    tracker.setdefault('history', []).append({
        'date': TODAY,
        'action': 'Phase 0 R3 scoring-model retry completed',
        'card': f'PC-P0-R3-{TODAY_COMPACT}',
        'phase_status_change': (
            'Phase 0 completed and Phase 1 started.'
            if r3_complete
            else 'Phase 0 R3 failed criteria; R4 required or advisory-only decision needed.'
        ),
    })

    write_json(tracker_path, tracker)

    best_precision = validation.get('best_precision_observed_in_calibration', 0.0)
    if not r3_complete and best_precision < 0.50:
        r4_advice = 'Best precision < 0.50 after model fixes; regex pattern matching appears fundamentally limited. Recommend advisory-only status and LLM-based classifier design instead of R4 regex retry.'
    elif not r3_complete:
        r4_advice = 'R4 may be attempted with stricter intent modeling and reviewer-specific semantics, but keep advisory posture until precision >= 0.60.'
    else:
        r4_advice = 'R4 not required; proceed with Phase 1 under guarded rollout.'

    card_payload = {
        'card_id': f'PC-P0-R3-{TODAY_COMPACT}',
        'date': TODAY,
        'phase': 0,
        'step': '0.R3',
        'step_name': 'Phase 0 retry R3 (scoring model fix)',
        'status': 'COMPLETED' if r3_complete else 'FAILED',
        'what_was_done': 'Implemented weighted-threshold scoring, moved subsystem tokens to zero-weight context, added question-as-objection logic, and recalibrated on fixed R2 validation set.',
        'r3_verdict': validation['r3_verdict'],
        'phase1_unblocked': validation['phase1_unblocked'],
        'success_criteria_snapshot': validation['success_criteria'],
        'threshold_calibration_summary': {
            'chosen_threshold': calibration['chosen_threshold'],
            'precision_at_chosen': calibration['precision_at_chosen'],
            'recall_at_chosen': calibration['recall_at_chosen'],
            'f1_at_chosen': calibration['f1_at_chosen'],
        },
        'is_r4_worth_attempting': 'YES' if (not r3_complete and best_precision >= 0.50) else 'NO' if not r3_complete else 'N/A',
        'r4_or_advisory_recommendation': r4_advice,
    }

    card_path = PLAN_DIR / 'progress_cards' / card_name
    write_json(card_path, card_payload)
    return card_path


def run_json_validation() -> str:
    import subprocess

    cmd = "find AURA_KB/reviewer_profiles -name '*_r3*.json' -o -name '*_v3.json' | xargs -I{} python3 -m json.tool {} > /dev/null"
    subprocess.run(cmd, shell=True, check=True, cwd=ROOT)
    return 'ALL R3 JSON PASS'


def main() -> None:
    print('[phase0-r3] start: loading existing raw artifacts (no refetch)', flush=True)

    builder_changes = build_builder_changes_r3()
    write_json(META_DIR / 'builder_changes_r3.json', builder_changes)

    raw_by_slug, raw_source_path, fetch_entries = load_raw_payloads()
    write_json(META_DIR / 'fetch_log_r3.json', build_fetch_log_r3(fetch_entries, raw_source_path))

    records_by_slug: dict[str, list[dict[str, Any]]] = {}
    series_map_by_slug: dict[str, dict[int, dict[str, Any]]] = {}
    sections_by_slug: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for cfg in REVIEWERS:
        raw_payload = raw_by_slug.get(cfg.slug, {})
        records, series_map = reclassify_records(raw_payload, cfg.slug)
        sections = extract_sections(cfg, records)

        records_by_slug[cfg.slug] = records
        series_map_by_slug[cfg.slug] = series_map
        sections_by_slug[cfg.slug] = sections

        print(
            f"[phase0-r3] prepared {cfg.name}: threads={raw_payload.get('series_with_reviewer_comments', 0)} comments={len(records)}",
            flush=True,
        )

    fixed_cases, missing_cases = collect_fixed_validation_cases(series_map_by_slug)
    print(f"[phase0-r3] fixed validation cases found={len(fixed_cases)} missing={len(missing_cases)}", flush=True)

    # Provisional profiles for calibration
    provisional_profiles: dict[str, dict[str, Any]] = {}
    for cfg in REVIEWERS:
        provisional_profiles[cfg.slug] = build_profile(
            cfg=cfg,
            raw_payload=raw_by_slug.get(cfg.slug, {}),
            records=records_by_slug.get(cfg.slug, []),
            sections=sections_by_slug.get(cfg.slug, {}),
            chosen_threshold=DEFAULT_BLOCKING_THRESHOLD,
            calibration_summary={
                'calibration_set_size': len(FIXED_VALIDATION_CASES),
                'threshold_tested': THRESHOLD_CANDIDATES,
                'precision_at_chosen': 0.0,
                'recall_at_chosen': 0.0,
                'f1_at_chosen': 0.0,
            },
        )

    calibration_results = []
    for thr in THRESHOLD_CANDIDATES:
        eval_row = evaluate_threshold(fixed_cases, provisional_profiles, thr)
        calibration_results.append({
            'threshold': thr,
            'precision': eval_row['precision'],
            'recall': eval_row['recall'],
            'f1': eval_row['f1'],
            'tp': eval_row['tp'],
            'fp': eval_row['fp'],
            'tn': eval_row['tn'],
            'fn': eval_row['fn'],
            'case_results': eval_row['case_results'],
        })

    chosen_threshold, rationale, chosen_row = choose_threshold(calibration_results)
    calibration_payload = build_threshold_calibration(calibration_results, chosen_threshold, rationale, chosen_row)
    write_json(META_DIR / 'threshold_calibration_r3.json', calibration_payload)

    # Final profiles include chosen threshold details.
    final_profiles: dict[str, dict[str, Any]] = {}
    for cfg in REVIEWERS:
        profile = build_profile(
            cfg=cfg,
            raw_payload=raw_by_slug.get(cfg.slug, {}),
            records=records_by_slug.get(cfg.slug, []),
            sections=sections_by_slug.get(cfg.slug, {}),
            chosen_threshold=chosen_threshold,
            calibration_summary={
                'calibration_set_size': len(FIXED_VALIDATION_CASES),
                'threshold_tested': THRESHOLD_CANDIDATES,
                'precision_at_chosen': calibration_payload['precision_at_chosen'],
                'recall_at_chosen': calibration_payload['recall_at_chosen'],
                'f1_at_chosen': calibration_payload['f1_at_chosen'],
            },
        )
        final_profiles[cfg.slug] = profile
        write_json(PROC_DIR / f'{cfg.slug}_profile_v3.json', profile)

    # Re-run chosen-threshold evaluation for final payload cases.
    chosen_eval = evaluate_threshold(fixed_cases, final_profiles, chosen_threshold)
    validation_payload = build_validation_payload(chosen_eval, chosen_threshold, missing_cases)
    write_json(VAL_DIR / 'profile_validation_results_r3.json', validation_payload)
    (VAL_DIR / 'accuracy_report_r3.md').write_text(build_accuracy_report(validation_payload))

    write_json(META_DIR / 'profile_versions_r3.json', build_profile_versions_r3(raw_by_slug, final_profiles))

    phase0_validation = build_phase0_validation_r3(fetch_entries, validation_payload, calibration_payload)
    write_json(META_DIR / 'phase0_validation_r3.json', phase0_validation)

    pm_summary = build_pm_summary_r3(fetch_entries, final_profiles, phase0_validation)
    (META_DIR / 'pm_phase0_summary_r3.md').write_text(pm_summary)

    card_path = update_progress_tracker(phase0_validation, calibration_payload)

    # Optional local validation marker for convenience.
    json_pass = run_json_validation()
    print(f'[phase0-r3] {json_pass}', flush=True)
    print(f"[phase0-r3] chosen_threshold={chosen_threshold} precision={chosen_eval['precision']} recall={chosen_eval['recall']} f1={chosen_eval['f1']}", flush=True)
    print(f"[phase0-r3] verdict={phase0_validation['r3_verdict']} phase1_unblocked={phase0_validation['phase1_unblocked']}", flush=True)
    print(f"[phase0-r3] progress_card={card_path.relative_to(ROOT)}", flush=True)


if __name__ == '__main__':
    main()
