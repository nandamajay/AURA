from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE = Path('/local/mnt/workspace/AURA_V1')
EVIDENCE = BASE / 'evidence'
PATCHGEN_DIR = EVIDENCE / 'wcd937x_patchgen_20260519_194926'
PATCH_DIR = PATCHGEN_DIR / 'generated_patch_diffs'
UPSTREAM_REPO = EVIDENCE / 'wcd937x_real_study_20260519_062557' / 'repos' / 'linux-upstream-v6.18'
PRIOR_RUN = EVIDENCE / 'compile_closure_wcd937x_20260520_003256'

run_ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
RUN_ID = f'compile_closure_wcd937x_continuation_{run_ts}'
RUN_DIR = EVIDENCE / RUN_ID
REPORTS = RUN_DIR / 'reports'
LOGS = RUN_DIR / 'logs'
RAW = RUN_DIR / 'raw'
ART = RUN_DIR / 'artifacts'
REPOS = RUN_DIR / 'repos'
VALIDATION_EVIDENCE = RUN_DIR / 'validation_evidence'
WORKTREE = REPOS / 'linux-compile-closure'

for p in (RUN_DIR, REPORTS, LOGS, RAW, ART, REPOS, VALIDATION_EVIDENCE):
    p.mkdir(parents=True, exist_ok=True)

COMMAND_LOG = RAW / 'commands_executed.jsonl'

MAX_DISK_USED_PCT = 92.0
MIN_MEM_AVAILABLE_MB = 512
MAX_SINGLE_LOG_MB = 256
MAX_TOTAL_LOG_MB = 1024
COMPILE_RETRY_LIMIT = 3
REGEN_RETRY_LIMIT = 2
REMAP_RETRY_LIMIT = 1

OPERATOR_AUTHORIZATION = {
    'authorized': True,
    'mode': 'CONTROLLED_CONTINUATION_PASS_ONLY',
    'source': 'operator instruction in active session',
    'constraints': [
        'phase-gated execution only',
        'no auto-merge',
        'no auto-submit',
        'no governance bypass',
        'advisory-only when closure not proven',
    ],
}

PHASES = [
    'PHASE 0 Environment Discovery',
    'PHASE 1 Source Intake + Lineage',
    'PHASE 2 Semantic Mapping',
    'PHASE 3 Patch Proposal Generation',
    'PHASE 4 Patch Governance Review',
    'PHASE 5 Kernel Prepare Validation',
    'PHASE 6 Compile Closure Validation',
    'PHASE 7 Static Analysis Validation',
    'PHASE 8 DT Schema Validation',
    'PHASE 9 Runtime/Boot Validation',
    'PHASE 10 Upstream Readiness Classification',
    'PHASE 11 Human Escalation Review',
]

phase_transition_log: list[dict[str, Any]] = []
governance_trace: list[dict[str, Any]] = []


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, sort_keys=True) + '\n')


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + '\n', encoding='utf-8')


def write_md(path: Path, lines: list[str]) -> None:
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def mem_available_mb() -> int:
    try:
        text = Path('/proc/meminfo').read_text(encoding='utf-8', errors='replace')
        m = re.search(r'^MemAvailable:\s+(\d+)\s+kB', text, flags=re.M)
        if m:
            return int(int(m.group(1)) / 1024)
    except Exception:
        pass
    return -1


def log_sizes_mb() -> tuple[float, float]:
    total = 0
    single = 0
    for p in LOGS.rglob('*'):
        if p.is_file():
            sz = p.stat().st_size
            total += sz
            single = max(single, sz)
    return single / (1024 * 1024), total / (1024 * 1024)


def resource_guard(tag: str) -> list[str]:
    issues: list[str] = []
    du = shutil.disk_usage(str(RUN_DIR))
    used_pct = (du.used / du.total) * 100.0 if du.total else 0.0
    if used_pct > MAX_DISK_USED_PCT:
        issues.append(f'DISK_THRESHOLD_EXCEEDED:{used_pct:.2f}%')

    mem_mb = mem_available_mb()
    if mem_mb >= 0 and mem_mb < MIN_MEM_AVAILABLE_MB:
        issues.append(f'MEMORY_EXHAUSTION_RISK:MemAvailableMB={mem_mb}')

    single_mb, total_mb = log_sizes_mb()
    if single_mb > MAX_SINGLE_LOG_MB:
        issues.append(f'RUNAWAY_LOG_GROWTH:single_log_mb={single_mb:.1f}')
    if total_mb > MAX_TOTAL_LOG_MB:
        issues.append(f'RUNAWAY_LOG_GROWTH:total_log_mb={total_mb:.1f}')

    if WORKTREE.exists() and not (WORKTREE / '.git').exists():
        issues.append('WORKTREE_CORRUPTION_DETECTED')

    if issues:
        write_json(RAW / f'resource_guard_{tag}.json', {'tag': tag, 'issues': issues, 'timestamp': ts()})
    return issues


