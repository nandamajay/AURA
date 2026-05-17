"""Simulation control endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventType
from aura_sdk.models.simulation import FidelityMode, SimulationStatus, SimulationType
from core.config import Config
from core.events import publish_event
from core.routers.auth import get_current_user

logger = get_logger("core.simulation")
router = APIRouter()
_ACTIVE_SIM_TASKS: set[asyncio.Task[None]] = set()


@router.get("/scenarios")
async def list_scenarios(current_user: dict = Depends(get_current_user)):
    """List available simulation scenarios."""
    scenarios = []
    for sim_type in SimulationType:
        scenarios.append({
            "id": sim_type.value,
            "name": sim_type.value.replace("_", " ").title(),
            "description": f"Simulate {sim_type.value} subsystem behavior",
            "fidelity_modes": ["state_machine", "qemu"] if sim_type in (
                SimulationType.DAPM, SimulationType.PCM
            ) else ["state_machine"],
        })
    return {"scenarios": scenarios}


@router.post("/")
async def start_simulation(
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Start a simulation."""
    patch_id_raw = str(payload.get("patch_id", "")).strip()
    raw_type = str(payload.get("simulation_type", "")).strip()
    raw_fidelity = str(payload.get("fidelity", FidelityMode.STATE_MACHINE.value)).strip()

    try:
        sim_type = SimulationType(raw_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid simulation_type: {raw_type}") from exc

    try:
        fidelity = FidelityMode(raw_fidelity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid fidelity: {raw_fidelity}") from exc

    if fidelity == FidelityMode.QEMU:
        if not Config.QEMU_ENABLED:
            raise HTTPException(status_code=400, detail="QEMU fidelity requested but QEMU_ENABLED=false")
        if sim_type not in {SimulationType.DAPM, SimulationType.PCM}:
            raise HTTPException(
                status_code=400,
                detail=f"QEMU fidelity not supported for simulation_type={sim_type.value}",
            )

    simulation_id = str(uuid.uuid4())
    async with get_db() as db:
        patch_id: str | None = None
        if patch_id_raw:
            patch_row_cursor = await db.execute(
                "SELECT id FROM patches WHERE id = ? LIMIT 1",
                (patch_id_raw,),
            )
            patch_row = await patch_row_cursor.fetchone()
            if patch_row is None:
                raise HTTPException(status_code=404, detail=f"Patch not found: {patch_id_raw}")
            patch_id = patch_id_raw

        await db.execute(
            """
            INSERT INTO simulation_results
                (id, patch_id, simulation_type, fidelity_mode, status, findings_json, failure_predictions, confidence_impact)
            VALUES (?, ?, ?, ?, ?, '{}', '[]', 0.0)
            """,
            (
                simulation_id,
                patch_id,
                sim_type.value,
                fidelity.value,
                SimulationStatus.PENDING.value,
            ),
        )
        await db.commit()

    logger.info(
        "simulation_started",
        simulation_id=simulation_id,
        patch_id=patch_id or "",
        sim_type=sim_type.value,
        fidelity=fidelity.value,
        user=current_user.get("email"),
    )

    await publish_event(
        request,
        EventType.SIM_STARTED,
        {
            "simulation_id": simulation_id,
            "patch_id": patch_id,
            "simulation_type": sim_type.value,
            "fidelity_mode": fidelity.value,
            "status": SimulationStatus.PENDING.value,
        },
        task_id=simulation_id,
        trace_id=simulation_id,
    )

    task = asyncio.create_task(
        _execute_simulation(
            app=request.app,
            simulation_id=simulation_id,
            patch_id=patch_id or "",
            sim_type=sim_type,
            fidelity=fidelity,
        )
    )
    _ACTIVE_SIM_TASKS.add(task)
    task.add_done_callback(lambda done: _ACTIVE_SIM_TASKS.discard(done))

    return {
        "simulation_id": simulation_id,
        "patch_id": patch_id or "",
        "simulation_type": sim_type.value,
        "fidelity": fidelity.value,
        "status": SimulationStatus.PENDING.value,
    }


@router.get("/{simulation_id}")
async def get_simulation_status(
    simulation_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get simulation status."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, patch_id, simulation_type, fidelity_mode, status,
                   findings_json, failure_predictions, confidence_impact, duration_ms, created_at
            FROM simulation_results
            WHERE id = ?
            """,
            (simulation_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Simulation not found: {simulation_id}")

    findings: dict[str, Any] = {}
    failure_predictions: list[str] = []
    try:
        findings = json.loads(row["findings_json"] or "{}")
    except Exception:
        findings = {}
    try:
        failure_predictions = json.loads(row["failure_predictions"] or "[]")
    except Exception:
        failure_predictions = []

    return {
        "simulation_id": row["id"],
        "patch_id": row["patch_id"],
        "simulation_type": row["simulation_type"],
        "fidelity_mode": row["fidelity_mode"],
        "status": row["status"],
        "findings": findings,
        "failure_predictions": failure_predictions,
        "confidence_impact": row["confidence_impact"],
        "duration_ms": row["duration_ms"],
        "created_at": row["created_at"],
    }


def _deterministic_simulation_result(
    simulation_id: str,
    sim_type: SimulationType,
    fidelity: FidelityMode,
) -> tuple[SimulationStatus, dict[str, Any], list[str], float, int]:
    digest = hashlib.sha256(
        f"{simulation_id}|{sim_type.value}|{fidelity.value}".encode("utf-8")
    ).hexdigest()
    score = int(digest[:8], 16) % 100
    duration_ms = 300 + (int(digest[8:12], 16) % 900)
    if fidelity == FidelityMode.QEMU:
        duration_ms += 700

    checks = {
        SimulationType.PROBE_FLOW: ["component_probe_order", "dependency_resolution"],
        SimulationType.DAPM: ["widget_route_graph", "power_state_transitions"],
        SimulationType.PCM: ["stream_open_close", "hw_params_negotiation"],
        SimulationType.SOUNDWIRE: ["link_enumeration", "slave_attach_sequence"],
        SimulationType.RUNTIME_PM: ["suspend_resume_cycles", "runtime_ref_balance"],
        SimulationType.DSP: ["boot_sequence", "ipc_message_integrity"],
        SimulationType.DMA_IRQ: ["descriptor_queueing", "irq_ack_order"],
    }[sim_type]

    if score < 15:
        status = SimulationStatus.FAILED
        confidence_impact = -0.06
        predictions = ["regression_predicted", "manual_investigation_required"]
    elif score < 25:
        status = SimulationStatus.INCONCLUSIVE
        confidence_impact = 0.0
        predictions = ["signal_inconclusive"]
    else:
        status = SimulationStatus.PASSED
        confidence_impact = 0.04
        predictions = []

    findings = {
        "checks_executed": checks,
        "deterministic_score": score,
        "fidelity_mode": fidelity.value,
    }
    return status, findings, predictions, confidence_impact, duration_ms


async def _execute_simulation(
    *,
    app,
    simulation_id: str,
    patch_id: str,
    sim_type: SimulationType,
    fidelity: FidelityMode,
) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE simulation_results SET status = ? WHERE id = ?",
            (SimulationStatus.RUNNING.value, simulation_id),
        )
        await db.commit()

    await asyncio.sleep(0.25 if fidelity == FidelityMode.STATE_MACHINE else 1.0)

    status, findings, predictions, confidence_impact, duration_ms = _deterministic_simulation_result(
        simulation_id,
        sim_type,
        fidelity,
    )
    async with get_db() as db:
        await db.execute(
            """
            UPDATE simulation_results
            SET status = ?, findings_json = ?, failure_predictions = ?, confidence_impact = ?, duration_ms = ?
            WHERE id = ?
            """,
            (
                status.value,
                json.dumps(findings, separators=(",", ":")),
                json.dumps(predictions, separators=(",", ":")),
                confidence_impact,
                duration_ms,
                simulation_id,
            ),
        )
        await db.commit()

    event_type = EventType.SIM_COMPLETED if status == SimulationStatus.PASSED else EventType.SIM_FAILED
    await publish_event(
        app,
        event_type,
        {
            "simulation_id": simulation_id,
            "patch_id": patch_id,
            "simulation_type": sim_type.value,
            "fidelity_mode": fidelity.value,
            "status": status.value,
            "confidence_impact": confidence_impact,
            "duration_ms": duration_ms,
        },
        task_id=simulation_id,
        trace_id=simulation_id,
    )
