"""Upstream readiness classification based on patch cognition evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class UpstreamReadinessResult:
    upstream_readiness_report: dict[str, Any]
    readiness_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def classify_upstream_readiness(
    *,
    target_id: str,
    upstream_governance_gate: Mapping[str, Any],
    vendor_contamination_report: Mapping[str, Any],
    subsystem_boundary_map: Mapping[str, Any],
    patch_dependency_graph: Mapping[str, Any],
    runtime_patch_correlation: Mapping[str, Any],
    bisectability_report: Mapping[str, Any],
    api_evolution_trace: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> UpstreamReadinessResult:
    governance = _as_dict(upstream_governance_gate)
    contamination = _as_dict(vendor_contamination_report)
    boundaries = _as_dict(subsystem_boundary_map)
    dependency = _as_dict(patch_dependency_graph)
    runtime_corr = _as_dict(runtime_patch_correlation)
    bisectability = _as_dict(bisectability_report)
    api_trace = _as_dict(api_evolution_trace)

    governance_score = _to_float(governance.get("gate_score", 0.0), 0.0)
    contamination_score = 1.0 - _to_float(contamination.get("contamination_score", 1.0), 1.0)
    boundary_score = _to_float(boundaries.get("boundary_confidence", 0.0), 0.0)
    dependency_score = _to_float(dependency.get("dependency_stability_score", 0.0), 0.0)
    runtime_score = _to_float(runtime_corr.get("runtime_alignment_score", 0.0), 0.0)
    bisect_score = _to_float(bisectability.get("bisectability_score", 0.0), 0.0)
    api_score = _to_float(api_trace.get("compatibility_score", 0.0), 0.0)

    readiness_score = round(
        max(
            0.0,
            min(
                1.0,
                0.20 * governance_score
                + 0.12 * contamination_score
                + 0.12 * boundary_score
                + 0.12 * dependency_score
                + 0.14 * runtime_score
                + 0.15 * bisect_score
                + 0.15 * api_score,
            ),
        ),
        3,
    )

    classification = "PASS"
    if str(governance.get("classification", "")) == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
    elif any(
        [
            str(contamination.get("classification", "")) == "FAIL_CLOSED",
            str(bisectability.get("classification", "")) == "FAIL_CLOSED",
            str(api_trace.get("classification", "")) == "FAIL_CLOSED",
            readiness_score < 0.45,
        ]
    ):
        classification = "FAIL_CLOSED"
    elif readiness_score < 0.70:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_readiness_report",
        "target_id": str(target_id),
        "classification": classification,
        "readiness_score": readiness_score,
        "factors": {
            "governance_safety": round(governance_score, 3),
            "vendor_contamination_safety": round(contamination_score, 3),
            "subsystem_boundary_confidence": round(boundary_score, 3),
            "dependency_stability": round(dependency_score, 3),
            "runtime_patch_alignment": round(runtime_score, 3),
            "bisectability": round(bisect_score, 3),
            "api_evolution_compatibility": round(api_score, 3),
        },
        "summary": {
            "governance_classification": str(governance.get("classification", "UNKNOWN")),
            "vendor_contamination_classification": str(contamination.get("classification", "UNKNOWN")),
            "bisectability_classification": str(bisectability.get("classification", "UNKNOWN")),
            "api_evolution_classification": str(api_trace.get("classification", "UNKNOWN")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return UpstreamReadinessResult(
        upstream_readiness_report=payload,
        readiness_score=readiness_score,
        deterministic_fingerprint=fingerprint,
    )
