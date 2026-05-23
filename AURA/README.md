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
# deterministic Python environment sync
make env-sync

# development mode
make dev

# tests
make test

# parity checks (local py3.12 or docker fallback)
make ci-parity

# lint
make lint

# logs / db shell
make logs-core
make shell-db
```

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
- immutable capture lineage chain and replay-safe session persistence
- plugin adapter boundary preserved (`runtime/topology/semantic` adapters only)

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
