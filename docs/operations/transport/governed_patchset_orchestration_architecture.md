# Governed Patchset Orchestration Architecture

## Objective

Extend AURA from single micro transformations to dependency-aware, multi-patch,
runtime-validated orchestration while preserving deterministic replay and
fail-closed governance.

## Pipeline

1. Build tiny realistic Qualcomm-style patchset model.
2. Resolve dependency graph and deterministic topological ordering.
3. Apply patch units sequentially using identifier-safe replacements.
4. Validate each intermediate state:
   - compile/syntax safety
   - runtime equivalence confidence
   - topology consistency
5. Build bisectability and rollback checkpoint registry.
6. Run upstream acceptance prediction.
7. Enforce fail-closed governance classification.
8. Persist replay-safe lineage and deterministic fingerprints.

## Key Engine

- `workspace/aura-sdk/src/aura_sdk/transport/governed_patchset_orchestration.py`
  - `GovernedPatchsetOrchestrationEngine`
  - `GovernedPatchsetOrchestrationRegistry`

## Inputs

- governance state from cognition registry
- replay determinism traces
- plugin capability state
- runtime truth + runtime evidence acquisition artifacts
- translation equivalence artifacts
- upstream acceptance simulation artifacts

## Outputs

- `governed_patchset_plan.json`
- `patch_dependency_graph.json`
- `runtime_patchset_equivalence.json`
- `patch_ordering_rationale.json`
- `bisectability_report.json`
- `patchset_review_risk_report.json`
- `rollback_checkpoint_registry.json`
- `deterministic_patchset_replay.json`
- `cumulative_runtime_validation.json`
- `upstream_patchset_prediction.json`
- `governed_patchset_summary.json`
- `tiny_multi_patchset.patch`

## Governance Rules

- `FAIL_CLOSED` on:
  - dependency cycles or unsafe ordering
  - compile failure in any intermediate checkpoint
  - cumulative runtime confidence/conflict failure
  - topology consistency break
  - upstream prediction below threshold
  - rollback checkpoint incompleteness
- advisory-only behavior:
  - no autonomous patch application or upstream submission

## Deterministic Guarantees

- stable ordering and artifact fingerprinting
- deterministic replay payload and lineage history
- checkpoint fingerprint chain for rollback reconstruction
