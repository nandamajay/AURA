"""Abstraction gap reasoner for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class AbstractionGapReasoningResult:
    abstraction_gap_report: dict[str, Any]
    abstraction_gap_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def reason_abstraction_gaps(
    *,
    target_id: str,
    topology_structure_graph: Mapping[str, Any],
    upstream_equivalence_trace: Mapping[str, Any],
    vendor_dependency_graph: Mapping[str, Any],
    lifecycle_incompatibility_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> AbstractionGapReasoningResult:
    topology = _as_dict(topology_structure_graph)
    upstream = _as_dict(upstream_equivalence_trace)
    vendor = _as_dict(vendor_dependency_graph)
    lifecycle = _as_dict(lifecycle_incompatibility_report)

    fe_be = _as_dict(topology.get("fe_be_topology"))
    frontend = [str(item) for item in _as_list(fe_be.get("frontend_dais")) if str(item).strip()]
    backend = [str(item) for item in _as_list(fe_be.get("backend_dais")) if str(item).strip()]
    inferred_links = [row for row in _as_list(fe_be.get("inferred_links")) if isinstance(row, dict)]

    unresolved = [
        row
        for row in _as_list(upstream.get("entries"))
        if isinstance(row, dict)
        and str(row.get("equivalence_status", "")).upper() == "UNRESOLVED"
    ]

    vendor_dsp = [str(item) for item in _as_list(vendor.get("dsp_coupling")) if str(item).strip()]
    soundwire_gaps = [str(item) for item in _as_list(vendor.get("soundwire_portability_gaps")) if str(item).strip()]

    lifecycle_rows = [row for row in _as_list(lifecycle.get("lifecycle_incompatibilities")) if isinstance(row, dict)]

    gap_items: list[dict[str, Any]] = []

    dpcm_blockers = []
    if frontend and backend and not inferred_links:
        dpcm_blockers.append("missing_fe_be_inference")
    if unresolved:
        unresolved_dpcm = [
            str(row.get("downstream_construct", ""))
            for row in unresolved
            if "dai" in str(row.get("downstream_construct", "")).lower()
            or "fe" in str(row.get("downstream_construct", "")).lower()
            or "be" in str(row.get("downstream_construct", "")).lower()
            or "dpcm" in str(row.get("downstream_construct", "")).lower()
        ]
        if unresolved_dpcm:
            dpcm_blockers.extend(unresolved_dpcm)
    dpcm_blockers = _dedupe_sorted(dpcm_blockers)
    if dpcm_blockers:
        gap_items.append(
            {
                "type": "dpcm_fe_be_migration_blockers",
                "severity": "HIGH",
                "details": dpcm_blockers,
            }
        )

    topology_incompat = []
    dapm = _as_dict(topology.get("dapm_graph"))
    routes = _as_list(dapm.get("routes"))
    if not routes:
        topology_incompat.append("missing_dapm_routes")
    if len(frontend) != len(backend) and backend:
        topology_incompat.append("frontend_backend_cardinality_mismatch")
    if topology_incompat:
        gap_items.append(
            {
                "type": "topology_incompatibilities",
                "severity": "MEDIUM",
                "details": topology_incompat,
            }
        )

    if soundwire_gaps:
        gap_items.append(
            {
                "type": "soundwire_portability_gaps",
                "severity": "MEDIUM",
                "details": soundwire_gaps,
            }
        )

    if vendor_dsp:
        gap_items.append(
            {
                "type": "dsp_coupling",
                "severity": "HIGH",
                "details": vendor_dsp,
            }
        )

    api_drift = _dedupe_sorted(
        [
            item
            for row in lifecycle_rows
            if str(row.get("type", "")) == "api_drift"
            for item in _as_list(row.get("constructs"))
        ]
    )
    if api_drift:
        gap_items.append(
            {
                "type": "api_drift",
                "severity": "HIGH",
                "details": api_drift[:150],
            }
        )

    lifecycle_mismatch = [
        row
        for row in lifecycle_rows
        if str(row.get("type", "")) in {"component_lifecycle_mismatch", "ops_lifecycle_mismatch"}
    ]
    if lifecycle_mismatch:
        gap_items.append(
            {
                "type": "lifecycle_mismatches",
                "severity": "MEDIUM",
                "details": lifecycle_mismatch,
            }
        )

    score = round(
        min(
            1.0,
            0.18 * len([item for item in gap_items if str(item.get("severity", "")).upper() == "HIGH"])
            + 0.08 * len([item for item in gap_items if str(item.get("severity", "")).upper() == "MEDIUM"]),
        ),
        3,
    )

    classification = "PASS"
    if any(str(item.get("severity", "")).upper() == "HIGH" for item in gap_items):
        classification = "FAIL_CLOSED"
    elif gap_items:
        classification = "ADVISORY_ONLY"

    recommendations = [
        {
            "recommendation": "isolate_vendor_specific_callbacks",
            "mode": "ADVISORY_ONLY",
            "reason": "Reduce downstream callback dependency before upstream mapping.",
        },
        {
            "recommendation": "normalize_fe_be_contracts",
            "mode": "ADVISORY_ONLY",
            "reason": "Stabilize DPCM/FE-BE intent into explicit portable links.",
        },
        {
            "recommendation": "audit_soundwire_vendor_hooks",
            "mode": "ADVISORY_ONLY",
            "reason": "Bridge SoundWire portability gaps with upstream-compatible abstractions.",
        },
        {
            "recommendation": "gate_conversion_on_replay_stability",
            "mode": "GOVERNED_ONLY",
            "reason": "Prevent drift amplification during phased migration.",
        },
    ]

    payload = {
        "schema_version": "1.0",
        "report_name": "abstraction_gap_report",
        "target_id": str(target_id),
        "classification": classification,
        "abstraction_gap_score": score,
        "gaps": gap_items,
        "abstraction_recommendations": recommendations,
        "summary": {
            "frontend_count": len(frontend),
            "backend_count": len(backend),
            "dpcm_inferred_link_count": len(inferred_links),
            "unresolved_upstream_constructs": len(unresolved),
            "gap_count": len(gap_items),
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return AbstractionGapReasoningResult(
        abstraction_gap_report=payload,
        abstraction_gap_score=score,
        deterministic_fingerprint=fingerprint,
    )
