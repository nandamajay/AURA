# Replay Boundary Assessment

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Evidence
- Replay during active pressure: `{'404': 53, '200': 187}`
- Replay after stabilization (per domain):
- `driver`: {'200': 14} integrity_ok=14/14
- `media`: {'200': 14} integrity_ok=14/14
- `automation`: {'200': 14} integrity_ok=14/14
- `research`: {'200': 14} integrity_ok=14/14

## Namespace Validation
- expected_task_count: `56`
- found_task_log_count: `56`
- missing_task_log_count: `0`
- namespace_mismatch_count: `0`
- found_domain_counts: `{'driver': 14, 'media': 14, 'automation': 14, 'research': 14}`

## Classification
- Proven: per-task replay lineage retained domain marker with zero mismatches in this run.
- Bounded: active-run replay returns non-200 (`404`) before finalization.
- Unproven: hard runtime namespace enforcement independent of task/input conventions.
