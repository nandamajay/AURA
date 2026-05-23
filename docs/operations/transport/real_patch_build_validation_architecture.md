# Real Patch Application + Governed Build Validation Architecture

## Mission Scope

This layer executes real downstream patch application in sandbox mode and
enforces fail-closed governed build validation before any promotion decision.

Scope is intentionally limited to tiny safe transformations:

- logging normalization
- helper abstraction cleanup
- wrapper replacement
- trivial API migration
- safe macro normalization
- capability wrapper cleanup

Out of scope:

- DSP algorithm rewrites
- IRQ/synchronization semantic changes
- runtime PM sequencing modifications
- mailbox ordering modifications

## Execution Flow

1. ingest real patch (`downstream_to_upstream.patch` or equivalent)
2. parse touched files + replacement pairs + changed line lineage
3. prepare sandbox with touched file set from real source tree
4. run patch dry-run
5. run real patch apply in sandbox
6. build applied diff (`applied_patch.diff`)
7. validate include closure for touched files
8. build touched object graph (`.c -> .o`)
9. run incremental compile (`cc -fsyntax-only`) on touched objects
10. validate symbol replacement consistency
11. classify runtime-sensitive compile impacts
12. compute build confidence
13. governance fail-closed evaluation
14. rollback patch in sandbox when fail-closed
15. persist deterministic replay + lineage artifacts

## Engines

- `RealPatchApplicationGovernedBuildEngine`
  - real patch application and compile-oriented cognition
- `RealPatchApplicationGovernedBuildRegistry`
  - artifact persistence + cognition lineage + replay reconstruction

## Fail-Closed Triggers

- patch apply conflict/reject/failure
- incremental compile failure on touched objects
- include dependency closure unresolved
- symbol replacement inconsistency
- unsafe runtime-sensitive compile impact
- confidence score below threshold
- rollback incomplete after escalation

## Deterministic Guarantees

- every artifact includes deterministic fingerprint
- deterministic replay artifact captures lineage and result state
- rollback lineage persists before/after/post-rollback fingerprints
- governance classification is reproducible from persisted artifacts only

## Generated Artifacts

- `applied_patch.diff`
- `patch_apply_report.json`
- `incremental_build_report.json`
- `touched_object_graph.json`
- `symbol_resolution_report.json`
- `include_closure_report.json`
- `runtime_sensitive_compile_report.json`
- `build_confidence_report.json`
- `rollback_lineage.json`
- `deterministic_build_replay.json`
- `compile_warning_clusters.json`
- `governance_build_escalation.json`
- `real_patch_validation_summary.json`

