# AURA — Audio Upstream Refactor Agent

AURA is a governed, deterministic audio cognition/runtime platform for Qualcomm
audio engineering workflows. The current implementation prioritizes:

- runtime evidence as truth
- deterministic replay and reconstruction
- fail-closed governance enforcement
- persistent cognition state (no chat-memory dependency)
- advisory/governed execution only

## Core Architecture Model

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │────▶│  aura-core   │────▶│ llm-gateway  │──▶ OpenAI
│   Port 3000  │◄────│   Port 8000  │     │   Port 8002  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                     ┌──────┴──────┐
                     │   ws-server  │
                     │   Port 8001  │
                     └─────────────┘
                            │
                     ┌──────┴──────┐
                     │   SQLite     │
                     │  /data/aura  │
                     └─────────────┘
```

### Services

| Service | Port | Responsibility |
|---------|------|----------------|
| `aura-core` | `8000` | orchestration, governance, APIs |
| `llm-gateway` | `8002` | LLM boundary/proxy |
| `ws-server` | `8001` | streaming/event fanout |
| `dashboard` | `3000` | operational visibility |

## Current Capability Baseline

The platform currently includes:

- deterministic RB3Gen2 runtime playback orchestration
- topology cognition and DTSI/runtime correlation artifacts
- persistent cognition registry and boot reconstruction
- governance restoration and fail-closed decision handling
- cognition bus with event lifecycle, lineage, and replay
- stability harnesses for replay determinism and quarantine
- portability architecture artifacts for multi-target cognition
- translation intelligence foundation for downstream-to-upstream conversion planning

## Quick Start (Deterministic Local Bring-up)

```bash
# 1) Configure environment
cp .env.example .env
# Edit .env for JWT + provider credentials

# 2) Validate host/toolchain first (failure-first)
make env-doctor

# 3) Deterministic bootstrap
make repro-up

# Optional strict mode
./scripts/repro-bootstrap.sh --strict-doctor

# 4) Verify services
curl http://localhost:8000/health/ready
```

## Development Commands

```bash
# deterministic runtime sync (container-authoritative Python 3.12)
make env-sync

# stabilization bootstrap / validation / startup
make aura-bootstrap
make aura-validate
make aura-start

# development mode
make dev

# tests
make test

# parity checks (container-authoritative Python 3.12)
make ci-parity

# unified deterministic runtime launcher
./scripts/aura_runtime_launcher.sh --mode runtime-pipeline
./scripts/aura_runtime_launcher.sh --mode semantic
./scripts/aura_runtime_launcher.sh --mode semantic-scaling
./scripts/aura_runtime_launcher.sh --mode simulation
./scripts/aura_pytest.sh workspace/aura-sdk/tests/test_runtime_replay_static.py

# lint
make lint

# logs / db shell
make logs-core
make shell-db
```

## Environment Stabilization and Replay Hardening

Use the stabilization scripts when preparing for runtime ingestion and
contract/governance checks:

- `scripts/aura_bootstrap.sh`
  - strict host diagnostics
  - deterministic runtime container verification (Python 3.12 authoritative)
  - deterministic dashboard dependency sync
  - optional validation execution
- `scripts/aura_validate.sh`
  - runs validator inside deterministic container runtime only
  - emits required reports to `docs/operations/transport/`:
    - `environment_validation_report.json`
    - `backend_runtime_validation.json`
    - `dashboard_runtime_validation.json`
    - `dependency_integrity_report.json`
    - `bootstrap_readiness_report.md`
    - `replay_integrity_report.json`
    - `replay_drift_analysis.json`
    - `replay_registry_validation.json`
    - `governance_replay_consistency.json`
    - `runtime_contract_integrity.json`
    - `dto_alignment_report.json`
    - `transport_schema_validation.json`
    - `runtime_execution_fingerprint_report.json`
- `scripts/aura_start.sh`
  - unified backend-first startup sequencing
  - runtime verification before promotion
  - optional post-start validation pass

## Deterministic Demo Flow

```bash
make demo-prepare
make demo-up
make demo-verify
make demo-workload
```

Artifacts are emitted to `evidence/demo/`.

## RB3Gen2 Deterministic Runtime Operations

Primary scripts:

- `scripts/rb3-runtime-procedural-playback.py`
- `scripts/rb3-deterministic-stability.py`
- `scripts/rb3-playback-cognition-validation.py`
- `scripts/aura-cognition-boot.py`
- `scripts/aura_stability_harness.py`
- `scripts/aura_determinism_validator.py`
- `scripts/aura_crash_recovery_validator.py`
- `scripts/aura_confidence_integrity.py`
- `scripts/aura_event_quarantine_tests.py`
- `scripts/aura-incremental-migration-orchestration.py`
- `scripts/aura-runtime-evidence-fusion.py`
- `scripts/aura-runtime-incident-reconstruction.py`
- `scripts/aura-runtime-evidence-ingestion.py`
- `scripts/aura-engineering-investigation.py`
- `scripts/aura-governed-translation-intelligence.py`
- `scripts/aura-governed-patchset-orchestration.py`

Key output directory:

- `../docs/operations/transport/`

Representative artifacts include:

- `deterministic_runtime_profile.json`
- `runtime_confidence_report.json`
- `playback_drift_report.json`
- `procedural_signature.json`
- `stable_route_fingerprint.json`
- `aura_stability_report.json`
- `aura_replay_determinism_report.json`
- `aura_confidence_integrity_report.json`
- `aura_recovery_validation_report.json`
- `aura_event_quarantine_report.json`
- `aura_stability_fingerprint.json`

## Real Runtime Evidence Ingestion Layer

This phase introduces governed, read-only runtime evidence observability while
preserving deterministic replay, plugin isolation, and fail-closed governance.

### Ingestion Components

- Orchestrator:
  - `workspace/aura-sdk/src/aura_sdk/transport/runtime_evidence_ingestor.py`
- Source ingestors:
  - `dmesg_ingestor.py`
  - `ftrace_ingestor.py`
  - `tracecmd_ingestor.py`
  - `tinymix_state_ingestor.py`
  - `procfs_runtime_ingestor.py`
  - `debugfs_runtime_ingestor.py`
  - `soundwire_runtime_ingestor.py`
  - `dsp_mailbox_ingestor.py`
  - `irq_runtime_ingestor.py`
- Session + replay persistence:
  - `runtime_session_registry.py`
  - `runtime_capture_fingerprint.py`
  - `engineering_session_replay.py`
- Runner:
  - `scripts/aura-runtime-evidence-ingestion.py`

### Runtime Ingestion Inputs

- dmesg/kernel log streams
- ftrace and trace-cmd/perf traces
- tinyalsa/tinymix snapshots
- ALSA procfs runtime state
- debugfs runtime state
- SoundWire runtime dumps
- DSP mailbox logs
- IRQ timing traces

### Generated Artifacts

- `normalized_runtime_evidence.json`
- `runtime_session_graph.json`
- `evidence_capture_lineage.json`
- `subsystem_runtime_state.json`
- `dsp_runtime_trace.json`
- `soundwire_runtime_trace.json`
- `pcm_runtime_state.json`
- `runtime_capture_fingerprint.json`
- `deterministic_runtime_session_replay.json`
- `runtime_evidence_ingestion_summary.json`

### Run Runtime Evidence Ingestion

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-evidence-ingestion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id runtime_session_v1 \
  --lineage-id runtime_evidence_ingestion_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_runtime_evidence_ingestion_static.py -q
```

### Architecture Document

- `docs/operations/transport/runtime_evidence_ingestion_architecture.md`

### Governance and Determinism Properties

- read-only ingestion only (no runtime mutation paths)
- fail-closed on missing required evidence or governance violations
- deterministic timestamp/event ordering normalization

## Runtime Consolidation Mode

Execution is container-authoritative (Python 3.12) for runtime ingestion,
equivalence, replay/governance, semantic extraction, and simulation.

- Unified launcher: `scripts/aura_runtime_launcher.sh`
- Deterministic pytest wrapper: `scripts/aura_pytest.sh`
- Consolidation contracts/orchestration runner:
  - `scripts/aura-runtime-consolidation.py`
  - emits:
    - `runtime_stage_blueprint.json`
    - `runtime_execution_order.json`
    - `runtime_incremental_rebuild_plan.json`
    - `runtime_replay_regeneration_triggers.json`
    - `runtime_graph_invalidation_report.json`
    - `runtime_ingestion_contract_catalog.json`
    - `runtime_deterministic_cache_schema.json`
    - `runtime_observability_report.json`
    - `runtime_consolidation_summary.json`
- immutable capture lineage chain and replay-safe session persistence
- plugin adapter boundary preserved (`runtime/topology/semantic` adapters only)

## Large-Scale Semantic Ingestion Expansion

