"""Engineering Memory API — 10 ledgers and registers."""

from datetime import datetime, timezone
import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ValidationError

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
    StabilizationEntry,
    TechnicalDebt,
)
from aura_sdk.memory.persistence import MemoryStore
from aura_sdk.validation.models import ValidationPlan
from aura_sdk.validation.runners import ValidationOrchestrator
from core.routers.auth import get_current_user

logger = get_logger("core.memory")
router = APIRouter()

store = MemoryStore()


class ValidationRunRequest(BaseModel):
    """Payload for adversarial validation runs."""

    target: str = "aura-core"
    attempts: int = 5


class NondeterminismCheckRequest(BaseModel):
    """Payload for nondeterminism checks."""

    source_code: str = ""


async def _persist_with_guard(operation):
    """Convert SQLite integrity failures into client-visible validation errors."""
    try:
        return await operation
    except sqlite3.IntegrityError as exc:
        logger.warning("memory_write_rejected", error=str(exc))
        raise HTTPException(status_code=422, detail=f"Invalid payload: {exc}") from exc


def _validate_payload(model_cls, data: dict):
    """Validate request payloads as pydantic models and map failures to 422."""
    try:
        return model_cls(**data)
    except ValidationError as exc:
        logger.warning(
            "memory_payload_validation_failed",
            model=model_cls.__name__,
            errors=exc.errors(),
        )
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso_epoch(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except Exception:
        return ""


async def _table_exists(db, table_name: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return await cursor.fetchone() is not None


# ── Summary ──

@router.get("/summary")
async def memory_summary(current_user: dict = Depends(get_current_user)):
    """Get summary of all engineering memory."""
    return await store.get_memory_summary()


# ── Decision Ledger ──

@router.get("/decisions")
async def list_decisions(
    subsystem: str = "",
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List engineering decisions."""
    return {"decisions": await store.list_decisions(subsystem=subsystem, limit=limit)}


@router.post("/decisions")
async def create_decision(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record an engineering decision."""
    record = _validate_payload(DecisionRecord, {**data, "decided_by": current_user.get("sub", "")})
    id = await _persist_with_guard(store.create_decision(record))
    logger.info("decision_recorded", id=id, title=record.title)
    return {"decision_id": id, "status": "recorded"}


# ── Failure Ledger ──

@router.get("/failures")
async def list_failures(
    status: str = "", limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List failure investigations."""
    return {"failures": await store.list_failures(status=status, limit=limit)}


@router.post("/failures")
async def create_failure(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a failure investigation."""
    record = _validate_payload(FailureRecord, data)
    id = await _persist_with_guard(store.create_failure(record))
    return {"failure_id": id, "status": "recorded"}


# ── Replay Incident Ledger ──

@router.get("/replay-incidents")
async def list_replay_incidents(
    task_id: str = "", limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List replay incidents."""
    return {"incidents": await store.list_replay_incidents(task_id=task_id, limit=limit)}


@router.post("/replay-incidents")
async def create_replay_incident(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a replay incident."""
    record = _validate_payload(ReplayIncident, data)
    id = await _persist_with_guard(store.create_replay_incident(record))
    return {"incident_id": id, "status": "recorded"}


# ── Architecture Drift ──

@router.get("/drift")
async def list_drifts(
    status: str = "", limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List architecture drift entries."""
    return {"drifts": await store.list_drifts(status=status, limit=limit)}


@router.post("/drift")
async def create_drift(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record architecture drift."""
    record = _validate_payload(ArchitectureDrift, data)
    id = await _persist_with_guard(store.create_drift(record))
    return {"drift_id": id, "status": "recorded"}


# ── Operational Incidents ──

@router.get("/ops-incidents")
async def list_ops_incidents(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List operational incidents."""
    return {"incidents": await store.list_ops_incidents(limit=limit)}


@router.post("/ops-incidents")
async def create_ops_incident(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record an operational incident."""
    record = _validate_payload(OperationalIncident, data)
    id = await _persist_with_guard(store.create_ops_incident(record))
    return {"incident_id": id, "status": "recorded"}


# ── Stabilization Timeline ──

@router.get("/stabilization")
async def list_stabilizations(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List stabilization entries."""
    return {"entries": await store.list_stabilizations(limit=limit)}


@router.post("/stabilization")
async def create_stabilization(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a stabilization milestone."""
    record = _validate_payload(StabilizationEntry, data)
    id = await _persist_with_guard(store.create_stabilization(record))
    return {"entry_id": id, "status": "recorded"}


# ── Technical Debt ──

@router.get("/debt")
async def list_debts(
    status: str = "", limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List technical debt entries."""
    return {"debts": await store.list_debts(status=status, limit=limit)}


@router.post("/debt")
async def create_debt(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record technical debt."""
    record = _validate_payload(TechnicalDebt, data)
    id = await _persist_with_guard(store.create_debt(record))
    return {"debt_id": id, "status": "recorded"}


# ── Deferred Scalability ──

@router.get("/scalability")
async def list_scalability_items(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List deferred scalability items."""
    return {"items": await store.list_scalability_items(limit=limit)}


@router.post("/scalability")
async def create_scalability_item(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a deferred scalability item."""
    record = _validate_payload(DeferredScalability, data)
    id = await _persist_with_guard(store.create_scalability_item(record))
    return {"item_id": id, "status": "recorded"}


# ── Known Risks ──

@router.get("/risks")
async def list_risks(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List known risks."""
    return {"risks": await store.list_risks(limit=limit)}


@router.post("/risks")
async def create_risk(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a known risk."""
    record = _validate_payload(KnownRisk, data)
    id = await _persist_with_guard(store.create_risk(record))
    return {"risk_id": id, "status": "recorded"}


# ── Future Migrations ──

@router.get("/migrations")
async def list_migrations(
    limit: int = 50, current_user: dict = Depends(get_current_user)
):
    """List future migrations."""
    return {"migrations": await store.list_migrations(limit=limit)}


@router.post("/migrations")
async def create_migration(
    data: dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
):
    """Record a future migration."""
    record = _validate_payload(FutureMigration, data)
    id = await _persist_with_guard(store.create_migration(record))
    return {"migration_id": id, "status": "recorded"}


# ── Learning / Maintainer Aggregates ──

@router.get("/learning/timeline")
async def learning_timeline(
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """Cross-ledger learning timeline with deterministic ordering and evidence lineage."""
    _ = current_user
    safe_limit = max(1, min(limit, 1000))
    generated_at = _now_iso()
    fail_closed_reasons: list[str] = []
    entries: list[dict[str, Any]] = []

    async with get_db() as db:
        queries = [
            (
                "engineering_decisions",
                """SELECT decision_id AS id, created_at AS ts, subsystem, title AS summary
                   FROM engineering_decisions
                   ORDER BY created_at DESC
                   LIMIT ?""",
                "decision",
            ),
            (
                "failure_investigations",
                """SELECT failure_id AS id, created_at AS ts, subsystem, title AS summary, status, severity
                   FROM failure_investigations
                   ORDER BY created_at DESC
                   LIMIT ?""",
                "failure",
            ),
            (
                "replay_incidents",
                """SELECT incident_id AS id, created_at AS ts, task_id AS subsystem, description AS summary, status, severity
                   FROM replay_incidents
                   ORDER BY created_at DESC
                   LIMIT ?""",
                "replay_incident",
            ),
            (
                "architecture_drift",
                """SELECT drift_id AS id, introduced_at AS ts, subsystem, title AS summary, status
                   FROM architecture_drift
                   ORDER BY introduced_at DESC
                   LIMIT ?""",
                "architecture_drift",
            ),
            (
                "technical_debt",
                """SELECT debt_id AS id, created_at AS ts, subsystem, title AS summary, status, severity
                   FROM technical_debt
                   ORDER BY created_at DESC
                   LIMIT ?""",
                "technical_debt",
            ),
            (
                "audit_ledger",
                """SELECT CAST(id AS TEXT) AS id, timestamp AS ts, target_type AS subsystem,
                          event_type AS summary
                   FROM audit_ledger
                   ORDER BY id DESC
                   LIMIT ?""",
                "audit_event",
            ),
        ]

        for table_name, sql, kind in queries:
            if not await _table_exists(db, table_name):
                fail_closed_reasons.append(f"table_missing:{table_name}")
                continue
            cursor = await db.execute(sql, (safe_limit,))
            rows = await cursor.fetchall()
            for row in rows:
                item = dict(row)
                ts = item.get("ts", 0)
                entries.append(
                    {
                        "kind": kind,
                        "id": item.get("id", ""),
                        "summary": item.get("summary", ""),
                        "subsystem": item.get("subsystem", "") or "unknown",
                        "status": item.get("status", ""),
                        "severity": item.get("severity", ""),
                        "timestamp": int(ts or 0),
                        "timestamp_iso": _to_iso_epoch(ts),
                        "evidence": {
                            "table": table_name,
                            "record_id": item.get("id", ""),
                        },
                    }
                )

    entries.sort(key=lambda item: (int(item.get("timestamp") or 0), str(item.get("id") or "")), reverse=True)
    entries = entries[:safe_limit]

    classification = "PASS" if not fail_closed_reasons else "FAIL_CLOSED"
    if classification == "FAIL_CLOSED":
        logger.warning(
            "learning_timeline_fail_closed",
            fail_closed_reasons=fail_closed_reasons,
        )

    return {
        "generated_at": generated_at,
        "classification": classification,
        "fail_closed_reasons": sorted(set(fail_closed_reasons)),
        "limit": safe_limit,
        "count": len(entries),
        "entries": entries,
    }


@router.get("/maintainer/intelligence")
async def maintainer_intelligence(
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    """Maintainer-facing evidence aggregate for escalations, regressions, and debt drift."""
    _ = current_user
    safe_limit = max(1, min(limit, 500))
    generated_at = _now_iso()
    fail_closed_reasons: list[str] = []

    governance_escalations = 0
    rejected_patch_events = 0
    rejected_approval_events = 0
    replay_open_incidents = 0
    open_failures = 0
    unresolved_drift = 0
    debt_hotspots: list[dict[str, Any]] = []
    regression_history: list[dict[str, Any]] = []
    replay_failure_clusters: list[dict[str, Any]] = []
    recent_timeline: list[dict[str, Any]] = []

    async with get_db() as db:
        if await _table_exists(db, "audit_ledger"):
            escalation_cursor = await db.execute(
                """SELECT COUNT(*) AS count
                   FROM audit_ledger
                   WHERE event_type IN ('approval.escalated', 'governance.escalation_triggered')"""
            )
            escalation_row = await escalation_cursor.fetchone()
            governance_escalations = int(escalation_row["count"]) if escalation_row else 0

            rejected_patch_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM audit_ledger WHERE event_type = 'patch.rejected'"
            )
            rejected_patch_row = await rejected_patch_cursor.fetchone()
            rejected_patch_events = int(rejected_patch_row["count"]) if rejected_patch_row else 0

            rejected_approval_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM audit_ledger WHERE event_type = 'approval.rejected'"
            )
            rejected_approval_row = await rejected_approval_cursor.fetchone()
            rejected_approval_events = int(rejected_approval_row["count"]) if rejected_approval_row else 0

            timeline_cursor = await db.execute(
                """SELECT id, timestamp, event_type, target_type, target_id
                   FROM audit_ledger
                   WHERE event_type IN (
                        'approval.escalated', 'approval.rejected', 'patch.rejected',
                        'task.failed', 'agent.failed', 'agent.timeout', 'sim.failed'
                   )
                   ORDER BY id DESC
                   LIMIT ?""",
                (safe_limit,),
            )
            recent_timeline = [dict(row) for row in await timeline_cursor.fetchall()]
        else:
            fail_closed_reasons.append("table_missing:audit_ledger")

        if await _table_exists(db, "replay_incidents"):
            open_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM replay_incidents WHERE status NOT IN ('resolved', 'closed')"
            )
            open_row = await open_cursor.fetchone()
            replay_open_incidents = int(open_row["count"]) if open_row else 0

            cluster_cursor = await db.execute(
                """SELECT COALESCE(divergence_cause, 'unknown') AS divergence_cause,
                          COUNT(*) AS count
                   FROM replay_incidents
                   GROUP BY COALESCE(divergence_cause, 'unknown')
                   ORDER BY count DESC
                   LIMIT 12"""
            )
            replay_failure_clusters = [dict(row) for row in await cluster_cursor.fetchall()]
        else:
            fail_closed_reasons.append("table_missing:replay_incidents")

        if await _table_exists(db, "failure_investigations"):
            open_failure_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM failure_investigations WHERE status NOT IN ('resolved', 'closed')"
            )
            open_failure_row = await open_failure_cursor.fetchone()
            open_failures = int(open_failure_row["count"]) if open_failure_row else 0

            regression_cursor = await db.execute(
                """SELECT failure_id, title, subsystem, status, severity, created_at
                   FROM failure_investigations
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (safe_limit,),
            )
            regression_history = [dict(row) for row in await regression_cursor.fetchall()]
        else:
            fail_closed_reasons.append("table_missing:failure_investigations")

        if await _table_exists(db, "architecture_drift"):
            drift_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM architecture_drift WHERE status NOT IN ('resolved', 'closed')"
            )
            drift_row = await drift_cursor.fetchone()
            unresolved_drift = int(drift_row["count"]) if drift_row else 0
        else:
            fail_closed_reasons.append("table_missing:architecture_drift")

        if await _table_exists(db, "technical_debt"):
            debt_cursor = await db.execute(
                """SELECT COALESCE(subsystem, 'unknown') AS subsystem, COUNT(*) AS count
                   FROM technical_debt
                   WHERE status NOT IN ('resolved', 'closed')
                   GROUP BY COALESCE(subsystem, 'unknown')
                   ORDER BY count DESC
                   LIMIT 20"""
            )
            debt_hotspots = [dict(row) for row in await debt_cursor.fetchall()]
        else:
            fail_closed_reasons.append("table_missing:technical_debt")

    risk_score = (
        governance_escalations
        + rejected_patch_events
        + rejected_approval_events
        + replay_open_incidents
        + open_failures
        + unresolved_drift
    )
    classification = "PASS" if not fail_closed_reasons else "FAIL_CLOSED"
    if classification == "FAIL_CLOSED":
        logger.warning(
            "maintainer_intelligence_fail_closed",
            fail_closed_reasons=fail_closed_reasons,
        )

    return {
        "generated_at": generated_at,
        "classification": classification,
        "fail_closed_reasons": sorted(set(fail_closed_reasons)),
        "lineage": {
            "source": "sqlite",
            "limit": safe_limit,
            "generated_at": generated_at,
        },
        "signals": {
            "governance_escalations": governance_escalations,
            "rejected_patch_events": rejected_patch_events,
            "rejected_approval_events": rejected_approval_events,
            "replay_open_incidents": replay_open_incidents,
            "open_failures": open_failures,
            "unresolved_drift": unresolved_drift,
            "risk_score": risk_score,
        },
        "debt_hotspots": debt_hotspots,
        "regression_history": regression_history[:safe_limit],
        "replay_failure_clusters": replay_failure_clusters,
        "recent_governance_timeline": recent_timeline[:safe_limit],
    }


# ── Adversarial Validation ──

@router.post("/validation/run")
async def run_validation(
    data: ValidationRunRequest = Body(default_factory=ValidationRunRequest),
    current_user: dict = Depends(get_current_user),
):
    """Run adversarial validation against a target component."""
    target = data.target
    attempts = data.attempts

    orchestrator = ValidationOrchestrator()

    # Generate edge-case matrix
    edge_cases = await orchestrator.generate_edge_case_matrix(target)

    # Build validation plan from edge cases
    tests = []
    for ec in edge_cases:
        tests.append({
            "category": ec.category.value,
            "name": f"{ec.category.value}: {ec.description[:50]}",
            "description": ec.description,
            "trigger": ec.trigger_condition,
            "severity": ec.severity,
            "probability": ec.probability,
        })

    plan = ValidationPlan(
        target=target,
        description=f"Adversarial validation plan for {target}",
        tests=tests,
        created_by=current_user.get("email", "system"),
    )

    # Run plan
    report = await orchestrator.run_plan(plan, attempts=attempts)

    # Failure probability analysis
    failure_prob = await orchestrator.generate_failure_probability_analysis(target)

    return {
        "report": {
            "target": report.target,
            "tests_run": len(report.results),
            "blocking": report.blocking_count,
            "flaky": report.flaky_count,
            "summary": report.summary,
            "truthful_status": report.generate_truthful_summary(),
        },
        "edge_cases": {
            "total": len(edge_cases),
            "critical": len([e for e in edge_cases if e.severity >= 4]),
            "by_category": _group_by_category(edge_cases),
        },
        "failure_probability": {
            "component": failure_prob.component,
            "overall_risk": failure_prob.overall_risk,
            "requires_action": failure_prob.requires_action,
            "probabilities": {
                "crash": failure_prob.crash_probability,
                "data_loss": failure_prob.data_loss_probability,
                "hang": failure_prob.hang_probability,
                "silent_corruption": failure_prob.silent_corruption_probability,
                "cascade": failure_prob.cascade_probability,
            },
            "mitigations": failure_prob.mitigations,
        },
    }


@router.post("/validation/nondeterminism-check")
async def check_nondeterminism(
    data: NondeterminismCheckRequest = Body(default_factory=NondeterminismCheckRequest),
    current_user: dict = Depends(get_current_user),
):
    """Run nondeterminism detection on a code module."""
    from aura_sdk.validation.detectors import NondeterminismDetector

    source_code = data.source_code

    detector = NondeterminismDetector()
    findings = detector.check_code_for_nondeterminism(source_code)

    return {
        "findings": findings,
        "risk_count": len(findings),
        "recommendation": (
            f"Found {len(findings)} potential nondeterminism sources. "
            "Review each finding and replace with deterministic equivalents."
            if findings else "No obvious nondeterminism sources detected."
        ),
    }


def _group_by_category(edge_cases: list) -> dict[str, int]:
    from collections import Counter
    categories = [ec.category.value for ec in edge_cases]
    return dict(Counter(categories))
