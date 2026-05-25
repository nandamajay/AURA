from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

run_dir = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926')
reports = run_dir / 'reports'
reports.mkdir(parents=True, exist_ok=True)
raw = run_dir / 'raw'
artifacts = run_dir / 'artifacts'
logs = run_dir / 'logs'
source_study = Path('/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557')

runtime_ids = json.loads((raw / 'runtime_ids.json').read_text())
workflow_rows = json.loads((raw / 'workflow_rows.json').read_text())
workflow = workflow_rows[0] if workflow_rows else {}
validation_rows = json.loads((raw / 'validation_runs_rows.json').read_text())
lineage_rows = json.loads((raw / 'source_lineage_rows.json').read_text())
gov_rows = json.loads((raw / 'governance_actions_rows.json').read_text())
evidence_rows = json.loads((raw / 'engineering_evidence_links_rows.json').read_text())
trace = json.loads((raw / 'runtime_lifecycle_trace.json').read_text())
exit_codes = {}
for line in (artifacts / 'validation_exit_codes.txt').read_text().splitlines():
    if '=' in line:
        k, v = line.split('=', 1)
        exit_codes[k.strip()] = v.strip()

patch_files = sorted(p.name for p in (run_dir / 'generated_patch_diffs').glob('*.patch'))

group_rows = [
    {
        'group': 'Group 1: build/symbol wiring',
        'patch': '0001-ASoC-codecs-wcd937x-annotate-build-wiring-constraint.patch',
        'commit_message': 'ASoC: codecs: wcd937x: annotate build wiring constraints for migration',
        'rationale': 'Keep WCD937x core/SDW split explicit and surface migration constraints at Kconfig/Makefile boundary.',
        'affected_dependencies': 'Kconfig symbol graph, Makefile object wiring, SND_SOC_WCD937X(_SDW)',
        'status': 'advisory-only',
        'blockers': 'No sign-off/commit body yet; needs maintainer-quality message and operator review.',
        'validation_expectations': 'checkpatch clean after sign-off/message fixes; compile depends on prepared kernel config.',
    },
    {
        'group': 'Group 2: codec core port',
        'patch': '0002-ASoC-codecs-wcd937x-add-core-port-migration-guardrai.patch',
        'commit_message': 'ASoC: codecs: wcd937x: add core-port migration guardrails',
        'rationale': 'Annotate codec core boundary to prevent downstream-only hooks from being reintroduced during porting.',
        'affected_dependencies': 'wcd937x core, wcd-common, mbhc/clsh integration path, regmap/pm-runtime touchpoints',
        'status': 'advisory-only',
        'blockers': 'No functional downstream feature parity implemented in this patch; comments only.',
        'validation_expectations': 'No functional regression expected; final port requires real code deltas + compile closure.',
    },
    {
        'group': 'Group 3: SoundWire transport migration',
        'patch': '0003-ASoC-codecs-wcd937x-sdw-document-SWR-to-SDW-migratio.patch',
        'commit_message': 'ASoC: codecs: wcd937x-sdw: document SWR to SDW migration boundary',
        'rationale': 'Capture SWR→SDW ownership boundary explicitly before functional transport-porting changes.',
        'affected_dependencies': 'wcd937x-sdw channel maps, sdw_stream_add_slave path, SDW transport assumptions',
        'status': 'advisory-only',
        'blockers': 'Real transport semantic conversion still unresolved; no SWR compatibility shim included.',
        'validation_expectations': 'Compile subject to prepared kernel tree; follow-up patch needed for behavior alignment.',
    },
    {
        'group': 'Group 4: MBHC/CLSH alignment',
        'patch': '0004-ASoC-codecs-add-MBHC-CLSH-conversion-alignment-notes.patch',
        'commit_message': 'ASoC: codecs: add MBHC/CLSH conversion alignment notes for WCD937x',
        'rationale': 'Flag MBHC and Class-H as dedicated validation gates for WCD937x migration sequencing.',
        'affected_dependencies': 'wcd-mbhc-v2, wcd-clsh-v2, headset detect flow, class-H power path',
        'status': 'advisory-only',
        'blockers': 'No callback behavior rewrite yet; downstream calibration interactions unresolved.',
        'validation_expectations': 'Needs targeted runtime audio validation once functional patches exist.',
    },
    {
        'group': 'Group 5: downstream abstraction removal',
        'patch': '0005-ASoC-codecs-wcd937x-record-downstream-abstraction-ex.patch',
        'commit_message': 'ASoC: codecs: wcd937x: record downstream abstraction exclusion boundaries',
        'rationale': 'Pin explicit exclusion of qti-regmap-debugfs/msm_cdc/wcdcal wrappers in upstream codec scope.',
        'affected_dependencies': 'qti-regmap-debugfs, msm_cdc_* wrappers, wcdcal hwdep calibration path',
        'status': 'blocked',
        'blockers': 'No upstream-equivalent implementation for excluded downstream abstractions in current patchset.',
        'validation_expectations': 'Cannot claim upstream compatibility until replacement strategy is implemented and validated.',
    },
    {
        'group': 'Group 6: DT binding alignment',
        'patch': '0006-dt-bindings-sound-qcom-wcd937x-clarify-upstream-sche.patch',
        'commit_message': 'dt-bindings: sound: qcom,wcd937x: clarify upstream schema boundary',
        'rationale': 'Keep DT schema as upstream contract and reject downstream helper abstractions in binding surface.',
        'affected_dependencies': 'qcom,wcd937x.yaml schema semantics, DT validation pipeline',
        'status': 'advisory-only',
        'blockers': 'dt-doc-validate tool missing in current environment; schema checks not fully executable.',
        'validation_expectations': 'dt_binding_check must pass with dtschema installed before submission.',
    },
]

