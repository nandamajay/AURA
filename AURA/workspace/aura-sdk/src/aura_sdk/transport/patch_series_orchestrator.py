"""Patch series orchestration with maintainership-safe sequencing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PatchSeriesPlanResult:
    patch_series_plan: dict[str, Any]
    orchestration_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def orchestrate_patch_series(
    *,
    target_id: str,
    upstream_readiness_report: Mapping[str, Any],
    upstream_governance_gate: Mapping[str, Any],
    patch_dependency_graph: Mapping[str, Any],
    subsystem_boundary_map: Mapping[str, Any],
    runtime_patch_correlation: Mapping[str, Any],
    bisectability_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> PatchSeriesPlanResult:
    readiness = _as_dict(upstream_readiness_report)
    governance = _as_dict(upstream_governance_gate)
    dependency = _as_dict(patch_dependency_graph)
    boundaries = _as_dict(subsystem_boundary_map)
    runtime_corr = _as_dict(runtime_patch_correlation)
    bisectability = _as_dict(bisectability_report)

    nodes = [row for row in _as_list(dependency.get("nodes")) if isinstance(row, dict)]
    subsystems = [row for row in _as_list(boundaries.get("subsystems")) if isinstance(row, dict)]
    subsystem_names = [str(row.get("subsystem", "")).strip() for row in subsystems if str(row.get("subsystem", "")).strip()]

    series_steps: list[dict[str, Any]] = []
    for index, row in enumerate(sorted(nodes, key=lambda item: str(item.get("patch_id", ""))), start=1):
        patch_id = str(row.get("patch_id", "")).strip()
        scope = [str(item) for item in _as_list(row.get("scope")) if str(item).strip()]
        risk = str(row.get("risk", "MEDIUM")).strip().upper()
        depends_on = [str(item) for item in _as_list(row.get("depends_on")) if str(item).strip()]

        if "vendor" in patch_id:
            maintainers = ["soc-audio-maintainers", "vendor-audio-maintainers"]
        elif "soundwire" in patch_id:
            maintainers = ["soundwire-maintainers", "soc-audio-maintainers"]
        else:
            maintainers = ["soc-audio-maintainers"]

        series_steps.append(
            {
                "sequence": index,
                "patch_group_id": patch_id,
                "risk": risk,
                "scope": sorted(set(scope)),
                "depends_on": sorted(set(depends_on)),
                "maintainer_review_groups": maintainers,
                "subsystem_owners": subsystem_names[:8],
                "runtime_validation_gate": {
                    "required": True,
                    "blast_radius": str(runtime_corr.get("regression_blast_radius", "UNKNOWN")),
                },
                "bisect_gate": {
                    "required": True,
                    "minimum_score": 0.70,
                    "current_score": float(bisectability.get("bisectability_score", 0.0) or 0.0),
                },
            }
        )

    readiness_score = float(readiness.get("readiness_score", 0.0) or 0.0)
    bisect_score = float(bisectability.get("bisectability_score", 0.0) or 0.0)

    orchestration_score = round(max(0.0, min(1.0, 0.55 * readiness_score + 0.45 * bisect_score)), 3)

    classification = "PASS"
    if str(governance.get("classification", "")) == "FAIL_CLOSED" or str(readiness.get("classification", "")) == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
    elif orchestration_score < 0.65:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "patch_series_plan",
        "target_id": str(target_id),
        "classification": classification,
        "orchestration_score": orchestration_score,
        "series": series_steps,
        "summary": {
            "series_count": len(series_steps),
            "readiness_score": round(readiness_score, 3),
            "bisectability_score": round(bisect_score, 3),
            "governance_classification": str(governance.get("classification", "UNKNOWN")),
        },
        "policy": {
            "advisory_only": True,
            "autonomous_patch_submission": False,
            "maintainership_review_required": True,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PatchSeriesPlanResult(
        patch_series_plan=payload,
        orchestration_score=orchestration_score,
        deterministic_fingerprint=fingerprint,
    )
