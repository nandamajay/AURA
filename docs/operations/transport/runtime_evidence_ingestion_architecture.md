# Runtime Evidence Ingestion Architecture

## Mission

The Runtime Evidence Ingestion Layer transitions AURA from runtime modeling-only
reasoning to governed, replay-safe runtime observability.

The layer is designed to ingest real engineering runtime evidence while keeping:

- runtime truth precedence
- deterministic replay behavior
- fail-closed governance
- plugin isolation boundaries
- advisory-only cognition behavior

This phase now includes hardware self-discovery and toolchain introspection so
runtime ingestion can bootstrap from physical Linux audio targets without static
board profiles.

## Architecture Overview

`runtime_evidence_ingestor.py` is the phase orchestrator.

It coordinates read-only providers:

- `dmesg_ingestor.py`
- `ftrace_ingestor.py`
- `tracecmd_ingestor.py`
- `tinymix_state_ingestor.py`
- `procfs_runtime_ingestor.py`
- `debugfs_runtime_ingestor.py`
- `soundwire_runtime_ingestor.py`
- `dsp_mailbox_ingestor.py`
- `irq_runtime_ingestor.py`

Session persistence and replay safety are handled by:

- `runtime_session_registry.py`
- `runtime_capture_fingerprint.py`
- `engineering_session_replay.py`

Runner:

- `AURA/scripts/aura-runtime-evidence-ingestion.py`

## Ingestion Lifecycle

1. Runtime source payloads are loaded (log/json inputs and deterministic offline
   fallbacks when archives are available).
2. Each provider performs read-only extraction.
3. Source outputs are normalized into a common event model.
4. Events are correlated against persisted cognition domains:
   - topology cognition
   - runtime truth graphs
   - migration lineage
   - patch lineage
   - structural cognition
   - semantic ontology
5. Session-level artifacts are generated.
6. Registry persistence writes immutable lineage records.
7. Deterministic replay payload is regenerated from persisted lineage.
8. Hardware topology, component lineage, mixer dependency inference, and
   playback observability timelines are generated from ingested evidence.

## Normalization Model

The normalized runtime event schema includes:

- `timestamp_ms` (normalized and ordered)
- `source` and `source_key`
- `subsystem` and `subsystem_id`
- `fe_reference` / `be_reference`
- `dpcm_lifecycle_state`
- `dsp_lineage_id`
- `soundwire_entity`
- `correlated_domains`

Additional runtime discovery model includes:

- SoC / kernel / board metadata
- sound cards / PCM devices / FE-BE references
- codec / amplifier / SoundWire/Slimbus entities
- source-path availability and ingestibility
- runtime toolchain availability and install recommendations

This produces deterministic cross-source correlation and stable replay
fingerprints.

## Generated Artifacts

- `normalized_runtime_evidence.json`
- `runtime_session_graph.json`
- `evidence_capture_lineage.json`
- `subsystem_runtime_state.json`
- `dsp_runtime_trace.json`
- `soundwire_runtime_trace.json`
- `pcm_runtime_state.json`
- `runtime_discovery_report.json`
- `runtime_toolchain_discovery.json`
- `hardware_topology_graph.json`
- `audio_component_lineage_map.json`
- `runtime_evidence_snapshots.json`
- `inferred_playback_route_graph.json`
- `inferred_capture_route_graph.json`
- `mixer_dependency_report.json`
- `real_playback_observability_timeline.json`
- `offline_runtime_replay_foundation.json`
- `runtime_capture_fingerprint.json`
- `deterministic_runtime_session_replay.json`
- `runtime_evidence_ingestion_summary.json`

## Governance Boundaries

Enforced constraints:

- ingestion is read-only
- no runtime mutation
- no auto execution of kernel operations
- no autonomous patching/topology rewriting/upstream generation
- fail-closed on incomplete required evidence

Fail-closed triggers include:

- missing required source coverage
- governance policy violations
- missing correlation context

## Replay Guarantees

Replay guarantees are enforced through:

- deterministic source fingerprints
- deterministic normalization ordering
- immutable evidence capture chain hashing
- deterministic runtime capture fingerprinting
- deterministic session replay lineage payload

## Plugin Isolation

Core ingestion logic is target-agnostic.

Target interpretation surfaces only through plugin adapters:

- `runtime_evidence_adapter`
- `topology_evidence_adapter`
- `semantic_evidence_adapter`

No target-specific branching is allowed in core ingestion orchestration.

## Operational Execution

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 AURA/scripts/aura-runtime-evidence-ingestion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id runtime_session_v1 \
  --lineage-id runtime_evidence_ingestion_v1 \
  --capture-root /
```

## Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  AURA/workspace/aura-sdk/tests/test_runtime_evidence_ingestion_static.py -q
```

## Mission Alignment Impact

This layer directly improves:

- live debugging: unified ingestion of runtime logs/traces into one normalized timeline
- runtime regression analysis: deterministic replay and lineage compare points
- topology/runtime validation: FE/BE and lifecycle evidence correlation
- DSP synchronization tracing: mailbox and DSP lineage extraction
- SoundWire analysis: runtime entity extraction and subsystem state tracking
- migration confidence: runtime correlation against migration and patch lineage
- deterministic runtime replay: reproducible session fingerprints and replay payloads
