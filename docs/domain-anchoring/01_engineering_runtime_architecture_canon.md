# Engineering Runtime Architecture Canon

Date: 2026-05-18
Primary domain: Audio downstream-to-upstream engineering workflow orchestration

## 1) Domain Reclassification of AURA
Under this target domain, AURA is reclassified as:

A deterministic engineering runtime control plane for:
1. downstream driver intake orchestration
2. patch transformation workflow orchestration
3. upstream preparation sequencing
4. validation/testing dispatch and evidence capture
5. review/governance gate enforcement
6. replayable engineering execution and audit lineage
7. operator-led intervention/approval chains
8. deterministic retry/recovery under bounded runtime constraints

AURA is not:
- a full patch authoring IDE
- a Linux maintainer workflow replacement
- a zero-loss CI transport fabric
- a fully isolated multi-tenant plugin runtime

## 2) Stable Layering (Engineering Runtime View)
1. `aura-core` kernel layer:
   - deterministic control behavior and integrity constraints
2. Runtime orchestration layer:
   - queueing, agent lifecycle, retries, watchdog
3. Replay/governance integrity layer:
   - replay state machine, hash integrity, approval transitions, audit ledger
4. Plugin runtime layer:
   - domain extension points under controlled contracts
5. Domain workflow layer:
   - downstream intake, diff analysis, upstream prep, validation/review flows
6. Application/API layer:
   - REST surfaces for tasks/patches/governance/simulation/knowledge
7. Operator layer:
   - dashboard, intervention, replay and governance inspection
8. External integration edge:
   - LLM gateway, CI/review systems, toolchain wrappers

## 3) Architecture Anchor by Domain Activity

### Downstream driver intake
- anchored as task/plugin-domain ingestion activity into orchestrator queue
- must remain replay-visible and auditable

### Patch transformation
- anchored as task-driven transformation outputs + patch status evolution
- patch metadata table exists; current patch API behavior is partially stubbed

### Upstream preparation
- anchored as sequenced validation/simulation/review stages, not hidden automation

### Validation/testing orchestration
- anchored as orchestrated task and simulation execution with explicit evidence outputs

### Review/governance workflow
- anchored as deterministic approval state transitions + role-based authority

### Replayable engineering execution
- anchored to `task_logs` mutable/finalized boundaries and hash verification

### Operator approval chains
- anchored via governance approvals, charter controls, and manual control endpoints

### Evidence/audit lineage
- anchored via append-only audit ledger plus evidence artifacts under `evidence/`

### Deterministic retry/recovery
- anchored via scoped retry lineage and bounded failure handling

## 4) Current Domain Maturity Truth
Implemented strongly:
- deterministic task orchestration kernel
- governance transition conflict handling
- finalized replay integrity checks
- persistence-before-broadcast event path

Implemented but bounded:
- queue fairness under pressure
- websocket/sse delivery completeness
- replay completeness during active churn
- WAL contention resilience

Partial/stubbed for this domain:
- patch API operational depth (`/patches` routes largely placeholders)
- fully integrated end-to-end downstream->patch->upstream workflow state machine
- dedicated domain plugin set beyond `audio-qualcomm`

## 5) Runtime Assumptions (Engineering Domain)
1. Single-node transactional execution remains the governing consistency model.
2. CLI-agent subprocess model remains mandatory for execution isolation boundaries.
3. SQLite WAL is the authoritative persistence layer for task/replay/governance state.
4. Event transport is bounded-loss under pressure and cannot be treated as hard-delivery truth.
5. Operator authority remains mandatory for high-risk and irreversible engineering decisions.
