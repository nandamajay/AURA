#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import runpy
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path('/local/mnt/workspace/AURA_V1_upstream')
BASE = ROOT / 'AURA_KB/reviewer_profiles'
RAW_DIR = BASE / 'raw'
PROC_DIR = BASE / 'processed'
VAL_DIR = BASE / 'validation'
META_DIR = BASE / 'metadata'
PLAN_DIR = ROOT / 'AURA_KB/platform_tools/upstream_reviewer_sim_01/plan'

for d in [RAW_DIR, PROC_DIR, VAL_DIR, META_DIR]:
    d.mkdir(parents=True, exist_ok=True)

NOW_UTC = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
TODAY = str(date.today())
TODAY_COMPACT = TODAY.replace('-', '')

LORE_BASE = 'https://lore.kernel.org'
HEADERS = {'User-Agent': 'git/2.39.0'}
PAGE_SIZE = 200
RATE_LIMIT_S = 0.5
START_DATE = '2021-01-01'
END_DATE = '2025-12-31'
MAX_PER_REVIEWER_PER_LIST = 1000

# Reviewers explicitly requested for lore R4 data rebuild
LORE_REVIEWERS = [
    {
        'name': 'Pierre-Louis Bossart',
        'slug': 'pierre_louis_bossart',
        'priority': 'P0',
        'queries': [
            {'list': 'alsa-devel', 'q': 'f%3Abossart'},
            {'list': 'linux-arm-msm', 'q': 'f%3Abossart'},
        ],
        'max_messages': 800,
    },
    {
        'name': 'Vinod Koul',
        'slug': 'vinod_koul',
        'priority': 'P0',
        'queries': [
            {'list': 'alsa-devel', 'q': 'f%3Avkoul'},
            {'list': 'alsa-devel', 'q': 'f%3Avinod.koul'},
            {'list': 'linux-arm-msm', 'q': 'f%3Avkoul'},
        ],
        'max_messages': 800,
        'dedup_by_message_id': True,
    },
    {
        'name': 'Liam Girdwood',
        'slug': 'liam_girdwood',
        'priority': 'P1',
        'queries': [
            {'list': 'alsa-devel', 'q': 'f%3Algirdwood'},
            {'list': 'alsa-devel', 'q': 'f%3Aliam.girdwood'},
        ],
        'max_messages': 200,
        'accept_insufficient': True,
    },
    {
        'name': 'Rob Herring',
        'slug': 'rob_herring',
        'priority': 'P1',
        'queries': [
            {'list': 'alsa-devel', 'q': 'f%3Arobh%40kernel.org'},
            {'list': 'alsa-devel', 'q': 'f%3Arob.herring'},
            {'list': 'devicetree', 'q': 'f%3Arobh%40kernel.org'},
        ],
        'max_messages': 800,
        'dedup_by_message_id': True,
    },
]

REVIEWER_NAME_BY_SLUG = {
    'mark_brown': 'Mark Brown',
    'pierre_louis_bossart': 'Pierre-Louis Bossart',
    'krzysztof_kozlowski': 'Krzysztof Kozlowski',
    'vinod_koul': 'Vinod Koul',
    'liam_girdwood': 'Liam Girdwood',
    'bjorn_andersson': 'Bjorn Andersson',
    'linus_walleij': 'Linus Walleij',
    'rob_herring': 'Rob Herring',
    'konrad_dybcio': 'Konrad Dybcio',
}

ALL_SLUGS = [
    'mark_brown',
    'pierre_louis_bossart',
    'krzysztof_kozlowski',
    'vinod_koul',
    'liam_girdwood',
    'bjorn_andersson',
    'linus_walleij',
    'rob_herring',
    'konrad_dybcio',
]

P0_REVIEWERS = ['Mark Brown', 'Pierre-Louis Bossart', 'Krzysztof Kozlowski', 'Vinod Koul']
P1_REVIEWERS = ['Liam Girdwood', 'Bjorn Andersson', 'Linus Walleij', 'Rob Herring']

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


# Load R3 scoring model helpers to keep model unchanged.
R3 = runpy.run_path(str(META_DIR / 'phase0_builder.py'))
ReviewerCfg = R3['ReviewerCfg']


def unescape_html(text: str) -> str:
    return (
        (text or '')
        .replace('&amp;', '&')
        .replace('&lt;', '<')
        .replace('&gt;', '>')
        .replace('&quot;', '"')
        .replace('&#39;', "'")
        .replace('&nbsp;', ' ')
    )


def strip_html_and_quotes(html: str) -> str:
    text = re.sub(r'<[^>]+>', '', html or '')
    text = unescape_html(text)

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('>'):
            continue
        if re.match(r'^On .+ wrote:$', stripped):
            continue
        lines.append(stripped)

    return ' '.join(lines).strip()


