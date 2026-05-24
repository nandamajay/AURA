# SYSTEM_CAPABILITY_MATRIX

| Capability Domain | Implemented Components | Current State |
|---|---|---|
| Runtime ingestion | runtime_trace_ingestion_engine, dmesg/ftrace/tracecmd/tinymix/procfs/debugfs/soundwire/dsp/irq ingestors | Implemented |
| Runtime topology reconstruction | runtime_hardware_truth_graph, soundwire_runtime_graph, topology_runtime_correlator | Implemented |
| Runtime equivalence | runtime_equivalence_engine, runtime_fingerprint_engine | Implemented |
| Replay determinism | runtime_replay_engine, deterministic_runtime_replay, runtime_replay_registry | Implemented |
| Runtime governance | runtime_governance_engine + fail-closed runtime decision artifacts | Implemented |
| Contract-first transport | transport_artifact_contracts + runtime router typed responses | Implemented |
| Dashboard runtime integration | RuntimeCognitionCenter + typed contracts/adapters/query layer | Integrated |
| Environment reproducibility | aura_bootstrap/aura_validate/aura_start + deterministic constraints | Blocked by host Python 3.12 availability |
| Hardware onboarding boundaries | runtime capture boundary folders + trace contracts + capture plan | Prepared (schema only) |
