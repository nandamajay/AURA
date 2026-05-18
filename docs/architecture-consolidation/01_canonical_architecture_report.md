# AURA Canonical Architecture Report

Date: 2026-05-18
Branch baseline: `stabilization/p1-runtime-reliability`
Scope: consolidation-only (no feature expansion, no infrastructure escalation)

## Evidence Baseline
- `evidence/runtime-isolation/2026-05-18-bounded-runtime-isolation-stabilization-report.md`
- `evidence/runtime-isolation/2026-05-18-coexistence-delta-report.md`
- `evidence/runtime-isolation/2026-05-18-runtime-isolation-confidence-summary.json`
- `evidence/plugin-coexistence/2026-05-18-plugin-coexistence-report.md`
- `evidence/plugin-coexistence/2026-05-18-runtime-cell-feasibility-report.md`
- `evidence/endurance/2026-05-18-endurance-soak-validation-report.md`

## Canonical System Shape
AURA is a deterministic, governance-first, single-node modular monolith with:
- SQLite (WAL)
- in-memory EventBus
- Docker Compose deployment
- CLI agent subprocess execution

No distributed queue, no multi-node replay, and no runtime sandbox isolation are part of the current architecture.

## aura-core Definition

### Core Responsibilities
`aura-core` owns the global correctness plane:
- orchestration and queue scheduling (3-tier + fairness controls)
- runtime spawn/terminate lifecycle for CLI agents
- event routing and persistence-before-broadcast
- retry sequencing and retry lineage persistence
- replay lifecycle gates (`mutable` to `finalized`)
- governance state transition enforcement
- append-only audit chronology
- architecture/determinism/governance CI gates

Primary code-path anchors:
- `AURA/services/core/src/core/services/task_queue.py`
- `AURA/services/core/src/core/services/agent_runtime.py`
- `AURA/services/core/src/core/services/watchdog.py`
- `AURA/services/core/src/core/events.py`
- `AURA/services/core/src/core/routers/governance.py`
- `AURA/workspace/aura-sdk/src/aura_sdk/replay/recorder.py`
- `AURA/workspace/aura-sdk/src/aura_sdk/replay/replayer.py`
- `AURA/workspace/aura-sdk/src/aura_sdk/validation/architecture.py`

### Core Invariants
- Events are persisted to audit before WS forward (`_persist_and_forward`).
- Governance approval transitions are serialized with `BEGIN IMMEDIATE`.
- Replay integrity is computed from finalized immutable snapshot hashes.
- Retry lineage is monotonic per scoped retry key in validated runs.
- Runtime behavior is auditable and replay-visible by default.

### Core Non-Goals (Current)
- tenant-grade isolation
- distributed durability semantics
- zero-loss stream delivery
- plugin trust sandboxing
- cross-node consensus

### Forbidden Responsibilities in `aura-core`
- domain/business logic of plugins
- hidden autonomous policy rewrites
- non-audited side effects
- untracked fallback behavior
- distributed orchestration features (Kafka/Redis/K8s/etc.)

## aura-plugin / runtime-cell Definition
Plugins are bounded workload providers, not autonomous infrastructure controllers.

### What Plugins Own
- domain-specific rule loading
- domain-specific validation/suggestion logic
- domain metadata and capabilities

### What Plugins Do Not Own
- queue policy
- retry policy
- governance transitions
- replay finalization rules
- audit ledger semantics

### Current Runtime-Cell Model
- isolation marker: `plugin_domain` and `runtime_cell_scope=domain:<name>`
- routing scope: base channel + domain channel
- retry scope: includes task/domain/agent identity
- replay lineage: per task log, domain-tagged by payload convention

### Shared vs Isolated
- Shared: scheduler core, event bus process, audit ledger, WS/SSE service, replay buffer memory.
- Isolated by policy/tagging: routing channels, retry lineage, queue/fairness metadata, replay namespace checks.
- Bounded (not strong isolation): queue fairness under heavy bursts, stream pressure behavior, replay buffer contention, plugin fault containment.

## Architecture Truth Statement
Current architecture is coherence-first and deterministic-first for controlled internal workloads.
It is not a multi-tenant isolation platform and does not claim hard trust boundaries between plugins.
