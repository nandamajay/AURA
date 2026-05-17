"""Engineering Memory API — 10 ledgers and registers."""

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ValidationError

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
