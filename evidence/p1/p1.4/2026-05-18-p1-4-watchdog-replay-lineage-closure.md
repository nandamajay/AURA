# P1.4 Watchdog + Event Replay Lineage Closure (2026-05-18)

## Subphase objective
- Close replay lineage gap for watchdog-managed task terminations.
- Ensure timeout/termination chain becomes replay-visible and deterministic without architecture redesign.

## Runtime finding reproduced (BEFORE)
- Baseline reference: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-3-after-20260518T090500Z.json`
- `watchdog_pressure_testing.replay_integrity_result.watchdog_task_replay_presence`
  - all watchdog synthetic tasks were `False` (no replay entries)
- Baseline note explicitly indicated recorder integration incompleteness.

## Affected code paths
- `AURA/services/core/src/core/services/watchdog.py`
- `AURA/services/core/src/core/lifespan.py`
- `AURA/services/core/tests/test_watchdog.py`
- `AURA/scripts/p1_adversarial_rerun.py`

## Minimal correction implemented
- Added optional replay recorder integration to watchdog manager (`TaskRecorder`).
- Added replay lifecycle capture for watchdog flow:
  - `watchdog_timeout_detected`
  - `watchdog_sigterm_issued`
  - `watchdog_sigkill_issued` (when needed)
  - `watchdog_terminated`
  - `watchdog_unregistered`
- Added safe replay-row initialization for watchdog-managed tasks when no row exists.
- Added terminal replay finalization for watchdog outcomes (`completed` or `killed`) with reason + heartbeat context.
- Wired production watchdog initialization to recorder in lifespan (`TaskRecorder(Config.SQLITE_PATH)`).
- Updated adversarial watchdog test harness to validate replay presence and missing count.

## Adversarial regression tests added/executed
- Added unit regression:
  - `test_watchdog_timeout_flow_finalizes_replay_and_preserves_existing_row`
- Execution evidence:
  - `docker exec -u 0 aura-core ... pytest -q tests/test_watchdog.py`
  - Result: `5 passed`

## Mandatory validation rerun (AFTER)
- Final after artifact: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-4-after-20260518T093500Z.json`
- Full rerun scope executed (all 8 required areas):
  - concurrency
  - event ordering
  - WAL contention
  - replay stress
  - watchdog pressure
  - websocket/SSE instability
  - governance pressure
  - failure injection/corruption

## Before vs after watchdog lineage delta
- BEFORE (`p1-3-after`): watchdog replay presence was all `False`.
- AFTER (`p1-4-after-20260518T093500Z`): watchdog replay presence is all `True` with `missing_replay_count=0`.
- Observed watchdog behavior remained stable:
  - `timeout_event_count=9`
  - `killed_event_count=5`
  - `remaining_watch_count=0`

## Runtime replay proof (live API)
- Verified real replay endpoint for watchdog task:
  - `GET /api/v1/tasks/wd-task-kill-0-p1-4-after-20260518T093500Z/replay` -> `200`
  - `integrity_ok=True`, `recording_state=finalized`, `execution_steps=5`
  - output includes watchdog terminal context (`status=killed`, `reason=watchdog_timeout`, `heartbeats_missed=20`)

## Replay + audit integrity
- Replay integrity improved specifically for watchdog lineage closure.
- Audit mismatch deltas remained `0` in rerun summary checks.
- No new nondeterminism findings introduced.

## Truthful residual weaknesses
- Watchdog pressure test still runs on synthetic process doubles; behavior is validated under controlled simulation, not OS-level process chaos.
- Audit delta during standalone watchdog pressure test remains `0` in this harness shape because it uses local event bus scope, not full core event-bridge persistence path.

## Subphase status
- P1.4 complete.
- P1 sequence (`P1.1 -> P1.2 -> P1.3 -> P1.4`) executed in order with isolated commits/evidence.
