"""Incremental equivalence engine for staged migration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class IncrementalEquivalenceResult:
    incremental_equivalence_report: dict[str, Any]
    incremental_equivalence_score: float
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


def evaluate_incremental_equivalence(
    *,
    target_id: str,
    upstream_equivalence_confidence: Mapping[str, Any],
    migration_dependency_graph: Mapping[str, Any],
    portability_transition_state: Mapping[str, Any],
    runtime_stability_gate_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> IncrementalEquivalenceResult:
    upstream = _as_dict(upstream_equivalence_confidence)
    dependency_graph = _as_dict(migration_dependency_graph)
    transition = _as_dict(portability_transition_state)
    runtime_gate = _as_dict(runtime_stability_gate_report)

    overall_confidence = _to_float(_as_dict(upstream.get("scores")).get("overall_confidence", 0.0))
    topology_confidence = _to_float(_as_dict(upstream.get("scores")).get("topology_conversion_confidence", 0.0))
    runtime_confidence = _to_float(_as_dict(upstream.get("scores")).get("runtime_portability_confidence", 0.0))

    transition_items = [item for item in _as_list(transition.get("transitions")) if isinstance(item, dict)]
    completed = len([item for item in transition_items if str(item.get("state", "")) == "COMPLETED"])
    in_progress = len([item for item in transition_items if str(item.get("state", "")) == "IN_PROGRESS"])
    blocked = len([item for item in transition_items if str(item.get("state", "")) == "BLOCKED"])
    total = max(1, len(transition_items))

    phase_progress = (completed + 0.5 * in_progress) / total

    high_risk_dependencies = len(
        [
            row
            for row in _as_list(dependency_graph.get("nodes"))
            if isinstance(row, dict) and str(row.get("risk", "")).upper() == "HIGH"
        ]
    )

    stability_score = _to_float(runtime_gate.get("stability_score", 0.0))

    compatibility_windows = [
        {
            "window": "component_registration_window",
            "status": "OPEN" if overall_confidence >= 0.4 else "NARROW",
            "confidence": round(min(1.0, 0.6 * overall_confidence + 0.4 * phase_progress), 3),
        },
        {
            "window": "dpcm_lifecycle_window",
            "status": "OPEN" if topology_confidence >= 0.45 else "NARROW",
            "confidence": round(min(1.0, 0.7 * topology_confidence + 0.3 * stability_score), 3),
        },
        {
            "window": "runtime_capability_parity_window",
            "status": "OPEN" if runtime_confidence >= 0.5 and stability_score >= 0.5 else "NARROW",
            "confidence": round(min(1.0, 0.5 * runtime_confidence + 0.5 * stability_score), 3),
        },
    ]

    incremental_equivalence_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * overall_confidence
                + 0.2 * topology_confidence
                + 0.2 * runtime_confidence
                + 0.15 * phase_progress
                + 0.1 * stability_score
                - 0.04 * blocked
                - 0.01 * high_risk_dependencies,
            ),
        ),
        3,
    )

    classification = "PASS"
    if blocked > 0 or incremental_equivalence_score < 0.4:
        classification = "FAIL_CLOSED"
    elif incremental_equivalence_score < 0.65:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "incremental_equivalence_report",
        "target_id": str(target_id),
        "classification": classification,
        "incremental_equivalence_score": incremental_equivalence_score,
        "compatibility_windows": compatibility_windows,
        "progress": {
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "total": total,
            "phase_progress": round(phase_progress, 3),
        },
        "drivers": {
            "overall_equivalence_confidence": round(overall_confidence, 3),
            "topology_conversion_confidence": round(topology_confidence, 3),
            "runtime_portability_confidence": round(runtime_confidence, 3),
            "runtime_stability_score": round(stability_score, 3),
            "high_risk_dependency_count": high_risk_dependencies,
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return IncrementalEquivalenceResult(
        incremental_equivalence_report=payload,
        incremental_equivalence_score=incremental_equivalence_score,
        deterministic_fingerprint=fingerprint,
    )