Deterministic, source-derived ingestion for Linux audio trees with incremental
cache reuse and fail-closed topology/simulation governance.

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/semantic_scaling_ingestion_engine.py`
- Runner:
  - `scripts/aura-semantic-scaling-ingestion.py`
- Static validation:
  - `workspace/aura-sdk/tests/test_semantic_scaling_ingestion_static.py`

Run:

```bash
./scripts/aura_runtime_launcher.sh --mode semantic-scaling
```

Core generated artifacts include:

- `semantic_driver_discovery_registry.json`
- `semantic_incremental_ingestion_report.json`
- `semantic_include_dependency_graph.json`
- `semantic_function_call_graph.json`
- `semantic_macro_lineage_graph.json`
- `semantic_dapm_route_graph.json`
- `semantic_clock_dependency_graph.json`
- `semantic_control_propagation_graph.json`
- `semantic_subsystem_ownership_graph.json`
- `semantic_stream_path_relationships.json`
- `semantic_backend_frontend_dai_graph.json`
- `semantic_inter_driver_dependency_graph.json`
- `semantic_topology_model.json`
- `semantic_runtime_replay_simulation.json`
- `semantic_simulation_transition_log.json`
- `semantic_failure_diagnostics.json`
- `semantic_scaling_summary.json`

## Runtime Cognition + Live Evidence Governance (Offline-First)

This phase extends AURA into runtime behavior reconstruction and governance
gating using mocked/simulated traces first (no mandatory hardware dependency).

### Runtime Cognition Components

- `workspace/aura-sdk/src/aura_sdk/transport/runtime_trace_ingestion_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_hardware_truth_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_equivalence_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_fingerprint_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_governance_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_replay_engine.py`

### Runners

- `scripts/aura-runtime-trace-ingestion.py`
- `scripts/aura-runtime-equivalence.py`
- `scripts/aura-runtime-governance.py`

### Validation Suites

- `workspace/aura-sdk/tests/test_runtime_trace_ingestion_static.py`
- `workspace/aura-sdk/tests/test_runtime_equivalence_static.py`
- `workspace/aura-sdk/tests/test_runtime_governance_static.py`
- `workspace/aura-sdk/tests/test_runtime_replay_static.py`

### Core Runtime Artifacts

- `runtime_equivalence_fingerprint.json`
- `runtime_divergence_report.json`
- `hardware_truth_graph.json`
- `ipc_topology_map.json`
- `runtime_confidence_report.json`
- `deterministic_runtime_replay.json`
- `runtime_governance_decision.json`
- `replay_consistency_report.json`

### Runtime Governance Behavior

- runtime-truth precedence and advisory-only reasoning
- deterministic replay lineage persistence
- fail-closed runtime promotion gating on low confidence or drift
- runtime-sensitive instability blocks promotion by policy
- plugin/runtime isolation preserved

## Contract-First Runtime Cognition Integration

This phase bridges runtime transport artifacts into operational dashboard
workflows using typed contracts and governed runtime APIs.

### Backend Contract Layer

- `services/core/src/core/contracts/transport_artifact_contracts.py`
- Strict typed models for:
  - `runtime_equivalence_report.json`
  - `hardware_truth_graph.json`
  - `replay_consistency_report.json`
  - `runtime_governance_decision.json`
  - `transformation_confidence_report.json`
- Contract validation includes:
  - schema/type validation
  - lineage/session/timestamp metadata normalization
  - replay fingerprint extraction
  - topology integrity checks
  - cross-artifact lineage consistency checks

### Runtime API Endpoints

- `GET /api/v1/runtime/artifacts/index`
- `GET /api/v1/runtime/artifacts/read`
- `GET /api/v1/runtime/governance/summary`
- `GET /api/v1/runtime/topology`
- `GET /api/v1/runtime/equivalence`
- `GET /api/v1/runtime/confidence`

### Dashboard Runtime View

- Route: `/runtime`
- Page: `dashboard/src/pages/RuntimeCognitionCenter.tsx`
- Shared frontend runtime contract/adapter layer:
  - `dashboard/src/runtime/contracts.ts`
  - `dashboard/src/runtime/adapters.ts`
  - `dashboard/src/runtime/useRuntimeQuery.ts`

### Integration Artifacts

- `docs/operations/transport/runtime_contract_integration_summary.md`
- `docs/operations/transport/runtime_dashboard_contracts.md`
- `docs/operations/transport/runtime_api_contracts.json`
- `docs/operations/transport/runtime_integration_validation_report.json`
- `docs/operations/transport/runtime_dashboard_readiness_report.md`

## Portable Multi-Target Cognition Phase

This phase introduces architecture hardening for cross-target portability while
keeping RB3Gen2 as the known-good reference target.

### Objectives

- abstract target-specific assumptions behind explicit interfaces
- separate target identity, overlay identity, topology, routing, evidence, and mixer capabilities
- preserve deterministic replay and fail-closed governance
- keep execution advisory/governed only
- prohibit autonomous patching/upstream generation/topology rewrite

### Generator

```bash
python3 scripts/aura-portable-target-cognition-architecture.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport
```

### Generated Architecture Artifacts

- `portable_target_cognition_architecture.json`
- `cognition_abstraction_layer.json`
- `target_profile_schema.json`
- `runtime_capability_negotiation_model.json`
- `deterministic_replay_compatibility_strategy.json`
- `rb3_to_portable_migration_plan.json`
- `new_target_validation_strategy.json`
- `cross_target_governance_boundaries.json`
- `portable_multi_target_cognition_phase_summary.json`

## Phase-3 Plugin Hardening

Phase-3 converts RB3-focused cognition into a plugin-oriented portable target framework
without rewriting validated runtime execution paths.

### Hardening Principles

- generic runtime layer has no target-specific branching
- all target intelligence comes from plugin providers
- deterministic replay compatibility is validated per plugin
- fail-closed governance remains the default behavior
- no autonomous patching/topology mutation/upstream generation

### Plugin Contract

Every target plugin must expose:

- `target_id`
- `topology_provider`
- `mixer_provider`
- `pcm_provider`
- `route_provider`
- `evidence_provider`
- `capability_provider`
- `validation_provider`

### Runtime Components

- Plugin contracts and loader:
  - `workspace/aura-sdk/src/aura_sdk/transport/plugins/contracts.py`
  - `workspace/aura-sdk/src/aura_sdk/transport/plugins/loader.py`
  - `workspace/aura-sdk/src/aura_sdk/transport/plugins/target_plugin_registry.json`
- First formal plugin:
  - `workspace/aura-sdk/src/aura_sdk/transport/plugins/rb3_plugin.py`
- Generic plugin runtime facade:
  - `workspace/aura-sdk/src/aura_sdk/transport/portable_runtime_layer.py`
- Optional planner entrypoint:
  - `build_target_plugin_workflow(...)` in `workspace/aura-sdk/src/aura_sdk/transport/command_planner.py`

### Phase-3 Artifact Generator

```bash
python3 scripts/aura-phase3-plugin-hardening.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport
```

### Phase-3 Artifacts

- `aura_plugin_contract.json`
- `aura_target_plugin_registry.json`
- `rb3_plugin_capabilities.json`
- `portable_runtime_layer.json`
- `plugin_replay_compatibility.json`
- `target_negotiation_graph.json`
- `phase3_plugin_hardening_summary.json`

### Migration + Lifecycle Docs

- `phase3_plugin_migration_notes.md`
- `plugin_lifecycle.md`
- `replay_portability.md`
- `governance_portability_boundaries.md`
- `plugin_semantic_lifecycle.md`

## Portable Runtime Stabilization Phase

This phase stress-tests plugin-isolated portability boundaries before any
upstream semantic reasoning is introduced.

### Stabilization Scope

- plugin isolation validation for core runtime
- cross-target simulation without hardware (`fake_target_alpha`, `fake_target_beta`, `degraded_target_gamma`)
- capability negotiation stress paths
- replay portability verification
- lifecycle + quarantine + recovery orchestration
- plugin drift detection

### Stabilization Generator

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-portable-runtime-stabilization.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --repo-root /local/mnt/workspace/AURA_V1
```

### Stabilization Artifacts

- `portable_runtime_stability_report.json`
- `plugin_isolation_report.json`
- `replay_portability_matrix.json`
- `capability_negotiation_trace.json`
- `plugin_lifecycle_graph.json`
- `quarantine_recovery_trace.json`

## Semantic Kernel Cognition Foundation

This phase introduces plugin-driven downstream kernel semantic cognition while
keeping replay determinism, governance boundaries, and portability isolation.

### Semantic Components

- `workspace/aura-sdk/src/aura_sdk/transport/semantic_cognition.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_registry.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_fingerprint.py`

### Semantic Plugin Adapters

Each plugin provides:

- `dts_adapter`
- `topology_adapter`
- `vendor_api_adapter`
- `subsystem_descriptor_provider`

Core runtime does not parse target semantics directly.

### Semantic Generator

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-semantic-kernel-foundation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2
```

### Semantic Artifacts

- `downstream_semantic_graph.json`
- `subsystem_mapping_graph.json`
- `dts_topology_graph.json`
- `vendor_dependency_fingerprint.json`
- `semantic_confidence_report.json`
- `semantic_replay_trace.json`
- `semantic_kernel_foundation_summary.json`

### Semantic Governance Constraints

- Allowed: analyze, classify, correlate, fingerprint, replay, recommend
- Forbidden: generate final patches, rewrite DTS, mutate drivers, fabricate compatibility

### Stabilization Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_target_plugin_runtime_static.py \
  workspace/aura-sdk/tests/test_portable_runtime_stabilization_static.py \
  workspace/aura-sdk/tests/test_semantic_cognition_static.py -q
```

## Multi-Domain Cognition Correlation Phase

This phase fuses runtime evidence, topology cognition, semantic cognition,
replay history, regression lineage, and governance state into one deterministic,
lineage-backed correlation model.

### Correlation Components

