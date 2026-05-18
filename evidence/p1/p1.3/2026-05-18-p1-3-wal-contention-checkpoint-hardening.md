# P1.3 WAL Contention / Checkpoint Determinism Hardening (2026-05-18)

## Subphase objective
- Harden persistence behavior under SQLite WAL pressure without architecture change.
- Make retry semantics and checkpoint behavior explicit, deterministic, and test-backed.

## Runtime finding baseline (BEFORE)
- Baseline reference: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-2-after-20260518T083500Z.json`
- `sqlite_wal_stress` baseline observation:
  - `no_retry_failures=40`
  - `with_retry_failures=40`
  - `busy_timeout_failures=20`
  - `checkpoint_total=50`
- Interpretation: forced exclusive lock scenario remains bounded but opaque in application-level retry/checkpoint policy.

## Affected code paths
- `AURA/services/core/src/core/events.py`
- `AURA/services/core/tests/test_event_audit_persistence.py`

## Minimal correction implemented
- Replaced implicit linear retry delay with deterministic backoff schedule:
  - `_PERSIST_RETRY_BACKOFF_SECONDS=(0.05, 0.1, 0.2, 0.4, 0.8)`
  - `_PERSIST_RETRY_ATTEMPTS=6`
- Added explicit checkpoint policy for audit WAL:
  - `_WAL_CHECKPOINT_EVERY` (env-configurable, default `200`)
  - periodic `PRAGMA wal_checkpoint(PASSIVE)` after successful persisted writes
  - checkpoint result logged (`checkpoint_status`, `wal_pages`, `checkpointed_pages`)
- Preserved per-event transaction model (`BEGIN IMMEDIATE` + commit/rollback) to avoid changing audit chronology semantics.

## Adversarial regression tests added
- `test_persist_event_to_audit_retries_locked_then_succeeds`
- `test_persist_event_to_audit_uses_deterministic_retry_backoff`
- `test_persist_event_to_audit_triggers_wal_checkpoint_at_threshold`

## Regression test execution evidence
- `docker exec -u 0 aura-core ... pytest -q tests/test_event_audit_persistence.py tests/test_watchdog.py`
- Result: `10 passed`
- ws regression sanity:
  - `docker exec aura-ws-server ... pytest -q tests/test_main.py`
  - Result: `8 passed`

## Mandatory validation rerun (AFTER)
- Evidence file: `AURA/data/outputs/runtime_discovery/runtime_discovery_p1-3-after-20260518T090500Z.json`
- Full rerun scope executed:
  - concurrency
  - event ordering
  - WAL stress
  - replay stress
  - watchdog pressure
  - websocket/SSE instability
  - governance pressure
  - failure injection/corruption

## Before vs after operational delta
- Global severity distribution unchanged:
  - BEFORE (`p1-2-after`): `high=0, medium=0, low=3, info=5`
  - AFTER (`p1-3-after`): `high=0, medium=0, low=3, info=5`
- WAL stress class remained `info` (expected under forced exclusive-lock test shape).
- Deterministic policy improvements validated via code-path tests and runtime logs.

## Runtime proof of checkpoint behavior
- Core runtime log evidence (post-fix):
  - `audit_wal_checkpoint` emitted with checkpoint tuple values.
  - sample: `checkpoint_status=0, wal_pages=0, checkpointed_pages=0`
- This proves checkpoint execution is now explicit and observable from core persistence path.

## Replay integrity + audit chronology
- Replay metrics remained stable (`mutable_replay_success_count=0`, `stable_replay_hash_count=1`).
- Audit mismatch deltas remained `0` in rerun summary checks.
- No new nondeterminism/race findings were introduced in rerun output.

## Truthful residual weaknesses
- Forced-lock WAL stress still shows full write failure during lock hold (`with_retry_failures=40`) because lock is intentionally held across retry window in test shape.
- Current change improves determinism/observability rather than claiming lock elimination.
- Write batching remains intentionally unmodified in core audit path to preserve strict per-event audit ordering semantics.

## Subphase status
- P1.3 complete.
- Architecture shape preserved.