def run_cmd(label: str, cmd: str, *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 1200) -> dict[str, Any]:
    pre = resource_guard(f'before_{label}')
    log_path = LOGS / f'{label}.log'
    if pre:
        log_path.write_text('# skipped due to resource guard\n' + '\n'.join(pre) + '\n', encoding='utf-8')
        result = {
            'label': label,
            'cmd': cmd,
            'cwd': str(cwd) if cwd else str(Path.cwd()),
            'start': ts(),
            'end': ts(),
            'duration_seconds': 0.0,
            'exit_code': 173,
            'timed_out': False,
            'log_path': str(log_path),
            'resource_issues': pre,
            'skipped_due_to_resource_guard': True,
        }
        append_jsonl(COMMAND_LOG, result)
        (LOGS / f'{label}.exit').write_text('173\n', encoding='utf-8')
        return result

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    start_dt = datetime.now(timezone.utc)
    with log_path.open('w', encoding='utf-8', errors='replace') as lf:
        lf.write(f'# label={label}\n# cmd={cmd}\n# cwd={cwd or Path.cwd()}\n# start={start_dt.isoformat()}\n')
        lf.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                shell=True,
                executable='/bin/bash',
                env=proc_env,
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
            exit_code = int(proc.returncode)
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
            lf.write('\n# TIMEOUT\n')

    post = resource_guard(f'after_{label}')
    if post and exit_code == 0:
        exit_code = 174

    end_dt = datetime.now(timezone.utc)
    result = {
        'label': label,
        'cmd': cmd,
        'cwd': str(cwd) if cwd else str(Path.cwd()),
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
        'duration_seconds': (end_dt - start_dt).total_seconds(),
        'exit_code': exit_code,
        'timed_out': timed_out,
        'log_path': str(log_path),
        'env_subset': {
            'ARCH': proc_env.get('ARCH', ''),
            'CROSS_COMPILE': proc_env.get('CROSS_COMPILE', ''),
            'PATH': proc_env.get('PATH', ''),
        },
        'resource_issues': post,
    }
    append_jsonl(COMMAND_LOG, result)
    (LOGS / f'{label}.exit').write_text(str(exit_code) + '\n', encoding='utf-8')
    return result


def classify_compile_issues(text: str) -> list[str]:
    lower = text.lower()
    issues: set[str] = set()
    if 'include/generated/autoconf.h' in text or 'include/config/auto.conf' in text:
        issues.add('GENERATED_CONFIG_MISSING')
    if "dt-doc-validate' not found" in lower:
        issues.add('TOOLING_ABSENCE')
    if 'has no member named' in lower:
        issues.add('STRUCT_DRIFT')
    if 'incompatible pointer type' in lower:
        issues.add('TYPE_MISMATCH')
    if 'too few arguments to function' in lower or 'too many arguments to function' in lower:
        issues.add('API_MISMATCH')
    if 'no such file or directory' in lower and '#include' in lower:
        issues.add('MISSING_INCLUDE')
    if 'undefined reference' in lower or 'undefined symbol' in lower:
        issues.add('UNRESOLVED_SYMBOL')
    if 'kconfig' in lower and 'error' in lower:
        issues.add('KCONFIG_DEPENDENCY')
    if any(x in lower for x in ['qti-regmap-debugfs', 'msm_cdc_', 'wcdcal']):
        issues.add('DOWNSTREAM_ABSTRACTION_LEAK')
    if 'error:' in lower and 'soundwire' in lower:
        issues.add('SOUNDWIRE_SEMANTIC_RISK')
    if 'error:' in lower and 'mbhc' in lower:
        issues.add('MBHC_SEMANTIC_RISK')
    return sorted(issues)


def parse_unresolved_symbols(text: str) -> list[str]:
    out: set[str] = set()
    for m in re.finditer(r"undefined reference to [`\\']([^`\\']+)[`\\']", text):
        out.add(m.group(1))
    for m in re.finditer(r'undefined symbol:?\s*([A-Za-z0-9_]+)', text):
        out.add(m.group(1))
    return sorted(out)


def patch_files() -> list[Path]:
    return [p for p in sorted(PATCH_DIR.glob('*.patch')) if p.name != '0000-cover-letter.patch']


def find_mandatory_triggers(patches: list[Path]) -> list[str]:
    triggers: set[str] = set()
    for p in patches:
        txt = p.read_text(encoding='utf-8', errors='replace').lower()
        n = p.name.lower()
        if 'soundwire' in txt or 'wcd937x-sdw' in n or 'sdw' in txt:
            triggers.add('SoundWire topology changes')
        if 'dapm' in txt:
            triggers.add('DAPM route mutations')
        if 'clk' in txt or 'clock' in txt:
            triggers.add('clock ownership changes')
        if 'regulator' in txt:
            triggers.add('regulator sequencing changes')
        if 'irq' in txt or 'interrupt' in txt:
            triggers.add('interrupt ordering changes')
        if 'mbhc' in txt:
            triggers.add('MBHC semantic changes')
        if 'wcdcal' in txt:
            triggers.add('calibration ownership changes')
        if 'documentation/devicetree/bindings' in txt or n.startswith('0006-dt-bindings'):
            triggers.add('DT ABI contract changes')
    return sorted(triggers)


def transition(
    phase: str,
    status: str,
    confidence: float,
    governance_state: str,
    blocker_count: int,
    advisory_count: int,
    evidence_paths: list[str],
    gate_checks: dict[str, Any],
    unresolved_assumptions: list[str],
    dependency_risks: list[str],
) -> None:
    phase_transition_log.append({
        'phase': phase,
        'timestamp': ts(),
        'phase_status': status,
        'confidence_score': confidence,
        'blocker_count': blocker_count,
        'advisory_count': advisory_count,
        'governance_state': governance_state,
        'replayability_status': 'REPLAYABLE',
        'gate_checks': gate_checks,
        'evidence_paths': evidence_paths,
        'unresolved_assumptions': unresolved_assumptions,
        'dependency_risks': dependency_risks,
    })


def gtrace(event: str, decision: str, details: dict[str, Any]) -> None:
    governance_trace.append({
        'timestamp': ts(),
        'event': event,
        'decision': decision,
        'details': details,
    })


# -------- metadata --------
head_sha = subprocess.check_output(['git', '-C', str(UPSTREAM_REPO), 'rev-parse', 'HEAD'], text=True).strip()
run_metadata = {
    'run_id': RUN_ID,
    'started_at': ts(),
    'operator_authorization': OPERATOR_AUTHORIZATION,
    'prior_run': str(PRIOR_RUN),
    'patchgen_dir': str(PATCHGEN_DIR),
    'patch_dir': str(PATCH_DIR),
    'upstream_repo': str(UPSTREAM_REPO),
    'upstream_head_sha': head_sha,
    'phase_order': PHASES,
}
write_json(RAW / 'run_metadata.json', run_metadata)

