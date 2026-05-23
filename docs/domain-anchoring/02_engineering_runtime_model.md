# Engineering Runtime Model

Date: 2026-05-18

## 1) Task Lifecycle
Source of truth:
- `TaskStatus`: `created -> queued -> started -> running -> completed|failed|cancelled|timed_out`
- source: `AURA/workspace/aura-sdk/src/aura_sdk/models/task.py`

Operational anchors:
- creation, queueing, dispatch, retries: `TaskQueueManager`
- agent subprocess runtime: `AgentRuntimeManager`

## 2) Patch Lifecycle
Source of truth:
- `PatchStatus`: `draft -> migrating -> validating -> simulating -> reviewing -> approved|rejected -> upstreamed`
- source: `AURA/workspace/aura-sdk/src/aura_sdk/models/patch.py`
- schema: `AURA/knowledge/schema/005_patches.sql`

Current execution truth:
- lifecycle model and schema exist
- current patch REST endpoints are largely placeholders; operational transition engine is incomplete in API layer

## 3) Validation Lifecycle
Runtime model (current):
- validation is currently represented through task execution, optional simulation runs, and evidence artifacts, not a dedicated first-class `validation_runs` domain table.
- simulation lifecycle exists with `pending|running|passed|failed|inconclusive` in `simulation_results`.

Implication:
- validation orchestration is real but fragmented across task/simulation/evidence surfaces.

## 4) Approval Lifecycle
Source of truth:
- approval statuses: `pending -> in_progress -> passed|failed|skipped`
- serialized transition logic with deterministic conflict handling (`409` on conflicting terminal overwrite)
- source: `AURA/services/core/src/core/routers/governance.py`

## 5) Replay Lifecycle
Source of truth:
- `recording_state`: `mutable|finalized`
- finalized replay requires integrity checks (`output_hash`, `snapshot_hash`)
- source: `AURA/knowledge/schema/018_task_logs_replay_boundaries.sql`
- API surfaces: `/tasks/{task_id}/replay` and `/tasks/{task_id}/replay/state`

## 6) Evidence Lifecycle
Evidence classes:
1. audit ledger events (DB append-only chronology)
2. replay artifacts (`task_logs`)
3. runtime campaign outputs (`evidence/` reports)
4. startup/demo/validation artifacts

Lifecycle:
- generated during runtime or campaign execution
- retained for replay/diagnosis/governance review
- must not be silently reset in bootstrap flows

## 7) Operator Intervention Lifecycle
Anchors:
- charter manual controls: intervene, override, rollback
- task cancellation endpoint
- replay and audit inspection endpoints

Lifecycle:
1. operator detects issue (dashboard/evidence)
2. operator inspects replay + governance chronology
3. operator intervenes (cancel/intervene/override/rollback)
4. operator verifies post-action replay/audit continuity

## 8) Engineering Runtime Sequence (Domain-Aligned)
1. intake task queued (`plugin_domain=audio/driver` style domain marker)
2. transformation tasks run through agent runtime
3. validation/simulation tasks executed and captured
4. governance approvals processed deterministically
5. finalized replay and evidence reviewed by operator
6. retry/recovery executed within bounded deterministic rules