- `workspace/aura-sdk/src/aura_sdk/transport/cognition_correlation.py`
- `workspace/aura-sdk/src/aura_sdk/transport/evidence_correlation.py`
- `workspace/aura-sdk/src/aura_sdk/transport/causal_lineage.py`
- `workspace/aura-sdk/src/aura_sdk/transport/confidence_evolution.py`

### Plugin-Safe Correlation Adapters

Each target plugin provides:

- `runtime_evidence_adapter`
- `topology_evidence_adapter`
- `semantic_evidence_adapter`

Core correlation runtime stays target-agnostic and does not branch on target IDs.

### Correlation Generator

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-multi-domain-cognition-correlation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id multi_domain_correlation_v1
```

### Correlation Artifacts

- `unified_cognition_graph.json`
- `causal_reasoning_graph.json`
- `evidence_lineage_graph.json`
- `confidence_evolution_report.json`
- `anomaly_correlation_report.json`
- `cognition_fusion_trace.json`
- `multi_domain_cognition_correlation_summary.json`

### Correlation Governance Boundaries

- Allowed: correlate, classify, infer, recommend, replay, quarantine
- Forbidden: fabricate evidence, fabricate causality, auto patch, auto modify runtime, override governance

### Correlation Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_target_plugin_runtime_static.py \
  workspace/aura-sdk/tests/test_portable_runtime_stabilization_static.py \
  workspace/aura-sdk/tests/test_semantic_cognition_static.py \
  workspace/aura-sdk/tests/test_cognition_correlation_static.py -q
```

## Translation Intelligence Layer

This phase is scoped specifically to downstream-to-upstream kernel conversion
cognition. It does not perform autonomous code generation or runtime mutation.

### Mission Alignment

Every component in this layer contributes directly to:

- driver understanding via downstream/vendor to upstream semantic mapping
- topology understanding via FE/BE and PCM/DPCM translation reasoning
- runtime evidence reasoning via portability blocker classification
- regression detection via migration drift lineage
- deterministic replay via lineage-bound replay fingerprints
- upstream conversion capability via governed advisory planning outputs

### Translation Components

- `workspace/aura-sdk/src/aura_sdk/transport/downstream_upstream_mapping.py`
- `workspace/aura-sdk/src/aura_sdk/transport/topology_translation_cognition.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_conversion_reasoning.py`
- `workspace/aura-sdk/src/aura_sdk/transport/migration_lineage.py`
- `workspace/aura-sdk/src/aura_sdk/transport/upstream_conversion_planner.py`

### Plugin-Safe Translation Adapters

Each plugin provides conversion adapters:

- `downstream_upstream_adapter`
- `topology_translation_adapter`
- `runtime_conversion_adapter`

Core conversion planner remains target-agnostic and does not branch on target IDs.

### Translation Generator

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-translation-intelligence-layer.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id translation_intelligence_v1
```

### Translation Artifacts

- `downstream_upstream_mapping_graph.json`
- `topology_translation_report.json`
- `runtime_portability_analysis.json`
- `migration_lineage.json`
- `upstream_conversion_confidence.json`
- `deterministic_translation_replay.json`
- `translation_intelligence_summary.json`

### Runtime Evidence and Replay Linkage

- Runtime evidence is consumed from registry-backed cognition state.
- Translation confidence is computed from semantic, topology, runtime, migration, replay, and governance factors.
- Translation replay is deterministic and lineage-indexed (`deterministic_translation_replay.json`).
- All outputs remain advisory and governance-bounded.

### Translation Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_target_plugin_runtime_static.py \
  workspace/aura-sdk/tests/test_portable_runtime_stabilization_static.py \
  workspace/aura-sdk/tests/test_semantic_cognition_static.py \
  workspace/aura-sdk/tests/test_cognition_correlation_static.py \
  workspace/aura-sdk/tests/test_translation_intelligence_static.py -q
```

## Real Downstream Kernel Ingestion Cognition

This phase moves conversion reasoning from synthetic semantic assumptions to
real downstream kernel source ingestion while keeping execution governed and
fail-closed.

### Mission Alignment

Each new component directly maps to AURA mission goals:

- driver understanding:
  - real-tree parsing for `snd_soc_ops`, dai-link structures, vendor hooks, and proprietary runtime paths
- topology understanding:
  - FE/BE/DPCM reconstruction and normalized portable route modeling
- runtime evidence reasoning:
  - runtime evidence + replay contract are required inputs for conversion safety
- regression detection:
  - migration risk report merges drift lineage and blocker classification
- deterministic replay:
  - conversion bundle, artifact set, and replay traces use deterministic fingerprints
- upstream conversion capability:
  - confidence-scored upstream equivalence map + staged deterministic conversion plan

### New Engines

- `workspace/aura-sdk/src/aura_sdk/transport/downstream_driver_ingestion.py`
  - parses real downstream trees and emits `downstream_driver_graph`
- `workspace/aura-sdk/src/aura_sdk/transport/upstream_semantic_matcher.py`
  - maps downstream constructs to upstream ALSA/ASoC/DAPM/SoundWire abstractions
- `workspace/aura-sdk/src/aura_sdk/transport/portability_blocker_classifier.py`
  - classifies blockers into replay-safe/advisory/blocked-unsafe classes
- `workspace/aura-sdk/src/aura_sdk/transport/topology_reconstruction_cognition.py`
  - reconstructs normalized FE/BE + PCM/DPCM runtime topology graph
- `workspace/aura-sdk/src/aura_sdk/transport/real_downstream_conversion_planner.py`
  - plugin-driven orchestration, deterministic conversion plan, and replay-safe persistence

### Plugin Isolation Extensions

Target plugins now provide real ingestion adapters:

- `downstream_ingestion_adapter`
- `upstream_match_adapter`
- `topology_reconstruction_adapter`

Core runtime remains target-agnostic and contains no `if target == ...` branching.

### Real Ingestion Generator

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-real-downstream-ingestion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id real_downstream_ingestion_v1
```

Default source references used by this generator:

- downstream:
  - `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar`
- upstream:
  - `/local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/linux-upstream-v6.18`

### Generated Artifacts

- `downstream_driver_graph.json`
- `topology_runtime_graph.json`
- `upstream_equivalence_map.json`
- `portability_blockers.json`
- `migration_risk_report.json`
- `deterministic_conversion_plan.json`
- `governance_conversion_boundaries.json`
- `deterministic_conversion_replay.json`
- `real_downstream_ingestion_summary.json`

### Governance Constraints (Enforced)

- Allowed: analyze, classify, correlate, fingerprint, plan, recommend, replay
- Forbidden:
  - autonomous patch generation
  - autonomous topology mutation
  - unsafe runtime rewriting
  - unsupported semantic assumptions
- Planner is advisory/governed only and never rewrites DTS/drivers.

### Real Ingestion Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_target_plugin_runtime_static.py \
  workspace/aura-sdk/tests/test_portable_runtime_stabilization_static.py \
  workspace/aura-sdk/tests/test_translation_intelligence_static.py \
  workspace/aura-sdk/tests/test_real_downstream_ingestion_static.py -q
```

### Artifact Intent

- `portable_target_cognition_architecture.json`
  - reference target, design principles, execution posture, explicit non-goals
- `cognition_abstraction_layer.json`
  - interface contracts for identity, overlay, topology, route, evidence, mixer, scoring, replay adaptation
- `target_profile_schema.json`
  - portable target profile schema with required confidence/governance/replay fields
- `runtime_capability_negotiation_model.json`
  - state machine, deterministic degradation rules, confidence weighting model
- `deterministic_replay_compatibility_strategy.json`
  - RB3 reference replay contract and compatibility levels (`FULL`, `PARTIAL`, `INCOMPATIBLE`)
- `rb3_to_portable_migration_plan.json`
  - staged migration with explicit exit criteria and non-goals
- `new_target_validation_strategy.json`
  - onboarding gates and threshold-based exit criteria for new targets
- `cross_target_governance_boundaries.json`
  - cross-target policy boundaries and required validation artifacts
- `portable_multi_target_cognition_phase_summary.json`
  - artifact index and per-artifact fingerprint map

## Kernel Semantic Knowledge Layer

This subsystem ingests the Qualcomm Audio Knowledge Hub HTML and converts it
into governed, deterministic semantic cognition artifacts. It is explicitly
advisory-only and cannot execute runtime changes.

### Scope and Safety

- source:
  - `/local/mnt/workspace/Audio_knowledge_Hub/qcom_audio_knowledge_hub_v16.html`
- semantic knowledge is advisory cognition only
- runtime evidence remains execution truth
- no raw HTML is injected into runtime execution decisions
- no direct runtime execution from semantic outputs
- fail-closed governance remains enforced
- plugin isolation is preserved via `semantic_knowledge_adapter`

### Implemented Modules

Phase 1:

- `workspace/aura-sdk/src/aura_sdk/transport/semantic_html_parser.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_entity_extractor.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_relationship_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_ontology_builder.py`

Phase 2:

- `workspace/aura-sdk/src/aura_sdk/transport/semantic_runtime_advisory.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_governance_boundary.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_portability_reasoning.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_equivalence_mapper.py`

Phase 3:

- `workspace/aura-sdk/src/aura_sdk/transport/semantic_replay_compatibility.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_confidence_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/semantic_traceability_engine.py`

Runner:

- `scripts/aura-kernel-semantic-knowledge-layer.py`

### Generated Artifacts

