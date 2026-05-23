"""Migration/runtime alignment reasoning for unified engineering truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationRuntimeAlignmentResult:
    migration_runtime_alignment: dict[str, Any]
    alignment_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_migration_runtime_alignment(
    *,
    target_id: str,
    migration_dependency_graph: Mapping[str, Any],
    portability_transition_state: Mapping[str, Any],
    migration_checkpoint_registry: Mapping[str, Any],
    runtime_drift_report: Mapping[str, Any],
    runtime_confidence_score: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> MigrationRuntimeAlignmentResult:
    dependencies = _as_dict(migration_dependency_graph)
    transitions = _as_dict(portability_transition_state)
    checkpoints = _as_dict(migration_checkpoint_registry)
    drift = _as_dict(runtime_drift_report)
    runtime_conf = _as_dict(runtime_confidence_score)

    dependency_nodes = [row for row in _as_list(dependencies.get("nodes")) if isinstance(row, dict)]
    transition_rows = [row for row in _as_list(transitions.get("transitions")) if isinstance(row, dict)]

    blocked = len([row for row in transition_rows if str(_as_dict(row).get("state", "")) == "BLOCKED"])
    in_progress = len([row for row in transition_rows if str(_as_dict(row).get("state", "")) == "IN_PROGRESS"])
    completed = len([row for row in transition_rows if str(_as_dict(row).get("state", "")) == "COMPLETED"])
    total = max(1, len(transition_rows))

    drift_score = float(drift.get("drift_score", 0.0) or 0.0)
    runtime_confidence = float(runtime_conf.get("runtime_confidence", 0.0) or 0.0)
    checkpoint_integrity = float(checkpoints.get("checkpoint_integrity_score", 0.0) or 0.0)

    high_risk_dependencies = len([row for row in dependency_nodes if str(_as_dict(row).get("risk", "")).upper() == "HIGH"])

    alignment_score = round(
        max(
            0.0,
            min(
                1.0,
                0.30 * (completed / total)
                + 0.20 * (in_progress / total)
                + 0.20 * runtime_confidence
                + 0.15 * checkpoint_integrity
                + 0.15 * (1.0 - drift_score)
                - 0.02 * high_risk_dependencies
                - 0.05 * blocked,
            ),
        ),
        3,
    )

    alignment_breakers: list[dict[str, Any]] = []
    if blocked > 0:
        alignment_breakers.append(
            {
                "code": "blocked_transitions",
                "severity": "HIGH",
                "details": f"Migration contains {blocked} blocked transitions.",
            }
        )
    if drift_score > 0.35:
        alignment_breakers.append(
            {
                "code": "runtime_drift_exceeds_alignment_window",
                "severity": "MEDIUM",
                "details": f"Runtime drift score {drift_score:.3f} exceeds expected migration alignment window.",
            }
        )

    classification = "PASS"
    if any(str(_as_dict(row).get("severity", "")).upper() == "HIGH" for row in alignment_breakers):
        classification = "FAIL_CLOSED"
    elif alignment_breakers or alignment_score < 0.60:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "migration_runtime_alignment",
        "target_id": str(target_id),
        "classification": classification,
        "alignment_score": alignment_score,
        "summary": {
            "transition_total": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "high_risk_dependencies": high_risk_dependencies,
            "runtime_confidence": round(runtime_confidence, 3),
            "runtime_drift_score": round(drift_score, 3),
            "checkpoint_integrity": round(checkpoint_integrity, 3),
        },
        "alignment_breakers": alignment_breakers,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "preserve_migration_governance_rules": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationRuntimeAlignmentResult(
        migration_runtime_alignment=payload,
        alignment_score=alignment_score,
        deterministic_fingerprint=fingerprint,
    )
