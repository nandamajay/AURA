# P0 Mandatory Replay Hooks Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `replay-hooks-not-finalized-on-failure`
- Before evidence:
  - `AURA/data/outputs/runtime_discovery/replay_hooks_before_replay-hooks-before-3d0b2bc1.json`
- Observed issue before fix:
  - Unrecoverable agent failure left `task_logs.recording_state='mutable'`.
  - Replay returned `Task log not finalized` for failed execution.
  - Execution step ledger remained empty (`execution_order_json='[]'`).

## Affected subsystem and code paths
- Subsystem: `S2 Agent Runtime` + `S3 Replay`
- Code path:
  - `AURA/agents/src/aura_agents/base.py`
- Tests:
  - `AURA/agents/tests/test_base_agent_replay_hooks.py`

## Minimal correction implemented
- Added mandatory lifecycle step persistence in `BaseAgent`:
  - `task_started`, `execute_begin`, `execute_success|execute_timeout|execute_exception`, `task_result`, `task_finished`
  - persisted via `TaskRecorder.record_execution_step()` with monotonic sequence numbers.
- Added replay finalization for all terminal outcomes:
  - success
  - timeout
  - unrecoverable exception
- Finalized output now stores deterministic terminal payload:
  - `status`, `exit_code`, `results`

## Regression validation
- Containerized regression run:
  - `python -m pytest -q /app/agents/tests/test_base_agent_replay_hooks.py /app/services/core/tests/test_task_queue_retry_ordering.py /app/services/core/tests/test_task_queue_external_spawn.py /app/services/core/tests/test_tasks_input_validation.py /app/services/core/tests/test_governance_stabilization.py /app/services/core/tests/test_event_audit_persistence.py /app/workspace/aura-sdk/tests/test_replay.py /app/workspace/aura-sdk/tests/test_architecture_enforcer.py`
  - Result: `29 passed`

## Runtime validation after fix
- After evidence:
  - `AURA/data/outputs/runtime_discovery/replay_hooks_after_replay-hooks-after-b109baef.json`
- Same failing-agent scenario rerun:
  - `recording_state='finalized'`
  - `execution_step_count=5`
  - replay now succeeds with `fidelity='perfect'`
  - terminal output persisted (`status='unrecoverable'`, `exit_code=2`)

## Replay and deterministic impact
- Replay completeness improved for failed/timeouts (no mutable-terminal gap).
- Execution-step lineage is explicit and ordered using deterministic sequence numbers.
- No architecture shape changes introduced.

## Regression risk assessment
- Medium:
  - Additional execution-step writes increase replay row write volume.
  - Step schema is additive and backward-compatible.

## Rollback strategy
- Revert commit touching `agents/src/aura_agents/base.py` and replay-hook tests/evidence.
- Re-run before/after replay-hook scenarios to verify behavior reversion.