# 1) upstream_patch_series_plan.md
series_lines = [
    '# Upstream Patch Series Plan (Controlled Proposal)',
    '',
    f'Generated: `{datetime.now(timezone.utc).isoformat()}`',
    '',
    '## Workflow Binding',
    f"- intake_id: `{runtime_ids['intake_id']}`",
    f"- source_snapshot_id: `{runtime_ids['source_snapshot_id']}`",
    f"- engineering_snapshot_id: `{runtime_ids['engineering_snapshot_id']}`",
    f"- workflow_id: `{runtime_ids['workflow_id']}`",
    f"- task_id: `{runtime_ids['task_id']}`",
    f"- provenance: `{runtime_ids['source_repo']}` @ `{runtime_ids['source_branch']}` (`{runtime_ids['source_head_commit']}`)",
    '',
    '## Patch Groups',
]
for row in group_rows:
    series_lines.extend([
        f"### {row['group']}",
        f"- proposed git diff: `generated_patch_diffs/{row['patch']}`",
        f"- commit message: `{row['commit_message']}`",
        f"- upstream rationale: {row['rationale']}",
        f"- affected dependencies: {row['affected_dependencies']}",
        f"- unresolved blockers: {row['blockers']}",
        f"- validation expectations: {row['validation_expectations']}",
        f"- replay evidence linkage: workflow `{runtime_ids['workflow_id']}` evidence table + lineage stage entries",
        f"- classification: **{row['status']}**",
        '',
    ])
series_lines.extend([
    '## Classification Summary',
    '- compile-ready: none (0)',
    '- advisory-only: groups 1,2,3,4,6',
    '- blocked: group 5',
    '- unresolved dependency state: present (downstream-only abstraction parity incomplete + environment/tooling gaps)',
    '',
    '## Authoritative Inputs Used',
    f"- `{source_study}/reports/dependency_graph_report.md`",
    f"- `{source_study}/reports/downstream_upstream_api_mapping_report.md`",
    f"- `{source_study}/reports/semantic_transformation_plan.md`",
    f"- `{source_study}/reports/patch_grouping_proposal.md`",
    f"- `{source_study}/reports/replay_lineage_report.md`",
])
(reports / 'upstream_patch_series_plan.md').write_text('\n'.join(series_lines) + '\n', encoding='utf-8')

# 2) validation_execution_report.md
checkpatch_log = (logs / 'checkpatch.log').read_text(encoding='utf-8', errors='replace')
cp_errors = checkpatch_log.count('ERROR:')
cp_warn = checkpatch_log.count('WARNING:')
val_lines = [
    '# Validation Execution Report',
    '',
    f"- workflow_id: `{runtime_ids['workflow_id']}`",
    f"- validation_status (runtime): `{runtime_ids['workflow_validation_status']}`",
    '',
    '## External Validation Attempts',
    f"- patchwise Checkpatch+Sparse exit: `{exit_codes.get('patchwise_checkpatch_sparse', '')}` (timeout/non-completion)",
    f"- checkpatch exit: `{exit_codes.get('checkpatch', '')}`",
    f"- sparse exit: `{exit_codes.get('sparse', '')}`",
    f"- clang exit: `{exit_codes.get('clang', '')}`",
    f"- dt_binding_check exit: `{exit_codes.get('dt_binding_check', '')}`",
    f"- compile_scope exit: `{exit_codes.get('compile_scope', '')}`",
    '',
    f"- checkpatch findings count: errors={cp_errors}, warnings={cp_warn}",
    '',
    '## Runtime Validation Rows (API)',
]
for row in validation_rows:
    val_lines.append(
        f"- tool={row['tool_name']} passed={row['passed']} version={row['tool_version']} findings={row['findings_json']}"
    )
