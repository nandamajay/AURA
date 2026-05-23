# AURA Operator Workflows

Date: 2026-05-18
Scope: operational interface layer

## 1) Runtime State Triage
1. Open `Global Command Center` (`/`).
2. Check `Operational Class`, `Queue Pressure`, `Replay Health`, `Websocket/SSE`.
3. If alert rows exist, classify by `surface` (queue, retry, replay_buffer, websocket_sse).
4. Move to `Live Agent Observability` (`/agents`) for per-domain pressure details.

## 2) Replay Lineage Inspection
1. Open `Replay & Evidence Explorer` (`/debug`).
2. Enter `task_id` and run `Inspect Replay`.
3. Confirm boundary classification:
   - `finalized replay`
   - `mutable replay (not deterministic replayable yet)`
   - `non-replayable`
4. For finalized replay, inspect:
   - `output_hash`
   - `snapshot_hash`
   - lifecycle timeline and execution steps

## 3) Governance Chronology Inspection
1. Open `Governance Timeline Viewer` (`/governance`).
2. Filter by event/user/target.
3. Validate chronology signals:
   - contiguous id pairs
   - id gaps
   - non-monotonic timestamp count
4. Inspect linked replay for task-targeted audit rows.

## 4) Coexistence / Domain Pressure Diagnosis
1. Open `Live Agent Observability` (`/agents`).
2. Review `Runtime Pressure Surface` and `Per-Domain Coexistence Health`.
3. Confirm queue starvation markers and fairness override signals by domain.
4. Correlate with `Global Command Center` alert surface.

## 5) Evidence Navigation
1. Open `/debug` and use `Evidence Browser`.
2. Load evidence index.
3. Filter and open reports under sections:
   - `runtime_evidence`
   - `architecture_consolidation`
   - `p1_docs`
4. Use evidence files as operator source-of-truth during incident analysis.

## 6) Determinism Audit Support
1. In `/debug`, use `Determinism Inspector`.
2. Paste suspect code snippet.
3. Run scan and review nondeterminism findings and recommendation.

## Operational Doctrine Embedded in UX
- Bounded behavior is visible, not hidden.
- Replay boundary (`finalized` vs `mutable`) is explicit.
- Governance timeline ordering diagnostics are explicit.
- Evidence is first-class navigable data.
