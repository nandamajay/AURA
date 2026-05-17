"""Memory persistence — CRUD for all 10 engineering memory ledgers.

Uses SQLite as the backing store (consistent with the rest of AURA).
"""

from datetime import datetime, timezone
from typing import Any

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.memory.models import (
    ArchitectureDrift,
    DecisionRecord,
    DeferredScalability,
    FailureRecord,
    FutureMigration,
    KnownRisk,
    OperationalIncident,
    ReplayIncident,
    Severity,
    StabilizationEntry,
    Status,
    TechnicalDebt,
)

logger = get_logger("memory")


class MemoryStore:
    """CRUD store for all engineering memory ledgers.

    All operations are async and use aiosqlite.
    Every write is append-only (no deletes, updates via status changes).
    """

    # ── Decision Ledger ──

    async def create_decision(self, record: DecisionRecord) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO engineering_decisions
                (decision_id, title, subsystem, decision_made, reasoning, context,
                 constraints, alternatives_considered, rejected_alternatives,
                 operational_impact, scalability_impact, determinism_impact,
                 observability_impact, security_impact, cost_impact,
                 decided_by, approved_by, related_decisions, reversible, reversal_conditions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.decision_id, record.title, record.subsystem,
                    record.decision_made, record.reasoning, record.context,
                    json_str(record.constraints),
                    json_str(record.alternatives_considered),
                    json_str(record.rejected_alternatives),
                    record.operational_impact, record.scalability_impact,
                    record.determinism_impact, record.observability_impact,
                    record.security_impact, record.cost_impact,
                    nullable_text(record.decided_by), nullable_text(record.approved_by),
                    json_str(record.related_decisions),
                    record.reversible, record.reversal_conditions,
                ),
            )
            await db.commit()
            logger.info("decision_recorded", id=record.decision_id, title=record.title[:50])
            return record.decision_id

    async def list_decisions(self, subsystem: str = "", limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            if subsystem:
                cursor = await db.execute(
                    "SELECT * FROM engineering_decisions WHERE subsystem = ? ORDER BY created_at DESC LIMIT ?",
                    (subsystem, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM engineering_decisions ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Failure Ledger ──

    async def create_failure(self, record: FailureRecord) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO failure_investigations
                (failure_id, title, subsystem, description, root_cause,
                 root_cause_category, impact_scope, impact_severity,
                 affected_components, first_observed_at, resolved_at,
                 detection_latency_ms, recovery_method, prevention_strategy,
                 replay_affected, replay_recovery, approval_required_after_fix,
                 status, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.failure_id, record.title, record.subsystem,
                    record.description, record.root_cause,
                    record.root_cause_category, record.impact_scope,
                    record.impact_severity.value,
                    json_str(record.affected_components),
                    ts_or_none(record.first_observed_at),
                    ts_or_none(record.resolved_at),
                    record.detection_latency_ms,
                    record.recovery_method, record.prevention_strategy,
                    record.replay_affected, record.replay_recovery,
                    record.approval_required_after_fix,
                    record.status.value, record.severity.value,
                ),
            )
            await db.commit()
            logger.info("failure_recorded", id=record.failure_id, title=record.title[:50])
            return record.failure_id

    async def list_failures(self, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM failure_investigations WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM failure_investigations ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Replay Incident Ledger ──

    async def create_replay_incident(self, record: ReplayIncident) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO replay_incidents
                (incident_id, task_id, agent_type, description,
                 expected_fidelity, actual_fidelity, divergence_cause,
                 divergence_point, seed_used, model_version_used,
                 original_llm_calls, replay_llm_calls,
                 mismatched_llm_responses, original_output_hash,
                 replay_output_hash, hash_match, resolution,
                 replay_recovered, status, severity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.incident_id, record.task_id, record.agent_type,
                    record.description, record.expected_fidelity,
                    record.actual_fidelity, record.divergence_cause,
                    record.divergence_point, record.seed_used,
                    record.model_version_used, record.original_llm_calls,
                    record.replay_llm_calls, record.mismatched_llm_responses,
                    record.original_output_hash, record.replay_output_hash,
                    record.hash_match, record.resolution,
                    record.replay_recovered,
                    record.status.value, record.severity.value,
                ),
            )
            await db.commit()
            return record.incident_id

    async def list_replay_incidents(self, task_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            if task_id:
                cursor = await db.execute(
                    "SELECT * FROM replay_incidents WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
                    (task_id, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM replay_incidents ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Architecture Drift Ledger ──

    async def create_drift(self, record: ArchitectureDrift) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO architecture_drift
                (drift_id, title, intended_design, actual_implementation,
                 drift_description, drift_type, functional_impact,
                 maintainability_impact, scalability_impact, compliance_impact,
                 remediation_plan, remediation_priority, status, subsystem,
                 detected_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.drift_id, record.title, record.intended_design,
                    record.actual_implementation, record.drift_description,
                    record.drift_type, record.functional_impact,
                    record.maintainability_impact, record.scalability_impact,
                    record.compliance_impact, record.remediation_plan,
                    record.remediation_priority.value,
                    record.status.value, record.subsystem,
                    record.detected_by,
                ),
            )
            await db.commit()
            return record.drift_id

    async def list_drifts(self, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM architecture_drift WHERE status = ? ORDER BY introduced_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM architecture_drift ORDER BY introduced_at DESC LIMIT ?", (limit,)
                )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Operational Incident Ledger ──

    async def create_ops_incident(self, record: OperationalIncident) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO operational_incidents
                (incident_id, title, description, category,
                 started_at, detected_at, resolved_at, duration_minutes,
                 affected_services, affected_users, detection_method,
                 response_actions, postmortem, action_items,
                 severity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.incident_id, record.title, record.description,
                    record.category,
                    ts_or_none(record.started_at),
                    ts_or_none(record.detected_at),
                    ts_or_none(record.resolved_at),
                    record.duration_minutes,
                    json_str(record.affected_services),
                    record.affected_users,
                    record.detection_method,
                    json_str(record.response_actions),
                    record.postmortem,
                    json_str(record.action_items),
                    record.severity.value, record.status.value,
                ),
            )
            await db.commit()
            return record.incident_id

    async def list_ops_incidents(self, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM operational_incidents ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Stabilization Timeline ──

    async def create_stabilization(self, record: StabilizationEntry) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO stabilization_timeline
                (entry_id, milestone, description, failures_before,
                 known_issues_before, changes, tests_added,
                 tests_passing, tests_total, stability_duration_hours,
                 metrics_after, subsystem, achieved_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.entry_id, record.milestone, record.description,
                    json_str(record.failures_before),
                    json_str(record.known_issues_before),
                    json_str(record.changes),
                    json_str(record.tests_added),
                    record.tests_passing, record.tests_total,
                    record.stability_duration_hours,
                    json_str(record.metrics_after),
                    record.subsystem, record.achieved_by,
                ),
            )
            await db.commit()
            return record.entry_id

    async def list_stabilizations(self, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM stabilization_timeline ORDER BY achieved_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Technical Debt Register ──

    async def create_debt(self, record: TechnicalDebt) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO technical_debt
                (debt_id, title, description, subsystem, debt_type,
                 interest_rate, current_impact, future_impact,
                 estimated_fix_effort, estimated_fix_complexity,
                 payoff_if_fixed, status, severity,
                 target_resolution)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.debt_id, record.title, record.description,
                    record.subsystem, record.debt_type,
                    record.interest_rate, record.current_impact,
                    record.future_impact, record.estimated_fix_effort,
                    record.estimated_fix_complexity,
                    record.payoff_if_fixed,
                    record.status.value, record.severity.value,
                    ts_or_none(record.target_resolution),
                ),
            )
            await db.commit()
            return record.debt_id

    async def list_debts(self, status: str = "", limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            if status:
                cursor = await db.execute(
                    "SELECT * FROM technical_debt WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM technical_debt ORDER BY created_at DESC LIMIT ?", (limit,)
                )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Deferred Scalability Register ──

    async def create_scalability_item(self, record: DeferredScalability) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO deferred_scalability
                (item_id, title, description, current_approach,
                 target_approach, trigger_condition, trigger_metric,
                 trigger_threshold, current_value, estimated_effort,
                 estimated_phase, status, priority, subsystem)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.item_id, record.title, record.description,
                    record.current_approach, record.target_approach,
                    record.trigger_condition, record.trigger_metric,
                    record.trigger_threshold, record.current_value,
                    record.estimated_effort, record.estimated_phase,
                    record.status.value, record.priority.value, record.subsystem,
                ),
            )
            await db.commit()
            return record.item_id

    async def list_scalability_items(self, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM deferred_scalability ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Known Risk Register ──

    async def create_risk(self, record: KnownRisk) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO known_risks
                (risk_id, title, description, probability, impact,
                 risk_score, affected_subsystems, affected_users,
                 mitigation_plan, contingency_plan, residual_risk,
                 monitoring_metric, alert_threshold, status, severity, owner)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.risk_id, record.title, record.description,
                    record.probability, record.impact, record.risk_score,
                    json_str(record.affected_subsystems),
                    record.affected_users, record.mitigation_plan,
                    record.contingency_plan, record.residual_risk,
                    record.monitoring_metric, record.alert_threshold,
                    record.status.value, record.severity.value, record.owner,
                ),
            )
            await db.commit()
            return record.risk_id

    async def list_risks(self, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM known_risks ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Future Migration Register ──

    async def create_migration(self, record: FutureMigration) -> str:
        async with get_db() as db:
            await db.execute(
                """INSERT INTO future_migrations
                (migration_id, title, description, from_state, to_state,
                 trigger_phase, trigger_condition, prerequisites,
                 estimated_duration, estimated_team_size, rollback_plan,
                 risk_level, risk_factors, status, priority)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.migration_id, record.title, record.description,
                    record.from_state, record.to_state,
                    record.trigger_phase, record.trigger_condition,
                    json_str(record.prerequisites),
                    record.estimated_duration, record.estimated_team_size,
                    record.rollback_plan, record.risk_level,
                    json_str(record.risk_factors),
                    record.status.value, record.priority.value,
                ),
            )
            await db.commit()
            return record.migration_id

    async def list_migrations(self, limit: int = 50) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT * FROM future_migrations ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            return [dict(row) for row in await cursor.fetchall()]

    # ── Dashboard / Summary ──

    async def get_memory_summary(self) -> dict[str, Any]:
        """Get a summary of all memory ledgers."""
        async with get_db() as db:
            counts = {}
            tables = [
                "engineering_decisions", "failure_investigations",
                "replay_incidents", "architecture_drift",
                "operational_incidents", "stabilization_timeline",
                "technical_debt", "deferred_scalability",
                "known_risks", "future_migrations",
            ]
            for table in tables:
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
                row = await cursor.fetchone()
                counts[table] = row[0] if row else 0

        return {
            "total_entries": sum(counts.values()),
            "by_ledger": counts,
            "ledgers": [
                {"name": "Engineering Decisions", "count": counts["engineering_decisions"]},
                {"name": "Failure Investigations", "count": counts["failure_investigations"]},
                {"name": "Replay Incidents", "count": counts["replay_incidents"]},
                {"name": "Architecture Drift", "count": counts["architecture_drift"]},
                {"name": "Operational Incidents", "count": counts["operational_incidents"]},
                {"name": "Stabilization Timeline", "count": counts["stabilization_timeline"]},
                {"name": "Technical Debt", "count": counts["technical_debt"]},
                {"name": "Deferred Scalability", "count": counts["deferred_scalability"]},
                {"name": "Known Risks", "count": counts["known_risks"]},
                {"name": "Future Migrations", "count": counts["future_migrations"]},
            ],
        }


# ── Helpers ──

import json


def json_str(data: list | dict | Any) -> str:
    """Convert to JSON string."""
    if data is None:
        return "[]"
    if isinstance(data, str):
        return data
    return json.dumps(data, default=str)


def ts_or_none(dt: datetime | None) -> int | None:
    """Convert datetime to Unix timestamp or None."""
    if dt is None:
        return None
    return int(dt.timestamp())


def nullable_text(value: str | None) -> str | None:
    """Normalize empty strings to NULL for nullable FK/text columns."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None