val_lines.extend([
    '',
    '## Honest Result',
    '- Validation did not reach compile closure.',
    '- No upstream-readiness claim is made in this phase.',
    '',
    '## Logs',
    '- `logs/patchwise_checkpatch_sparse.log`',
    '- `logs/checkpatch.log`',
    '- `logs/sparse.log`',
    '- `logs/clang.log`',
    '- `logs/dt_binding_check.log`',
    '- `logs/compile_scope.log`',
])
(reports / 'validation_execution_report.md').write_text('\n'.join(val_lines) + '\n', encoding='utf-8')

# 3) governance_decision_report.md
gov_lines = [
    '# Governance Decision Report',
    '',
    f"- workflow_id: `{runtime_ids['workflow_id']}`",
    f"- governance_state: `{workflow.get('governance_state', '')}`",
    '',
    '## Governance Timeline',
]
for row in gov_rows:
    gov_lines.append(
        f"- id={row['id']} op=`{row['operation']}` status=`{row['status']}` reason=`{row['reason']}` requested_by=`{row['requested_by']}` decided_by=`{row['decided_by']}`"
    )
gov_lines.extend([
    '',
    '## Gate Enforcement',
    '- No governance approval decision was auto-executed for transformation_proposal.',
    '- Workflow remains approval-gated pending operator action.',
    '- NO auto-merge / NO auto-apply preserved.',
])
(reports / 'governance_decision_report.md').write_text('\n'.join(gov_lines) + '\n', encoding='utf-8')

# 4) replay_patch_lineage_report.md
replay_lines = [
    '# Replay Patch Lineage Report',
    '',
    f"- workflow_id: `{runtime_ids['workflow_id']}`",
    f"- task_id: `{runtime_ids['task_id']}`",
    f"- workflow_reconstruction_hash: `{runtime_ids['workflow_reconstruction_hash']}`",
    f"- source_reconstruction_hash: `{runtime_ids['source_reconstruction_hash']}`",
    f"- workflow_trust_valid: `{runtime_ids['workflow_trust_valid']}`",
    '',
    '## Source Lineage Chain',
]
for row in lineage_rows:
    replay_lines.append(
        f"- stage=`{row['lineage_stage']}` hash=`{row['lineage_hash']}` parent=`{row['parent_lineage_hash']}`"
    )
replay_lines.extend([
    '',
    f"## Workflow Evidence Links ({len(evidence_rows)})",
])
for row in evidence_rows:
    replay_lines.append(
        f"- id={row['id']} type=`{row['evidence_type']}` ref=`{row['evidence_ref']}` hash=`{row['evidence_hash']}`"
    )
replay_lines.extend([
    '',
    '## Replay Notes',
    '- Patch proposal artifacts are replay-linked via engineering_evidence_links.',
    '- Governance decision remains pending; lineage is complete up to approval request stage.',
])
(reports / 'replay_patch_lineage_report.md').write_text('\n'.join(replay_lines) + '\n', encoding='utf-8')

# 5) unresolved_gap_analysis.md
unresolved_lines = [
    '# Unresolved Gap Analysis',
    '',
    '## Functional/Architecture Gaps',
    '- Downstream-only abstractions unresolved: qti-regmap-debugfs, msm_cdc_* wrappers, wcdcal hwdep path.',
    '- Proposed patches are mostly annotation/scoping deltas, not full behavioral upstream parity implementation.',
    '- Governance decision for transformation proposal intentionally pending operator approval.',
    '',
    '## Tooling/Environment Gaps',
    '- Kernel tree not prepared for module compile (`include/generated/autoconf.h` and `include/config/auto.conf` missing).',
    '- dt schema tool missing (`dt-doc-validate`).',
    '- patchwise run did not complete within timeout window.',
    '',
    '## Mapping Gaps (from authoritative mapping report)',
    '- No confirmed direct upstream equivalent for qti-regmap-debugfs.',
    '- No confirmed direct upstream equivalent for wcdcal hooks.',
    '- No confirmed direct upstream equivalent for msm_cdc wrapper layer.',
]
(reports / 'unresolved_gap_analysis.md').write_text('\n'.join(unresolved_lines) + '\n', encoding='utf-8')

