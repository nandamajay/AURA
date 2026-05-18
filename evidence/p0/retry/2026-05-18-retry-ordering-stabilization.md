# P0 Retry Ordering Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `retry-ordering-non-monotonic-and-missing-lineage`
- Before evidence:
  - `AURA/data/outputs/runtime_discovery/retry_semantics_before_retry-before-66dc8cd7.json`
- Observed issue before fix:
  - Retryable failure (`exit_code=3`) moved task directly to `failed`.
  - No retry requeue happened despite `max_retries=3`.
  - Retry event lineage was absent (`retry_event_count=0`, `current_attempt=1`).

## Affected subsystem and code paths
- Subsystem: `S1 Orchestrator` task queue/runtime integration
- Code path:
  - `AURA/services/core/src/core/services/task_queue.py`
- Tests:
  - `AURA/services/core/tests/test_task_queue_retry_ordering.py`

## Minimal correction implemented
- Added retryable exit-code classification: `timeout`, `resource_exhausted`, `llm_unavailable`.
- Implemented deterministic retry scheduling in `_on_agent_failed`:
  - Requeue only when `current_attempt < max_retries`.
  - Persist monotonic `retry_lineage` entries with explicit `retry_sequence`.
  - Persist `last_failure`, `retry_pending`, and final status markers in `result_data`.
- Added duplicate-failure guard:
  - Ignore repeated `AGENT_FAILED` once task has left `STARTED|RUNNING` for that attempt.
- Added replay-visible retry event emission:
  - Publish `TASK_QUEUED` with retry metadata after persistence path.

## Regression validation
- Containerized run (Python 3.12 runtime parity):
  - `python -m pytest -q /app/services/core/tests/test_task_queue_retry_ordering.py /app/services/core/tests/test_task_queue_external_spawn.py /app/services/core/tests/test_tasks_input_validation.py /app/services/core/tests/test_governance_stabilization.py /app/services/core/tests/test_event_audit_persistence.py /app/workspace/aura-sdk/tests/test_replay.py`
  - Result: `21 passed`

## Runtime validation after fix
- After evidence:
  - `AURA/data/outputs/runtime_discovery/retry_semantics_after_retry-after-d0494528.json`
- Result delta:
  - `runtime_spawn_calls=3`
  - `retry_event_count=2`
  - `retry_sequences=[1,2]` with `retry_sequence_monotonic=true`
  - final task state: `completed`, `current_attempt=3`
  - duplicate first failure did not double-schedule retry (lineage remained single entry for attempt 1)

## Replay and deterministic impact
- Retry progression is now persisted in task result lineage and is replay-visible.
- Retry ordering is deterministic and monotonic within a task.
- Duplicate failure fanout no longer causes nondeterministic double-requeue.

## Regression risk assessment
- Low/medium:
  - `result_data` schema now stores richer retry metadata (`retry_lineage`, `last_failure`, `retry_pending`).
  - Consumers that parse `result_data` loosely remain compatible; strict consumers should tolerate new keys.

## Rollback strategy
- Revert commit touching:
  - `AURA/services/core/src/core/services/task_queue.py`
  - `AURA/services/core/tests/test_task_queue_retry_ordering.py`
  - retry evidence artifacts/docs for this fix
- Rebuild/restart core service.
- Re-run before/after retry scenario artifacts to verify behavior reversion.