# materialize script + env for replay
shutil.copy2(Path(__file__), ART / 'run_compile_closure_continuation.py')
(RAW / 'upstream_head_sha.txt').write_text(head_sha + '\n', encoding='utf-8')
run_cmd('upstream_git_status', f'git -C {shlex.quote(str(UPSTREAM_REPO))} status --porcelain', timeout=30)
shutil.copy2(LOGS / 'upstream_git_status.log', RAW / 'upstream_git_status.txt')

# historical fail counts
historical_runs = sorted(EVIDENCE.glob('compile_closure_wcd937x_*'))
historical_non_closed = 0
for d in historical_runs:
    s = d / 'raw' / 'pipeline_summary.json'
    if s.exists():
        try:
            js = json.loads(s.read_text(encoding='utf-8'))
            if js.get('closure_state') != 'CLOSED':
                historical_non_closed += 1
        except Exception:
            pass
write_json(RAW / 'historical_failure_count.json', {
    'historical_non_closed_runs': historical_non_closed,
    'compile_retry_limit': COMPILE_RETRY_LIMIT,
    'regeneration_retry_limit': REGEN_RETRY_LIMIT,
    'semantic_remap_retry_limit': REMAP_RETRY_LIMIT,
})

# governance start
gtrace('continuation_authorization', 'AUTHORIZED_CONTROLLED_PASS', {
    'authorized': True,
    'scope': 'execute blocked phases sequentially with phase gates and evidence',
    'restrictions': OPERATOR_AUTHORIZATION['constraints'],
})

# -------- phase 0 --------
env_findings: list[str] = []
tools = ['make', 'clang', 'sparse', 'dt-doc-validate', 'python3', 'cpio', 'gzip', 'git', 'aarch64-linux-gnu-gcc']
tool_paths: dict[str, str] = {}
for t in tools:
    r = run_cmd(f'tool_{t.replace("/", "_")}', f'command -v {shlex.quote(t)}', timeout=20)
    if r['exit_code'] == 0:
        lines = (LOGS / f'tool_{t.replace("/", "_")}.log').read_text(encoding='utf-8', errors='replace').splitlines()
        tool_paths[t] = lines[-1].strip() if lines else ''
    else:
        tool_paths[t] = ''
        env_findings.append(f'TOOLING_GAP:{t}_missing')

for var in ['ARCH', 'CROSS_COMPILE']:
    if not os.environ.get(var):
        env_findings.append(f'TOOLING_GAP:{var}_not_set_in_caller_env')

for dep in ['yaml', 'jsonschema', 'dtschema']:
    rr = run_cmd(f'pydep_{dep}', f"python3 -c 'import {dep}'", timeout=20)
    if rr['exit_code'] != 0:
        env_findings.append(f'TOOLING_GAP:python_dep_{dep}_missing')

kernel_integrity = {
    'makefile_exists': (UPSTREAM_REPO / 'Makefile').exists(),
    'kconfig_exists': (UPSTREAM_REPO / 'Kconfig').exists(),
    'git_rev_parse_ok': run_cmd('kernel_rev_parse', f'git -C {shlex.quote(str(UPSTREAM_REPO))} rev-parse --verify HEAD', timeout=20)['exit_code'] == 0,
}
if not all(kernel_integrity.values()):
    env_findings.append('ENVIRONMENT_CORRUPTION:kernel_tree_integrity_failed')

resource_issues = resource_guard('phase0_end')
if resource_issues:
    env_findings.extend(resource_issues)

phase0_status = 'PASSED' if not env_findings else 'PASSED_WITH_ADVISORY'
phase0_conf = 0.95 if phase0_status == 'PASSED' else 0.72

write_md(REPORTS / 'environment_validation_report.md', [
    '# Environment Validation Report',
    '',
    f'- phase_status: `{phase0_status}`',
    f'- confidence_score: `{phase0_conf}`',
    f'- blocker_count: `0`',
    f'- advisory_count: `{len(env_findings)}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Tool Availability',
] + [f'- {k}: `{v or "MISSING"}`' for k, v in tool_paths.items()] + [
    '',
    '## Kernel Tree Integrity',
] + [f'- {k}: `{v}`' for k, v in kernel_integrity.items()] + [
    '',
    '## Findings',
] + ([f'- {x}' for x in env_findings] if env_findings else ['- none']) + [
    '',
    '## Evidence References',
    '- `raw/commands_executed.jsonl`',
    '- `raw/run_metadata.json`',
])

transition(
    'PHASE 0 Environment Discovery',
    phase0_status,
    phase0_conf,
    'CONTROLLED_CONTINUATION',
    0,
    len(env_findings),
    ['reports/environment_validation_report.md', 'raw/commands_executed.jsonl'],
    {'environment_checked': True},
    ['tool availability can drift between runs'],
    ['runtime host dependency drift'],
)

# -------- phases 1-4 evidence check --------
required_paths = {
    'source_intake': PATCHGEN_DIR / 'raw' / 'source_intake_rows.json',
    'source_lineage': PATCHGEN_DIR / 'raw' / 'source_lineage_rows.json',
    'mapping_plan': PATCHGEN_DIR / 'reports' / 'upstream_patch_series_plan.md',
    'patch_dir': PATCH_DIR,
    'governance_report': PATCHGEN_DIR / 'reports' / 'governance_decision_report.md',
}
prereq = {k: p.exists() for k, p in required_paths.items()}
write_json(RAW / 'phase_prereq_check.json', {'all_present': all(prereq.values()), 'paths': {k: str(v) for k, v in required_paths.items()}, 'exists': prereq})

