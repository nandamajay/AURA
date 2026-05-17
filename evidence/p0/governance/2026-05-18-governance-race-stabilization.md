# P0 Governance Race Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `governance-race-last-writer-wins`
- Discovery evidence:
  - `AURA/data/outputs/runtime_discovery/governance_race_before_before-856e6263.json`
  - `AURA/data/outputs/runtime_discovery/governance_race_after_after-dc3d391a.json`
- Observed failure:
  - Concurrent `grant` + `reject` both returned `200` in baseline.
  - `escalate` returned `500` due invalid `approvals.status='escalated'` violating schema check.

## Affected subsystem and code paths
- Subsystem: `S6 Governance`
- Code path:
  - `AURA/services/core/src/core/routers/governance.py` (`process_approval`)
- Tests:
  - `AURA/services/core/tests/test_governance_stabilization.py`

## Minimal correction implemented
- Kept first-writer serialized transition logic and optimistic write guard.
- Fixed schema-invalid mapping:
  - `escalate: escalated -> in_progress`
- Corrected terminal status set:
  - removed invalid terminal state `escalated`
- Preserved audit semantics:
  - event type remains `approval.escalated`

## Regression validation
- Unit/regression tests (containerized):
  - `pytest -q /app/tests/test_governance_stabilization.py /app/tests/test_tasks_input_validation.py /app/tests/test_agents_spawn_input_validation.py`
  - Result: `12 passed`

## Runtime validation (after fix)
- Evidence artifact:
  - `AURA/data/outputs/runtime_discovery/governance_race_after_fix_afterfix-509eb2f3.json`
- Result delta:
  - Conflict call statuses: `[200, 409]` (no dual-success)
  - Escalate status: `200`
  - Escalate state: `in_progress`
  - Audit events include `approval.escalated`

## Adversarial rerun (pressure)
- Evidence artifact:
  - `AURA/data/outputs/runtime_discovery/governance_race_stress_after_fix_afterfix-stress-5cc18702.json`
- Result:
  - 20/20 runs: status pair `[200, 409]`
  - `double_success_count=0`
  - Per-conflict audit entry count: exactly 1 (no duplicates)

## Replay and deterministic impact
- Replay semantics were not redesigned.
- Change is replay-visible through persisted audit ordering and deterministic conflict rejection (`409`).
- Deterministic impact: improves transition determinism by enforcing single-writer terminal transition on same approval id.

## Regression risk assessment
- Low/medium:
  - `escalate` semantics now map to `in_progress` (schema-aligned).
  - Clients expecting literal status `escalated` must read audit event `approval.escalated` instead.

## Rollback strategy
- Revert commit affecting `governance.py` and stabilization tests.
- Rebuild and restart `aura-core` service.
- Re-run governance race evidence script to confirm pre-rollback behavior.
