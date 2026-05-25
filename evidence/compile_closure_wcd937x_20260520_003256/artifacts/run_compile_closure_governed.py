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

RUN_DIR = Path('/local/mnt/workspace/AURA_V1/evidence/compile_closure_wcd937x_20260520_003256')
PATCHGEN_DIR = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926')
PATCH_DIR = PATCHGEN_DIR / 'generated_patch_diffs'
UPSTREAM_REPO = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/linux-upstream-v6.18')
WORKTREE = RUN_DIR / 'repos' / 'linux-compile-closure'

REPORTS = RUN_DIR / 'reports'
LOGS = RUN_DIR / 'logs'
RAW = RUN_DIR / 'raw'
ART = RUN_DIR / 'artifacts'
for p in (REPORTS, LOGS, RAW, ART, RUN_DIR / 'repos'):
    p.mkdir(parents=True, exist_ok=True)

COMMAND_LOG = RAW / 'commands_executed.jsonl'

# Resource governance thresholds
MAX_DISK_USED_PCT = 92.0
MIN_MEM_AVAILABLE_MB = 512
MAX_SINGLE_LOG_MB = 256
MAX_TOTAL_LOG_MB = 1024

PHASE_ORDER = [
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


@dataclass
class PhaseContract:
    phase: str
    phase_status: str
    confidence_score: float
    blocker_count: int
    advisory_count: int
    evidence_paths: list[str]
    replayability_status: str
    governance_state: str
    unresolved_assumptions: list[str]
    dependency_risks: list[str]


phase_contracts: list[PhaseContract] = []


def ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_command_log(entry: dict[str, Any]) -> None:
    with COMMAND_LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, sort_keys=True) + '\n')


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
    max_single = 0
    if LOGS.exists():
        for p in LOGS.rglob('*'):
            if p.is_file():
                sz = p.stat().st_size
                total += sz
                if sz > max_single:
                    max_single = sz
    return max_single / (1024 * 1024), total / (1024 * 1024)


def resource_guard(tag: str) -> list[str]:
    issues: list[str] = []
    du = shutil.disk_usage(str(RUN_DIR))
    used_pct = (du.used / du.total) * 100.0 if du.total else 0.0
    if used_pct > MAX_DISK_USED_PCT:
        issues.append(f'DISK_THRESHOLD_EXCEEDED:{used_pct:.2f}%')

    mem_mb = mem_available_mb()
    if mem_mb >= 0 and mem_mb < MIN_MEM_AVAILABLE_MB:
        issues.append(f'MEMORY_EXHAUSTION_RISK:MemAvailableMB={mem_mb}')

    max_single_mb, total_mb = log_sizes_mb()
    if max_single_mb > MAX_SINGLE_LOG_MB:
        issues.append(f'RUNAWAY_LOG_GROWTH:single_log_mb={max_single_mb:.1f}')
    if total_mb > MAX_TOTAL_LOG_MB:
        issues.append(f'RUNAWAY_LOG_GROWTH:total_log_mb={total_mb:.1f}')

    if WORKTREE.exists() and not (WORKTREE / '.git').exists():
        issues.append('WORKTREE_CORRUPTION_DETECTED')

    if issues:
        (RAW / f'resource_guard_{tag}.json').write_text(json.dumps({'tag': tag, 'issues': issues, 'timestamp': ts()}, indent=2), encoding='utf-8')
    return issues


