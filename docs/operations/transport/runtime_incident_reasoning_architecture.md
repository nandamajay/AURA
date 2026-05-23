# Runtime Incident Reconstruction and Root-Cause Reasoning Architecture

## Mission Scope

This layer moves AURA into deterministic runtime engineering incident reasoning.
It reconstructs incident timelines and causality without autonomous mutation.

The layer answers:

- what failed
- where failure originated
- what runtime sequence drifted
- what topology/runtime dependency broke
- what patch/migration/runtime event contributed
- what upstream/downstream abstraction mismatch exists

## Preserved Constraints

- runtime-truth precedence
- fail-closed governance on uncertain classifications
- deterministic replay-first behavior
- plugin/runtime isolation through adapter contracts
- advisory-only behavior (no autonomous fixing)
- no runtime evidence mutation
- no autonomous source rewriting

## Core Components

- `runtime_incident_reconstructor.py`
- `runtime_sequence_drift_engine.py`
- `lifecycle_violation_detector.py`
- `topology_runtime_failure_mapper.py`
- `patch_runtime_causality_engine.py`
- `root_cause_reasoner.py`
- `evidence_confidence_engine.py`

Runner:

- `scripts/aura-runtime-incident-reconstruction.py`

## Runtime Evidence Ingestion Model

Primary evidence sources:

- dmesg logs
- ftrace traces
- PCM lifecycle traces
- DAPM transition traces
- SoundWire runtime traces
- DSP/mailbox traces
- IRQ timing traces
- topology snapshots
- patch lineage metadata

Offline mode behavior:

- consumes persisted runtime artifacts
- uses archived/synthetic source fallbacks when logs are absent
- remains deterministic and replayable
- keeps live-device ingestion optional for future phases

## Causality Model

The incident causality model is layered:

1. Runtime sequence reconstruction
   - ordered runtime timeline
   - subsystem activation ordering
   - FE/BE dependency sequence
   - DPCM lifecycle transitions
   - DSP sync timing
   - SoundWire activation graph
   - IRQ/runtime causality chains
2. Lifecycle violation detection
   - stage-order violations
   - missing transitions
   - DSP-linked lifecycle degradation
3. Topology/runtime failure mapping
   - route activation consistency
   - topology/runtime edge consistency
   - FE/BE correlation completeness
4. Patch/migration/runtime causality
   - patch-induced regression overlap
   - migration-induced incompatibility
   - portability blockers and abstraction mismatch
   - vendor contamination signals
5. Root-cause candidate reasoning
   - ranked, evidence-linked candidate set
   - uncertain outcome detection
6. Engineering confidence scoring
   - evidence completeness
   - drift/lifecycle/topology/regression confidence
   - governance + replay safety

## Deterministic Replay Model

Deterministic replay guarantees include:

- artifact fingerprint chaining across incident outputs
- preserved evidence ordering and timeline serialization
- lineage history with deterministic replay fingerprints
- replay-safe persistence in cognition registry

Generated replay artifact:

- `deterministic_incident_replay.json`

## Runtime Truth Precedence System

Runtime truth is the primary execution signal:

- runtime-derived traces and ordering drive incident reconstruction
- topology/semantic/migration/patch cognition are correlated as explanatory domains
- static assumptions never override runtime evidence
- uncertain classification always fails closed

## Generated Artifacts

- `runtime_incident_graph.json`
- `root_cause_candidates.json`
- `lifecycle_violation_report.json`
- `runtime_sequence_drift.json`
- `topology_runtime_causality.json`
- `regression_causality_report.json`
- `deterministic_incident_replay.json`
- `engineering_confidence_report.json`

Additional output:

- `runtime_incident_reconstruction_summary.json`

## Validation Strategy

Validation includes:

- deterministic output equivalence with identical inputs
- runtime causality reconstruction verification
- drift detection verification
- topology/runtime correlation verification
- replay fingerprint stability verification
- fail-closed governance behavior verification
- plugin isolation checks (`no if target == ...` in incident core)

## Operational Command

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-incident-reconstruction.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id runtime_incident_reconstruction_v1
```
