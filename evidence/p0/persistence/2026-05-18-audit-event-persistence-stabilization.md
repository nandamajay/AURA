# P0 Audit/Event Persistence Stabilization (2026-05-18)

## Runtime finding fixed
- Finding ID: `audit-event-persistence-gap`
- Discovery reference:
  - `AURA/data/outputs/runtime_discovery/runtime_discovery_20260517T193152Z-kieleu.json`
- Observed issue:
  - Runtime event flows (including watchdog/event pressure scenarios) were emitted to event bus/ws transport but not consistently represented in `audit_ledger` chronology.

## Reproduction before fix (runtime)
- Artifact:
  - `AURA/data/outputs/runtime_discovery/audit_event_persistence_before_before-audit-8b7967de.json`
- Scenario:
  - 12 concurrent task creations + 5 cancellations.
- Result:
  - `created_ok=12`, `cancel_ok=5`, `audit_rows_count=0` for affected task IDs.

## Affected subsystem and code paths
- Subsystem: `S1 Orchestrator` event bridge + audit persistence path
- Code paths:
  - `AURA/services/core/src/core/events.py`
  - `AURA/knowledge/schema/017_audit_ledger_event_expansion.sql`

## Minimal correction implemented
- Added mandatory audit persistence in event bridge before ws broadcast.
- Added bounded lock-retry behavior for SQLite busy/locked writes.
- Added explicit rule: if persistence fails, skip broadcast (no unpersisted fanout).
- Expanded audit event-type constraint to include runtime lifecycle events emitted by core event bus.

## Regression validation
- Tests added:
  - `AURA/services/core/tests/test_event_audit_persistence.py`
- Containerized regression run:
  - `22 passed` across watchdog/circuit-breaker/governance/tasks/agents/event-persistence suites.

## Runtime validation after fix
- Artifact:
  - `AURA/data/outputs/runtime_discovery/audit_event_persistence_after_after-audit-a5141554.json`
- Same scenario rerun:
  - `created_ok=12`, `cancel_ok=5`, `audit_rows_count=50` (captured snapshot).
  - Event-type distribution sample: `task.created=12`, `task.queued=12`, `task.started=9`, `task.progress=10`, `task.cancelled=7`.

## Replay and audit integrity impact
- Replay visibility improved indirectly: event chronology now persisted in append-only audit ledger before fanout.
- Audit chain trigger remained active; migration preserves append-only triggers and chain-hash behavior.

## Regression risk assessment
- Medium:
  - Increased audit write volume for high-frequency runtime events.
  - Backpressure behavior intentionally favors persistence over transport fanout.

## Rollback strategy
- Revert commit touching:
  - `core/events.py`
  - `knowledge/schema/017_audit_ledger_event_expansion.sql`
  - `tests/test_event_audit_persistence.py`
- Rebuild/restart `aura-core`.
- Rerun before/after audit persistence scenario to verify rollback delta.