- `semantic_entity_graph.json`
- `semantic_relationship_map.json`
- `semantic_ontology.json`
- `semantic_portability_rules.json`
- `semantic_equivalence_map.json`
- `semantic_runtime_advisories.json`
- `semantic_traceability_graph.json`
- `semantic_confidence_report.json`

Additional governance/replay outputs:

- `kernel_semantic_knowledge_layer_summary.json`
- `semantic_knowledge_replay_trace.json`

### Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-kernel-semantic-knowledge-layer.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id kernel_semantic_knowledge_layer_v1 \
  --knowledge-html /local/mnt/workspace/Audio_knowledge_Hub/qcom_audio_knowledge_hub_v16.html \
  --source-id qcom_audio_knowledge_hub \
  --source-version v16
```

### Mission Alignment

- driver understanding:
  - extracts Qualcomm/downstream abstractions and kernel subsystem vocabulary
- topology understanding:
  - captures FE/BE, DPCM, DAPM, PCM lifecycle concepts and cross-links
- runtime evidence reasoning:
  - runtime advisories are contextualized by semantic rules while keeping runtime truth precedence
- regression detection:
  - portability blockers and equivalence gaps become traceable migration risk signals
- deterministic replay:
  - deterministic fingerprints, artifact lineage, replay trace, and persisted registry state
- downstream-to-upstream conversion intelligence:
  - confidence-scored semantic equivalence maps and portability rules support governed migration planning

## Kernel Structural Cognition Layer

This phase adds deterministic source-structure cognition for real Linux kernel
trees while preserving:

- fail-closed governance
- runtime evidence as execution truth
- replay determinism
- plugin isolation
- advisory-only cognition behavior
- portable multi-target architecture

### Mission Alignment

Structural cognition directly improves:

- runtime debugging:
  - correlates runtime command evidence and route fingerprints to concrete source files and callback chains
- topology reasoning:
  - reconstructs DTS/DTSI structure, FE/BE linkage, DAPM graph shape, and SoundWire markers
- regression tracing:
  - produces deterministic structural fingerprints and lineage-indexed replay artifacts
- portability analysis:
  - inventories downstream hooks/vendor APIs and classifies blockers against upstream equivalence coverage
- downstream-to-upstream migration:
  - builds confidence-scored upstream equivalence traces from registration, ops, topology, and hook constructs
- deterministic replay confidence:
  - stores artifact fingerprints plus replay trace for exact structural state reconstruction

### Structural Components

- `workspace/aura-sdk/src/aura_sdk/transport/kernel_structural_cognition.py`
  - parser/orchestrator for:
    - Kconfig parsing
    - Makefile dependency cognition
    - DTS/DTSI structure extraction
    - ALSA registration tracing
    - `snd_soc_component` lifecycle extraction
    - DAPM widget/route extraction
    - FE/BE linkage reconstruction
    - SoundWire topology extraction
    - downstream hook inventory
    - upstream equivalence tracing
    - callback-chain reconstruction
    - runtime-to-source correlation
  - replay-safe registry persistence and lineage replay
- `scripts/aura-kernel-structural-cognition.py`
  - deterministic runner for artifact generation and registry persistence

### Plugin Isolation Extension

The plugin contract now includes:

- `structural_cognition_adapter`

Core structural planner remains target-agnostic and invokes only plugin
adapters, with no target-branching in core runtime.

### Run Structural Cognition

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-kernel-structural-cognition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id kernel_structural_cognition_v1
```

### Required Structural Artifacts

- `structural_graph.json`
- `driver_registration_graph.json`
- `topology_structure_graph.json`
- `runtime_source_correlation.json`
- `downstream_hook_inventory.json`
- `upstream_equivalence_trace.json`
- `portability_blocker_graph.json`
- `callback_chain_graph.json`
- `deterministic_structural_fingerprint.json`

Additional generated outputs:

- `deterministic_structural_replay.json`
- `kernel_structural_cognition_summary.json`
- `docs/operations/transport/kernel_structural_cognition_architecture.md`

### Structural Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_target_plugin_runtime_static.py \
  workspace/aura-sdk/tests/test_kernel_structural_cognition_static.py -q
```

## Governed Conversion Reasoning Engine

This phase reasons about *why* downstream implementations cannot directly map
to upstream Linux abstractions while preserving:

- advisory-only reasoning
- fail-closed governance
- deterministic replay
- runtime-truth precedence
- plugin isolation
- semantic/structural separation

### Mission Alignment

This phase directly improves:

- upstream migration planning:
  - phased migration plan gated by blocker/risk/equivalence evidence
- regression prevention:
  - deterministic conversion reasoning trace with lineage + replay fingerprints
- runtime portability analysis:
  - explicit unsupported runtime dependencies and runtime blocker reasoning
- topology conversion confidence:
  - confidence model combines topology gaps, lifecycle mismatch, and upstream coverage
- governed conversion reasoning:
  - risk/classification is fail-closed with explicit governance boundary checks
- deterministic migration replay:
  - replay-safe persistence for all reasoning artifacts

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/conversion_reasoning_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/portability_blocker_classifier.py` (governed classifier extension)
- `workspace/aura-sdk/src/aura_sdk/transport/abstraction_gap_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/migration_phase_planner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/upstream_equivalence_confidence.py`
- `workspace/aura-sdk/src/aura_sdk/transport/lifecycle_incompatibility_detector.py`
- `workspace/aura-sdk/src/aura_sdk/transport/vendor_dependency_classifier.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_portability_reasoner.py`

Runner:

- `scripts/aura-governed-conversion-reasoning.py`

### Required Artifacts

- `conversion_reasoning_graph.json`
- `portability_blocker_report.json`
- `migration_phase_plan.json`
- `abstraction_gap_report.json`
- `upstream_equivalence_confidence.json`
- `lifecycle_incompatibility_report.json`
- `vendor_dependency_graph.json`
- `runtime_portability_analysis.json`
- `deterministic_conversion_reasoning_trace.json`

Additional outputs:

- `deterministic_conversion_reasoning_replay.json`
- `governed_conversion_reasoning_summary.json`
- `docs/operations/transport/governed_conversion_reasoning_architecture.md`

### Run Governed Conversion Reasoning

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-conversion-reasoning.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id governed_conversion_reasoning_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_governed_conversion_reasoning_static.py \
  workspace/aura-sdk/tests/test_translation_intelligence_static.py \
  workspace/aura-sdk/tests/test_real_downstream_ingestion_static.py -q
```

## Incremental Migration Orchestration Layer

This phase adds governed staged migration orchestration that decomposes
downstream-to-upstream conversion into replay-safe, rollback-aware phases
without mutating runtime state or source code.

### Mission Alignment

This phase directly improves:

- safe incremental upstreaming:
  - migration is decomposed into explicit staged phases with hard boundaries
- runtime-safe migration sequencing:
  - runtime stability gates must pass (or remain advisory) before phase advance
- regression containment:
  - dependency-linked transition state isolates blocked/high-risk paths
- rollback-aware conversion:
  - irreversible and checkpoint-only boundaries are explicitly modeled
- topology transition governance:
  - FE/BE and DPCM-related sequencing is included in dependency + phase plans
- deterministic migration replay:
  - every orchestration artifact has deterministic fingerprints and lineage trace

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/migration_orchestrator.py`
- `workspace/aura-sdk/src/aura_sdk/transport/staged_conversion_planner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/rollback_boundary_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_stability_gate.py`
- `workspace/aura-sdk/src/aura_sdk/transport/migration_dependency_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/portability_transition_tracker.py`
- `workspace/aura-sdk/src/aura_sdk/transport/incremental_equivalence_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/migration_checkpoint_registry.py`

Runner:

- `scripts/aura-incremental-migration-orchestration.py`

### Orchestration Outputs

- `staged_migration_plan.json`
- `migration_dependency_graph.json`
- `rollback_boundary_report.json`
- `runtime_stability_gate_report.json`
- `portability_transition_state.json`
- `incremental_equivalence_report.json`
- `migration_checkpoint_registry.json`
- `deterministic_migration_orchestration_trace.json`

Additional operational outputs:

- `deterministic_migration_orchestration_replay.json`
- `incremental_migration_orchestration_summary.json`
- `docs/operations/transport/incremental_migration_orchestration_architecture.md`

### Run Incremental Orchestration

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-incremental-migration-orchestration.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id incremental_migration_orchestration_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_incremental_migration_orchestration_static.py \
  workspace/aura-sdk/tests/test_governed_conversion_reasoning_static.py \
  workspace/aura-sdk/tests/test_translation_intelligence_static.py \
  workspace/aura-sdk/tests/test_real_downstream_ingestion_static.py -q
