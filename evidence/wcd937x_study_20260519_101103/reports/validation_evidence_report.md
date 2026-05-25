# Validation Evidence Report

## Runtime Validation (AURA engineering endpoint)
- workflow_id: `d285331f26c70c20ac81f9ed3b273279`
- status: `failed`

| Tool | Passed | Tool version | Findings |
|---|---:|---|---|
| checkpatch | 0 | `unavailable` | `["tool_unavailable:checkpatch","version_drift:checkpatch:expected=checkpatch:observed=unavailable"]` |
| clang_build | 0 | `unavailable` | `["tool_unavailable:clang_build","version_drift:clang_build:expected=clang:observed=unavailable","clang_build_probe_failed:command_not_found:clang"]` |
| forbidden_path | 1 | `builtin-v1` | `["forbidden_path_check_passed"]` |
| lineage_integrity | 1 | `builtin-v1` | `[]` |
| sparse | 0 | `unavailable` | `["tool_unavailable:sparse","version_drift:sparse:expected=sparse:observed=unavailable"]` |

## External Validation Commands
- checkpatch exit: `1`
- sparse probe exit: `126`
- clang probe exit: `127`
- compile scope attempt 1 exit: `2`
- compile scope attempt 2 exit: `2`
- dt binding check exit: `2`
- forbidden pattern scan exit: `0`

## checkpatch Aggregate (downstream snapshot files)
- aggregated errors: `14`
- aggregated warnings: `44`
- aggregated lines checked: `8452`

## Observed Hard Failures / Gaps
- sparse unavailable / not executable in environment.
- clang not installed.
- dt-binding check failed due missing `dt-doc-validate` (dtschema tooling).
- direct compile scope attempt failed with missing kernel arch include (`asm/types.h`) in host setup.

## Raw Logs
- `logs/checkpatch.log`
- `logs/sparse.log`
- `logs/clang.log`
- `logs/compile_scope.log`
- `logs/compile_scope_retry.log`
- `logs/dt_binding_check.log`
- `logs/forbidden_pattern_scan.log`