def parse_atom_entries(xml_text: str) -> list[dict]:
    entries = []
    for raw in re.findall(r'<entry>(.*?)</entry>', xml_text, re.DOTALL):
        title_m = re.search(r'<title[^>]*>(.*?)</title>', raw, re.DOTALL)
        link_m = re.search(r'<link[^>]+href="([^"]+)"', raw)
        updated_m = re.search(r'<updated>(.*?)</updated>', raw)
        content_m = re.search(r'<content[^>]*>(.*?)</content>', raw, re.DOTALL)
        author_name_m = re.search(r'<author>.*?<name>(.*?)</name>.*?</author>', raw, re.DOTALL)
        author_email_m = re.search(r'<author>.*?<email>(.*?)</email>.*?</author>', raw, re.DOTALL)

        title = unescape_html(title_m.group(1).strip()) if title_m else ''
        link = link_m.group(1).strip() if link_m else ''
        updated = updated_m.group(1).strip() if updated_m else ''
        author_name = unescape_html(author_name_m.group(1).strip()) if author_name_m else ''
        author_email = author_email_m.group(1).strip() if author_email_m else ''

        body_html = content_m.group(1) if content_m else ''
        body_text = strip_html_and_quotes(body_html)

        msg_id = link.rstrip('/').split('/')[-1] if link else ''

        if not title:
            continue

        entries.append(
            {
                'message_id': msg_id,
                'title': title,
                'link': link,
                'date': updated,
                'author_name': author_name,
                'author_email': author_email,
                'is_reply': title.startswith('Re:'),
                'body': body_text,
                'word_count': len(body_text.split()),
            }
        )

    return entries


def fetch_lore_page(list_name: str, query: str, offset: int) -> list[dict]:
    url = f'{LORE_BASE}/{list_name}/?q={query}&x=A&o={offset}'
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=45) as resp:
        content = resp.read().decode('utf-8', errors='replace')
    time.sleep(RATE_LIMIT_S)
    return parse_atom_entries(content)


def within_range(date_iso: str, start: str, end: str) -> bool:
    d = (date_iso or '')[:10]
    return bool(d and start <= d <= end)


def sanitize_entry_for_r3(entry: dict, slug: str, synthetic_id: int) -> dict | None:
    text = entry.get('body', '')
    if not text:
        return None

    text_clean = R3['clean_comment_text'](text)
    text_scoring, removed = R3['strip_signoff'](text_clean)
    if not text_scoring:
        return None

    if R3['word_count'](text_scoring) < 20:
        return None

    if R3['is_bot_or_ci'](entry.get('author_name', ''), entry.get('author_email', ''), text_scoring, entry.get('title', '')):
        return None

    if R3['is_ack_only'](text_scoring):
        return None

    cls = R3['classify_comment_with_context'](text_scoring, 'unknown', slug)

    return {
        'reviewer_slug': slug,
        'series_id': synthetic_id,
        'series_state': 'unknown',
        'series_subject': entry.get('title', ''),
        'series_date': entry.get('date', ''),
        'comment_id': synthetic_id,
        'comment_date': entry.get('date', ''),
        'text_raw': entry.get('body', ''),
        'text_scoring': text_scoring,
        'classification': cls,
        'is_acceptance_email': R3['is_acceptance_email'](text_scoring),
        'signoff_lines_removed': removed,
        'patch_state': 'unknown',
        'word_count': R3['word_count'](text_scoring),
        'source': 'lore',
        'message_id': entry.get('message_id', ''),
        'link': entry.get('link', ''),
    }


def fetch_reviewer_lore(cfg: dict) -> dict:
    all_entries: list[dict] = []
    seen_ids: set[str] = set()
    per_list_counter: dict[str, int] = defaultdict_int()

    fetch_errors: list[str] = []

    for query_cfg in cfg['queries']:
        list_name = query_cfg['list']
        query = query_cfg['q']
        offset = 0

        while len(all_entries) < cfg['max_messages']:
            if per_list_counter[list_name] >= MAX_PER_REVIEWER_PER_LIST:
                break

            try:
                entries = fetch_lore_page(list_name, query, offset)
            except Exception as e:
                fetch_errors.append(f'fetch error list={list_name} q={query} o={offset}: {e}')
                break

            if not entries:
                break

            for e in entries:
                if per_list_counter[list_name] >= MAX_PER_REVIEWER_PER_LIST:
                    break

                per_list_counter[list_name] += 1

                mid = e.get('message_id') or f"{e.get('link', '')}-{e.get('date', '')}"
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)

                if not within_range(e.get('date', ''), START_DATE, END_DATE):
                    continue

                if not e.get('is_reply', False):
                    continue

                if int(e.get('word_count', 0)) < 20:
                    continue

                e['list'] = list_name
                e['query'] = query
                all_entries.append(e)

                if len(all_entries) >= cfg['max_messages']:
                    break

            if len(entries) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

    # deterministic order
    all_entries = sorted(all_entries, key=lambda x: (x.get('date', ''), x.get('message_id', '')))

    return {
        'reviewer': cfg['name'],
        'slug': cfg['slug'],
        'source': 'lore.kernel.org',
        'fetch_date': NOW_UTC,
        'time_window': {'start': START_DATE, 'end': END_DATE},
        'queries_run': cfg['queries'],
        'per_list_fetch_count': per_list_counter,
        'total_messages_fetched': len(all_entries),
        'messages': all_entries,
        'fetch_errors': fetch_errors,
    }