```

### Governance and Architecture Constraints (Preserved)

- advisory-only orchestration (no autonomous rewriting)
- fail-closed governance enforcement
- runtime-truth precedence
- plugin isolation (core runtime remains target-agnostic)
- deterministic replay compatibility
- semantic/structural separation

## Patch Cognition and Upstream Readiness Engine

This phase evolves migration orchestration into governed upstream patch
intelligence. It reasons about patch lineage, subsystem boundaries,
maintainership-safe sequencing, runtime impact, and bisect-safe evolution.

### Mission Alignment

This phase directly improves:

- upstream patch preparation:
  - generates readiness scoring, patch dependency ordering, and upstream-safe series planning
- subsystem-safe migration:
  - maps subsystem ownership boundaries and cross-subsystem risk before series formation
- regression containment:
  - correlates runtime evidence and source impact to estimate blast radius by patch group
- maintainership alignment:
  - generates maintainership-aware sequencing and review group recommendations per patch step
- runtime-aware patch sequencing:
  - ties patch grouping and order to runtime-source correlation and topology/runtime evidence
- bisect-safe evolution:
  - validates bisectability per patch group with guardrail requirements
- deterministic patch replay:
  - persists lineage and deterministic replay fingerprint for reproducible patch cognition state

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/patch_cognition_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/upstream_readiness_classifier.py`
- `workspace/aura-sdk/src/aura_sdk/transport/patch_dependency_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/subsystem_boundary_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/vendor_contamination_detector.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_patch_correlation.py`
- `workspace/aura-sdk/src/aura_sdk/transport/bisectability_validator.py`
- `workspace/aura-sdk/src/aura_sdk/transport/api_evolution_tracker.py`
- `workspace/aura-sdk/src/aura_sdk/transport/patch_series_orchestrator.py`
- `workspace/aura-sdk/src/aura_sdk/transport/upstream_governance_gate.py`

Runner:

- `scripts/aura-patch-cognition-readiness.py`

### Required Artifacts

- `upstream_readiness_report.json`
- `patch_dependency_graph.json`
- `subsystem_boundary_map.json`
- `vendor_contamination_report.json`
- `runtime_patch_correlation.json`
- `bisectability_report.json`
- `api_evolution_trace.json`
- `patch_series_plan.json`
- `deterministic_patch_replay.json`

Additional outputs:

- `patch_cognition_summary.json`
- `docs/operations/transport/patch_cognition_upstream_readiness_architecture.md`

### Run Patch Cognition Phase

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-patch-cognition-readiness.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id patch_cognition_upstream_readiness_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_patch_cognition_static.py \
  workspace/aura-sdk/tests/test_incremental_migration_orchestration_static.py \
  workspace/aura-sdk/tests/test_governed_conversion_reasoning_static.py \
  workspace/aura-sdk/tests/test_real_downstream_ingestion_static.py -q
```

### Governance Boundaries (Preserved)

- advisory-only behavior
- no autonomous patch submission
- fail-closed governance enforcement
- deterministic replay preservation
- plugin isolation preservation
- runtime-truth precedence
- semantic/structural/runtime separation

## Runtime Truth Cognition Layer (Offline Foundation)

This phase introduces runtime-truth correlation and replay-aware execution
cognition using archived traces, synthetic runtime sequences, deterministic
replay artifacts, and persisted runtime lineage. Live target/device dependency
is explicitly out of scope for this phase.

### Mission Alignment

This phase directly improves:

- runtime debugging:
  - correlates runtime events into domain-specific traces (PCM/DAPM/IRQ/DSP/SoundWire)
- real hardware reasoning:
  - builds hardware-facing cognition models from offline runtime evidence without requiring live connection
- downstream timing analysis:
  - tracks PCM lifecycle timing, IRQ ordering, DSP sync latency, and runtime timing drift
- regression localization:
  - drift detector localizes sequencing/timing regressions against expected lineage
- topology runtime validation:
  - validates runtime topology activation via FE/BE and SoundWire runtime graph correlation
- DSP/runtime synchronization analysis:
  - reasons over mailbox + DSP response sequencing and sync failure patterns
- deterministic runtime replay:
  - produces deterministic runtime replay artifact and replay-safe lineage persistence
- upstream runtime equivalence reasoning:
  - creates replayable runtime truth evidence usable by governed downstream→upstream reasoning phases

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/runtime_truth_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_event_ingestion.py`
- `workspace/aura-sdk/src/aura_sdk/transport/trace_correlation_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/dapm_runtime_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/pcm_lifecycle_tracker.py`
- `workspace/aura-sdk/src/aura_sdk/transport/soundwire_runtime_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/irq_timing_analyzer.py`
- `workspace/aura-sdk/src/aura_sdk/transport/dsp_sync_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_drift_detector.py`
- `workspace/aura-sdk/src/aura_sdk/transport/deterministic_runtime_replay.py`

Runner:

- `scripts/aura-runtime-truth-cognition.py`

### Required Artifacts

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
- `docs/operations/transport/runtime_truth_cognition_architecture.md`

### Run Runtime Truth Cognition

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-truth-cognition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id runtime_truth_cognition_offline_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_runtime_truth_cognition_static.py \
  workspace/aura-sdk/tests/test_patch_cognition_static.py \
  workspace/aura-sdk/tests/test_real_downstream_ingestion_static.py -q
```

### Runtime Truth Constraints (Preserved)

- runtime-truth precedence over static assumptions
- fail-closed governance boundaries
- deterministic replay-first behavior
- plugin isolation and hardware-agnostic core reasoning
- advisory-only behavior
- semantic/structural/runtime separation
- offline foundation mode (no live device connection required)

## Runtime Evidence Fusion Layer

This phase fuses semantic, structural, topology, runtime, migration, and patch
cognition into a unified engineering-truth model with deterministic replay and
fail-closed governance.

### Mission Alignment

This phase directly improves:

- root-cause debugging:
  - correlates runtime drift, lifecycle causality, DSP timing, patch lineage, and migration state into one causal view
- runtime regression localization:
  - identifies cross-domain causes behind runtime drift and sequencing instability
- downstream→upstream runtime equivalence:
  - aligns migration checkpoints and patch readiness against runtime truth evidence
- DSP synchronization analysis:
  - correlates DSP sync health with IRQ timing and SoundWire runtime observations
- topology/runtime causality reasoning:
  - links FE/BE topology activation to PCM/DAPM runtime transitions and confidence outcomes
- patch/runtime drift analysis:
  - traces patch-group runtime impact against observed drift and readiness posture
- deterministic engineering replay:
  - emits replay-safe fusion lineage and deterministic fingerprints for every fusion artifact
- unified kernel cognition:
  - generates a single graph-backed engineering truth model spanning runtime, topology, semantic, migration, and patch domains

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/runtime_evidence_fusion_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/unified_engineering_truth_graph.py`
- `workspace/aura-sdk/src/aura_sdk/transport/cross_domain_reasoning_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/lifecycle_causality_mapper.py`
- `workspace/aura-sdk/src/aura_sdk/transport/topology_runtime_correlator.py`
- `workspace/aura-sdk/src/aura_sdk/transport/patch_runtime_lineage.py`
- `workspace/aura-sdk/src/aura_sdk/transport/migration_runtime_alignment.py`
- `workspace/aura-sdk/src/aura_sdk/transport/dsp_runtime_causality.py`
- `workspace/aura-sdk/src/aura_sdk/transport/regression_rootcause_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/deterministic_fusion_replay.py`

Runner:

- `scripts/aura-runtime-evidence-fusion.py`

### Required Artifacts

- `unified_engineering_truth_graph.json`
- `runtime_topology_correlation.json`
- `lifecycle_causality_map.json`
- `migration_runtime_alignment.json`
- `patch_runtime_lineage.json`
- `dsp_runtime_causality_report.json`
- `regression_rootcause_report.json`
- `deterministic_fusion_replay.json`
- `engineering_confidence_score.json`

Additional outputs:

- `runtime_evidence_fusion_summary.json`
- `docs/operations/transport/runtime_evidence_fusion_architecture.md`

### Run Runtime Evidence Fusion

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-evidence-fusion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id runtime_evidence_fusion_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_runtime_evidence_fusion_static.py \
  workspace/aura-sdk/tests/test_runtime_truth_cognition_static.py \
  workspace/aura-sdk/tests/test_patch_cognition_static.py -q
```

### Fusion Constraints (Preserved)

- runtime-truth precedence over static/semantic assumptions
- fail-closed governance and bounded advisory-only reasoning
- deterministic replay and lineage persistence
- plugin isolation with target intelligence only through adapters
- semantic/runtime separation boundaries
- migration governance preservation (no autonomous rewriting or mutation)

## Runtime Incident Reconstruction and Root-Cause Reasoning Layer

This phase transitions AURA from knowledge+migration cognition into deterministic
runtime engineering incident reasoning.

It reconstructs:

- what failed
- where failure originated
- what runtime sequence drifted
- what topology/runtime dependency broke
- what patch/migration/runtime event contributed to the issue
- what upstream/downstream abstraction mismatch exists

This layer remains advisory-only and governed. It does not autonomously fix,
rewrite source, or mutate runtime evidence.

### Mission Alignment

This phase directly improves:

- runtime debugging:
  - reconstructs ordered runtime timeline and subsystem activation chain from multi-source evidence
- regression localization:
  - correlates drift, lifecycle violations, topology inconsistencies, and patch/migration causality
- upstream migration confidence:
  - surfaces abstraction mismatches, portability blockers, and migration-induced incompatibilities
- deterministic replay:
  - persists replay-safe incident lineage with deterministic incident replay fingerprints
- topology/runtime reasoning:
  - maps FE/BE dependency sequence, DPCM lifecycle transitions, and topology activation inconsistencies
- DSP/runtime synchronization analysis:
  - incorporates DSP/mailbox/IRQ/SoundWire timing into incident causality and confidence scoring

### Implemented Components

- `workspace/aura-sdk/src/aura_sdk/transport/runtime_incident_reconstructor.py`
- `workspace/aura-sdk/src/aura_sdk/transport/root_cause_reasoner.py`
- `workspace/aura-sdk/src/aura_sdk/transport/topology_runtime_failure_mapper.py`
- `workspace/aura-sdk/src/aura_sdk/transport/patch_runtime_causality_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/lifecycle_violation_detector.py`
- `workspace/aura-sdk/src/aura_sdk/transport/runtime_sequence_drift_engine.py`
- `workspace/aura-sdk/src/aura_sdk/transport/evidence_confidence_engine.py`

Runner:

- `scripts/aura-runtime-incident-reconstruction.py`

### Required Artifacts

- `runtime_incident_graph.json`
- `root_cause_candidates.json`
- `lifecycle_violation_report.json`
- `runtime_sequence_drift.json`
- `topology_runtime_causality.json`
- `regression_causality_report.json`
- `deterministic_incident_replay.json`
- `engineering_confidence_report.json`

Additional outputs:

- `runtime_incident_reconstruction_summary.json`
- `docs/operations/transport/runtime_incident_reasoning_architecture.md`

### Run Runtime Incident Reconstruction

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-incident-reconstruction.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --lineage-id runtime_incident_reconstruction_v1
```

