"""Portability transition state tracker for incremental migration orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PortabilityTransitionStateResult:
    portability_transition_state: dict[str, Any]
    transition_stability_score: float
    deterministic_fingerprint: str


_ALLOWED_STATES = {"PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"}


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


def _normalize_state(value: Any) -> str:
    state = str(value).strip().upper()
    if state in _ALLOWED_STATES:
        return state
    return "PENDING"


def track_portability_transitions(
    *,
    target_id: str,
    migration_dependency_graph: Mapping[str, Any],
    runtime_stability_gate_report: Mapping[str, Any],
    portability_blocker_report: Mapping[str, Any],
    previous_transition_state: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> PortabilityTransitionStateResult:
    dependencies = _as_dict(migration_dependency_graph)
    runtime_gate = _as_dict(runtime_stability_gate_report)
    blockers = _as_dict(portability_blocker_report)
    previous = _as_dict(previous_transition_state)

    previous_transitions = {
        str(item.get("transition_id", "")).strip(): _normalize_state(item.get("state", "PENDING"))
        for item in _as_list(previous.get("transitions"))
        if isinstance(item, dict) and str(item.get("transition_id", "")).strip()
    }

    runtime_classification = str(runtime_gate.get("classification", "UNKNOWN"))
    blocker_classification = str(blockers.get("classification", "UNKNOWN"))
    risk_classification = str(blockers.get("risk_classification", "UNKNOWN"))

    transitions: list[dict[str, Any]] = []

    dependency_nodes = [row for row in _as_list(dependencies.get("nodes")) if isinstance(row, dict)]

    for node in dependency_nodes:
        transition_id = str(node.get("id", "")).strip()
        if not transition_id:
            continue

        previous_state = previous_transitions.get(transition_id, "PENDING")
        risk = str(node.get("risk", "MEDIUM")).strip().upper()
        deps = [str(item).strip() for item in _as_list(node.get("depends_on")) if str(item).strip()]

        if previous_state == "COMPLETED":
            state = "COMPLETED"
        elif previous_state == "IN_PROGRESS" and runtime_classification == "PASS":
            state = "COMPLETED"
        elif blocker_classification == "FAIL_CLOSED" and risk == "HIGH":
            state = "BLOCKED"
        elif runtime_classification == "FAIL_CLOSED":
            state = "BLOCKED"
        elif all(previous_transitions.get(dep, "PENDING") == "COMPLETED" for dep in deps):
            state = "IN_PROGRESS" if risk in {"HIGH", "MEDIUM"} else "COMPLETED"
        else:
            state = previous_state if previous_state in _ALLOWED_STATES else "PENDING"

        transitions.append(
            {
                "transition_id": transition_id,
                "state": state,
                "risk": risk,
                "depends_on": deps,
                "signals": _as_dict(node.get("signals")),
            }
        )

    transitions.sort(key=lambda row: str(row.get("transition_id", "")))

    completed = len([row for row in transitions if str(row.get("state", "")) == "COMPLETED"])
    in_progress = len([row for row in transitions if str(row.get("state", "")) == "IN_PROGRESS"])
    blocked = len([row for row in transitions if str(row.get("state", "")) == "BLOCKED"])
    total = max(1, len(transitions))

    progress = round((completed + 0.5 * in_progress) / total, 3)
    transition_stability_score = round(max(0.0, min(1.0, 0.7 * (1.0 - blocked / total) + 0.3 * progress)), 3)

    classification = "PASS"
    if blocked > 0:
        classification = "FAIL_CLOSED"
    elif in_progress > 0 or risk_classification in {"MEDIUM", "HIGH"}:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "portability_transition_state",
        "target_id": str(target_id),
        "classification": classification,
        "runtime_classification": runtime_classification,
        "blocker_classification": blocker_classification,
        "risk_classification": risk_classification,
        "transitions": transitions,
        "summary": {
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "total": total,
            "progress": progress,
        },
        "transition_stability_score": transition_stability_score,
        "runtime_truth_precedence": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PortabilityTransitionStateResult(
        portability_transition_state=payload,
        transition_stability_score=transition_stability_score,
        deterministic_fingerprint=fingerprint,
    )
