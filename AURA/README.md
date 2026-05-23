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
