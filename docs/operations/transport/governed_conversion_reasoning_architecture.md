# Governed Conversion Reasoning Engine Architecture

## Mission Scope

This layer reasons about *why* downstream kernel implementations cannot map
cleanly to upstream Linux abstractions, without generating autonomous patches
or mutating runtime state.

Primary outputs:

- portability blocker reasoning
- abstraction gap reasoning
- lifecycle incompatibility detection
- vendor dependency classification
- runtime portability reasoning
- confidence-scored upstream equivalence
- phased governed migration planning
- deterministic conversion reasoning trace

## Preserved Constraints

- advisory-only reasoning
- fail-closed governance
- deterministic replay and lineage
- runtime evidence as execution truth
- plugin isolation in core runtime
- semantic/structural separation
- no autonomous rewriting or topology mutation

## Engine Components

- `conversion_reasoning_engine.py`
- `portability_blocker_classifier.py` (governed extension)
- `abstraction_gap_reasoner.py`
- `migration_phase_planner.py`
- `upstream_equivalence_confidence.py`
- `lifecycle_incompatibility_detector.py`
- `vendor_dependency_classifier.py`
- `runtime_portability_reasoner.py`

## Data Flow

1. Load plugin adapter hints (no target-branching in core):
   - `downstream_upstream_adapter`
   - `runtime_conversion_adapter`
2. Ingest structural artifacts:
   - driver registration graph
   - callback chain graph
   - topology structure graph
   - runtime-source correlation
   - downstream hook inventory
   - upstream equivalence trace
3. Classify vendor dependencies.
4. Detect lifecycle incompatibilities and API drift.
5. Reason abstraction gaps (including DPCM/FE-BE and SoundWire migration gaps).
6. Reason runtime portability and unsupported runtime dependencies.
7. Score upstream equivalence confidence.
8. Classify governed portability blockers and risk.
9. Produce phased migration plan (advisory/governed only).
10. Emit deterministic reasoning graph + deterministic reasoning trace.

## Generated Artifacts

- `conversion_reasoning_graph.json`
- `portability_blocker_report.json`
- `migration_phase_plan.json`
- `abstraction_gap_report.json`
- `upstream_equivalence_confidence.json`
- `lifecycle_incompatibility_report.json`
- `vendor_dependency_graph.json`
- `runtime_portability_analysis.json`
- `deterministic_conversion_reasoning_trace.json`

Additional operational outputs:

- `deterministic_conversion_reasoning_replay.json`
- `governed_conversion_reasoning_summary.json`

## Replay + Governance Behavior

- Every artifact carries deterministic fingerprinting.
- The deterministic trace stores artifact fingerprint lineage for replay.
- Governance violations force fail-closed classification.
- Runtime-truth precedence is explicit in runtime portability reasoning.

## Plugin Isolation

Core engine remains target-agnostic:

- no `if target == ...` logic
- target intelligence sourced only from plugin adapters

## Operational Runner

Use:

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-conversion-reasoning.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id governed_conversion_reasoning_v1
```

This runner persists artifacts and registry lineage in replay-safe form.