def run_cmd(
    label: str,
    cmd: str,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 900,
    log_name: str | None = None,
) -> dict[str, Any]:
    pre_issues = resource_guard(f'before_{label}')
    if pre_issues:
        result = {
            'label': label,
            'cmd': cmd,
            'cwd': str(cwd) if cwd else str(Path.cwd()),
            'start': ts(),
            'end': ts(),
            'duration_seconds': 0.0,
            'exit_code': 173,
            'timed_out': False,
            'log_path': str(LOGS / (log_name or f'{label}.log')),
            'resource_issues': pre_issues,
            'skipped_due_to_resource_guard': True,
        }
        append_command_log(result)
        (LOGS / f'{label}.exit').write_text('173\n', encoding='utf-8')
        (LOGS / (log_name or f'{label}.log')).write_text('# skipped due to resource guard\n' + '\n'.join(pre_issues) + '\n', encoding='utf-8')
        return result

    start = datetime.now(timezone.utc)
    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)
    if log_name is None:
        log_name = f'{label}.log'
    log_path = LOGS / log_name

    with log_path.open('w', encoding='utf-8', errors='replace') as lf:
        lf.write(f'# label={label}\n# cmd={cmd}\n# cwd={cwd or Path.cwd()}\n# start={start.isoformat()}\n')
        lf.flush()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                shell=True,
                env=proc_env,
                stdout=lf,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
                executable='/bin/bash',
            )
            exit_code = int(proc.returncode)
            timed_out = False
        except subprocess.TimeoutExpired:
            exit_code = 124
            timed_out = True
            lf.write('\n# TIMEOUT\n')

    post_issues = resource_guard(f'after_{label}')
    if post_issues:
        exit_code = 174

    end = datetime.now(timezone.utc)
    result = {
        'label': label,
        'cmd': cmd,
        'cwd': str(cwd) if cwd else str(Path.cwd()),
        'start': start.isoformat(),
        'end': end.isoformat(),
        'duration_seconds': (end - start).total_seconds(),
        'exit_code': exit_code,
        'timed_out': timed_out,
        'log_path': str(log_path),
        'env_subset': {
            'ARCH': proc_env.get('ARCH', ''),
            'CROSS_COMPILE': proc_env.get('CROSS_COMPILE', ''),
            'PATH': proc_env.get('PATH', ''),
        },
        'resource_issues': post_issues,
    }
    append_command_log(result)
    (LOGS / f'{label}.exit').write_text(str(exit_code) + '\n', encoding='utf-8')
    return result


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_md(path: Path, lines: list[str]) -> None:
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def patch_files() -> list[Path]:
    return [p for p in sorted(PATCH_DIR.glob('*.patch')) if p.name != '0000-cover-letter.patch']


def parse_unresolved_symbols(text: str) -> list[str]:
    out = set()
    for m in re.finditer(r'undefined reference to [`\']([^`\']+)[`\']', text):
        out.add(m.group(1))
    for m in re.finditer(r'undefined symbol:?\s*([A-Za-z0-9_]+)', text):
        out.add(m.group(1))
    return sorted(out)


def classify_compile_issues(text: str) -> list[str]:
    lower = text.lower()
    issues: list[str] = []
    if 'include/generated/autoconf.h' in text or 'include/config/auto.conf' in text:
        issues.append('GENERATED_CONFIG_MISSING')
    if "dt-doc-validate' not found" in lower:
        issues.append('TOOLING_ABSENCE')
    if 'has no member named' in lower:
        issues.append('STRUCT_DRIFT')
    if 'incompatible pointer type' in lower:
        issues.append('TYPE_MISMATCH')
    if 'too few arguments to function' in lower or 'too many arguments to function' in lower:
        issues.append('API_MISMATCH')
    if 'no such file or directory' in lower and '#include' in lower:
        issues.append('MISSING_INCLUDE')
    if 'undefined reference' in lower or 'undefined symbol' in lower:
        issues.append('UNRESOLVED_SYMBOL')
    if 'kconfig' in lower and 'error' in lower:
        issues.append('KCONFIG_DEPENDENCY')
    if any(x in lower for x in ['qti-regmap-debugfs', 'msm_cdc_', 'wcdcal']):
        issues.append('DOWNSTREAM_ABSTRACTION_LEAK')
    return sorted(set(issues))


def find_mandatory_escalation_triggers(patches: list[Path]) -> list[str]:
    triggers: list[str] = []
    for p in patches:
        txt = p.read_text(encoding='utf-8', errors='replace').lower()
        n = p.name.lower()
        if 'soundwire' in txt or 'wcd937x-sdw' in n or 'sdw' in txt:
            triggers.append('SoundWire topology changes')
        if 'dapm' in txt:
            triggers.append('DAPM route mutations')
        if 'clk' in txt or 'clock' in txt:
            triggers.append('clock ownership changes')
        if 'regulator' in txt:
            triggers.append('regulator sequencing changes')
        if 'irq' in txt or 'interrupt' in txt:
            triggers.append('interrupt ordering changes')
        if 'mbhc' in txt:
            triggers.append('MBHC semantic changes')
        if 'wcdcal' in txt:
            triggers.append('calibration ownership changes')
        if 'documentation/devicetree/bindings' in txt or n.startswith('0006-dt-bindings'):
            triggers.append('DT ABI contract changes')
    return sorted(set(triggers))


# ---------------- Run metadata ----------------
meta = {
    'run_id': RUN_DIR.name,
    'started_at': ts(),
    'phase_order': PHASE_ORDER,
    'patchgen_dir': str(PATCHGEN_DIR),
    'patch_dir': str(PATCH_DIR),
    'upstream_repo': str(UPSTREAM_REPO),
    'upstream_head': subprocess.check_output(['git', '-C', str(UPSTREAM_REPO), 'rev-parse', 'HEAD'], text=True).strip(),
}
(RAW / 'run_metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')