### Validation Tests

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_runtime_incident_reconstruction_static.py \
  workspace/aura-sdk/tests/test_runtime_evidence_fusion_static.py \
  workspace/aura-sdk/tests/test_runtime_truth_cognition_static.py \
  workspace/aura-sdk/tests/test_patch_cognition_static.py -q
```

### Incident Reasoning Constraints (Preserved)

- runtime-truth precedence over static assumptions
- fail-closed behavior on uncertain classifications
- deterministic replay and lineage persistence
- plugin/runtime isolation via adapter contracts
- advisory-only behavior (no autonomous source/runtime mutation)
- migration governance and semantic/runtime separation boundaries

## Engineering Investigation and Query Reasoning Layer

This phase transitions AURA from runtime observability to interactive,
deterministic engineering reasoning.

### Scope

- interactive engineering query handling for:
  - runtime failures
  - topology inconsistencies
  - migration blockers
  - upstream readiness and patch causality
  - DSP/runtime synchronization
  - lifecycle drift and regression lineage
- deterministic evidence-backed answers with explicit:
  - evidence sources
  - causality chains
  - confidence scores
  - replay lineage
  - governance state
  - fail-closed justification

### Core Modules

- orchestration:
  - `workspace/aura-sdk/src/aura_sdk/transport/engineering_query_engine.py`
- planning + reasoning:
  - `causality_query_planner.py`
  - `investigation_reasoner.py`
- resolvers:
  - `runtime_question_resolver.py`
  - `migration_question_resolver.py`
  - `topology_question_resolver.py`
  - `patch_reasoning_resolver.py`
  - `replay_evidence_resolver.py`
- session and lineage:
  - `investigation_session_registry.py`
  - `engineering_query_history.py`
  - `reasoning_lineage_tracker.py`
- runner:
  - `scripts/aura-engineering-investigation.py`

### Generated Artifacts

- `investigation_reasoning_graph.json`
- `engineering_answer_trace.json`
- `causality_resolution_report.json`
- `migration_blocker_reasoning.json`
- `runtime_question_lineage.json`
- `deterministic_investigation_replay.json`
- `engineering_investigation_summary.json`

### Run Engineering Investigation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-engineering-investigation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id engineering_investigation_session_v1 \
  --lineage-id engineering_investigation_v1 \
  --question "What caused this runtime failure?"
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_engineering_investigation_static.py \
  workspace/aura-sdk/tests/test_runtime_incident_reconstruction_static.py \
  workspace/aura-sdk/tests/test_runtime_evidence_ingestion_static.py -q
```

### Investigation Constraints (Preserved)

- no hallucinated explanations
- fail-closed behavior on insufficient evidence
- runtime-truth precedence over static assumptions
- deterministic replay and lineage persistence
- plugin/runtime isolation via adapters
- advisory-only behavior (no autonomous mutation or patch generation)

### Architecture Document

- `docs/operations/transport/engineering_investigation_architecture.md`

## Governed Downstream-To-Upstream Translation Intelligence Layer

This layer converts downstream translation cognition into a governed,
evidence-backed translation plan with deterministic replay lineage.

### Focus Coverage

- PCM lifecycle translation
- DAPM route equivalence
- FE/BE topology conversion
- SoundWire upstream mapping
- vendor callback abstraction replacement
- runtime-safe API substitution reasoning

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/governed_translation_intelligence.py`
- Runner:
  - `scripts/aura-governed-translation-intelligence.py`

### Required Artifacts (Generated)

- `upstream_translation_plan.json`
- `api_replacement_map.json`
- `unsupported_vendor_constructs.json`
- `lifecycle_translation_graph.json`
- `runtime_equivalence_validation.json`
- `translation_confidence_report.json`
- `deterministic_translation_replay.json`
- `governed_translation_intelligence_summary.json`

### Run Governed Translation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-translation-intelligence.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_translation_session_v1 \
  --lineage-id governed_translation_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_governed_translation_intelligence_static.py \
  workspace/aura-sdk/tests/test_translation_intelligence_static.py -q
```

### Governance + Determinism Constraints

- no fake or unsupported mappings accepted as PASS
- fail-closed on ambiguity/insufficient evidence/unsupported constructs
- runtime-truth precedence for equivalence validation
- deterministic translation replay lineage persistence
- plugin/runtime isolation preserved (no core target branching)

### Architecture Document

- `docs/operations/transport/governed_translation_intelligence_architecture.md`

## Governed Translation Execution Layer

This layer executes governed AST-aware source transformations from translation
intelligence artifacts, with deterministic patch lineage and fail-closed
gating.

### Focus Coverage

- callback replacement transformation
- vendor macro elimination
- FE/BE topology rewrite scaffolding
- DAPM route conversion generation
- SoundWire upstream adaptation
- runtime-safe API substitution
- migration staging boundaries
- rollback-safe patch chunking

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/governed_translation_execution.py`
- Runner:
  - `scripts/aura-governed-translation-execution.py`

### Required Artifacts (Generated)

- `generated_upstream_patch.diff`
- `transformation_lineage.json`
- `unsafe_transformation_blocks.json`
- `runtime_validated_patch_segments.json`
- `deterministic_patch_generation_replay.json`
- `translation_execution_report.json`
- `governed_translation_execution_summary.json`

### Run Governed Translation Execution

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-translation-execution.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_translation_execution_session_v1 \
  --lineage-id governed_translation_execution_v1 \
  --dry-run
```

Optional source inputs:

```bash
  --source-root /path/to/downstream/kernel \
  --source-file sound/soc/qcom/qdsp6/q6apm-dai.c \
  --source-file sound/soc/qcom/qdsp6/q6apm-lpass-dais.c
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_governed_translation_execution_static.py \
  workspace/aura-sdk/tests/test_governed_translation_intelligence_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on unresolved blockers or insufficient confidence
- runtime-equivalence gating before transformations
- runtime-truth precedence over static assumptions
- deterministic replay lineage persistence for patch generation
- plugin/runtime isolation preserved (no core target branching)
- advisory-only behavior (no autonomous patch submission)

### Architecture Document

- `docs/operations/transport/governed_translation_execution_architecture.md`

## Governed Adaptive Remediation and Translation Learning Layer

This layer learns from governed translation outcomes and manual remediation
decisions while preserving fail-closed governance.

### Focus Coverage

- translation pattern memory
- vendor abstraction learning
- runtime validation feedback correlation
- reusable remediation template extraction
- confidence calibration refinement
- cross-driver equivalence reuse
- historical blocker similarity detection
- subsystem-specific migration intelligence

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/governed_adaptive_remediation.py`
- Runner:
  - `scripts/aura-governed-adaptive-remediation.py`

### Required Artifacts (Generated)

- `learned_translation_patterns.json`
- `remediation_template_registry.json`
- `historical_blocker_similarity_map.json`
- `confidence_calibration_report.json`
- `reusable_equivalence_library.json`
- `subsystem_translation_memory.json`
- `adaptive_remediation_trace.json`
- `governed_adaptive_remediation_summary.json`

### Run Governed Adaptive Remediation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-adaptive-remediation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_adaptive_remediation_session_v1 \
  --lineage-id governed_adaptive_remediation_v1
```

Optional manual learning input:

```bash
  --manual-remediation-file /path/to/manual_remediation_outcomes.json
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_governed_adaptive_remediation_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on insufficient runtime-backed learning evidence
- learned patterns cannot bypass fail-closed without runtime-backed evidence
- deterministic lineage and replay-safe persistence
- plugin/runtime isolation preserved (no target branching in core)
- advisory-only behavior (no autonomous patching/mutation)

### Architecture Document

- `docs/operations/transport/governed_adaptive_remediation_architecture.md`

## Runtime Evidence Acquisition and Hardware Truth Validation Layer

This layer ingests real runtime traces (or archived target sessions), correlates
hardware truth against translation expectations, and enforces runtime-backed
equivalence confidence before governed transformation reuse.

### Focus Coverage

