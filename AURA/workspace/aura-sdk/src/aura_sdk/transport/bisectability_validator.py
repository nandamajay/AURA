"""Bisectability validation for patch series safety."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class BisectabilityValidationResult:
    bisectability_report: dict[str, Any]
    bisectability_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def validate_bisectability(
    *,
    target_id: str,
    patch_dependency_graph: Mapping[str, Any],
    runtime_patch_correlation: Mapping[str, Any],
    vendor_contamination_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> BisectabilityValidationResult:
    graph = _as_dict(patch_dependency_graph)
    runtime = _as_dict(runtime_patch_correlation)
    contamination = _as_dict(vendor_contamination_report)

    nodes = [row for row in _as_list(graph.get("nodes")) if isinstance(row, dict)]
    blast_radius = str(runtime.get("regression_blast_radius", "MEDIUM")).strip().upper()
    downstream_only_count = int(_as_dict(contamination.get("summary", {})).get("downstream_only_api_count", 0) or 0)

    units: list[dict[str, Any]] = []
    blocked_units = 0

    for row in nodes:
        patch_id = str(row.get("patch_id", "")).strip()
        depends_on = [str(item).strip() for item in _as_list(row.get("depends_on")) if str(item).strip()]
        risk = str(row.get("risk", "MEDIUM")).strip().upper()

        independent = len(depends_on) <= 2 and risk != "HIGH"
        if blast_radius == "HIGH" and risk == "HIGH":
            independent = False
        if downstream_only_count > 50 and "vendor" in patch_id:
            independent = False

        if not independent:
            blocked_units += 1

        units.append(
            {
                "patch_id": patch_id,
                "risk": risk,
                "depends_on": depends_on,
                "bisect_safe": independent,
                "required_guardrails": [
                    "compile_check",
                    "runtime_smoke_validation",
                    "artifact_lineage_snapshot",
                ],
            }
        )

    total = max(1, len(units))
    bisectability_score = round(max(0.0, min(1.0, 1.0 - blocked_units / total)), 3)

    classification = "PASS"
    if blocked_units > 2:
        classification = "FAIL_CLOSED"
    elif blocked_units > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "bisectability_report",
        "target_id": str(target_id),
        "classification": classification,
        "bisectability_score": bisectability_score,
        "summary": {
            "total_units": total,
            "blocked_units": blocked_units,
            "bisect_safe_units": total - blocked_units,
            "runtime_blast_radius": blast_radius,
        },
        "units": sorted(units, key=lambda row: str(row.get("patch_id", ""))),
        "advisory_only_behavior": True,
        "runtime_truth_precedence": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return BisectabilityValidationResult(
        bisectability_report=payload,
        bisectability_score=bisectability_score,
        deterministic_fingerprint=fingerprint,
    )
