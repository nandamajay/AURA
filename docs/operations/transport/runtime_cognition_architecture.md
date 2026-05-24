# Runtime Cognition + Live Evidence Governance Architecture

## Scope

This phase adds deterministic runtime cognition over live-style evidence sources
while remaining hardware-optional. The stack is designed for mocked/offline
traces first and transitions to live adapters without architecture changes.

## Mission Alignment

How this directly improves AURA mission goals:

- Driver understanding:
  - reconstructs PCM/DAPM/IRQ/DSP execution behavior from runtime traces.
- Topology understanding:
  - builds FE/BE + DAPM + SoundWire runtime path graphs from evidence.
- Runtime evidence reasoning:
  - normalizes dmesg/ftrace/trace-cmd/tinymix/procfs/debugfs/mailbox/IRQ data
    into one ordered schema.
- Regression detection:
  - compares baseline vs transformed runtime sequences and classifies drift.
- Deterministic replay:
  - fingerprints runtime dimensions and persists replay lineage.
- Upstream conversion capability:
  - gates promotion using runtime equivalence confidence and fail-closed policy.

## Subsystems

1. `runtime_trace_ingestion_engine.py`
- Ingests source traces and emits deterministic normalized events.
- Required sources: dmesg, ftrace, trace-cmd, tinymix, procfs, debugfs,
  SoundWire, DSP mailbox, IRQ, clock, regulator.
- Emits fail-closed classification if trace coverage is incomplete.

2. `runtime_hardware_truth_graph.py`
- Reconstructs runtime topology graph from normalized events.
- Models PCM lifecycle, DAPM routes, FE/BE edges, SoundWire links,
  DSP/mailbox sync, IRQ order, clock/regulator order.

3. `runtime_equivalence_engine.py`
- Compares baseline and transformed runtime behavior.
- Detects IRQ/lifecycle/clock/DSP/mailbox/SoundWire/PCM drift.
- Produces confidence score and divergence reasons.

4. `runtime_fingerprint_engine.py`
- Produces deterministic runtime fingerprints for key sequence dimensions.
- Generates replay artifact binding evidence, confidence, and topology lineage.

5. `runtime_governance_engine.py`
- Integrates runtime cognition into promotion decisions.
- FAIL_CLOSED on low confidence, critical divergence, or runtime-sensitive
  instability.
- Persists cumulative runtime confidence trajectory.

6. `runtime_replay_engine.py`
- Persists replay registry and validates cross-session consistency.
- Detects replay drift and triggers FAIL_CLOSED when lineage diverges.

## Runners

- `scripts/aura-runtime-trace-ingestion.py`
- `scripts/aura-runtime-equivalence.py`
- `scripts/aura-runtime-governance.py`

## Generated Artifacts

Core outputs under `docs/operations/transport/`:

- `runtime_equivalence_fingerprint.json`
- `runtime_divergence_report.json`
- `hardware_truth_graph.json`
- `ipc_topology_map.json`
- `runtime_confidence_report.json`
- `deterministic_runtime_replay.json`
- `runtime_governance_decision.json`
- `replay_consistency_report.json`

Additional governance/replay support artifacts:

- `runtime_path_graph.json`
- `runtime_equivalence_report.json`
- `runtime_escalation_report.json`
- `runtime_risk_report.json`
- `runtime_replay_registry.json`

## Governance Policy

- Runtime-truth precedence over static assumptions.
- Advisory-only behavior; no runtime mutation and no autonomous rewriting.
- Plugin/runtime isolation preserved.
- Replay lineage persistence required for all decisions.
- FAIL_CLOSED if:
  - trace coverage incomplete,
  - confidence below threshold,
  - critical runtime divergence,
  - runtime-sensitive instability,
  - replay inconsistency.

## Determinism Guarantees

- deterministic event ordering by timestamp/source/event id
- stable fingerprints for all generated artifacts
- replay registry tracks lineage fingerprints across sessions
- cross-session replay drift is explicitly surfaced and blocks promotion
