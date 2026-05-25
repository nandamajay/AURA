# Environment Validation Report

- phase_status: `PASSED_WITH_ADVISORY`
- confidence_score: `0.71`
- blocker_count: `0`
- advisory_count: `5`
- governance_state: `PENDING_REVIEW`
- replayability_status: `REPLAYABLE`

## Tool Availability
- make: `/usr/bin/make`
- clang: `MISSING`
- sparse: `/usr2/nandam/.local/bin/sparse`
- dt-doc-validate: `MISSING`
- python3: `/usr/bin/python3`
- cpio: `/usr/bin/cpio`
- gzip: `/usr/bin/gzip`

## Kernel Tree Integrity
- git_ok: `True`
- makefile_exists: `True`
- kconfig_exists: `True`

## Findings
- TOOLING_GAP:ARCH_not_set_in_caller_env
- TOOLING_GAP:CROSS_COMPILE_not_set_in_caller_env
- TOOLING_GAP:clang_missing
- TOOLING_GAP:dt-doc-validate_missing
- TOOLING_GAP:python_dep_dtschema_missing

## Unresolved Assumptions
- aarch64 cross toolchain may still be absent at build execution time

## Dependency Risks
- dt schema tooling absence may block DT closure
- sparse/clang absence may downgrade static analysis confidence

## Evidence References
- `raw/commands_executed.jsonl`
- `raw/run_metadata.json`
