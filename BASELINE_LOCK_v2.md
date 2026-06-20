# Baseline Lock v2

Generated: 2026-06-20T20:21:53.812389+00:00

## Scope

- Production target audited read-only: `/local/mnt/workspace/AURA`
- WCD9378 conversion: paused and untouched.
- Upstream Reviewer Simulation Phase 0: separate track and not mixed.

## Git Anchors

- Production system SHA: `8c8f0d3446b39e73bab7e9b10df6b22f2f514d74`
- Tracking repo SHA: `9a8cf3ffb2375a70c28aaa224c16df06d72a27be`
- Tracking branch: `aura_upstream_learning`

## Database Baseline

- Schema version: `UNVERSIONED:approvals,events,runs`
- Migration files found: `0`
- Schema version tracked: `False`

## Contract Versions

| Contract | Version | Stability | Breaking Risk |
|---|---|---|---|
| IC-001 - cli.py → Orchestrator.run_module | v1.0.0 | STABLE | HIGH |
| IC-002 - Orchestrator._run_agent → agent run.sh | v1.0.0 | UNSTABLE | HIGH |
| IC-003 - worker_entry.py → worker_runner.run_worker | v1.0.0 | STABLE | MEDIUM |
| IC-004 - rule_engine.py → rules YAML | v1.0.0 | UNSTABLE | HIGH |
| IC-005 - state.py → orchestration.db | v1.0.0 | UNSTABLE | HIGH |
| IC-006 - dashboard.py → orchestration.db queries | v1.0.0 | UNSTABLE | MEDIUM |
| IC-007 - Orchestrator → approval gate artifact | v1.0.0 | UNSTABLE | HIGH |

## Test Coverage Baseline

- Tests found: `15`
- Tests passed: `15`
- Tests failed: `0`
- Contract coverage score: `71.43%`
- Untested contracts: `0`
- Partially tested contracts: `4`

## Known Gaps At Baseline

- Total gaps: `12`
- High severity: `10`
- Medium severity: `2`
- Low severity: `0`

See `PRODUCTION_GAP_MATRIX.md` for full file/line-level gap inventory.

## Immutable Baseline Statement

**This baseline is immutable. Phase 1 changes must not regress below this baseline.**

