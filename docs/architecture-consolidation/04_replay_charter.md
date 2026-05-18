# Replay Charter

Date: 2026-05-18

## Replay Architecture
Replay is split into two states:
- `mutable`: task execution is recording prompts/responses/steps.
- `finalized`: immutable snapshot (`snapshot_json`, `snapshot_hash`) exists and replay is allowed.

## Replay Lineage Requirements
- Task starts with `start_task`.
- Execution steps are recorded incrementally.
- Finalization computes output hash + snapshot hash under transaction.
- Replay engine rejects non-finalized rows for deterministic replay.

## Replay Integrity Model
Integrity check passes only if:
- stored `output_hash` matches computed hash
- stored `snapshot_hash` matches computed hash (when present)

## Replay Failure Semantics
- Missing task log: `incomplete`
- Non-finalized task log: `incomplete`
- Hash mismatch: integrity failure
- Corrupt JSON fields: safe parsing fallback; replay can degrade to incomplete semantics

## Bounded-Loss Semantics
Replay from finalized logs is strong.
Replay visibility through event stream during active pressure is bounded due to shared buffer and delivery drops.

## Non-Replayable State Classes (Current)
- transient WS connection state
- in-flight volatile queue occupancy at crash moment
- dropped SSE events beyond retained buffer window

## Canonical Boundaries
- Finalized replay is immutable by design.
- Mutable logs are not deterministic replay artifacts.
- Governance/audit events must remain available independently of WS delivery.
