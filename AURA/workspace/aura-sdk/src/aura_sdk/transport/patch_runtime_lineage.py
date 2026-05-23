"""Patch/runtime lineage mapping for fusion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PatchRuntimeLineageResult:
    patch_runtime_lineage: dict[str, Any]
    lineage_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_patch_runtime_lineage(
    *,
    target_id: str,
    patch_series_plan: Mapping[str, Any],
    runtime_patch_correlation: Mapping[str, Any],
    runtime_drift_report: Mapping[str, Any],
    upstream_readiness_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> PatchRuntimeLineageResult:
    patch_plan = _as_dict(patch_series_plan)
    runtime_corr = _as_dict(runtime_patch_correlation)
    drift = _as_dict(runtime_drift_report)
    readiness = _as_dict(upstream_readiness_report)

    series = [row for row in _as_list(patch_plan.get("series")) if isinstance(row, dict)]
    mappings = [row for row in _as_list(runtime_corr.get("command_patch_mappings")) if isinstance(row, dict)]
    drift_rows = [row for row in _as_list(drift.get("drifts")) if isinstance(row, dict)]

    patch_ids = [str(_as_dict(row).get("patch_group_id", "")) for row in series if str(_as_dict(row).get("patch_group_id", ""))]

    impacted_counts: dict[str, int] = {patch_id: 0 for patch_id in patch_ids}
    for row in mappings:
        for patch_id in [str(item) for item in _as_list(_as_dict(row).get("impacted_patch_nodes")) if str(item).strip()]:
            if patch_id in impacted_counts:
                impacted_counts[patch_id] += 1

    drift_severity = {
        "HIGH": len([row for row in drift_rows if str(_as_dict(row).get("severity", "")).upper() == "HIGH"]),
        "MEDIUM": len([row for row in drift_rows if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"]),
    }

    lineage_rows: list[dict[str, Any]] = []
    for row in series:
        item = _as_dict(row)
        patch_id = str(item.get("patch_group_id", "")).strip()
        if not patch_id:
            continue
        lineage_rows.append(
            {
                "patch_group_id": patch_id,
                "sequence": int(item.get("sequence", 0) or 0),
                "risk": str(item.get("risk", "UNKNOWN")),
                "impacted_runtime_command_count": int(impacted_counts.get(patch_id, 0)),
                "runtime_validation_required": bool(_as_dict(item.get("runtime_validation_gate")).get("required", False)),
                "bisect_gate_score": float(
                    _as_dict(item.get("bisect_gate")).get("current_score", 0.0) or 0.0
                ),
            }
        )

    average_impact = (sum(impacted_counts.values()) / max(1, len(impacted_counts))) if impacted_counts else 0.0
    readiness_score = float(readiness.get("readiness_score", 0.0) or 0.0)

    lineage_score = round(
        max(
            0.0,
            min(
                1.0,
                0.40 * min(1.0, average_impact / 20.0)
                + 0.35 * readiness_score
                + 0.25 * (1.0 - min(1.0, (drift_severity["HIGH"] * 2 + drift_severity["MEDIUM"]) / 10.0)),
            ),
        ),
        3,
    )

    classification = "PASS"
    if drift_severity["HIGH"] > 0:
        classification = "FAIL_CLOSED"
    elif drift_severity["MEDIUM"] > 0 or lineage_score < 0.55:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "patch_runtime_lineage",
        "target_id": str(target_id),
        "classification": classification,
        "lineage_score": lineage_score,
        "lineage": sorted(lineage_rows, key=lambda row: int(_as_dict(row).get("sequence", 0))),
        "summary": {
            "patch_group_count": len(lineage_rows),
            "total_runtime_impacts": int(sum(impacted_counts.values())),
            "average_runtime_impact": round(average_impact, 3),
            "drift_high_count": drift_severity["HIGH"],
            "drift_medium_count": drift_severity["MEDIUM"],
            "upstream_readiness_score": round(readiness_score, 3),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PatchRuntimeLineageResult(
        patch_runtime_lineage=payload,
        lineage_score=lineage_score,
        deterministic_fingerprint=fingerprint,
    )
