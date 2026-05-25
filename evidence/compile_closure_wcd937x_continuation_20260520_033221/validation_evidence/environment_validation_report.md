# Environment Validation Report

- phase_status: `PASSED_WITH_ADVISORY`
- confidence_score: `0.72`
- blocker_count: `0`
- advisory_count: `5`
- governance_state: `CONTROLLED_CONTINUATION`
- replayability_status: `REPLAYABLE`

## Tool Availability
- make: `/usr/bin/make`
- clang: `MISSING`
- sparse: `/usr2/nandam/.local/bin/sparse`
- dt-doc-validate: `MISSING`
- python3: `/usr/bin/python3`
- cpio: `/usr/bin/cpio`
- gzip: `/usr/bin/gzip`
- git: `/usr/bin/git`
- aarch64-linux-gnu-gcc: `/usr/bin/aarch64-linux-gnu-gcc`

## Kernel Tree Integrity
- makefile_exists: `True`
- kconfig_exists: `True`
- git_rev_parse_ok: `True`

## Findings
- TOOLING_GAP:clang_missing
- TOOLING_GAP:dt-doc-validate_missing
- TOOLING_GAP:ARCH_not_set_in_caller_env
- TOOLING_GAP:CROSS_COMPILE_not_set_in_caller_env
- TOOLING_GAP:python_dep_dtschema_missing

## Evidence References
- `raw/commands_executed.jsonl`
- `raw/run_metadata.json`