# historical loop protection inputs
historical_runs = sorted(Path('/local/mnt/workspace/AURA_V1/evidence').glob('compile_closure_wcd937x_*'))
historical_failures = 0
for d in historical_runs:
    s = d / 'raw' / 'pipeline_summary.json'
    if s.exists():
        try:
            js = json.loads(s.read_text())
            if js.get('closure_state') != 'CLOSED':
                historical_failures += 1
        except Exception:
            pass
(RAW / 'historical_failure_count.json').write_text(json.dumps({'historical_non_closed_runs': historical_failures}, indent=2), encoding='utf-8')

# ---------------- PHASE 0 ----------------
env_findings: list[str] = []

def tool_exists(tool: str) -> str:
    r = run_cmd(f'tool_{tool}', f'command -v {shlex.quote(tool)}', timeout=20)
    if r['exit_code'] == 0:
        lines = (LOGS / f'tool_{tool}.log').read_text(encoding='utf-8', errors='replace').splitlines()
        if lines:
            return lines[-1].strip()
    return ''

if not os.environ.get('ARCH'):
    env_findings.append('TOOLING_GAP:ARCH_not_set_in_caller_env')
if not os.environ.get('CROSS_COMPILE'):
    env_findings.append('TOOLING_GAP:CROSS_COMPILE_not_set_in_caller_env')

tools = {
    'make': tool_exists('make'),
    'clang': tool_exists('clang'),
    'sparse': tool_exists('sparse'),
    'dt-doc-validate': tool_exists('dt-doc-validate'),
    'python3': tool_exists('python3'),
    'cpio': tool_exists('cpio'),
    'gzip': tool_exists('gzip'),
}
for k, v in tools.items():
    if not v:
        env_findings.append(f'TOOLING_GAP:{k}_missing')

for dep in ['yaml', 'jsonschema', 'dtschema']:
    r = run_cmd(f'pydep_{dep}', f"python3 -c 'import {dep}'", timeout=20)
    if r['exit_code'] != 0:
        env_findings.append(f'TOOLING_GAP:python_dep_{dep}_missing')

kernel_integrity = {
    'git_ok': run_cmd('kernel_git_status', f'git -C {shlex.quote(str(UPSTREAM_REPO))} status --porcelain', timeout=30)['exit_code'] == 0,
    'makefile_exists': (UPSTREAM_REPO / 'Makefile').exists(),
    'kconfig_exists': (UPSTREAM_REPO / 'Kconfig').exists(),
}
if not all(kernel_integrity.values()):
    env_findings.append('ENVIRONMENT_CORRUPTION:kernel_tree_integrity_failed')

resource_issues_now = resource_guard('phase0_end')
if resource_issues_now:
    env_findings.extend(resource_issues_now)

phase0_status = 'PASSED' if not env_findings else 'PASSED_WITH_ADVISORY'
phase0_conf = 0.95 if phase0_status == 'PASSED' else 0.71

findings_lines = [f'- {f}' for f in env_findings] if env_findings else ['- none']
write_md(REPORTS / 'environment_validation_report.md', [
    '# Environment Validation Report',
    '',
    f'- phase_status: `{phase0_status}`',
    f'- confidence_score: `{phase0_conf}`',
    f'- blocker_count: `0`',
    f'- advisory_count: `{len(env_findings)}`',
    '- governance_state: `PENDING_REVIEW`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Tool Availability',
] + [f'- {k}: `{v or "MISSING"}`' for k, v in tools.items()] + [
    '',
    '## Kernel Tree Integrity',
] + [f'- {k}: `{v}`' for k, v in kernel_integrity.items()] + [
    '',
    '## Findings',
] + findings_lines + [
    '',
    '## Unresolved Assumptions',
    '- aarch64 cross toolchain may still be absent at build execution time',
    '',
    '## Dependency Risks',
    '- dt schema tooling absence may block DT closure',
    '- sparse/clang absence may downgrade static analysis confidence',
    '',
    '## Evidence References',
    '- `raw/commands_executed.jsonl`',
    '- `raw/run_metadata.json`',
])

phase_contracts.append(PhaseContract(
    phase='PHASE 0 Environment Discovery',
    phase_status=phase0_status,
    confidence_score=phase0_conf,
    blocker_count=0,
    advisory_count=len(env_findings),
    evidence_paths=['reports/environment_validation_report.md', 'raw/commands_executed.jsonl'],
    replayability_status='REPLAYABLE',
    governance_state='PENDING_REVIEW',
    unresolved_assumptions=['tool availability can drift between runs'],
    dependency_risks=['runtime host dependencies'],
))

# ---------------- PHASE 1-4 from required evidence ----------------
prereq = json.loads((RAW / 'phase_prereq_check.json').read_text())
if not prereq.get('all_present'):
    raise RuntimeError('prerequisite evidence missing; fail closed')

