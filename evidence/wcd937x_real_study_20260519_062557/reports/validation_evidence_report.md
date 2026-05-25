# Validation Evidence Report

## Engineering Runtime Validation Status: `failed`

| Tool | Passed | Version | Findings |
|---|---:|---|---|
| checkpatch | 0 | `unavailable` | `["tool_unavailable:checkpatch","version_drift:checkpatch:expected=checkpatch:observed=unavailable"]` |
| clang_build | 0 | `unavailable` | `["tool_unavailable:clang_build","version_drift:clang_build:expected=clang:observed=unavailable","clang_build_probe_failed:command_not_found:clang"]` |
| forbidden_path | 1 | `builtin-v1` | `["forbidden_path_check_passed"]` |
| lineage_integrity | 1 | `builtin-v1` | `[]` |
| sparse | 0 | `unavailable` | `["tool_unavailable:sparse","version_drift:sparse:expected=sparse:observed=unavailable"]` |

## External Validation Runs
- checkpatch exit: `1`
- sparse probe exit: `126`
- clang probe exit: `127`
- compile scope exit: `2`
- dt binding check exit: `2`
- forbidden pattern scan exit: `0`

- checkpatch errors/warnings/lines: `14/45/8632`

## Blockers
- sparse unavailable
- clang unavailable
- dt-doc-validate missing
- compile env missing asm include path

## Raw Logs
- `logs/checkpatch.log`
- `logs/sparse.log`
- `logs/clang.log`
- `logs/compile_scope.log`
- `logs/dt_binding_check.log`
- `logs/forbidden_pattern_scan.log`
