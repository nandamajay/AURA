# Translation Intelligence Layer

## Scope
Deterministic downstream-to-upstream conversion cognition only.

This layer is designed to improve:
- driver understanding
- topology understanding
- runtime evidence reasoning
- regression detection
- deterministic replay
- upstream conversion capability

It does not perform autonomous patching, DTS rewriting, driver mutation, or unsafe runtime mutation.

## Runtime Evidence Connection
- Runtime evidence feeds conversion reasoning through `runtime_conversion_reasoning.py`.
- Downstream-only runtime dependencies and portability blockers are derived from evidence-backed adapter output.
- Transformation classes are explicitly separated into:
  - replay-safe transformations
  - advisory-only transformations
  - forbidden/autonomous transformations

## Deterministic Replay Connection
- Conversion outputs are persisted with lineage and deterministic fingerprints.
- Replay reconstruction is produced in `deterministic_translation_replay.json`.
- Replay payload binds lineage ID, translation fingerprint, and artifact paths.

## Governance Connection
- Planner enforces fail-closed conversion boundaries.
- Allowed actions are advisory cognition actions only.
- Forbidden actions explicitly block autonomous rewrite/mutation behavior.
- Governance classification is included in runtime portability analysis and conversion confidence.

## Plugin Isolation Connection
- Core planner is target-agnostic.
- Target intelligence is provided only via plugin adapters:
  - `downstream_upstream_adapter`
  - `topology_translation_adapter`
  - `runtime_conversion_adapter`
- Contract and isolation validator enforce adapter presence and no target-specific branching in core.

## Portability Layer Connection
- Translation planner consumes portable plugin contract interfaces.
- Cross-target simulation plugins provide deterministic test coverage.
- RB3 remains reference target while core stays generic.
