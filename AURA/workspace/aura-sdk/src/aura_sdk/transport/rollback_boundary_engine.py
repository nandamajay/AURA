"""Rollback boundary reasoning for incremental migration orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RollbackBoundaryReportResult:
    rollback_boundary_report: dict[str, Any]
    rollback_confidence: float
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


def build_rollback_boundary_report(
    *,
    target_id: str,
    staged_migration_plan: Mapping[str, Any],
    portability_transition_state: Mapping[str, Any],
    runtime_stability_gate_report: Mapping[str, Any],
    portability_blocker_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RollbackBoundaryReportResult:
    plan = _as_dict(staged_migration_plan)
    transitions = _as_dict(portability_transition_state)
    runtime_gate = _as_dict(runtime_stability_gate_report)
    blockers = _as_dict(portability_blocker_report)

    transition_rows = [row for row in _as_list(transitions.get("transitions")) if isinstance(row, dict)]
    transition_map = {str(row.get("transition_id", "")): str(row.get("state", "PENDING")) for row in transition_rows}

    irreversible = [str(item) for item in _as_list(_as_dict(plan.get("irreversible_high_risk_transitions")).get("irreversible")) if str(item).strip()]
    high_risk = [str(item) for item in _as_list(_as_dict(plan.get("irreversible_high_risk_transitions")).get("high_risk")) if str(item).strip()]

    boundary_rows: list[dict[str, Any]] = []
    blocked_irreversible: list[str] = []

    for transition_id in sorted(set(irreversible + high_risk)):
        state = transition_map.get(transition_id, "PENDING")
        rollback_allowed = transition_id not in irreversible or state != "COMPLETED"
        if not rollback_allowed:
            blocked_irreversible.append(transition_id)

        boundary_rows.append(
            {
                "transition_id": transition_id,
                "state": state,
                "irreversible": transition_id in irreversible,
                "high_risk": transition_id in high_risk,
                "rollback_allowed": rollback_allowed,
                "rollback_mode": "SAFE" if rollback_allowed else "CHECKPOINT_ONLY",
            }
        )

    recommended_boundaries = [
        {
            "boundary": "pre_vendor_hook_elimination",
            "trigger": "before irreversible vendor hook removal",
            "checkpoint_required": True,
        },
        {
            "boundary": "pre_component_registration_cutover",
            "trigger": "before component registration migration",
            "checkpoint_required": True,
        },
        {
            "boundary": "pre_runtime_capability_parity",
            "trigger": "before runtime capability parity validation",
            "checkpoint_required": True,
        },
    ]

    stability_score = _to_float(runtime_gate.get("stability_score", 0.0))
    risk_classification = str(blockers.get("risk_classification", "UNKNOWN"))

    rollback_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * stability_score
                + 0.25 * (1.0 if risk_classification == "LOW" else (0.5 if risk_classification == "MEDIUM" else 0.2))
                + 0.2 * (1.0 - len(blocked_irreversible) / max(1, len(boundary_rows))),
            ),
        ),
        3,
    )

    classification = "PASS"
    if len(blocked_irreversible) > 0 and stability_score < 0.6:
        classification = "FAIL_CLOSED"
    elif len(blocked_irreversible) > 0 or risk_classification in {"MEDIUM", "HIGH"}:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "rollback_boundary_report",
        "target_id": str(target_id),
        "classification": classification,
        "rollback_confidence": rollback_confidence,
        "transition_boundaries": boundary_rows,
        "recommended_rollback_boundaries": recommended_boundaries,
        "summary": {
            "irreversible_transition_count": len(irreversible),
            "high_risk_transition_count": len(high_risk),
            "blocked_irreversible_count": len(blocked_irreversible),
            "runtime_stability_score": stability_score,
            "portability_risk_classification": risk_classification,
        },
        "advisory_only_orchestration": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RollbackBoundaryReportResult(
        rollback_boundary_report=payload,
        rollback_confidence=rollback_confidence,
        deterministic_fingerprint=fingerprint,
    )