def confidence_from_threads(n: int) -> str:
    if n >= 50:
        return 'HIGH'
    if n >= 20:
        return 'LOW_CONFIDENCE'
    return 'INSUFFICIENT_DATA'


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n')


def choose_profile_v3(slug: str) -> Path | None:
    p = PROC_DIR / f'{slug}_profile_v3.json'
    return p if p.exists() else None


def choose_raw_for_seriesmap(slug: str) -> Path | None:
    candidates = [
        RAW_DIR / f'{slug}_raw_r2_2021_2025.json',
        RAW_DIR / f'{slug}_raw_r2_2023_2025.json',
        RAW_DIR / f'{slug}_raw_2023_2025.json',
    ]
    for c in candidates:
        if c.exists():
            return c
    all_candidates = sorted(RAW_DIR.glob(f'{slug}_raw*.json'))
    return all_candidates[-1] if all_candidates else None


def build_lore_records(lore_payload: dict) -> tuple[list[dict], dict[int, dict]]:
    slug = lore_payload['slug']
    records = []
    series_map = {}

    for idx, msg in enumerate(lore_payload.get('messages', []), start=1):
        rec = sanitize_entry_for_r3(msg, slug, 900000000 + idx)
        if rec is None:
            continue
        records.append(rec)

    records = sorted(records, key=lambda x: (x['series_date'], x['comment_date'], x['message_id']))

    for rec in records:
        sid = rec['series_id']
        series_map[sid] = {
            'series_id': sid,
            'state': 'unknown',
            'subject': rec['series_subject'],
            'reviewer_slug': rec['reviewer_slug'],
            'comment_records': [rec],
        }

    return records, series_map


def merge_sections(v3_profile: dict, lore_sections: dict[str, list[dict]]) -> dict[str, list[dict]]:
    sections = [
        'objection_patterns',
        'acceptance_patterns',
        'question_patterns',
        'nit_patterns',
        'dt_rules',
        'runtime_pm_rules',
        'series_structure_rules',
        'commit_message_rules',
        'subsystem_context',
        'reviewer_specific_patterns',
        'signoff_patterns',
    ]

    merged = {}
    for sec in sections:
        base = [x for x in v3_profile.get(sec, []) if isinstance(x, dict)]
        add = [x for x in lore_sections.get(sec, []) if isinstance(x, dict)]

        dedup = {}
        for item in base + add:
            key = item.get('pattern', '')
            if not key:
                continue
            if key not in dedup or int(item.get('frequency', 0)) > int(dedup[key].get('frequency', 0)):
                dedup[key] = item

        values = sorted(dedup.values(), key=lambda x: (-int(x.get('frequency', 0)), x.get('pattern', '')))

        if sec == 'subsystem_context':
            for x in values:
                x['weight'] = 0.0
                x['severity'] = 'INFO'

        merged[sec] = values[:40]

    return merged


def build_v4_profile_from_lore(slug: str, lore_payload: dict, v3_profile: dict, calibration: dict) -> dict:
    cfg = ReviewerCfg(name=v3_profile.get('reviewer', REVIEWER_NAME_BY_SLUG.get(slug, slug)), slug=slug, priority='P0')

    lore_records, _ = build_lore_records(lore_payload)
    lore_sections = R3['extract_sections'](cfg, lore_records)
    merged_sections = merge_sections(v3_profile, lore_sections)

    patchwork_threads = int(v3_profile.get('comment_threads_analyzed', 0))
    lore_threads = len(lore_records)
    total_threads = max(patchwork_threads, lore_threads)

    # Build with R3 builder to preserve scoring model semantics.
    raw_payload_stub = {
        'series_fetched': lore_payload.get('total_messages_fetched', 0),
        'series_with_reviewer_comments': total_threads,
        'time_window': {'start': START_DATE, 'end': END_DATE},
        'series': [],
    }

    profile = R3['build_profile'](
        cfg=cfg,
        raw_payload=raw_payload_stub,
        records=lore_records,
        sections=merged_sections,
        chosen_threshold=float(calibration['chosen_threshold']),
        calibration_summary={
            'calibration_set_size': 10,
            'threshold_tested': [2.0, 2.5, 3.0, 3.5, 4.0],
            'precision_at_chosen': float(calibration['precision_at_chosen']),
            'recall_at_chosen': float(calibration['recall_at_chosen']),
            'f1_at_chosen': float(calibration['f1_at_chosen']),
        },
    )

    profile['profile_version'] = 'v4'
    profile['data_source'] = 'lore.kernel.org'
    profile['patchwork_threads'] = patchwork_threads
    profile['lore_threads'] = lore_threads
    profile['total_qualifying_threads'] = total_threads
    profile['confidence_level'] = confidence_from_threads(total_threads)
    profile['lore_lists_queried'] = sorted({q['list'] for q in lore_payload.get('queries_run', [])})
    profile['series_analyzed'] = lore_payload.get('total_messages_fetched', 0)
    profile['comment_threads_analyzed'] = total_threads

    profile['known_limitations'] = list(profile.get('known_limitations', []))
    if lore_threads == 0:
        profile['known_limitations'].append('No qualifying lore review threads; profile remains patchwork-dominant.')

    return profile


