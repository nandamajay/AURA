# Compile Execution Report

- phase_status: `SKIPPED`
- confidence_score: `0.25`
- blocker_count: `0`
- advisory_count: `0`
- governance_state: `BLOCKED`
- replayability_status: `REPLAYABLE`

## Classified Issues
- none (compile not executed or no classified issue)

## Evidence References
- `logs/make_image_dtbs_modules.log` (if executed)
- `raw/commands_executed.jsonl`

## Unresolved Assumptions
- compile step skipped if governance block active or prerequisites failed

## Dependency Risks
- toolchain/config generation mismatch risk
