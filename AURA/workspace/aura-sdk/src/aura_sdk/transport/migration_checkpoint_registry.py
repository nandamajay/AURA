"""Migration checkpoint registry model for incremental orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationCheckpointRegistryResult:
    migration_checkpoint_registry: dict[str, Any]
    checkpoint_integrity_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_migration_checkpoint_registry(
    *,
    target_id: str,
    lineage_id: str,
    staged_migration_plan: Mapping[str, Any],
    portability_transition_state: Mapping[str, Any],
    rollback_boundary_report: Mapping[str, Any],
    runtime_stability_gate_report: Mapping[str, Any],
    incremental_equivalence_report: Mapping[str, Any],
    previous_checkpoints: list[Mapping[str, Any]] | None,
    evidence_references: list[str] | None,
) -> MigrationCheckpointRegistryResult:
    plan = _as_dict(staged_migration_plan)
    transitions = _as_dict(portability_transition_state)
    rollback = _as_dict(rollback_boundary_report)
    runtime_gate = _as_dict(runtime_stability_gate_report)
    incremental = _as_dict(incremental_equivalence_report)

    phase_rows = [row for row in _as_list(plan.get("phases")) if isinstance(row, dict)]
    transition_rows = [row for row in _as_list(transitions.get("transitions")) if isinstance(row, dict)]

    completed_phases = [str(row.get("phase_id", "")) for row in phase_rows if str(row.get("status", "")) == "COMPLETED"]
    active_phases = [str(row.get("phase_id", "")) for row in phase_rows if str(row.get("status", "")) == "IN_PROGRESS"]
    blocked_phases = [str(row.get("phase_id", "")) for row in phase_rows if str(row.get("status", "")) == "BLOCKED"]

    checkpoints: list[dict[str, Any]] = [
        {
            "checkpoint_id": f"{lineage_id}:preflight",
            "type": "PRE_FLIGHT",
            "status": "CAPTURED",
            "conditions": {
                "runtime_stability_classification": str(runtime_gate.get("classification", "UNKNOWN")),
                "plan_classification": str(plan.get("classification", "UNKNOWN")),
            },
        },
        {
            "checkpoint_id": f"{lineage_id}:phase_progress",
            "type": "PHASE_PROGRESS",
            "status": "CAPTURED",
            "conditions": {
                "completed_phases": completed_phases,
                "active_phases": active_phases,
                "blocked_phases": blocked_phases,
            },
        },
        {
            "checkpoint_id": f"{lineage_id}:rollback_boundary",
            "type": "ROLLBACK_BOUNDARY",
            "status": "CAPTURED",
            "conditions": {
                "rollback_classification": str(rollback.get("classification", "UNKNOWN")),
                "irreversible_transition_count": int(
                    _as_dict(rollback.get("summary", {})).get("irreversible_transition_count", 0) or 0
                ),
            },
        },
        {
            "checkpoint_id": f"{lineage_id}:equivalence",
            "type": "INCREMENTAL_EQUIVALENCE",
            "status": "CAPTURED",
            "conditions": {
                "incremental_equivalence_score": _to_float(incremental.get("incremental_equivalence_score", 0.0)),
                "classification": str(incremental.get("classification", "UNKNOWN")),
            },
        },
    ]

    transition_progress = _to_float(_as_dict(transitions.get("summary", {})).get("progress", 0.0), 0.0)
    stability_score = _to_float(runtime_gate.get("stability_score", 0.0), 0.0)
    incremental_score = _to_float(incremental.get("incremental_equivalence_score", 0.0), 0.0)

    checkpoint_integrity_score = round(max(0.0, min(1.0, 0.4 * stability_score + 0.35 * transition_progress + 0.25 * incremental_score)), 3)

    history = [row for row in _as_list(previous_checkpoints or []) if isinstance(row, dict)]
    next_index = len(history) + 1
    history.append(
        {
            "lineage_id": str(lineage_id),
            "history_index": next_index,
            "classification": str(plan.get("classification", "UNKNOWN")),
            "transition_progress": transition_progress,
            "checkpoint_integrity_score": checkpoint_integrity_score,
            "checkpoint_count": len(checkpoints),
        }
    )
    history = history[-2000:]

    payload = {
        "schema_version": "1.0",
        "report_name": "migration_checkpoint_registry",
        "target_id": str(target_id),
        "lineage_id": str(lineage_id),
        "classification": str(plan.get("classification", "UNKNOWN")),
        "checkpoints": checkpoints,
        "partial_migration_state": {
            "completed_phases": completed_phases,
            "active_phases": active_phases,
            "blocked_phases": blocked_phases,
            "transition_progress": transition_progress,
            "transition_count": len(transition_rows),
        },
        "checkpoint_integrity_score": checkpoint_integrity_score,
        "history": history,
        "advisory_only_orchestration": True,
        "runtime_truth_precedence": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationCheckpointRegistryResult(
        migration_checkpoint_registry=payload,
        checkpoint_integrity_score=checkpoint_integrity_score,
        deterministic_fingerprint=fingerprint,
    )