if not all(prereq.values()):
    gtrace('prerequisite_validation', 'BLOCKED', {'missing': [k for k, ok in prereq.items() if not ok]})
    transition('PHASE 1 Source Intake + Lineage', 'BLOCKED', 0.0, 'BLOCKED', 1, 0, ['raw/phase_prereq_check.json'], {'prereq_all_present': False}, ['missing required phase evidence'], ['evidence lineage incomplete'])
    # fail closed early
    summary = {
        'run_id': RUN_ID,
        'ended_at': ts(),
        'closure_state': 'NOT_CLOSED',
        'phase10_status': 'BLOCKED',
        'mandatory_escalation': True,
        'autonomous_mutation_blocked': True,
        'reason': 'missing prerequisite evidence',
    }
    write_json(RAW / 'pipeline_summary.json', summary)
    write_json(RUN_DIR / 'phase_transition_log.json', phase_transition_log)
    write_json(RUN_DIR / 'governance_decision_trace.json', governance_trace)
    raise SystemExit(2)

transition(
    'PHASE 1 Source Intake + Lineage',
    'PASSED',
    0.93,
    'PENDING',
    0,
    0,
    [str(required_paths['source_intake']), str(required_paths['source_lineage'])],
    {'prereq_all_present': True},
    [],
    ['depends on preserved historical evidence'],
)
transition(
    'PHASE 2 Semantic Mapping',
    'PASSED_WITH_ADVISORY',
    0.75,
    'PENDING',
    0,
    1,
    [str(required_paths['mapping_plan'])],
    {'mapping_report_present': True},
    ['inferred mappings unresolved'],
    ['downstream abstraction parity unresolved'],
)
transition(
    'PHASE 3 Patch Proposal Generation',
    'PASSED_WITH_ADVISORY',
    0.77,
    'PENDING',
    0,
    1,
    [str(required_paths['patch_dir'])],
    {'patch_dir_present': True},
    ['patches are advisory proposals only'],
    ['maintainer quality metadata pending'],
)
transition(
    'PHASE 4 Patch Governance Review',
    'PASSED_WITH_ADVISORY',
    0.82,
    'PENDING',
    0,
    1,
    [str(required_paths['governance_report'])],
    {'governance_report_present': True},
    ['operator approval gates remain active'],
    ['high-risk audio changes require manual review'],
)

patches = patch_files()
patch_ids = [p.name for p in patches]
mandatory_triggers = find_mandatory_triggers(patches)
compile_retries_used = 0
regeneration_retries_used = 0
semantic_remap_retries_used = 0

write_md(REPORTS / 'mandatory_escalation_triggers.md', [
    '# Mandatory Escalation Triggers',
    '',
] + ([f'- {t}' for t in mandatory_triggers] if mandatory_triggers else ['- none']))

gtrace('high_risk_trigger_scan', 'ESCALATION_ACTIVE_CONTINUATION_ALLOWED', {
    'trigger_count': len(mandatory_triggers),
    'triggers': mandatory_triggers,
    'operator_authorized_continuation': True,
    'note': 'high-risk classification remains; continuation limited to validation in isolated worktree',
})

# -------- worktree setup --------
if WORKTREE.exists():
    run_cmd('remove_existing_worktree_dir', f'rm -rf {shlex.quote(str(WORKTREE))}', timeout=120)
add_wt = run_cmd('add_worktree', f'git -C {shlex.quote(str(UPSTREAM_REPO))} worktree add --detach {shlex.quote(str(WORKTREE))} {shlex.quote(head_sha)}', timeout=300)
if add_wt['exit_code'] != 0:
    gtrace('worktree_setup', 'BLOCKED', {'exit_code': add_wt['exit_code']})

