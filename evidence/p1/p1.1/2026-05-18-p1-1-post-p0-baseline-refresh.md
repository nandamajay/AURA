# P1.1 Post-P0 Adversarial Baseline Refresh (2026-05-18)

## Subphase objective
- Execute full post-P0 adversarial rerun without architecture mutation.
- Re-establish runtime truth baseline before any P1 hardening changes.

## Before evidence
- `AURA/data/outputs/runtime_discovery/runtime_discovery_20260517T193152Z-kieleu.json`
- Baseline truth: `high=1`, `medium=1`, `low=2`, `info=4`.
- Highest unresolved class at baseline time: `governance_pressure_testing` (high).

## After evidence
- `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-baseline-20260518T071004Z-ged4md.json`
- Refreshed truth: `high=0`, `medium=1`, `low=2`, `info=5`.

## Mandatory validation coverage (executed)
- Concurrency rerun: `concurrent_task_execution`
  - `max_overlapping_running=25`
  - final task states: `{'completed': 28}`
- Replay rerun: `replay_stress_validation`
  - mutable replay successes: `0`
  - stable finalized replay hash count: `1`
- Reconnect rerun: `websocket_sse_instability`
  - `ws_clients=14`, `broadcast_calls=220`, recipients `14..14`
- WAL contention rerun: `sqlite_wal_stress`
  - `no_retry_failures=40`, `with_retry_failures=40`, `busy_timeout_failures=20`
  - checkpoint invocations captured: `50`
- Corruption rerun: `failure_injection` + `replay_stress_validation`
  - malformed replay payload surfaced explicit parse error
  - rollback preservation remained true
- Audit verification: all subtests captured before/after audit summaries with `delta_mismatches=0`
  - notable deltas: concurrency `+370` audit rows, governance `+35` audit rows
- Deterministic sequencing verification: `event_ordering_pressure`
  - retry attempts observed as `[2,1,3]` (non-monotonic)
  - out-of-order sample `[5,3,4,2,1]`
  - replay-buffer drop estimate `200`

## Expected vs actual (P1.1)
- Expected: post-P0 rerun should remove prior governance high-severity race class.
- Actual: governance class downgraded out of high; no high severity remained.
- Remaining medium class: `event_ordering_pressure` only.

## Operational truth findings
- Governance race fix held under rerun (`conflict_statuses=[200,409]`, escalate `200`).
- Replay boundary fix held (`mutable_replay_success_count=0`).
- Audit persistence remained coherent (`delta_mismatches=0` across all tests).
- Event ordering remains weak under pressure (duplicates/out-of-order/non-monotonic retry order).
- WAL contention is now strongly characterized under forced lock (writes fail deterministically under held exclusive lock).

## Risks carried into P1.2+
- Ordering determinism remains unresolved (`event_ordering_pressure`, medium).
- Transport replay buffer still permits deterministic drop under pressure; policy is observable but not yet explicitly bounded in architecture contract.

## Subphase status
- P1.1 complete.
- No architecture redesign performed.
- Evidence package regenerated using post-P0 code state.