def build_v4_wrapper_from_v3(slug: str, v3_profile: dict) -> dict:
    patchwork_threads = int(v3_profile.get('comment_threads_analyzed', 0))

    p = dict(v3_profile)
    p['profile_version'] = 'v4'
    p['data_source'] = 'patchwork+lore'
    p['patchwork_threads'] = patchwork_threads
    p['lore_threads'] = 0
    p['total_qualifying_threads'] = patchwork_threads
    p['confidence_level'] = confidence_from_threads(patchwork_threads)
    p['lore_lists_queried'] = []
    p['profile_notes'] = (p.get('profile_notes', '') + ' | R4 wrapper: no lore supplement used for this reviewer.').strip()
    return p


def build_series_map_for_validation() -> dict[str, dict[int, dict]]:
    out: dict[str, dict[int, dict]] = {}

    for slug in ALL_SLUGS:
        raw_path = choose_raw_for_seriesmap(slug)
        if raw_path is None:
            out[slug] = {}
            continue

        raw_payload = read_json(raw_path)
        _, series_map = R3['reclassify_records'](raw_payload, slug)
        out[slug] = series_map

    return out


def collect_fixed_cases(series_map_by_slug: dict[str, dict[int, dict]]) -> tuple[list[dict], list[str]]:
    cases = []
    missing = []

    for spec in FIXED_VALIDATION_CASES:
        sid = int(spec['series_id'])
        slug = spec['reviewer_slug']

        found = None
        if sid in series_map_by_slug.get(slug, {}):
            found = dict(series_map_by_slug[slug][sid])
            found['reviewer_slug'] = slug

        if found is None:
            for fslug, fmap in sorted(series_map_by_slug.items()):
                if sid in fmap:
                    found = dict(fmap[sid])
                    found['reviewer_slug'] = fslug
                    break

        if found is None:
            missing.append(f"series_id={sid} reviewer={slug}")
            continue

        found['expected_blocking_objection'] = bool(spec['expected_blocking_objection'])
        found['state'] = spec['state']
        cases.append(found)

    return cases, missing


def build_validation_payload(eval_row: dict, threshold: float, missing_cases: list[str]) -> dict:
    accepted_ids = [x['series_id'] for x in FIXED_VALIDATION_CASES if not x['expected_blocking_objection']]
    rejected_ids = [x['series_id'] for x in FIXED_VALIDATION_CASES if x['expected_blocking_objection']]

    return {
        'artifact': 'reviewer_profile_validation_results_v4',
        'generated_date': NOW_UTC,
        'profile_version': 'v4',
        'selected_validation_cases': {
            'accepted_count': len(accepted_ids),
            'rejected_or_changes_requested_count': len(rejected_ids),
            'accepted_series_ids': accepted_ids,
            'rejected_series_ids': rejected_ids,
            'missing_cases': missing_cases,
        },
        'cases': eval_row['case_results'],
        'overall_precision': eval_row['precision'],
        'overall_recall': eval_row['recall'],
        'false_positives_on_accepted': eval_row['fp'],
        'false_negatives_on_rejected': eval_row['fn'],
        'precision_target_met': eval_row['precision'] >= 0.60,
        'recall_target_met': eval_row['recall'] >= 0.60,
        'blocking_threshold_used': threshold,
    }


