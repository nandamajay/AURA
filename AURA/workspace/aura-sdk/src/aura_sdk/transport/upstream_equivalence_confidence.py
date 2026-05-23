"""Upstream equivalence confidence scoring for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class UpstreamEquivalenceConfidenceResult:
    upstream_equivalence_confidence: dict[str, Any]
    overall_confidence: float
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


def score_upstream_equivalence_confidence(
    *,
    target_id: str,
    upstream_equivalence_trace: Mapping[str, Any],
    abstraction_gap_report: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    vendor_dependency_graph: Mapping[str, Any],
    lifecycle_incompatibility_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> UpstreamEquivalenceConfidenceResult:
    upstream = _as_dict(upstream_equivalence_trace)
    abstraction = _as_dict(abstraction_gap_report)
    runtime = _as_dict(runtime_portability_analysis)
    vendor = _as_dict(vendor_dependency_graph)
    lifecycle = _as_dict(lifecycle_incompatibility_report)

    summary = _as_dict(upstream.get("summary"))
    total = max(1, int(summary.get("total", 0) or 0))
    exact = int(summary.get("exact", 0) or 0)
    partial = int(summary.get("partial", 0) or 0)
    unresolved = int(summary.get("unresolved", 0) or 0)

    equivalence_coverage = (exact + 0.5 * partial) / total

    abstraction_penalty = _to_float(abstraction.get("abstraction_gap_score", 0.0))
    runtime_score = _to_float(runtime.get("runtime_portability_score", 0.0))
    vendor_risk = _to_float(vendor.get("dependency_risk_score", 0.0))
    lifecycle_risk = _to_float(lifecycle.get("lifecycle_risk_score", 0.0))

    topology_conversion_confidence = max(0.0, min(1.0, equivalence_coverage - 0.6 * abstraction_penalty))

    overall = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * equivalence_coverage
                + 0.2 * topology_conversion_confidence
                + 0.2 * runtime_score
                + 0.15 * (1.0 - vendor_risk)
                + 0.1 * (1.0 - lifecycle_risk),
            ),
        ),
        3,
    )

    equivalence_status = "STRONG"
    if overall < 0.45:
        equivalence_status = "WEAK"
    elif overall < 0.7:
        equivalence_status = "MODERATE"

    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_equivalence_confidence",
        "target_id": str(target_id),
        "equivalence_status": equivalence_status,
        "scores": {
            "equivalence_coverage": round(equivalence_coverage, 3),
            "topology_conversion_confidence": round(topology_conversion_confidence, 3),
            "runtime_portability_confidence": round(runtime_score, 3),
            "vendor_dependency_inverse_risk": round(max(0.0, 1.0 - vendor_risk), 3),
            "lifecycle_inverse_risk": round(max(0.0, 1.0 - lifecycle_risk), 3),
            "overall_confidence": overall,
        },
        "drivers": {
            "exact": exact,
            "partial": partial,
            "unresolved": unresolved,
            "total": total,
        },
        "summary": {
            "high_gap_penalty": abstraction_penalty >= 0.5,
            "runtime_portability_classification": str(runtime.get("classification", "UNKNOWN")),
            "vendor_dependency_classification": str(vendor.get("classification", "UNKNOWN")),
            "lifecycle_classification": str(lifecycle.get("classification", "UNKNOWN")),
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return UpstreamEquivalenceConfidenceResult(
        upstream_equivalence_confidence=payload,
        overall_confidence=overall,
        deterministic_fingerprint=fingerprint,
    )
