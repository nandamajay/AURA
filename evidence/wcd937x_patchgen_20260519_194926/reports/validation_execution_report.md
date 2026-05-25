# Validation Execution Report

- workflow_id: `f1a7203028b455b0b1086517d3070801`
- validation_status (runtime): `failed`

## External Validation Attempts
- patchwise Checkpatch+Sparse exit: `124` (timeout/non-completion)
- checkpatch exit: `1`
- sparse exit: `2`
- clang exit: `2`
- dt_binding_check exit: `2`
- compile_scope exit: `2`

- checkpatch findings count: errors=6, warnings=6

## Runtime Validation Rows (API)
- tool=checkpatch passed=0 version=unavailable findings=["tool_unavailable:checkpatch","version_drift:checkpatch:expected=checkpatch:observed=unavailable"]
- tool=clang_build passed=0 version=unavailable findings=["tool_unavailable:clang_build","version_drift:clang_build:expected=clang:observed=unavailable"]
- tool=forbidden_path passed=1 version=builtin-v1 findings=["forbidden_path_check_passed"]
- tool=lineage_integrity passed=1 version=builtin-v1 findings=[]
- tool=sparse passed=0 version=unavailable findings=["tool_unavailable:sparse","version_drift:sparse:expected=sparse:observed=unavailable"]

## Honest Result
- Validation did not reach compile closure.
- No upstream-readiness claim is made in this phase.

## Logs
- `logs/patchwise_checkpatch_sparse.log`
- `logs/checkpatch.log`
- `logs/sparse.log`
- `logs/clang.log`
- `logs/dt_binding_check.log`
- `logs/compile_scope.log`