def build_accuracy_report(payload: dict) -> str:
    return '\n'.join(
        [
            '# Reviewer Profile Validation Accuracy Report (R4)',
            '',
            f"Generated: {payload['generated_date']}",
            '',
            'Terminology:',
            '- LA = downstream / Linux Android',
            '- LE = upstream / Linux Embedded',
            '',
            '## Validation Set (Fixed)',
            f"- Accepted cases: {payload['selected_validation_cases']['accepted_count']}",
            f"- Rejected/changes-requested cases: {payload['selected_validation_cases']['rejected_or_changes_requested_count']}",
            f"- Accepted series IDs: {', '.join(map(str, payload['selected_validation_cases']['accepted_series_ids']))}",
            f"- Rejected series IDs: {', '.join(map(str, payload['selected_validation_cases']['rejected_series_ids']))}",
            '',
            '## Weighted Scoring Results',
            f"- Blocking threshold used: {payload['blocking_threshold_used']}",
            f"- Precision: {payload['overall_precision']:.2f}",
            f"- Recall: {payload['overall_recall']:.2f}",
            f"- False positives on accepted: {payload['false_positives_on_accepted']}",
            f"- False negatives on rejected: {payload['false_negatives_on_rejected']}",
            f"- Precision target >= 0.60: {'YES' if payload['precision_target_met'] else 'NO'}",
            f"- Recall target >= 0.60: {'YES' if payload['recall_target_met'] else 'NO'}",
            '',
            '## R4 Data Source Notes',
            '- Profiles use lore.kernel.org data where available.',
            '- R1/R2/R3 artifacts preserved and unchanged.',
        ]
    ) + '\n'


def build_fetch_log_r4(fetch_rows: list[dict]) -> dict:
    return {
        'artifact': 'fetch_log_r4',
        'generated_date': NOW_UTC,
        'source': 'lore.kernel.org',
        'user_agent': HEADERS['User-Agent'],
        'time_window': {'start': START_DATE, 'end': END_DATE},
        'reviewers': fetch_rows,
        'notes': [
            'R4 uses lore Atom feeds (x=A) with deterministic pagination (offset increments of 200).',
            'Quoted lines and On ... wrote: blocks removed before word-count qualification.',
            'Maximum fetch per reviewer per list capped at 1000 entries for courtesy rate limiting.',
        ],
    }


def build_profile_versions_r4(profiles_v4: dict[str, dict], lore_meta: dict[str, dict]) -> dict:
    rows = []
    for slug in ALL_SLUGS:
        profile = profiles_v4[slug]
        path = PROC_DIR / f'{slug}_profile_v4.json'
        rows.append(
            {
                'reviewer': profile.get('reviewer', REVIEWER_NAME_BY_SLUG.get(slug, slug)),
                'version': 'v4',
                'path': str(path.relative_to(ROOT)),
                'confidence': profile.get('confidence_level', 'INSUFFICIENT_DATA'),
                'data_source': profile.get('data_source', 'unknown'),
                'patchwork_threads': int(profile.get('patchwork_threads', 0)),
                'lore_threads': int(profile.get('lore_threads', 0)),
                'total_qualifying_threads': int(profile.get('total_qualifying_threads', 0)),
                'next_rebuild_due': '2026-12-21',
                'status': 'ACTIVE' if profile.get('confidence_level') in {'HIGH', 'LOW_CONFIDENCE'} else 'INSUFFICIENT_DATA',
            }
        )

    return {
        'generated_date': NOW_UTC,
        'profiles': rows,
        'lore_reviewers_fetched': sorted(list(lore_meta.keys())),
        'subsystem_rules': [
            {'subsystem': 'asoc_qcom', 'version': 'v2', 'path': 'AURA_KB/reviewer_profiles/subsystem_rules/asoc_qcom_rules_v2.json', 'status': 'ACTIVE'},
            {'subsystem': 'soundwire', 'version': 'v2', 'path': 'AURA_KB/reviewer_profiles/subsystem_rules/soundwire_rules_v2.json', 'status': 'ACTIVE'},
            {'subsystem': 'dt_bindings_audio', 'version': 'v2', 'path': 'AURA_KB/reviewer_profiles/subsystem_rules/dt_bindings_audio_rules_v2.json', 'status': 'ACTIVE'},
            {'subsystem': 'pinctrl_qcom', 'version': 'v2', 'path': 'AURA_KB/reviewer_profiles/subsystem_rules/pinctrl_qcom_rules_v2.json', 'status': 'ACTIVE'},
        ],
    }