# 6) compile_closure_status.md
compile_lines = [
    '# Compile Closure Status',
    '',
    '- closure_state: **NOT_CLOSED**',
    '- reason: kernel source tree in patch-proposal worktree is not prepared for build/analysis targets.',
    '',
    '## Evidence',
    f"- sparse exit `{exit_codes.get('sparse', '')}` with missing autoconf/include config",
    f"- clang exit `{exit_codes.get('clang', '')}` with same missing generated config",
    f"- compile_scope exit `{exit_codes.get('compile_scope', '')}` with same missing generated config",
    f"- dt_binding_check exit `{exit_codes.get('dt_binding_check', '')}` due missing dt-doc-validate",
    '',
    '## Truthful Classification',
    '- compile-ready patch group count: 0',
    '- advisory-only patch group count: 5',
    '- blocked patch group count: 1',
    '- upstream merge readiness: **not established**',
]
(reports / 'compile_closure_status.md').write_text('\n'.join(compile_lines) + '\n', encoding='utf-8')

# 7) lifecycle_execution_report.md (requested by phase requirements)
lifecycle_lines = [
    '# Lifecycle Execution Report',
    '',
    f"- intake_id: `{runtime_ids['intake_id']}`",
    f"- source_snapshot_id: `{runtime_ids['source_snapshot_id']}`",
    f"- engineering_snapshot_id: `{runtime_ids['engineering_snapshot_id']}`",
    f"- workflow_id: `{runtime_ids['workflow_id']}`",
    f"- task_id: `{runtime_ids['task_id']}`",
    '',
    '## Executed Lifecycle',
    '1. source_intake',
    '2. snapshot_frozen',
    '3. task_created',
    '4. patch_analysis',
    '5. transformation_proposal',
    '6. validation_running (completed -> failed)',
    '7. governance_review (request persisted, decision pending operator)',
    '',
    '## Detached Execution Guard',
    '- Verified: detached engineering task creation rejected with HTTP 400.',
    '',
    '## Replay/Governance State',
    f"- workflow_reconstruction_hash: `{runtime_ids['workflow_reconstruction_hash']}`",
    f"- workflow_trust_valid: `{runtime_ids['workflow_trust_valid']}`",
    f"- governance_state: `{workflow.get('governance_state', '')}`",
]
(reports / 'lifecycle_execution_report.md').write_text('\n'.join(lifecycle_lines) + '\n', encoding='utf-8')

# simple index
index_lines = [
    '# WCD937x Controlled Patch Generation Index',
    '',
    f"Generated: `{datetime.now(timezone.utc).isoformat()}`",
    '',
    '## Required Deliverables',
    '- `reports/upstream_patch_series_plan.md`',
    '- `generated_patch_diffs/`',
    '- `reports/validation_execution_report.md`',
    '- `reports/governance_decision_report.md`',
    '- `reports/replay_patch_lineage_report.md`',
    '- `reports/unresolved_gap_analysis.md`',
    '- `reports/compile_closure_status.md`',
    '',
    '## Additional',
    '- `reports/lifecycle_execution_report.md`',
    '- `raw/runtime_lifecycle_trace.json`',
    '- `raw/runtime_ids.json`',
]
(reports / 'WCD937x_controlled_patch_generation_index.md').write_text('\n'.join(index_lines) + '\n', encoding='utf-8')

# manifest
report_files = sorted(str(p.relative_to(run_dir)) for p in reports.glob('*.md'))
(run_dir / 'artifacts' / 'report_files.txt').write_text('\n'.join(report_files) + '\n', encoding='utf-8')
sha_lines = []
for rel in report_files:
    p = run_dir / rel
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    sha_lines.append(f"{h}  {rel}")
(run_dir / 'artifacts' / 'report_manifest_sha256.txt').write_text('\n'.join(sha_lines) + '\n', encoding='utf-8')
bundle_hash = hashlib.sha256((run_dir / 'artifacts' / 'report_manifest_sha256.txt').read_bytes()).hexdigest()
(run_dir / 'artifacts' / 'report_manifest_bundle.sha256').write_text(bundle_hash + '\n', encoding='utf-8')

print('reports_generated')