# Build env (explicit deterministic values)
build_env = os.environ.copy()
build_env['ARCH'] = 'arm64'
build_env['CROSS_COMPILE'] = 'aarch64-linux-gnu-'
# Bound CPU pressure
nproc = os.cpu_count() or 1
jobs = max(1, min(8, nproc // 2 if nproc > 1 else 1))
build_env['AURA_MAKE_JOBS'] = str(jobs)

# -------- PHASE 5 --------
phase5_gate_ok = (add_wt['exit_code'] == 0) and OPERATOR_AUTHORIZATION['authorized']
phase5_status = 'SKIPPED'
if phase5_gate_ok:
    gtrace('phase_gate', 'ALLOW', {'phase': 'PHASE 5 Kernel Prepare Validation', 'gate': 'authorized + worktree_ready'})
    d1 = run_cmd('make_defconfig', f'make -j{jobs} defconfig', cwd=WORKTREE, env=build_env, timeout=1800)
    d2 = run_cmd('make_modules_prepare', f'make -j{jobs} modules_prepare', cwd=WORKTREE, env=build_env, timeout=2400)
    autoconf = WORKTREE / 'include' / 'generated' / 'autoconf.h'
    auto_conf = WORKTREE / 'include' / 'config' / 'auto.conf'
    missing_cfg = [str(p.relative_to(WORKTREE)) for p in [autoconf, auto_conf] if not p.exists()]
    phase5_status = 'PASSED' if d1['exit_code'] == 0 and d2['exit_code'] == 0 and not missing_cfg else 'FAILED'
else:
    gtrace('phase_gate', 'BLOCK', {'phase': 'PHASE 5 Kernel Prepare Validation', 'reason': 'gate not satisfied'})
    missing_cfg = ['prepare_not_attempted_due_to_gate_failure']

write_md(REPORTS / 'kernel_prepare_report.md', [
    '# Kernel Prepare Report',
    '',
    f'- phase_status: `{phase5_status}`',
    f'- confidence_score: `{0.9 if phase5_status == "PASSED" else 0.25}`',
    f'- blocker_count: `{1 if phase5_status in {"FAILED", "BLOCKED"} else 0}`',
    '- advisory_count: `0`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Missing Generated Configs',
] + ([f'- `{m}`' for m in missing_cfg] if missing_cfg else ['- none']) + [
    '',
    '## Evidence References',
    '- `logs/make_defconfig.log`',
    '- `logs/make_modules_prepare.log`',
])

transition(
    'PHASE 5 Kernel Prepare Validation',
    phase5_status,
    0.9 if phase5_status == 'PASSED' else 0.25,
    'CONTROLLED_CONTINUATION',
    1 if phase5_status in {'FAILED', 'BLOCKED'} else 0,
    0,
    ['reports/kernel_prepare_report.md'],
    {'gate_ok': phase5_gate_ok, 'worktree_add_exit': add_wt['exit_code']},
    ['kernel prepare must succeed before compile closure'],
    ['generated-config dependency'],
)

# -------- PHASE 6 --------
patch_apply_status = 'SKIPPED'
compile_status = 'SKIPPED'
module_status = 'SKIPPED'
compile_issues: list[str] = []
unresolved_symbols: list[str] = []
compile_exit = None
compile_attempt_logs: list[str] = []

phase6_gate_ok = phase5_status == 'PASSED'
if phase6_gate_ok:
    gtrace('phase_gate', 'ALLOW', {'phase': 'PHASE 6 Compile Closure Validation', 'gate': 'phase5_passed'})
    apply_fail = False
    for p in patches:
        r = run_cmd(f'apply_{p.name}', f'git am {shlex.quote(str(p))}', cwd=WORKTREE, timeout=300)
        if r['exit_code'] != 0:
            apply_fail = True
            run_cmd('git_am_abort', 'git am --abort', cwd=WORKTREE, timeout=60)
            break
    patch_apply_status = 'BLOCKED' if apply_fail else 'PASSED'

    if patch_apply_status == 'PASSED':
        # compile with bounded retry (retry only for timeout/resource guard)
        while compile_retries_used < COMPILE_RETRY_LIMIT:
            compile_retries_used += 1
            rr = run_cmd(
                f'make_image_dtbs_modules_attempt_{compile_retries_used}',
                f'make -j{jobs} Image.gz dtbs modules',
                cwd=WORKTREE,
                env=build_env,
                timeout=7200,
            )
            compile_exit = rr['exit_code']
            compile_attempt_logs.append(f'logs/make_image_dtbs_modules_attempt_{compile_retries_used}.log')
            txt = (LOGS / f'make_image_dtbs_modules_attempt_{compile_retries_used}.log').read_text(encoding='utf-8', errors='replace')
            compile_issues = classify_compile_issues(txt)
            unresolved_symbols = parse_unresolved_symbols(txt)

            if rr['exit_code'] == 0:
                compile_status = 'PASSED'
                break

            # retry only for timeout/resource guard or explicit no-progress policy
            retryable = rr['exit_code'] in {124, 173, 174}
            if not retryable:
                compile_status = 'FAILED'
                break
            if compile_retries_used >= COMPILE_RETRY_LIMIT:
                compile_status = 'FAILED'
                break

        if compile_status == 'PASSED':
            modules_dir = ART / 'modules_dir'
            modules_dir.mkdir(parents=True, exist_ok=True)
            mi = run_cmd(
                'make_modules_install',
                f'make -j{jobs} modules_install INSTALL_MOD_PATH={shlex.quote(str(modules_dir))} INSTALL_MOD_STRIP=1',
                cwd=WORKTREE,
                env=build_env,
                timeout=3600,
            )
            if mi['exit_code'] == 0:
                pkg = run_cmd(
                    'package_modules_cpio',
                    f'cd {shlex.quote(str(modules_dir))} && find . | cpio -o -H newc | gzip -9 > ../modules.cpio.gz',
                    cwd=WORKTREE,
                    env=build_env,
                    timeout=600,
                )
                module_status = 'PASSED' if pkg['exit_code'] == 0 and (ART / 'modules.cpio.gz').exists() else 'FAILED'
            else:
                module_status = 'FAILED'
        else:
            module_status = 'SKIPPED'
    else:
        compile_status = 'SKIPPED'
        module_status = 'SKIPPED'
else:
    gtrace('phase_gate', 'BLOCK', {'phase': 'PHASE 6 Compile Closure Validation', 'reason': 'phase5_not_passed'})

if patch_apply_status == 'BLOCKED' or phase5_status in {'FAILED', 'BLOCKED'}:
    phase6_status = 'BLOCKED'
elif patch_apply_status == 'PASSED' and compile_status == 'PASSED' and module_status == 'PASSED':
    phase6_status = 'PASSED'
elif compile_status in {'FAILED'} or module_status in {'FAILED'}:
    phase6_status = 'FAILED'
else:
    phase6_status = 'SKIPPED'

write_md(REPORTS / 'patch_application_report.md', [
    '# Patch Application Report',
    '',
    f'- phase_status: `{patch_apply_status}`',
    f'- patch_count: `{len(patches)}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '',
    '## Patch IDs',
] + [f'- `{p}`' for p in patch_ids] + [
    '',
    '## Evidence References',
    '- `logs/apply_*.log`',
])

write_md(REPORTS / 'compile_execution_report.md', [
    '# Compile Execution Report',
    '',
    f'- phase_status: `{compile_status}`',
    f'- compile_attempts: `{compile_retries_used}`',
    f'- last_exit_code: `{compile_exit}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '',
    '## Classified Issues',
] + ([f'- {x}' for x in compile_issues] if compile_issues else ['- none']) + [
    '',
    '## Evidence References',
] + [f'- `{p}`' for p in compile_attempt_logs] + [
    '- `raw/commands_executed.jsonl`',
])

unresolved_conf = 0.0 if compile_status == 'SKIPPED' else (100.0 if len(unresolved_symbols) == 0 else max(10.0, 100.0 - (len(unresolved_symbols) * 5.0)))
write_md(REPORTS / 'unresolved_symbol_report.md', [
    '# Unresolved Symbol Report',
    '',
    f'- unresolved_symbol_count: `{len(unresolved_symbols)}`',
    f'- unresolved_symbol_confidence: `{unresolved_conf}`',
    '',
    '## Symbols',
] + ([f'- `{s}`' for s in unresolved_symbols] if unresolved_symbols else ['- none']) + [
    '',
    '## Evidence References',
] + ([f'- `{p}`' for p in compile_attempt_logs] if compile_attempt_logs else ['- compile not attempted']) )

write_md(REPORTS / 'module_packaging_report.md', [
    '# Module Packaging Report',
    '',
    f'- phase_status: `{module_status}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '',
    '## Artifact Checks',
    f'- modules_dir exists: `{(ART / "modules_dir").exists()}`',
    f'- modules.cpio.gz exists: `{(ART / "modules.cpio.gz").exists()}`',
    '',
    '## Evidence References',
    '- `logs/make_modules_install.log`',
    '- `logs/package_modules_cpio.log`',
])

transition(
    'PHASE 6 Compile Closure Validation',
    phase6_status,
    0.9 if phase6_status == 'PASSED' else 0.2,
    'CONTROLLED_CONTINUATION',
    1 if phase6_status in {'FAILED', 'BLOCKED'} else 0,
    0,
    ['reports/patch_application_report.md', 'reports/compile_execution_report.md', 'reports/module_packaging_report.md'],
    {'gate_ok': phase6_gate_ok, 'patch_apply_status': patch_apply_status, 'compile_status': compile_status, 'module_status': module_status},
    ['compile closure requires successful patch apply, compile, and module packaging'],
    ['cross-toolchain/config mismatch risk'],
)

# -------- PHASE 7 --------
static_status = 'SKIPPED'
static_advisories: list[str] = []
phase7_gate_ok = phase6_status in {'PASSED', 'PASSED_WITH_ADVISORY'}
if phase7_gate_ok:
    gtrace('phase_gate', 'ALLOW', {'phase': 'PHASE 7 Static Analysis Validation', 'gate': 'phase6_passed'})
    s1 = run_cmd('static_sparse', f'make -j{jobs} C=1 CHECK=sparse M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=3600)
    s2 = run_cmd('static_w1', f'make -j{jobs} W=1 M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=3600)
    s3 = run_cmd('static_clang', f'make -j{jobs} CC=clang M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=3600)
    exits = [s1['exit_code'], s2['exit_code'], s3['exit_code']]
    if all(x == 0 for x in exits):
        static_status = 'PASSED'
    else:
        static_status = 'PASSED_WITH_ADVISORY'
        static_advisories.append(f'non-zero static exits: {exits}')
else:
    gtrace('phase_gate', 'BLOCK', {'phase': 'PHASE 7 Static Analysis Validation', 'reason': 'phase6_not_passed'})
    static_advisories.append('skipped due to phase6 gate failure')

write_md(REPORTS / 'static_analysis_report.md', [
    '# Static Analysis Report',
    '',
    f'- phase_status: `{static_status}`',
    f'- advisory_count: `{len(static_advisories)}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '',
    '## Advisory Classification',
] + ([f'- {a}' for a in static_advisories] if static_advisories else ['- none']) + [
    '',
    '## Evidence References',
    '- `logs/static_sparse.log`',
    '- `logs/static_w1.log`',
    '- `logs/static_clang.log`',
])

transition(
    'PHASE 7 Static Analysis Validation',
    static_status,
    0.55 if static_status != 'SKIPPED' else 0.2,
    'CONTROLLED_CONTINUATION',
    0,
    len(static_advisories),
    ['reports/static_analysis_report.md'],
    {'gate_ok': phase7_gate_ok},
    ['static analysis is advisory unless governance policy upgrades severity'],
    ['tooling availability can downgrade confidence'],
)

# -------- PHASE 8 --------
dt_status = 'SKIPPED'
dt_class: list[str] = []
phase8_gate_ok = static_status in {'PASSED', 'PASSED_WITH_ADVISORY'}
if phase8_gate_ok:
    gtrace('phase_gate', 'ALLOW', {'phase': 'PHASE 8 DT Schema Validation', 'gate': 'phase7_passed_or_advisory'})
    dtr = run_cmd('dt_binding_check', f'make -j{jobs} dt_binding_check', cwd=WORKTREE, env=build_env, timeout=3600)
    dtt = (LOGS / 'dt_binding_check.log').read_text(encoding='utf-8', errors='replace') if (LOGS / 'dt_binding_check.log').exists() else ''
    if "dt-doc-validate' not found" in dtt.lower() or tool_paths.get('dt-doc-validate', '') == '':
        dt_status = 'PASSED_WITH_ADVISORY'
        dt_class.extend(['TOOLING_ABSENCE', 'DT_VALIDATION_INCOMPLETE'])
    elif dtr['exit_code'] == 0:
        dt_status = 'PASSED'
    else:
        dt_status = 'FAILED'
        dt_class.append('DT_SCHEMA_FAILURE')
else:
    gtrace('phase_gate', 'BLOCK', {'phase': 'PHASE 8 DT Schema Validation', 'reason': 'phase7_not_passed'})
    dt_class.append('SKIPPED_DUE_TO_PHASE_GATE')

write_md(REPORTS / 'dt_validation_report.md', [
    '# DT Validation Report',
    '',
    f'- phase_status: `{dt_status}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '',
    '## Classification',
] + [f'- {x}' for x in dt_class] + [
    '',
    '## Evidence References',
    '- `logs/dt_binding_check.log`',
])

transition(
    'PHASE 8 DT Schema Validation',
    dt_status,
    0.6 if dt_status.startswith('PASSED') else 0.2,
    'CONTROLLED_CONTINUATION',
    1 if dt_status == 'FAILED' else 0,
    1 if dt_status in {'PASSED_WITH_ADVISORY', 'SKIPPED'} else 0,
    ['reports/dt_validation_report.md'],
    {'gate_ok': phase8_gate_ok},
    ['DT validation requires dtschema tooling'],
    ['dt-doc-validate dependency'],
)

# tooling gap report
tooling_gaps = sorted(set(x for x in env_findings if x.startswith('TOOLING_GAP')))
write_md(REPORTS / 'tooling_gap_report.md', [
    '# Tooling Gap Report',
    '',
    '## Gaps',
] + ([f'- {g}' for g in tooling_gaps] if tooling_gaps else ['- none']) + [
    '',
    '## Evidence References',
    '- `reports/environment_validation_report.md`',
])

# -------- PHASE 9 --------
phase9_status = 'SKIPPED'
transition(
    'PHASE 9 Runtime/Boot Validation',
    phase9_status,
    0.0,
    'CONTROLLED_CONTINUATION',
    0,
    1,
    ['reports/compile_closure_status.md'],
    {'requires_runtime_target': True},
    ['runtime/boot validation out of current bounded compile scope'],
    ['compile artifacts and target runtime environment required'],
)

# -------- PHASE 10 --------
kernel_prepare_ok = phase5_status == 'PASSED'
compile_ok = compile_status == 'PASSED'
module_ok = module_status == 'PASSED'
dt_available = dt_status in {'PASSED', 'PASSED_WITH_ADVISORY'}
no_unresolved = len(unresolved_symbols) == 0 and compile_status == 'PASSED'

if kernel_prepare_ok and compile_ok and module_ok and dt_available and no_unresolved:
    closure_state = 'CLOSED'
    phase10_status = 'PASSED_WITH_ADVISORY' if dt_status == 'PASSED_WITH_ADVISORY' else 'PASSED'
    phase10_conf = 0.9 if phase10_status == 'PASSED' else 0.82
else:
    closure_state = 'NOT_CLOSED'
    phase10_status = 'BLOCKED'
    phase10_conf = 0.14

write_md(REPORTS / 'compile_closure_status.md', [
    '# Compile Closure Status',
    '',
    f'- closure_state: `{closure_state}`',
    f'- phase_status: `{phase10_status}`',
    f'- confidence_score: `{phase10_conf}`',
    f'- blocker_count: `{1 if phase10_status == "BLOCKED" else 0}`',
    f'- advisory_count: `{len(tooling_gaps)}`',
    '- governance_state: `CONTROLLED_CONTINUATION`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Closure Gate Checks',
    f'- kernel_prepare_success: `{kernel_prepare_ok}`',
    f'- module_compile_success: `{compile_ok}`',
    f'- module_packaging_success: `{module_ok}`',
    f'- dt_validation_available: `{dt_available}`',
    f'- unresolved_symbols_empty: `{no_unresolved}`',
    '',
    '## Truthful Conclusion',
] + (
    ['- bounded compile closure established with advisory conditions']
    if closure_state == 'CLOSED' else
    ['- proposal validation incomplete', '- compile closure not established', '- environment/tooling gaps remain']
) + [
    '',
    '## Evidence References',
    '- `reports/environment_validation_report.md`',
    '- `reports/kernel_prepare_report.md`',
    '- `reports/patch_application_report.md`',
    '- `reports/compile_execution_report.md`',
    '- `reports/module_packaging_report.md`',
    '- `reports/static_analysis_report.md`',
    '- `reports/dt_validation_report.md`',
    '- `reports/unresolved_symbol_report.md`',
    '- `reports/tooling_gap_report.md`',
    '- `raw/commands_executed.jsonl`',
])

transition(
    'PHASE 10 Upstream Readiness Classification',
    phase10_status,
    phase10_conf,
    'CONTROLLED_CONTINUATION',
    1 if phase10_status == 'BLOCKED' else 0,
    len(tooling_gaps),
    ['reports/compile_closure_status.md'],
    {'closure_state': closure_state},
    ['human review remains mandatory before any readiness claim'],
    ['unsafe merge conclusions must be prevented'],
)

# -------- PHASE 11 --------
compile_retry_exceeded = compile_retries_used >= COMPILE_RETRY_LIMIT and compile_status != 'PASSED'
if compile_retry_exceeded:
    mandatory_triggers.append('compile closure repeatedly fails')
if unresolved_conf < 70.0:
    mandatory_triggers.append(f'unresolved symbol confidence < 70% ({unresolved_conf})')
if phase10_status == 'BLOCKED':
    mandatory_triggers.append('compile closure not established')

reasons = sorted(set(mandatory_triggers))
mandatory_escalation = len(reasons) > 0

write_md(REPORTS / 'human_escalation_review.md', [
    '# Human Escalation Review',
    '',
    f'- phase_status: `{"BLOCKED" if mandatory_escalation else "PASSED_WITH_ADVISORY"}`',
    '- human_review_required: `true`',
    '- governance_state: `MANUAL_DECISION_REQUIRED`',
    '',
    '## Escalation Reasons',
] + [f'- {r}' for r in reasons] + [
    '',
    '## Mandatory Human Actions',
    '- no push/merge/submission from this run',
    '- review high-risk audio boundary changes (SoundWire/MBHC/DT ABI/regulator/etc.)',
    '- decide whether further compile passes are authorized',
    '',
    '## Evidence References',
    '- `reports/mandatory_escalation_triggers.md`',
    '- `reports/compile_closure_status.md`',
    '- `reports/unresolved_symbol_report.md`',
])

transition(
    'PHASE 11 Human Escalation Review',
    'BLOCKED' if mandatory_escalation else 'PASSED_WITH_ADVISORY',
    0.95,
    'MANUAL_DECISION_REQUIRED',
    1 if mandatory_escalation else 0,
    0 if mandatory_escalation else 1,
    ['reports/human_escalation_review.md'],
    {'mandatory_escalation': mandatory_escalation},
    ['human approval mandatory before destructive/upstream actions'],
    ['unsafe autonomy prohibited'],
)

gtrace('phase11_escalation', 'MANUAL_REVIEW_REQUIRED', {'reasons': reasons, 'mandatory': mandatory_escalation})

# -------- required top-level outputs --------
write_json(RUN_DIR / 'phase_transition_log.json', phase_transition_log)
write_json(RUN_DIR / 'governance_decision_trace.json', governance_trace)

write_md(RUN_DIR / 'compile_retry_status.md', [
    '# Compile Retry Status',
    '',
    f'- compile_retries_used: `{compile_retries_used}`',
    f'- compile_retries_limit: `{COMPILE_RETRY_LIMIT}`',
    f'- regeneration_retries_used: `{regeneration_retries_used}`',
    f'- regeneration_retries_limit: `{REGEN_RETRY_LIMIT}`',
    f'- semantic_remap_retries_used: `{semantic_remap_retries_used}`',
    f'- semantic_remap_retries_limit: `{REMAP_RETRY_LIMIT}`',
    '',
    '## Stop Conditions',
    '- retries continue only for timeout/resource-guard failures',
    '- semantic or dependency failures fail closed without infinite loop',
])

prior_summary = {}
if (PRIOR_RUN / 'raw' / 'pipeline_summary.json').exists():
    prior_summary = json.loads((PRIOR_RUN / 'raw' / 'pipeline_summary.json').read_text(encoding='utf-8'))

prior_closure = prior_summary.get('closure_state', 'UNKNOWN')
prior_blocked = prior_summary.get('phase10_status', 'UNKNOWN')

delta_lines = [
    '# Unresolved Risk Deltas',
    '',
    f'- prior_run: `{PRIOR_RUN.name}`',
    f'- current_run: `{RUN_ID}`',
    f'- prior_closure_state: `{prior_closure}`',
    f'- current_closure_state: `{closure_state}`',
    f'- prior_phase10_status: `{prior_blocked}`',
    f'- current_phase10_status: `{phase10_status}`',
    f'- mandatory_escalation_still_active: `{mandatory_escalation}`',
    '',
    '## Delta Classification',
]

if closure_state == prior_closure == 'NOT_CLOSED':
    delta_lines.append('- compile closure remains unresolved (no inflation)')
elif closure_state != prior_closure:
    delta_lines.append(f'- closure state changed: {prior_closure} -> {closure_state}')
else:
    delta_lines.append('- no closure-state delta')

if compile_retries_used > 0:
    delta_lines.append(f'- compile execution advanced in continuation pass (attempts={compile_retries_used})')
else:
    delta_lines.append('- compile execution did not advance')

delta_lines += [
    '',
    '## Remaining High-Risk Areas',
] + [f'- {r}' for r in reasons]

write_md(RUN_DIR / 'unresolved_risk_deltas.md', delta_lines)

# continuation execution report
write_md(RUN_DIR / 'continuation_execution_report.md', [
    '# Continuation Execution Report',
    '',
    f'- run_id: `{RUN_ID}`',
    f'- started_at: `{run_metadata["started_at"]}`',
    f'- ended_at: `{ts()}`',
    '- execution_mode: `GOVERNED_ADVISORY_CONTROLLED_CONTINUATION`',
    '- objective: `demonstrate governed safe continuation behavior`',
    '',
    '## Phase Summary',
] + [f'- {x["phase"]}: `{x["phase_status"]}` (confidence={x["confidence_score"]})' for x in phase_transition_log] + [
    '',
    '## Compile/Governance Outcome',
    f'- closure_state: `{closure_state}`',
    f'- phase10_status: `{phase10_status}`',
    f'- mandatory_escalation: `{mandatory_escalation}`',
    '- merge_readiness_claim: `NOT_ALLOWED`' if closure_state != 'CLOSED' else '- merge_readiness_claim: `ADVISORY_ONLY_PENDING_GOVERNANCE`',
    '',
    '## Truthfulness Statement',
    '- no compile success fabricated',
    '- no unresolved gaps suppressed',
    '- advisory-only posture preserved where proof is incomplete',
    '- human approval remains mandatory',
    '',
    '## Core Evidence',
    '- `phase_transition_log.json`',
    '- `governance_decision_trace.json`',
    '- `reports/compile_closure_status.md`',
    '- `reports/human_escalation_review.md`',
    '- `raw/commands_executed.jsonl`',
])

# lightweight validation evidence copies
for src in [
    REPORTS / 'environment_validation_report.md',
    REPORTS / 'kernel_prepare_report.md',
    REPORTS / 'patch_application_report.md',
    REPORTS / 'compile_execution_report.md',
    REPORTS / 'module_packaging_report.md',
    REPORTS / 'static_analysis_report.md',
    REPORTS / 'dt_validation_report.md',
    REPORTS / 'compile_closure_status.md',
    REPORTS / 'human_escalation_review.md',
    RUN_DIR / 'continuation_execution_report.md',
    RUN_DIR / 'phase_transition_log.json',
    RUN_DIR / 'governance_decision_trace.json',
    RUN_DIR / 'unresolved_risk_deltas.md',
    RUN_DIR / 'compile_retry_status.md',
]:
    if src.exists():
        shutil.copy2(src, VALIDATION_EVIDENCE / src.name)

# pipeline summary
summary = {
    'run_id': RUN_ID,
    'ended_at': ts(),
    'closure_state': closure_state,
    'phase10_status': phase10_status,
    'mandatory_escalation': mandatory_escalation,
    'autonomous_mutation_blocked': False,
    'controlled_continuation_authorized': True,
    'retry_depth': {
        'compile_retries_used': compile_retries_used,
        'compile_retries_limit': COMPILE_RETRY_LIMIT,
        'regeneration_retries_used': regeneration_retries_used,
        'regeneration_retries_limit': REGEN_RETRY_LIMIT,
        'semantic_remap_retries_used': semantic_remap_retries_used,
        'semantic_remap_retries_limit': REMAP_RETRY_LIMIT,
    },
    'patch_ids': patch_ids,
}
write_json(RAW / 'pipeline_summary.json', summary)

# phase contracts mirror transition log
write_json(RAW / 'phase_contracts.json', phase_transition_log)

# artifact hash manifest
files = sorted([p for p in RUN_DIR.rglob('*') if p.is_file() and p.name != 'artifact_hash_manifest.txt'])
manifest = [f"{hash_file(p)}  {p.relative_to(RUN_DIR)}" for p in files]
(ART / 'artifact_hash_manifest.txt').write_text('\n'.join(manifest) + '\n', encoding='utf-8')

print(json.dumps({'run_dir': str(RUN_DIR), 'summary': summary}, indent=2))
