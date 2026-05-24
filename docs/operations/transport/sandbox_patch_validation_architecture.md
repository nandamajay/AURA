# Sandbox Patch Validation and Real Transformation Governance Architecture

## Mission

Execute real controlled patch application in isolated sandboxes and validate
build/link/modpost/runtime-sensitive safety with deterministic fail-closed
governance.

## Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/sandbox_patch_validation_engine.py`
- Runner:
  - `scripts/aura-sandbox-patch-validation.py`
- Persistence:
  - `SandboxPatchValidationRegistry`

## Execution Flow

1. create isolated sandbox workspace (worktree or copy fallback)
2. dry-run and apply patch sequence in sandbox
3. record touched files/objects/subsystem boundaries
4. run controlled subsystem + object-level sandbox builds
5. validate modpost/linker integrity signals
6. compute symbol regression and build fingerprint equivalence
7. evaluate runtime-sensitive patch impact
8. execute deterministic rollback when fail-closed is triggered
9. compute runtime promotion eligibility
10. persist deterministic replay lineage and governance decision

## Safety & Governance

- original source tree remains immutable
- sandbox artifacts isolated and disposable
- fail-closed on unresolved compile/link/runtime risk
- rollback safety validated before promotion decision
- runtime promotion denied unless all safety gates pass

## Required Artifacts

- `sandbox_workspace_manifest.json`
- `applied_patch_lineage.json`
- `patch_application_trace.json`
- `subsystem_build_validation.json`
- `object_rebuild_lineage.json`
- `modpost_validation_report.json`
- `linker_closure_report.json`
- `symbol_regression_report.json`
- `build_fingerprint_diff.json`
- `transformation_equivalence_report.json`
- `runtime_promotion_eligibility.json`
- `rollback_lineage_report.json`
- `deterministic_patch_validation_replay.json`
- `runtime_sensitive_patch_impact.json`
- `sandbox_patch_validation_summary.json`
- `governance_patch_validation_decision.json`