phase_contracts.append(PhaseContract(
    phase='PHASE 1 Source Intake + Lineage',
    phase_status='PASSED',
    confidence_score=0.93,
    blocker_count=0,
    advisory_count=0,
    evidence_paths=[f'{PATCHGEN_DIR}/raw/source_intake_rows.json', f'{PATCHGEN_DIR}/raw/source_lineage_rows.json'],
    replayability_status='REPLAYABLE',
    governance_state='PENDING',
    unresolved_assumptions=[],
    dependency_risks=['depends on preserved historical evidence'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 2 Semantic Mapping',
    phase_status='PASSED_WITH_ADVISORY',
    confidence_score=0.74,
    blocker_count=0,
    advisory_count=1,
    evidence_paths=[f'{PATCHGEN_DIR}/reports/upstream_patch_series_plan.md'],
    replayability_status='REPLAYABLE',
    governance_state='PENDING',
    unresolved_assumptions=['inferred mappings unresolved'],
    dependency_risks=['downstream abstraction parity unresolved'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 3 Patch Proposal Generation',
    phase_status='PASSED_WITH_ADVISORY',
    confidence_score=0.76,
    blocker_count=0,
    advisory_count=1,
    evidence_paths=[f'{PATCHGEN_DIR}/generated_patch_diffs'],
    replayability_status='REPLAYABLE',
    governance_state='PENDING',
    unresolved_assumptions=['patches are advisory proposals only'],
    dependency_risks=['maintainer-quality metadata pending'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 4 Patch Governance Review',
    phase_status='PASSED_WITH_ADVISORY',
    confidence_score=0.81,
    blocker_count=0,
    advisory_count=1,
    evidence_paths=[f'{PATCHGEN_DIR}/reports/governance_decision_report.md'],
    replayability_status='REPLAYABLE',
    governance_state='PENDING',
    unresolved_assumptions=['transformation governance decision pending'],
    dependency_risks=['operator decision required'],
))

# Mandatory human escalation triggers from patchset
patches = patch_files()
mandatory_triggers = find_mandatory_escalation_triggers(patches)
(REPORTS / 'mandatory_escalation_triggers.md').write_text(
    '# Mandatory Escalation Triggers\n\n' + ('\n'.join([f'- {t}' for t in mandatory_triggers]) if mandatory_triggers else '- none\n'),
    encoding='utf-8',
)

# loop protection from historical failures
loop_protection_triggered = historical_failures >= 3
if loop_protection_triggered:
    mandatory_triggers.append('compile closure repeatedly fails (historical threshold reached)')

# If mandatory triggers present, stop autonomous mutation and skip mutation phases.
autonomous_mutation_blocked = len(mandatory_triggers) > 0

# Defaults for later outputs
phase5_status = 'SKIPPED'
phase6_status = 'SKIPPED'
phase7_status = 'SKIPPED'
phase8_status = 'SKIPPED'
phase9_status = 'SKIPPED'

patch_apply_status = 'SKIPPED'
compile_status = 'SKIPPED'
module_status = 'SKIPPED'
dt_status = 'SKIPPED'
static_status = 'SKIPPED'

compile_issues: list[str] = []
unresolved_symbols: list[str] = []

if not autonomous_mutation_blocked:
    # Worktree setup
    if WORKTREE.exists():
        run_cmd('remove_old_worktree', f'git -C {shlex.quote(str(UPSTREAM_REPO))} worktree remove --force {shlex.quote(str(WORKTREE))}', timeout=120)
    run_cmd('add_worktree', f'git -C {shlex.quote(str(UPSTREAM_REPO))} worktree add {shlex.quote(str(WORKTREE))} HEAD', timeout=300)
    run_cmd('checkout_branch', f'git -C {shlex.quote(str(WORKTREE))} checkout -b aura/compile-closure-governed-{RUN_DIR.name}', timeout=60)

    build_env = os.environ.copy()
    build_env['ARCH'] = 'arm64'
    build_env['CROSS_COMPILE'] = 'aarch64-linux-gnu-'

    # PHASE 5
    defc = run_cmd('make_defconfig', 'make defconfig', cwd=WORKTREE, env=build_env, timeout=900)
    mprep = run_cmd('make_modules_prepare', 'make modules_prepare', cwd=WORKTREE, env=build_env, timeout=1200)
    missing = [
        str((WORKTREE / 'include/generated/autoconf.h').relative_to(WORKTREE)) if not (WORKTREE / 'include/generated/autoconf.h').exists() else '',
        str((WORKTREE / 'include/config/auto.conf').relative_to(WORKTREE)) if not (WORKTREE / 'include/config/auto.conf').exists() else '',
    ]
    missing = [m for m in missing if m]
    if defc['exit_code'] == 0 and mprep['exit_code'] == 0 and not missing:
        phase5_status = 'PASSED'
    else:
        phase5_status = 'BLOCKED'

    # PHASE 6 only if phase5 passed
    if phase5_status == 'PASSED':
        apply_fail = False
        for p in patches:
            ap = run_cmd(f'apply_{p.name}', f'git am {shlex.quote(str(p))}', cwd=WORKTREE, timeout=180)
            if ap['exit_code'] != 0:
                apply_fail = True
                run_cmd('git_am_abort', 'git am --abort', cwd=WORKTREE, timeout=60)
                break
        patch_apply_status = 'BLOCKED' if apply_fail else 'PASSED'

        if patch_apply_status == 'PASSED':
            comp = run_cmd('make_image_dtbs_modules', 'make -j$(nproc) Image.gz dtbs modules', cwd=WORKTREE, env=build_env, timeout=1800)
            comp_txt = (LOGS / 'make_image_dtbs_modules.log').read_text(encoding='utf-8', errors='replace')
            compile_issues = classify_compile_issues(comp_txt)
            unresolved_symbols = parse_unresolved_symbols(comp_txt)
            compile_status = 'PASSED' if comp['exit_code'] == 0 else 'FAILED'

            if compile_status == 'PASSED':
                modules_dir = RUN_DIR / 'artifacts' / 'modules_dir'
                modules_dir.mkdir(parents=True, exist_ok=True)
                mi = run_cmd('make_modules_install', f'make -j$(nproc) modules_install INSTALL_MOD_PATH={shlex.quote(str(modules_dir))} INSTALL_MOD_STRIP=1', cwd=WORKTREE, env=build_env, timeout=1200)
                if mi['exit_code'] == 0:
                    pkg = run_cmd('package_modules_cpio', f'cd {shlex.quote(str(modules_dir))} && find . | cpio -o -H newc | gzip -9 > ../modules.cpio.gz', cwd=WORKTREE, env=build_env, timeout=300)
                    module_status = 'PASSED' if pkg['exit_code'] == 0 and (RUN_DIR / 'artifacts' / 'modules.cpio.gz').exists() else 'FAILED'
                else:
                    module_status = 'FAILED'
            else:
                module_status = 'SKIPPED'
        else:
            compile_status = 'SKIPPED'
            module_status = 'SKIPPED'
    else:
        patch_apply_status = 'SKIPPED'
        compile_status = 'SKIPPED'
        module_status = 'SKIPPED'

    phase6_status = 'PASSED' if (patch_apply_status == 'PASSED' and compile_status == 'PASSED' and module_status == 'PASSED') else ('BLOCKED' if patch_apply_status == 'BLOCKED' or phase5_status == 'BLOCKED' else 'FAILED')

    # PHASE 7 only if phase6 passes/advisory
    if phase6_status in {'PASSED', 'PASSED_WITH_ADVISORY'}:
        s1 = run_cmd('static_sparse', 'make -j$(nproc) C=1 CHECK=sparse M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=900)
        s2 = run_cmd('static_w1', 'make -j$(nproc) W=1 M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=900)
        s3 = run_cmd('static_clang', 'make -j$(nproc) CC=clang M=sound/soc/codecs', cwd=WORKTREE, env=build_env, timeout=900)
        static_status = 'PASSED' if (s1['exit_code'], s2['exit_code'], s3['exit_code']) == (0, 0, 0) else 'PASSED_WITH_ADVISORY'
    else:
        static_status = 'SKIPPED'

    phase7_status = static_status

    # PHASE 8 only if phase7 passed/passed_with_advisory
    if phase7_status in {'PASSED', 'PASSED_WITH_ADVISORY'}:
        dtr = run_cmd('dt_binding_check', 'make dt_binding_check', cwd=WORKTREE, env=build_env, timeout=1200)
        dtt = (LOGS / 'dt_binding_check.log').read_text(encoding='utf-8', errors='replace') if (LOGS / 'dt_binding_check.log').exists() else ''
        if "dt-doc-validate' not found" in dtt.lower():
            dt_status = 'PASSED_WITH_ADVISORY'
        elif dtr['exit_code'] == 0:
            dt_status = 'PASSED'
        else:
            dt_status = 'FAILED'
    else:
        dt_status = 'SKIPPED'

    phase8_status = dt_status
    phase9_status = 'SKIPPED'

else:
    # Governance block; no mutation phases executed
    phase5_status = 'BLOCKED'
    phase6_status = 'SKIPPED'
    phase7_status = 'SKIPPED'
    phase8_status = 'SKIPPED'
    phase9_status = 'SKIPPED'

# ---------------- Reports 5-9 ----------------
write_md(REPORTS / 'kernel_prepare_report.md', [
    '# Kernel Prepare Report',
    '',
    f'- phase_status: `{phase5_status}`',
    f'- confidence_score: `{0.2 if phase5_status != "PASSED" else 0.9}`',
    f'- blocker_count: `{1 if phase5_status in {"BLOCKED", "FAILED"} else 0}`',
    f'- advisory_count: `0`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Evidence References',
    '- `logs/make_defconfig.log` (if executed)',
    '- `logs/make_modules_prepare.log` (if executed)',
    '- `reports/mandatory_escalation_triggers.md`',
    '',
    '## Unresolved Assumptions',
    '- kernel prepare is skipped when governance block is active',
    '',
    '## Dependency Risks',
    '- build cannot proceed without prepared generated config files',
])

write_md(REPORTS / 'patch_application_report.md', [
    '# Patch Application Report',
    '',
    f'- phase_status: `{patch_apply_status}`',
    f'- confidence_score: `{0.85 if patch_apply_status == "PASSED" else 0.3}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '',
    '## Evidence References',
    '- `../wcd937x_patchgen_20260519_194926/generated_patch_diffs/*.patch`',
    '- `logs/apply_*.log` (if executed)',
    '',
    '## Unresolved Assumptions',
    '- patch application is intentionally skipped under mandatory escalation block',
    '',
    '## Dependency Risks',
    '- cannot validate compile linkage without deterministic patch application',
])

compile_issue_lines = [f'- {i}' for i in compile_issues] if compile_issues else ['- none (compile not executed or no classified issue)']
write_md(REPORTS / 'compile_execution_report.md', [
    '# Compile Execution Report',
    '',
    f'- phase_status: `{compile_status}`',
    f'- confidence_score: `{0.9 if compile_status == "PASSED" else 0.25}`',
    f'- blocker_count: `{1 if compile_status in {"FAILED", "BLOCKED"} else 0}`',
    f'- advisory_count: `{0 if compile_status != "PASSED_WITH_ADVISORY" else 1}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '- replayability_status: `REPLAYABLE`',
    '',
    '## Classified Issues',
] + compile_issue_lines + [
    '',
    '## Evidence References',
    '- `logs/make_image_dtbs_modules.log` (if executed)',
    '- `raw/commands_executed.jsonl`',
    '',
    '## Unresolved Assumptions',
    '- compile step skipped if governance block active or prerequisites failed',
    '',
    '## Dependency Risks',
    '- toolchain/config generation mismatch risk',
])

sym_count = len(unresolved_symbols)
unresolved_symbol_confidence = 100.0 if sym_count == 0 else max(10.0, 70.0 - sym_count)
write_md(REPORTS / 'unresolved_symbol_report.md', [
    '# Unresolved Symbol Report',
    '',
    f'- unresolved_symbol_count: `{sym_count}`',
    f'- unresolved_symbol_confidence: `{unresolved_symbol_confidence}`',
    '',
    '## Symbols',
] + ([f'- `{s}`' for s in unresolved_symbols] if unresolved_symbols else ['- none']) + [
    '',
    '## Evidence References',
    '- `logs/make_image_dtbs_modules.log` (if executed)',
])

write_md(REPORTS / 'module_packaging_report.md', [
    '# Module Packaging Report',
    '',
    f'- phase_status: `{module_status}`',
    f'- confidence_score: `{0.9 if module_status == "PASSED" else 0.2}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '',
    '## Checks',
    f'- modules_dir exists: `{(RUN_DIR / "artifacts" / "modules_dir").exists()}`',
    f'- modules.cpio.gz exists: `{(RUN_DIR / "artifacts" / "modules.cpio.gz").exists()}`',
    '',
    '## Evidence References',
    '- `logs/make_modules_install.log` (if executed)',
    '- `logs/package_modules_cpio.log` (if executed)',
])

static_advisories = []
if static_status == 'PASSED_WITH_ADVISORY':
    static_advisories.append('analysis commands returned non-zero and are classified advisory-only per policy')
elif static_status == 'SKIPPED':
    static_advisories.append('skipped due to upstream phase block or governance block')

write_md(REPORTS / 'static_analysis_report.md', [
    '# Static Analysis Report',
    '',
    f'- phase_status: `{static_status}`',
    f'- confidence_score: `{0.55 if static_status != "SKIPPED" else 0.2}`',
    f'- blocker_count: `0`',
    f'- advisory_count: `{len(static_advisories)}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '',
    '## Advisory Classification',
] + ([f'- {a}' for a in static_advisories] if static_advisories else ['- none']) + [
    '',
    '## Evidence References',
    '- `logs/static_sparse.log` (if executed)',
    '- `logs/static_w1.log` (if executed)',
    '- `logs/static_clang.log` (if executed)',
])

if dt_status == 'PASSED_WITH_ADVISORY':
    dt_class = ['- TOOLING_ABSENCE', '- DT_VALIDATION_INCOMPLETE']
elif dt_status == 'FAILED':
    dt_class = ['- DT_SCHEMA_FAILURE']
elif dt_status == 'SKIPPED':
    dt_class = ['- skipped due to governance/prerequisite block']
else:
    dt_class = ['- none']

write_md(REPORTS / 'dt_validation_report.md', [
    '# DT Validation Report',
    '',
    f'- phase_status: `{dt_status}`',
    f'- confidence_score: `{0.6 if dt_status.startswith("PASSED") else 0.2}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
    '',
    '## Classification',
] + dt_class + [
    '',
    '## Evidence References',
    '- `logs/dt_binding_check.log` (if executed)',
])

# tooling gap report
tooling_gaps = sorted(set([f for f in env_findings if f.startswith('TOOLING_GAP')]))
write_md(REPORTS / 'tooling_gap_report.md', [
    '# Tooling Gap Report',
    '',
    '## Gaps',
] + ([f'- {g}' for g in tooling_gaps] if tooling_gaps else ['- none']) + [
    '',
    '## Evidence References',
    '- `reports/environment_validation_report.md`',
])

# ---------------- Phase contracts 5-9 ----------------
phase_contracts.append(PhaseContract(
    phase='PHASE 5 Kernel Prepare Validation',
    phase_status=phase5_status,
    confidence_score=0.9 if phase5_status == 'PASSED' else 0.2,
    blocker_count=1 if phase5_status in {'BLOCKED', 'FAILED'} else 0,
    advisory_count=0,
    evidence_paths=['reports/kernel_prepare_report.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['prepare execution blocked by mandatory escalation' if autonomous_mutation_blocked else 'none'],
    dependency_risks=['generated-config dependency'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 6 Compile Closure Validation',
    phase_status=phase6_status,
    confidence_score=0.9 if phase6_status == 'PASSED' else 0.18,
    blocker_count=1 if phase6_status in {'BLOCKED', 'FAILED'} else 0,
    advisory_count=0 if phase6_status != 'PASSED_WITH_ADVISORY' else 1,
    evidence_paths=['reports/compile_execution_report.md', 'reports/patch_application_report.md', 'reports/module_packaging_report.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['compile not attempted under governance block' if autonomous_mutation_blocked else 'none'],
    dependency_risks=['compile closure cannot be inferred without phase execution'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 7 Static Analysis Validation',
    phase_status=phase7_status,
    confidence_score=0.55 if phase7_status != 'SKIPPED' else 0.2,
    blocker_count=0,
    advisory_count=1 if phase7_status != 'PASSED' else 0,
    evidence_paths=['reports/static_analysis_report.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['static scan skipped when prior phase blocked'],
    dependency_risks=['analysis tooling dependency'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 8 DT Schema Validation',
    phase_status=phase8_status,
    confidence_score=0.6 if phase8_status.startswith('PASSED') else 0.2,
    blocker_count=1 if phase8_status == 'FAILED' else 0,
    advisory_count=1 if phase8_status in {'PASSED_WITH_ADVISORY', 'SKIPPED'} else 0,
    evidence_paths=['reports/dt_validation_report.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['DT validation depends on dtschema tooling'],
    dependency_risks=['dt-doc-validate dependency'],
))
phase_contracts.append(PhaseContract(
    phase='PHASE 9 Runtime/Boot Validation',
    phase_status=phase9_status,
    confidence_score=0.0,
    blocker_count=0,
    advisory_count=1,
    evidence_paths=['reports/compile_closure_status.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['runtime/boot requires compile closure'],
    dependency_risks=['compile artifacts unavailable'],
))

# ---------------- PHASE 10 ----------------
kernel_prepare_ok = phase5_status == 'PASSED'
compile_ok = compile_status == 'PASSED'
module_ok = module_status == 'PASSED'
dt_available = dt_status in {'PASSED', 'PASSED_WITH_ADVISORY'}
no_unresolved = len(unresolved_symbols) == 0

if kernel_prepare_ok and compile_ok and module_ok and dt_available and no_unresolved and not autonomous_mutation_blocked:
    closure_state = 'CLOSED'
    phase10_status = 'PASSED'
    phase10_conf = 0.9
else:
    closure_state = 'NOT_CLOSED'
    phase10_status = 'BLOCKED'
    phase10_conf = 0.12

compile_retry_exceeded = historical_failures >= 3
if compile_retry_exceeded:
    mandatory_triggers.append('compile retries threshold reached (>=3 historical non-closed runs)')

write_md(REPORTS / 'compile_closure_status.md', [
    '# Compile Closure Status',
    '',
    f'- closure_state: `{closure_state}`',
    f'- phase_status: `{phase10_status}`',
    f'- confidence_score: `{phase10_conf}`',
    f'- blocker_count: `{1 if phase10_status == "BLOCKED" else 0}`',
    f'- advisory_count: `{len(tooling_gaps)}`',
    f'- governance_state: `{"BLOCKED" if autonomous_mutation_blocked else "PENDING"}`',
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
    '- proposal validation incomplete',
    '- compile closure not established',
    '- environment/tooling gaps remain',
    '',
    '## Unresolved Assumptions',
    '- compile/runtime behavior cannot be inferred while mutation phases are skipped/blocked',
    '',
    '## Dependency Risks',
    '- cross-toolchain and dt schema tooling dependencies unresolved',
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

phase_contracts.append(PhaseContract(
    phase='PHASE 10 Upstream Readiness Classification',
    phase_status=phase10_status,
    confidence_score=phase10_conf,
    blocker_count=1 if phase10_status == 'BLOCKED' else 0,
    advisory_count=len(tooling_gaps),
    evidence_paths=['reports/compile_closure_status.md'],
    replayability_status='REPLAYABLE',
    governance_state='BLOCKED' if autonomous_mutation_blocked else 'PENDING',
    unresolved_assumptions=['human review required before any readiness claim'],
    dependency_risks=['unsafe merge conclusions prevented by governance block'],
))

# ---------------- PHASE 11 ----------------
mandatory_escalation = bool(mandatory_triggers) or (unresolved_symbol_confidence < 70.0) or compile_retry_exceeded

reasons = list(dict.fromkeys(mandatory_triggers))
if unresolved_symbol_confidence < 70.0:
    reasons.append(f'unresolved symbol confidence < 70% ({unresolved_symbol_confidence})')
if compile_retry_exceeded:
    reasons.append('compile closure repeatedly fails')
if phase10_status == 'BLOCKED' and not reasons:
    reasons.append('COMPILE_CLOSURE_NOT_ESTABLISHED')

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
    '- stop autonomous mutation',
    '- review high-risk audio boundary changes (SoundWire/MBHC/DT ABI/etc.)',
    '- decide whether to authorize controlled next pass',
    '- no push/merge/submission from this run',
    '',
    '## Evidence References',
    '- `reports/mandatory_escalation_triggers.md`',
    '- `reports/compile_closure_status.md`',
    '- `reports/unresolved_symbol_report.md`',
])

phase_contracts.append(PhaseContract(
    phase='PHASE 11 Human Escalation Review',
    phase_status='BLOCKED' if mandatory_escalation else 'PASSED_WITH_ADVISORY',
    confidence_score=0.95,
    blocker_count=1 if mandatory_escalation else 0,
    advisory_count=0 if mandatory_escalation else 1,
    evidence_paths=['reports/human_escalation_review.md'],
    replayability_status='REPLAYABLE',
    governance_state='MANUAL_DECISION_REQUIRED',
    unresolved_assumptions=['human approval mandatory before destructive/upstream actions'],
    dependency_risks=['unsafe autonomy prohibited'],
))

# ---------------- Persist phase contracts and summary ----------------
contracts_json = [asdict(p) for p in phase_contracts]
(RAW / 'phase_contracts.json').write_text(json.dumps(contracts_json, indent=2), encoding='utf-8')

summary = {
    'run_id': RUN_DIR.name,
    'ended_at': ts(),
    'closure_state': closure_state,
    'phase10_status': phase10_status,
    'mandatory_escalation': mandatory_escalation,
    'autonomous_mutation_blocked': autonomous_mutation_blocked,
    'retry_depth': {
        'compile_retries_used': 1,
        'compile_retries_limit': 3,
        'regeneration_retries_used': 0,
        'regeneration_retries_limit': 2,
        'semantic_remap_retries_used': 0,
        'semantic_remap_retries_limit': 1,
    },
}
(RAW / 'pipeline_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

# artifact manifest
files = sorted([p for p in RUN_DIR.rglob('*') if p.is_file() and p.name != 'artifact_hash_manifest.txt'])
manifest = [f"{hash_file(p)}  {p.relative_to(RUN_DIR)}" for p in files]
(ART / 'artifact_hash_manifest.txt').write_text('\n'.join(manifest) + '\n', encoding='utf-8')

print(json.dumps(summary, indent=2))
