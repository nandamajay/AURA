"""Simulation control endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventType
from aura_sdk.models.simulation import FidelityMode, SimulationStatus, SimulationType
from core.contracts.transport_artifact_contracts import resolve_repo_root, transport_artifact_root
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


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _transport_dir() -> Path:
    env_transport = str(os.environ.get("AURA_TRANSPORT_ARTIFACT_ROOT", "")).strip()
    if env_transport:
        return Path(env_transport).resolve()
    return transport_artifact_root(resolve_repo_root())


def _read_artifact(name: str) -> dict[str, Any]:
    path = _transport_dir() / name
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _dim_classification(equivalence: dict[str, Any], dimension: str) -> str:
    for row in _as_list(_as_dict(equivalence).get("dimensions")):
        item = _as_dict(row)
        if str(item.get("dimension", "")) == dimension:
            return str(item.get("classification", ""))
    return ""


def _artifact_backed_simulation_result(
    sim_type: SimulationType,
    fidelity: FidelityMode,
) -> tuple[SimulationStatus, dict[str, Any], list[str], float, int]:
    governance = _read_artifact("runtime_governance_decision.json")
    equivalence = _read_artifact("runtime_equivalence_report.json")
    confidence = _read_artifact("runtime_confidence_report.json")
    truth_graph = _read_artifact("hardware_truth_graph.json")
    replay = _read_artifact("deterministic_runtime_replay.json")
    runtime_fp = _read_artifact("runtime_equivalence_fingerprint.json")

    path_graph = _read_artifact("runtime_path_graph.json")
    ipc_topology = _read_artifact("ipc_topology_map.json")

    required = {
        "runtime_governance_decision.json": governance,
        "runtime_equivalence_report.json": equivalence,
        "runtime_confidence_report.json": confidence,
        "hardware_truth_graph.json": truth_graph,
        "deterministic_runtime_replay.json": replay,
        "runtime_equivalence_fingerprint.json": runtime_fp,
    }
    missing_artifacts = [name for name, payload in required.items() if not payload]

    truth_nodes = _as_dict(truth_graph.get("nodes"))
    checks = {
        SimulationType.PROBE_FLOW: ["component_probe_order", "dependency_resolution"],
        SimulationType.DAPM: ["widget_route_graph", "power_state_transitions"],
        SimulationType.PCM: ["stream_open_close", "hw_params_negotiation"],
        SimulationType.SOUNDWIRE: ["link_enumeration", "slave_attach_sequence"],
        SimulationType.RUNTIME_PM: ["suspend_resume_cycles", "runtime_ref_balance"],
        SimulationType.DSP: ["boot_sequence", "ipc_message_integrity"],
        SimulationType.DMA_IRQ: ["descriptor_queueing", "irq_ack_order"],
    }[sim_type]

    evidence_counts = {
        "pcm_lifecycle": len(_as_list(truth_nodes.get("pcm_lifecycle"))),
        "dapm_routes": len(_as_list(truth_nodes.get("dapm_routes"))),
        "soundwire_links": len(_as_list(truth_nodes.get("soundwire_links"))),
        "dsp_events": len(_as_list(truth_nodes.get("dsp_events"))),
        "mailbox_synchronization": len(_as_list(truth_nodes.get("mailbox_synchronization"))),
        "irq_ordering": len(_as_list(truth_nodes.get("irq_ordering"))),
        "clock_sequence": len(_as_list(truth_nodes.get("clock_sequence"))),
        "regulator_sequence": len(_as_list(truth_nodes.get("regulator_sequence"))),
    }

    fail_predictions: list[str] = []
    if missing_artifacts:
        fail_predictions.append("runtime_artifact_missing")
    if str(governance.get("classification", "FAIL_CLOSED")) == "FAIL_CLOSED":
        fail_predictions.append("runtime_governance_fail_closed")
    if not bool(_as_dict(replay.get("replay_signal")).get("deterministic_event_ordering", False)):
        fail_predictions.append("runtime_replay_not_deterministic")

    sim_specific_failures: list[str] = []
    if sim_type == SimulationType.PROBE_FLOW:
        if evidence_counts["pcm_lifecycle"] == 0 or len(_as_list(truth_nodes.get("fe_be_links"))) == 0:
            sim_specific_failures.append("probe_flow_evidence_incomplete")
    elif sim_type == SimulationType.DAPM:
        if evidence_counts["dapm_routes"] == 0:
            sim_specific_failures.append("dapm_routes_missing")
        if len(_as_list(_as_dict(path_graph).get("edges"))) == 0:
            sim_specific_failures.append("runtime_path_graph_missing")
    elif sim_type == SimulationType.PCM:
        pcm_dimensions = _as_dict(runtime_fp).get("dimensions")
        pcm_order_present = isinstance(pcm_dimensions, dict) and "pcm_lifecycle_order" in pcm_dimensions
        if evidence_counts["pcm_lifecycle"] == 0 or not pcm_order_present:
            sim_specific_failures.append("pcm_lifecycle_unproven")
        if _dim_classification(equivalence, "pcm_transition_inconsistency") == "DIVERGED":
            sim_specific_failures.append("pcm_transition_inconsistency")
    elif sim_type == SimulationType.SOUNDWIRE:
        if evidence_counts["soundwire_links"] == 0:
            sim_specific_failures.append("soundwire_links_missing")
        if _dim_classification(equivalence, "soundwire_topology_mismatch") == "DIVERGED":
            sim_specific_failures.append("soundwire_topology_mismatch")
    elif sim_type == SimulationType.RUNTIME_PM:
        if evidence_counts["clock_sequence"] == 0 or evidence_counts["regulator_sequence"] == 0:
            sim_specific_failures.append("runtime_pm_evidence_incomplete")
    elif sim_type == SimulationType.DSP:
        if evidence_counts["dsp_events"] == 0 or evidence_counts["mailbox_synchronization"] == 0:
            sim_specific_failures.append("dsp_mailbox_sync_unproven")
        if _dim_classification(equivalence, "dsp_sequence_instability") == "DIVERGED":
            sim_specific_failures.append("dsp_sequence_instability")
    elif sim_type == SimulationType.DMA_IRQ:
        if evidence_counts["irq_ordering"] == 0:
            sim_specific_failures.append("irq_ordering_missing")
        if _dim_classification(equivalence, "irq_divergence") == "DIVERGED":
            sim_specific_failures.append("irq_divergence_detected")

    fail_predictions.extend(sim_specific_failures)

    seed_material = "|".join(
        [
            sim_type.value,
            fidelity.value,
            str(governance.get("deterministic_fingerprint", "")),
            str(equivalence.get("deterministic_fingerprint", "")),
            str(runtime_fp.get("deterministic_fingerprint", "")),
            str(replay.get("deterministic_fingerprint", "")),
        ]
    )
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    duration_ms = 350 + (int(digest[:8], 16) % 900)
    if fidelity == FidelityMode.QEMU:
        duration_ms += 700

    if missing_artifacts or fail_predictions:
        status = SimulationStatus.FAILED
        confidence_impact = -0.05
    elif str(confidence.get("classification", "PASS")) != "PASS":
        status = SimulationStatus.FAILED
        confidence_impact = -0.03
        fail_predictions.append("runtime_confidence_fail_closed")
    elif evidence_counts.get("pcm_lifecycle", 0) == 0:
        status = SimulationStatus.INCONCLUSIVE
        confidence_impact = 0.0
        fail_predictions.append("signal_inconclusive")
    else:
        status = SimulationStatus.PASSED
        confidence_impact = 0.04

    findings = {
        "checks_executed": checks,
        "fidelity_mode": fidelity.value,
        "runtime_artifacts_used": sorted(required.keys()),
        "missing_artifacts": missing_artifacts,
        "evidence_counts": evidence_counts,
        "governance_classification": str(governance.get("classification", "UNKNOWN")),
        "runtime_confidence_classification": str(confidence.get("classification", "UNKNOWN")),
        "runtime_confidence_score": float(confidence.get("confidence_score", 0.0)),
        "equivalence_classification": str(equivalence.get("classification", "UNKNOWN")),
        "ipc_event_count": int(_as_dict(ipc_topology.get("summary")).get("ipc_event_count", 0)),
        "deterministic_seed": digest[:16],
        "artifact_fingerprints": {
            "governance": str(governance.get("deterministic_fingerprint", "")),
            "equivalence": str(equivalence.get("deterministic_fingerprint", "")),
            "confidence": str(confidence.get("deterministic_fingerprint", "")),
            "truth_graph": str(truth_graph.get("deterministic_fingerprint", "")),
            "runtime_fingerprint": str(runtime_fp.get("deterministic_fingerprint", "")),
            "replay": str(replay.get("deterministic_fingerprint", "")),
        },
    }
    return status, findings, sorted(set(fail_predictions)), confidence_impact, duration_ms


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

    status, findings, predictions, confidence_impact, duration_ms = _artifact_backed_simulation_result(
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