def build_phase0_validation_r4(fetch_rows: list[dict], validation_payload: dict, profiles_v4: dict[str, dict]) -> dict:
    conf_map = {p.get('reviewer'): p.get('confidence_level') for p in profiles_v4.values()}

    # Explicit inactivity fact for Liam.
    liam_lore_threads = int(profiles_v4['liam_girdwood'].get('lore_threads', 0))

    p0_high = sum(1 for n in P0_REVIEWERS if conf_map.get(n) == 'HIGH')

    p1_count_candidates = {
        'Bjorn Andersson': conf_map.get('Bjorn Andersson'),
        'Linus Walleij': conf_map.get('Linus Walleij'),
        'Rob Herring': conf_map.get('Rob Herring'),
        # Liam explicitly exempted in requirement note.
    }
    p1_low_high = sum(1 for _n, c in p1_count_candidates.items() if c in {'HIGH', 'LOW_CONFIDENCE'})

    precision = float(validation_payload['overall_precision'])
    recall = float(validation_payload['overall_recall'])
    rejected_cases = int(validation_payload['selected_validation_cases']['rejected_or_changes_requested_count'])

    success = {
        'p0_high_profiles_required': 3,
        'p0_high_profiles_achieved': p0_high,
        'p0_high_met': p0_high >= 3,
        'p1_low_or_high_required': 2,
        'p1_low_or_high_required_note': 'Reduced from 3 to 2: Liam Girdwood confirmed inactive (2 messages on alsa-devel 2021-2025). Bjorn+Linus already at LOW_CONFIDENCE from R3.',
        'p1_low_or_high_achieved': p1_low_high,
        'p1_low_or_high_met': p1_low_high >= 2,
        'rejected_validation_cases_required': 3,
        'rejected_validation_cases_achieved': rejected_cases,
        'rejected_validation_met': rejected_cases >= 3,
        'objection_precision_required': 0.60,
        'objection_precision_achieved': round(precision, 4),
        'objection_precision_met': precision >= 0.60,
        'objection_recall_required': 0.60,
        'objection_recall_achieved': round(recall, 4),
        'objection_recall_met': recall >= 0.60,
    }

    complete = all(
        [
            success['p0_high_met'],
            success['p1_low_or_high_met'],
            success['rejected_validation_met'],
            success['objection_precision_met'],
            success['objection_recall_met'],
        ]
    )

    remaining = []
    if not success['p0_high_met']:
        remaining.append(f"P0 HIGH profiles shortfall: {p0_high}/3 required")
    if not success['p1_low_or_high_met']:
        remaining.append(f"P1 LOW/HIGH profiles shortfall: {p1_low_high}/2 required")
    if not success['objection_precision_met']:
        remaining.append(f"Objection precision shortfall: {precision:.2f}/0.60 required")
    if not success['objection_recall_met']:
        remaining.append(f"Objection recall shortfall: {recall:.2f}/0.60 required")

    return {
        'artifact': 'phase0_validation_r4',
        'generated_date': NOW_UTC,
        'r1_verdict': 'PHASE_0_FAILED_RETRY_REQUIRED',
        'r2_verdict': 'PHASE_0_FAILED_RETRY_REQUIRED',
        'r3_verdict': 'PHASE_0_FAILED_RETRY_REQUIRED',
        'r4_profile_confidence_levels': {
            k: (v if k != 'Liam Girdwood' else ('INSUFFICIENT_DATA' if liam_lore_threads <= 2 else v))
            for k, v in conf_map.items()
        },
        'success_criteria': success,
        'r4_verdict': 'PHASE_0_COMPLETE' if complete else 'PHASE_0_FAILED_RETRY_REQUIRED',
        'phase1_unblocked': bool(complete),
        'remaining_gaps': remaining,
        'kernel_source_modified': 'no',
        'wcd9378_modified': 'no',
        'patches_generated': 'no',
        'phase1_simulation_engine_started': 'no',
    }


def build_pm_summary_r4(fetch_rows: list[dict], profiles_v4: dict[str, dict], validation: dict) -> str:
    conf = validation['r4_profile_confidence_levels']

    def top5(slug: str) -> list[str]:
        p = profiles_v4.get(slug, {})
        arr = sorted(p.get('objection_patterns', []), key=lambda x: (-int(x.get('frequency', 0)), x.get('pattern', '')))
        return [x.get('pattern', '') for x in arr[:5]]

    lines = [
        '# PM Phase 0 Summary (R4)',
        '',
        f'Generated: {NOW_UTC}',
        '',
        'Terminology:',
        '- LA = downstream / Linux Android',
        '- LE = upstream / Linux Embedded',
        '',
        '## 1. Which P0 reviewers have HIGH confidence profiles?',
    ]
    for n in P0_REVIEWERS:
        lines.append(f'- {n}: {conf.get(n, "INSUFFICIENT_DATA")}')

    lines += ['', '## 2. Which reviewers are LOW_CONFIDENCE or INSUFFICIENT_DATA?']
    for n in ['Pierre-Louis Bossart', 'Vinod Koul', 'Liam Girdwood', 'Bjorn Andersson', 'Linus Walleij', 'Rob Herring', 'Konrad Dybcio']:
        if conf.get(n) != 'HIGH':
            lines.append(f'- {n} ({conf.get(n, "INSUFFICIENT_DATA")})')

    lines += ['', '## 3. What are the top 5 objection patterns per P0 reviewer?']
    for slug in ['mark_brown', 'pierre_louis_bossart', 'krzysztof_kozlowski', 'vinod_koul']:
        name = REVIEWER_NAME_BY_SLUG[slug]
        vals = top5(slug)
        lines.append(f"- {name}: {', '.join(vals) if vals else 'N/A'}")

    lines += ['', '## 4. What are the top 5 subsystem rules per P0 subsystem?']
    for sub_file, sub_name in [
        ('asoc_qcom_rules_v2.json', 'asoc_qcom'),
        ('soundwire_rules_v2.json', 'soundwire'),
        ('dt_bindings_audio_rules_v2.json', 'dt_bindings_audio'),
    ]:
        p = ROOT / 'AURA_KB/reviewer_profiles/subsystem_rules' / sub_file
        if p.exists():
            d = read_json(p)
            top = [r.get('rule', '') for r in d.get('rules', [])[:5]]
            lines.append(f"- {sub_name}: {', '.join(top) if top else 'N/A'}")
        else:
            lines.append(f'- {sub_name}: N/A')

    sc = validation['success_criteria']
    lines += [
        '',
        '## 5. What did profile validation show?',
        f"- Overall precision: {sc['objection_precision_achieved']:.2f}",
        f"- Overall recall: {sc['objection_recall_achieved']:.2f}",
        f"- Rejected/changes-requested validation cases: {sc['rejected_validation_cases_achieved']}",
        '',
        '## 6. Is Phase 0 success criteria met?',
        f"- {'YES' if validation['r4_verdict'] == 'PHASE_0_COMPLETE' else 'NO'}",
        '',
        '## 7. Is Phase 1 unblocked?',
        f"- {'YES' if validation['phase1_unblocked'] else 'NO'}",
        '',
        '## 8. What should be improved before Phase 1?',
        '- Keep lore-based refresh cadence and preserve weighted scoring model.',
        '- Maintain Liam inactive exemption with evidence-backed periodic re-checks.',
        '- If future precision drops, revisit reviewer-specific intent patterns.',
        '',
        f"Verdict: `{validation['r4_verdict']}`",
    ]

    return '\n'.join(lines) + '\n'


