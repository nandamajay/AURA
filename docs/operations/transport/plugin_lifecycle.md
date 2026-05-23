# Plugin Lifecycle Documentation

## Scope
Portable runtime stabilization lifecycle for target plugins under fail-closed governance.

## Lifecycle States
1. `load`
2. `negotiate`
3. `validate`
4. `activate`
5. `quarantine`
6. `unload`
7. `replay_restore`

## Deterministic Behavior Rules
- Lifecycle execution is ordered and append-only.
- Any plugin contract failure transitions to `quarantine` and then `unload`.
- `replay_restore` is allowed only when replay compatibility is not `INCOMPATIBLE`.
- Quarantined plugins cannot be loaded until quarantine is explicitly cleared.

## Fail-Closed Semantics
- Invalid plugin contract -> `FAIL_CLOSED`.
- Unsupported topology provider -> quarantine + `FAIL_CLOSED`.
- Replay incompatibility -> quarantine + `FAIL_CLOSED`.
- Missing target selection -> `FAIL_CLOSED`.

## Core/Plugin Boundary
- Core runtime controls lifecycle orchestration only.
- Target-specific route/topology/mixer/evidence logic is plugin-owned only.
- Core runtime does not branch on `if target == ...`.

## Semantic Adapter Lifecycle
- Semantic adapters are plugin-owned and invoked after lifecycle `activate`.
- Required semantic adapters:
  - `dts_adapter`
  - `topology_adapter`
  - `vendor_api_adapter`
  - `subsystem_descriptor_provider`
- Semantic outputs are advisory/governed cognition artifacts only.
- Semantic adapter failures trigger `quarantine` and preserve fail-closed posture.

## Correlation Adapter Lifecycle
- Correlation adapters are plugin-owned and invoked inside unified cognition fusion.
- Required correlation adapters:
  - `runtime_evidence_adapter`
  - `topology_evidence_adapter`
  - `semantic_evidence_adapter`
- Correlation outputs must remain deterministic, replay-safe, and lineage-backed.
- Correlation adapter failures trigger `quarantine` and preserve fail-closed posture.

## Translation Adapter Lifecycle
- Translation adapters are plugin-owned and invoked only by the conversion planner layer.
- Required translation adapters:
  - `downstream_upstream_adapter`
  - `topology_translation_adapter`
  - `runtime_conversion_adapter`
- Translation adapters must not execute runtime mutation and must return advisory cognition data only.
- Adapter contract failures are quarantined and fail-closed.