- live trace ingestion adapters
- IPCAT hardware descriptor ingestion
- runtime topology reconstruction
- PCM/DAPM/SoundWire lifecycle capture
- DSP/mailbox synchronization tracing
- IRQ ordering capture
- clock/regulator state correlation
- runtime equivalence fingerprinting
- target session persistence + replay
- cross-platform runtime comparison
- evidence quality scoring + missing-runtime-coverage detection

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/runtime_evidence_acquisition.py`
- Runner:
  - `scripts/aura-runtime-evidence-acquisition.py`

### Required Artifacts (Generated)

- `runtime_equivalence_fingerprint.json`
- `hardware_truth_graph.json`
- `target_runtime_capture.json`
- `downstream_upstream_runtime_diff.json`
- `ipc_topology_map.json`
- `evidence_quality_report.json`
- `runtime_divergence_report.json`
- `target_session_replay.json`
- `runtime_evidence_acquisition_summary.json`

### Run Runtime Evidence Acquisition

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-runtime-evidence-acquisition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id runtime_evidence_acquisition_session_v1 \
  --lineage-id runtime_evidence_acquisition_v1
```

Optional IPCAT descriptor:

```bash
  --ipcat-hardware-metadata /path/to/ipcat_hardware_descriptor.json
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_runtime_evidence_acquisition_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on low runtime-backed equivalence confidence
- transformations blocked below runtime-backed confidence threshold
- runtime-truth precedence over static assumptions
- deterministic replay-safe session persistence
- plugin/runtime isolation preserved (no target branching in core)
- advisory-only behavior (no autonomous runtime/source mutation)

### Architecture Document

- `docs/operations/transport/runtime_evidence_acquisition_architecture.md`

## Upstream Acceptance Simulation and Patch Validation Layer

This layer simulates upstream maintainer review readiness and blocks unsafe
downstream-to-upstream delivery unless runtime-backed governance thresholds are
met.

### Focus Coverage

- upstream review simulation
- patch series quality validation
- bisectability validation
- maintainer ownership reasoning
- subsystem boundary validation
- API conformity validation
- dependency cleanliness analysis
- runtime-backed regression risk scoring
- patch sequencing + commit taxonomy enforcement
- coding-style validation
- stable/backport suitability analysis
- runtime evidence citation mapping
- governance-aware acceptance confidence scoring

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/upstream_acceptance_simulation.py`
- Runner:
  - `scripts/aura-upstream-acceptance-simulation.py`

### Required Artifacts (Generated)

- `upstream_acceptance_report.json`
- `patch_series_validation.json`
- `maintainer_scope_map.json`
- `regression_risk_assessment.json`
- `bisectability_validation.json`
- `upstream_submission_plan.json`
- `patch_dependency_order.json`
- `acceptance_confidence_score.json`
- `deterministic_submission_replay.json`
- `upstream_acceptance_simulation_summary.json`

### Run Upstream Acceptance Simulation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-upstream-acceptance-simulation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id upstream_acceptance_session_v1 \
  --lineage-id upstream_acceptance_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_upstream_acceptance_simulation_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on insufficient runtime-backed equivalence confidence
- fail-closed on subsystem isolation violations
- fail-closed on regression containment confidence below threshold
- fail-closed when unsupported vendor abstractions remain unresolved
- autonomous delivery authorization only after acceptance passes threshold
- deterministic replay-safe submission lineage persistence

### Architecture Document

- `docs/operations/transport/upstream_acceptance_simulation_architecture.md`

## Controlled Downstream-to-Upstream Pilot Conversion Framework

This layer executes small, runtime-backed, governance-approved pilot
transformations and produces human-reviewable upstream patch proposals.

### Pilot Scope (Allowed)

- logging wrapper replacement
- vendor macro normalization
- simple helper abstraction removal
- PCM capability mapping cleanup
- small topology normalization
- static downstream wrapper elimination
- trivial API replacement equivalence
- isolated subsystem utility conversion

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/controlled_pilot_conversion.py`
- Runner:
  - `scripts/aura-controlled-pilot-conversion.py`

### Required Artifacts (Generated)

- `pilot_conversion_patch.diff`
- `transformation_explainability_report.json`
- `runtime_equivalence_validation.json`
- `upstream_review_package.json`
- `pilot_risk_assessment.json`
- `transformation_lineage.json`
- `rollback_validation_report.json`
- `deterministic_pilot_replay.json`
- `governance_decision_report.json`
- `controlled_pilot_conversion_summary.json`

### Run Controlled Pilot Conversion

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-controlled-pilot-conversion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id controlled_pilot_conversion_session_v1 \
  --lineage-id controlled_pilot_conversion_v1 \
  --source-manifest /local/mnt/workspace/AURA_V1/docs/operations/transport/pilot_source_manifest.json
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_controlled_pilot_conversion_static.py -q
```

### Governance + Determinism Constraints

- fail-closed by default
- no autonomous patch application to production branches
- human review required before final upstream export
- runtime-backed equivalence confidence is mandatory
- unsupported vendor abstractions block execution
- cross-subsystem transformations are prohibited in pilot mode
- deterministic replay and lineage persistence are mandatory

### Architecture Document

- `docs/operations/transport/controlled_pilot_conversion_architecture.md`

## First Real Governed Micro-Conversion Pilot

This phase runs one real tiny Qualcomm-style downstream construct conversion
end-to-end using existing governed layers:

- runtime truth cognition
- runtime evidence acquisition
- governed translation intelligence
- governed translation execution
- adaptive remediation
- upstream acceptance simulation
- controlled pilot conversion

### Pilot Focus

- `qcom_dbg_log` -> `dev_dbg`
- `qcom_cap_bool` -> `device_is_registered`

### Runner

- `scripts/aura-real-micro-conversion-pilot.py`

### Required Artifacts (Generated)

- `real_micro_conversion.patch`
- `transformation_explainability_report.json`
- `runtime_equivalence_validation.json`
- `governance_decision_report.json`
- `conversion_confidence_report.json`
- `rollback_lineage.json`
- `deterministic_conversion_replay.json`
- `upstream_acceptance_prediction.json`
- `real_micro_conversion_summary.json`

### Run

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-real-micro-conversion-pilot.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id real_micro_conversion_session_v1 \
  --lineage-id real_micro_conversion_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_real_micro_conversion_pilot_static.py -q
```

### Governance Rules

- fail-closed default
- no autonomous production patch application
- runtime-backed equivalence required
- unsupported vendor constructs must block conversion
- deterministic replay + lineage persistence required

## Governed Patchset Orchestration Engine

This phase extends AURA from single micro-conversion execution to
dependency-aware multi-patch orchestration while preserving:

- fail-closed governance
- runtime-truth precedence
- deterministic replay and lineage
- plugin-safe isolation boundaries
- advisory-only transformation posture

### Focus Coverage

- dependency-aware patch ordering and prerequisite reasoning
- subsystem grouping + runtime dependency validation
- cumulative runtime equivalence validation across sequential patches
- bisect-safe sequencing with intermediate compile safety checks
- rollback-safe checkpoint persistence
- upstream review risk prediction and governance escalation
- explainable patchset ordering and decision traceability

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/governed_patchset_orchestration.py`
- Runner:
  - `scripts/aura-governed-patchset-orchestration.py`

### Required Artifacts (Generated)

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

Additional generated outputs:

- `tiny_patchset_model.json`
- `governed_patchset_orchestration_runner_summary.json`

### Run Governed Patchset Orchestration

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-governed-patchset-orchestration.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --session-id governed_patchset_session_v1 \
  --lineage-id governed_patchset_orchestration_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_governed_patchset_orchestration_static.py -q
```

### Governance + Determinism Constraints

- fail-closed if dependency cycles or unsafe ordering are detected
- fail-closed if any intermediate compile/syntax safety check fails
- fail-closed if cumulative runtime confidence drops below threshold
- fail-closed if topology consistency fails after sequential application
- fail-closed if upstream prediction is below threshold
- deterministic replay + rollback checkpoint lineage required
- no autonomous patch application/submission

## Real Source-Tree Governed Conversion Layer

This phase upgrades AURA from synthetic-only micro transformations to real
Qualcomm downstream source-tree cognition with strict fail-closed governance.

### Focus Coverage

- parse real `.c/.h/Kconfig/Makefile` driver trees
- build source graph, include dependency graph, symbol dependency graph
- identify subsystem boundaries and runtime-sensitive regions
- classify vendor wrappers and upstream equivalence opportunities
- plan tiny controlled transformations (debug/helper normalization only)
- generate real patch proposal from actual source paths
- enforce compile-oriented validation and deterministic replay lineage

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/real_source_tree_governed_conversion.py`
- Runner:
  - `scripts/aura-real-source-tree-governed-conversion.py`

### Required Artifacts (Generated)

- `source_tree_graph.json`
- `subsystem_boundary_map.json`
- `symbol_dependency_graph.json`
- `wrapper_classification_report.json`
- `governed_conversion_plan.json`
- `compile_validation_report.json`
- `runtime_sensitive_regions.json`
- `governance_escalation_report.json`
- `deterministic_driver_replay.json`
- `transformation_confidence_report.json`
- `upstream_equivalence_map.json`
- `downstream_to_upstream.patch`
- `real_driver_conversion_summary.json`

### Run Real Source-Tree Governed Conversion

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 scripts/aura-real-source-tree-governed-conversion.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --source-root /local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar \
  --session-id real_source_tree_conversion_session_v1 \
  --lineage-id real_source_tree_governed_conversion_v1
```

### Validation

```bash
PYTHONPATH=/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/src \
python3 -m pytest \
  workspace/aura-sdk/tests/test_real_source_tree_governed_conversion_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on runtime-sensitive unsafe changes
- fail-closed on compile/inclusion/symbol-lineage uncertainty
- fail-closed on confidence drop below threshold
- advisory-only behavior; no autonomous patch application/submission
- deterministic replay lineage persisted for every artifact