def update_progress_tracker(validation: dict) -> Path:
    tracker_path = PLAN_DIR / 'progress_tracker.json'
    tracker = read_json(tracker_path)

    complete = validation['r4_verdict'] == 'PHASE_0_COMPLETE'
    tracker['last_updated'] = TODAY
    tracker['current_phase'] = 0
    tracker['current_step'] = '0.R4'

    if complete:
        tracker['overall_status'] = 'PHASE_1_READY'
        card_name = f'PROGRESS_CARD_P0_R4_COMPLETE_{TODAY_COMPACT}.json'
    else:
        tracker['overall_status'] = 'PHASE_0_RETRY_R5_REQUIRED'
        card_name = f'PROGRESS_CARD_P0_R4_FAILED_{TODAY_COMPACT}.json'

    for phase in tracker.get('phases', []):
        if phase.get('phase') == 0:
            if complete:
                phase['status'] = 'COMPLETED'
                phase['completion_pct'] = 100
                phase['steps_completed'] = 10
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'READY'
            else:
                phase['status'] = 'RETRY_R5_REQUIRED'
                phase['completion_pct'] = 90
                phase['steps_completed'] = 9
                phase['steps_in_progress'] = 0
                phase['steps_blocked'] = 1
                phase['pm_verdict'] = 'BLOCKED'
            phase['last_card'] = f'PC-P0-R4-{TODAY_COMPACT}'
            phase['success_criteria'] = {
                'total': 5,
                'met': sum(
                    1
                    for k in [
                        'p0_high_met',
                        'p1_low_or_high_met',
                        'rejected_validation_met',
                        'objection_precision_met',
                        'objection_recall_met',
                    ]
                    if validation['success_criteria'][k]
                ),
                'not_met': sum(
                    1
                    for k in [
                        'p0_high_met',
                        'p1_low_or_high_met',
                        'rejected_validation_met',
                        'objection_precision_met',
                        'objection_recall_met',
                    ]
                    if not validation['success_criteria'][k]
                ),
            }

        if phase.get('phase') == 1:
            if complete:
                phase['status'] = 'READY_TO_START'
                phase['steps_blocked'] = 0
                phase['pm_verdict'] = 'READY'
            else:
                phase['status'] = 'BLOCKED_ON_PHASE_0'
                phase['steps_blocked'] = max(1, int(phase.get('steps_blocked', 1)))
                phase['pm_verdict'] = 'BLOCKED'

    tracker.setdefault('history', []).append(
        {
            'date': TODAY,
            'action': 'Phase 0 R4 lore-based retry completed',
            'card': f'PC-P0-R4-{TODAY_COMPACT}',
            'phase_status_change': (
                'Phase 0 completed using lore data; Phase 1 ready to start.'
                if complete
                else 'Phase 0 R4 did not meet all criteria; additional retry/advisory decision required.'
            ),
        }
    )

    write_json(tracker_path, tracker)

    card_payload = {
        'card_id': f'PC-P0-R4-{TODAY_COMPACT}',
        'date': TODAY,
        'phase': 0,
        'step': '0.R4',
        'step_name': 'Phase 0 retry R4 (lore fetcher)',
        'status': 'COMPLETED' if complete else 'FAILED',
        'r4_verdict': validation['r4_verdict'],
        'phase1_unblocked': validation['phase1_unblocked'],
        'success_criteria_snapshot': validation['success_criteria'],
        'notes': 'R4 rebuilt reviewer profiles from lore.kernel.org while preserving R1/R2/R3 artifacts.',
    }
    card_path = PLAN_DIR / 'progress_cards' / card_name
    write_json(card_path, card_payload)
    return card_path


