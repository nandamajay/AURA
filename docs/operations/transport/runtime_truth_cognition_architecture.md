# Runtime Truth Cognition Layer Architecture (Offline Foundation)

## Mission Scope

This layer brings AURA from static/migration-only cognition into runtime-truth
execution cognition with deterministic replay and governance-safe reasoning.

This phase is explicitly offline foundation mode and uses:

- archived traces
- synthetic runtime sequences
- deterministic replay artifacts
- simulated ALSA/DAPM/SoundWire event streams
- persisted runtime lineage

No live target/device connection is required in this phase.

## Preserved Constraints

- runtime-truth precedence over static assumptions
- fail-closed governance
- deterministic replay-first behavior
- plugin isolation
- advisory-only behavior
- semantic/structural/runtime separation
- hardware-agnostic core runtime cognition

## Runtime Ingestion Sources

Ingestion model supports the required source categories:

- dmesg
- ftrace
- trace-cmd
- tinyalsa/tinymix dumps
- procfs/sysfs runtime state
- SoundWire debugfs
- ALSA topology runtime state
- mailbox event traces
- DSP response logs

For offline mode, sources may be missing and are substituted with deterministic
synthetic events to preserve replay behavior and pipeline coverage.

## Core Components

- `runtime_truth_engine.py`
- `runtime_event_ingestion.py`
- `trace_correlation_engine.py`
- `dapm_runtime_reasoner.py`
- `pcm_lifecycle_tracker.py`
- `soundwire_runtime_graph.py`
- `irq_timing_analyzer.py`
- `dsp_sync_reasoner.py`
- `runtime_drift_detector.py`
- `deterministic_runtime_replay.py`

## Plugin-Safe Design

Core runtime cognition remains target-agnostic and does not branch by target ID.
Target-specific interpretation is obtained only through plugin providers:

- `runtime_evidence_adapter`
- `topology_evidence_adapter`
- `runtime_conversion_adapter`

## Deterministic Runtime Flow

1. Normalize runtime/topology/conversion context through plugin adapters.
2. Ingest multi-source runtime events (archived + synthetic fallback).
3. Correlate traces into runtime ordering and domain coverage evidence.
4. Build DAPM transition trace.
5. Build PCM lifecycle trace and timing validation.
6. Build SoundWire runtime graph.
7. Analyze IRQ timing and latency spikes.
8. Analyze mailbox/DSP synchronization behavior.
9. Detect runtime drift from expected lineage and sequencing.
10. Build unified runtime truth graph.
11. Build deterministic runtime replay artifact.
12. Compute runtime confidence score under governance and replay constraints.
13. Persist replay-safe runtime lineage in cognition registry.

## Required Artifacts

- `runtime_truth_graph.json`
- `dapm_transition_trace.json`
- `pcm_lifecycle_trace.json`
- `soundwire_runtime_graph.json`
- `irq_timing_report.json`
- `dsp_sync_report.json`
- `runtime_drift_report.json`
- `deterministic_runtime_replay.json`
- `runtime_confidence_score.json`

Additional outputs:

- `runtime_truth_summary.json`

## Validation Strategy

Validation includes:

- deterministic output equivalence for same inputs
- required artifact presence and persistence
- fail-closed classification on governance violations
- replay fingerprint stability for same lineage
- plugin isolation checks in core runtime truth engine

## Mission Alignment Outcomes

This phase improves:

- runtime debugging via domain-specific runtime traces
- real hardware reasoning preparation using runtime-like evidence models
- downstream timing analysis through PCM/IRQ/DSP timing cognition
- regression localization through drift detection against lineage
- topology runtime validation through FE/BE and SoundWire runtime graph mapping
- DSP/runtime synchronization analysis via mailbox/DSP pairing
- deterministic runtime replay via lineage-safe replay artifacts
- upstream runtime equivalence reasoning by supplying runtime-truth evidence to conversion planning phases

## Operational Command

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-truth-cognition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id runtime_truth_cognition_offline_v1
```