## Real Patch Application + Governed Build Validation Layer

This phase upgrades AURA from static patch planning into real sandboxed patch
application with compile-oriented validation and deterministic rollback
lineage.

### Focus Coverage

- apply generated patch against real source-tree context in sandbox mode
- detect patch dry-run failures, apply failures, fuzz, and reject files
- compile touched objects only (`.c` touched by patch)
- validate include closure and symbol replacement consistency
- classify runtime-sensitive compile impacts (safe vs unsafe touches)
- trigger deterministic rollback on fail-closed conditions
- persist replay-safe build/governance lineage and confidence state

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/real_patch_application_governed_build.py`
- Runner:
  - `scripts/aura-real-patch-build-validation.py`

### Required Artifacts (Generated)

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

### Run Real Patch Build Validation

```bash
python3 scripts/aura-real-patch-build-validation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --source-root /local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar \
  --patch-path /local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch \
  --session-id real_patch_build_validation_session_v1 \
  --lineage-id real_patch_application_governed_build_v1
```

### Validation

```bash
python3 -m pytest \
  workspace/aura-sdk/tests/test_real_patch_application_governed_build_static.py -q
```

### Governance + Determinism Constraints

- fail-closed if patch apply fails/conflicts/rejects
- fail-closed if touched-object compile fails
- fail-closed if include or symbol closure is incomplete
- fail-closed if runtime-sensitive regions are unsafely impacted
- deterministic rollback lineage required for any fail-closed outcome
- advisory-only behavior; no autonomous patch application/submission

## Kernel Dependency Closure + Compile Cognition Layer

This phase hardens compile reasoning on top of governed source-tree conversion
by adding deterministic include/symbol/Kconfig/Makefile dependency cognition.

### Focus Coverage

- full include closure graph generation
- symbol provider/consumer dependency reasoning
- Kconfig chain validation and impossible-config detection
- Makefile object topology validation
- compile boundary governance for patch-touched subsystems
- runtime-sensitive compile strictness for DSP/mailbox/IRQ/PCM/DAPM/SoundWire
- deterministic compile replay lineage persistence

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/compile_cognition_engine.py`
- Runner:
  - `scripts/aura-compile-cognition.py`

### Required Artifacts (Generated)

- `include_closure_graph.json`
- `symbol_dependency_graph.json`
- `kconfig_dependency_map.json`
- `compile_boundary_report.json`
- `unresolved_dependency_report.json`
- `compile_governance_escalation.json`
- `deterministic_compile_replay.json`
- `compile_confidence_report.json`
- `subsystem_compile_topology.json`

### Run Compile Cognition

```bash
python3 scripts/aura-compile-cognition.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --source-root /local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar \
  --patch-path /local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch \
  --session-id compile_cognition_session_v1 \
  --lineage-id compile_cognition_v1
```

### Validation

```bash
python3 -m pytest \
  workspace/aura-sdk/tests/test_compile_cognition_static.py -q
```

### Governance + Determinism Constraints

- fail-closed if include closure is incomplete
- fail-closed if symbol lineage is unresolved
- fail-closed if Kconfig dependency chain is inconsistent
- fail-closed if subsystem compile topology cannot be proven
- fail-closed if runtime-sensitive compile boundaries are crossed unsafely
- deterministic replay lineage required for all compile cognition decisions

## Real Build Execution + Compilation Governance Layer

This phase extends compile cognition into real build command execution and
governance-first compilation risk classification.

### Focus Coverage

- controlled dry-run + execution build commands
- targeted subsystem/object build validation
- build topology reconstruction from Makefiles/object lineage
- symbol closure and cross-subsystem coupling analysis
- linker/modpost instability signal detection
- runtime-sensitive build-region risk escalation
- deterministic replay persistence for build command lineage

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/build_execution_engine.py`
- Runner:
  - `scripts/aura-build-execution.py`

### Required Artifacts (Generated)

- `build_topology_graph.json`
- `subsystem_build_map.json`
- `object_lineage_graph.json`
- `symbol_closure_report.json`
- `unresolved_dependency_report.json`
- `build_confidence_report.json`
- `runtime_sensitive_build_regions.json`
- `deterministic_build_replay.json`
- `build_execution_summary.json`
- `governance_build_decision.json`

### Run Build Execution Governance

```bash
python3 scripts/aura-build-execution.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --source-root /local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar \
  --patch-path /local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch \
  --session-id build_execution_session_v1 \
  --lineage-id build_execution_v1
```

### Validation

```bash
python3 -m pytest \
  workspace/aura-sdk/tests/test_build_execution_static.py -q
```

### Governance + Determinism Constraints

- fail-closed on unresolved symbol/dependency closure
- fail-closed on linker/modpost instability
- fail-closed on unsafe runtime-sensitive build regions
- fail-closed on unsafe incremental rebuild conditions
- deterministic replay lineage required for all build decisions

## Real Patch Application + Sandbox Build Validation Layer

This phase upgrades AURA from build cognition into real transformation
execution governance using isolated patch-application sandboxes and real build
validation commands.

### Focus Coverage

- isolated sandbox workspace creation with cleanup cognition
- real patch dry-run/apply trace and lineage
- subsystem + object-level sandbox build execution
- modpost/linker closure governance
- object rebuild lineage and symbol regression tracking
- build fingerprint equivalence and transformation gating
- deterministic rollback cognition
- runtime promotion eligibility gating

### Core Components

- Engine:
  - `workspace/aura-sdk/src/aura_sdk/transport/sandbox_patch_validation_engine.py`
- Runner:
  - `scripts/aura-sandbox-patch-validation.py`

### Required Artifacts (Generated)

- `sandbox_workspace_manifest.json`
- `applied_patch_lineage.json`
- `patch_application_trace.json`
- `subsystem_build_validation.json`
- `object_rebuild_lineage.json`
- `modpost_validation_report.json`
- `linker_closure_report.json`
- `symbol_regression_report.json`
- `build_fingerprint_diff.json`
- `transformation_equivalence_report.json`
- `runtime_promotion_eligibility.json`
- `rollback_lineage_report.json`
- `deterministic_patch_validation_replay.json`
- `runtime_sensitive_patch_impact.json`
- `sandbox_patch_validation_summary.json`
- `governance_patch_validation_decision.json`

### Run Sandbox Patch Validation

```bash
python3 scripts/aura-sandbox-patch-validation.py \
  --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport \
  --registry-path /local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json \
  --target-id RB3Gen2 \
  --source-root /local/mnt/workspace/AURA_V1/evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar \
  --patch-path /local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch \
  --session-id sandbox_patch_validation_session_v1 \
  --lineage-id sandbox_patch_validation_v1
```

### Validation

```bash
python3 -m pytest \
  workspace/aura-sdk/tests/test_sandbox_patch_validation_static.py -q
```

### Governance + Determinism Constraints

- fail-closed if patch apply is partial/conflicted
- fail-closed on unresolved compile/link/modpost closure
- fail-closed on unstable runtime-sensitive patch impacts
- fail-closed if rollback is unsafe/incomplete
- fail-closed if runtime promotion eligibility cannot be proven
- deterministic replay lineage required for patch execution governance

## Runtime Loop Automation (Three-Screen Validation)

Loop wrappers:

- `scripts/loop_cognition_boot.sh`
- `scripts/loop_stability_offline.sh`
- `scripts/loop_event_quarantine.sh`

Launch all 3 loops in one tmux session:

```bash
cd /local/mnt/workspace/AURA_V1/AURA
bash scripts/launch_three_tests_tmux.sh aura_tests
```

Useful tmux commands:

```bash
tmux attach -t aura_tests
tmux list-windows -t aura_tests
tmux capture-pane -pt aura_tests:0 -S -60
tmux capture-pane -pt aura_tests:1 -S -60
tmux capture-pane -pt aura_tests:2 -S -60
tmux kill-session -t aura_tests
```

## Governance and Safety Boundaries

All cognition/execution must preserve:

- fail-closed policy default
- runtime evidence-backed confidence only
- deterministic replay constraints
- bounded, governed execution posture
- no hidden prompt-memory dependency

Forbidden by design:

- autonomous patching
- autonomous topology rewriting
- autonomous upstream generation
- autonomous mixer mutation

## Troubleshooting

### `ModuleNotFoundError: No module named 'pydantic'`

Use deterministic env sync, then re-run:

```bash
make env-sync
python3 scripts/aura-cognition-boot.py --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport
```

### Shell loop syntax errors (`done: command not found`)

Ensure multiline bash format:

```bash
while true; do
  python3 scripts/aura-cognition-boot.py --output-dir /local/mnt/workspace/AURA_V1/docs/operations/transport
  sleep 5
done
```

## Repository Layout

```
AURA/
├── workspace/aura-sdk/        # shared SDK and cognition transport modules
├── services/
│   ├── core/                  # orchestrator + APIs + governance gateways
│   ├── llm-gateway/           # LLM provider boundary
│   └── ws-server/             # event and stream transport
├── dashboard/                 # operational UI
├── agents/                    # agent runtime surfaces
├── scripts/                   # deterministic operational tooling
├── knowledge/schema/          # DB schema migrations
├── governance/                # policy definitions
├── evidence/                  # generated execution evidence
└── Makefile                   # primary operator entry points
```

## License

Proprietary. All rights reserved.