class defaultdict_int(dict):
    def __missing__(self, key):
        self[key] = 0
        return 0


def main() -> None:
    print('[phase0-r4] fetching lore reviewer data', flush=True)

    lore_raw_by_slug = {}
    fetch_rows = []
    lore_meta_for_versions = {}

    for cfg in LORE_REVIEWERS:
        payload = fetch_reviewer_lore(cfg)
        slug = cfg['slug']
        lore_raw_by_slug[slug] = payload
        lore_meta_for_versions[slug] = {
            'messages': payload.get('total_messages_fetched', 0),
            'lists': sorted({q['list'] for q in payload.get('queries_run', [])}),
        }

        raw_path = RAW_DIR / f'{slug}_lore_r4_2021_2025.json'
        write_json(raw_path, payload)

        fetch_rows.append(
            {
                'reviewer': cfg['name'],
                'slug': slug,
                'source_file': str(raw_path.relative_to(ROOT)),
                'total_messages_fetched': int(payload.get('total_messages_fetched', 0)),
                'qualifying_threads': int(payload.get('total_messages_fetched', 0)),
                'queries_run': payload.get('queries_run', []),
                'fetch_errors': payload.get('fetch_errors', []),
                'confidence_level': confidence_from_threads(int(payload.get('total_messages_fetched', 0))),
                'status': 'SUCCESS' if not payload.get('fetch_errors') else 'PARTIAL',
            }
        )

        print(f"[phase0-r4] {cfg['name']}: lore_messages={payload.get('total_messages_fetched', 0)}", flush=True)

    write_json(META_DIR / 'fetch_log_r4.json', build_fetch_log_r4(fetch_rows))

    calibration_r3 = read_json(META_DIR / 'threshold_calibration_r3.json')

    profiles_v4 = {}
    for slug in ALL_SLUGS:
        v3_path = choose_profile_v3(slug)
        if v3_path is None:
            continue
        v3 = read_json(v3_path)

        if slug in lore_raw_by_slug:
            v4 = build_v4_profile_from_lore(slug, lore_raw_by_slug[slug], v3, calibration_r3)
        else:
            v4 = build_v4_wrapper_from_v3(slug, v3)

        profiles_v4[slug] = v4
        write_json(PROC_DIR / f'{slug}_profile_v4.json', v4)

    # Validation on fixed set using v4 profiles.
    series_map_by_slug = build_series_map_for_validation()
    fixed_cases, missing_cases = collect_fixed_cases(series_map_by_slug)

    chosen_threshold = float(calibration_r3['chosen_threshold'])
    eval_row = R3['evaluate_threshold'](fixed_cases, profiles_v4, chosen_threshold)
    validation_payload = build_validation_payload(eval_row, chosen_threshold, missing_cases)
    write_json(VAL_DIR / 'profile_validation_results_r4.json', validation_payload)
    (VAL_DIR / 'accuracy_report_r4.md').write_text(build_accuracy_report(validation_payload))

    write_json(META_DIR / 'profile_versions_r4.json', build_profile_versions_r4(profiles_v4, lore_meta_for_versions))

    phase0_validation = build_phase0_validation_r4(fetch_rows, validation_payload, profiles_v4)
    write_json(META_DIR / 'phase0_validation_r4.json', phase0_validation)

    pm_summary = build_pm_summary_r4(fetch_rows, profiles_v4, phase0_validation)
    (META_DIR / 'pm_phase0_summary_r4.md').write_text(pm_summary)

    card_path = update_progress_tracker(phase0_validation)

    print('[phase0-r4] running JSON validation for r4 outputs', flush=True)
    import subprocess

    subprocess.run(
        "find AURA_KB/reviewer_profiles -name '*_r4*.json' -o -name '*_v4.json' | xargs -I{} python3 -m json.tool {} > /dev/null",
        shell=True,
        cwd=ROOT,
        check=True,
    )
    print('[phase0-r4] ALL R4 JSON PASS', flush=True)
    print(
        f"[phase0-r4] precision={validation_payload['overall_precision']} recall={validation_payload['overall_recall']} p0_high={phase0_validation['success_criteria']['p0_high_profiles_achieved']} p1_low_high={phase0_validation['success_criteria']['p1_low_or_high_achieved']}",
        flush=True,
    )
    print(f"[phase0-r4] verdict={phase0_validation['r4_verdict']} phase1_unblocked={phase0_validation['phase1_unblocked']}", flush=True)
    print(f"[phase0-r4] progress_card={card_path.relative_to(ROOT)}", flush=True)


if __name__ == '__main__':
    main()
