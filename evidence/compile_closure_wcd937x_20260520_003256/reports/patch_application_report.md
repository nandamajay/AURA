# Patch Application Report

- phase_status: `SKIPPED`
- confidence_score: `0.3`
- governance_state: `BLOCKED`

## Evidence References
- `../wcd937x_patchgen_20260519_194926/generated_patch_diffs/*.patch`
- `logs/apply_*.log` (if executed)

## Unresolved Assumptions
- patch application is intentionally skipped under mandatory escalation block

## Dependency Risks
- cannot validate compile linkage without deterministic patch application
