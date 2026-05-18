# P1.2 Event Ordering + Duplicate/Out-of-Order Policy Hardening (2026-05-18)

## Subphase objective
- Fix runtime-validated `event_ordering_pressure` weakness from P1.1.
- Enforce explicit, deterministic ordering policy at ws broadcast ingestion without architecture expansion.

## Runtime finding reproduced (BEFORE)
- Evidence file: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-2-before-20260518T082000Z.json`
- `event_ordering_pressure` severity: `medium`
- Observed:
  - `retry_order_delivery=[2,1,3]` (non-monotonic)
  - `out_of_order_delivery=[5,3,4,2,1]`
  - duplicate deliveries observed under pressure (`duplicate_delivery_count=373`)
  - bounded replay buffer behavior remained deterministic (`replayed_burst_count=1000` from `burst_sent=1200`)
- Race finding: `Retry attempts were observed in non-monotonic order.`

## Affected code paths
- `AURA/services/ws-server/src/ws_server/main.py`
  - `/broadcast` ingestion and fanout path
  - SSE replay buffer insertion path
- `AURA/services/ws-server/tests/test_main.py`
  - added adversarial regression coverage for duplicate, retry normalization, and sequence violation detection

## Minimal correction implemented
- Added serialized broadcast ingestion lock (`_BROADCAST_LOCK`) for deterministic ingest sequencing.
- Added explicit ordering policy metadata (`_ordering`) per accepted/rejected event:
  - `policy_version`
  - `ingest_sequence`
  - `duplicate_event` + `first_seen_sequence` when duplicate is dropped
  - `sequence_violation` + expected/received sequence annotations for out-of-order streams
  - `retry_order_normalized` + original/expected attempts for non-monotonic retry events
- Added bounded duplicate memory (`OrderedDict`) to suppress duplicate `event_id` replay/broadcast.
- Added bounded stream tracking for retry normalization and out-of-order sequence observability.
- Preserved architecture shape (FastAPI + in-memory state, no new services/infra).

## Regression tests added/executed
- `services/ws-server/tests/test_main.py`
  - `test_broadcast_deduplicates_event_id_and_keeps_single_buffer_entry`
  - `test_broadcast_normalizes_retry_attempts_to_monotonic_order`
  - `test_broadcast_marks_sequence_violation_for_out_of_order_stream`
- Execution evidence:
  - `docker exec aura-ws-server ... pytest -q tests/test_main.py`
  - Result: `8 passed`

## Mandatory validation rerun (AFTER)
- Evidence file: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-2-after-20260518T083500Z.json`
- Full rerun scope executed (all 8 required areas):
  - concurrency
  - event ordering pressure
  - WAL contention
  - replay stress
  - watchdog pressure
  - websocket/SSE instability
  - governance pressure
  - failure injection/corruption

## Before vs after operational delta
- Global severity counts:
  - BEFORE: `high=0, medium=1, low=2, info=5`
  - AFTER: `high=0, medium=0, low=3, info=5`
- `event_ordering_pressure`:
  - BEFORE severity: `medium`
  - AFTER severity: `low`
  - BEFORE `retry_order_delivery=[2,1,3]`
  - AFTER `retry_order_delivery=[1,2,3]`
  - BEFORE race finding present; AFTER race finding cleared.

## Replay integrity + audit chronology
- Replay behavior for burst buffer remained bounded and deterministic:
  - `burst_sent=1200`, `replayed_burst_count=1000`, drop estimate `200` (unchanged, explicit bound).
- Audit mismatch deltas remained `0` in rerun summary checks.
- Ordering decisions are now replay-visible via `_ordering` metadata in buffered and delivered events.

## Determinism verification
- Broadcast samples now include deterministic ingest sequence and policy actions, e.g.:
  - duplicate suppression with `dropped_duplicate=true`
  - retry normalization with `retry_original_attempt` and `retry_expected_attempt`
  - out-of-order sequence violation annotation (`expected_seq`, `received_seq`)

## Residual weaknesses (truthful)
- Duplicate counts in the adversarial metric remain elevated because the test intentionally aggregates multiple concurrent subscribers into a single stream; this reflects fanout multiplicity, not only duplicate acceptance.
- Out-of-order payload sequences are intentionally not reordered except retry-attempt normalization path; they are flagged explicitly.
- Replay buffer remains bounded-loss by design (`_BUFFER_SIZE=1000`).

## Subphase status
- P1.2 complete.
- Scope remained surgical and architecture-preserving.
