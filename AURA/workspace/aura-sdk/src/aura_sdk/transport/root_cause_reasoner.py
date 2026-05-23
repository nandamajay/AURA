"""Root cause candidate reasoning for runtime incident reconstruction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RootCauseCandidatesResult:
    root_cause_candidates: dict[str, Any]
    root_cause_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_root_cause_candidates(
    *,
    target_id: str,
    runtime_sequence_drift: Mapping[str, Any],
    lifecycle_violation_report: Mapping[str, Any],
    topology_runtime_causality: Mapping[str, Any],
    regression_causality_report: Mapping[str, Any],
    fusion_rootcause_report: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RootCauseCandidatesResult:
    drift = _as_dict(runtime_sequence_drift)
    lifecycle = _as_dict(lifecycle_violation_report)
    topology = _as_dict(topology_runtime_causality)
    regression = _as_dict(regression_causality_report)
    fusion = _as_dict(fusion_rootcause_report)
    equivalence = _as_dict(upstream_equivalence_map)

    candidates: list[dict[str, Any]] = []

    for row in _as_list(regression.get("causes")):
        item = _as_dict(row)
        candidates.append(
            {
                "candidate": str(item.get("cause", "regression_unknown")),
                "origin": "patch_runtime_causality_engine",
                "severity": str(item.get("severity", "MEDIUM")),
                "confidence": float(item.get("confidence", 0.6) or 0.6),
                "details": str(item.get("details", "")),
                "evidence_links": ["regression_causality_report"],
            }
        )

    for row in _as_list(fusion.get("root_causes")):
        item = _as_dict(row)
        candidates.append(
            {
                "candidate": str(item.get("cause", "fusion_unknown")),
                "origin": "runtime_evidence_fusion",
                "severity": str(item.get("severity", "MEDIUM")),
                "confidence": float(item.get("confidence", 0.58) or 0.58),
                "details": str(item.get("details", "")),
                "evidence_links": ["regression_rootcause_report"],
            }
        )

    for row in _as_list(lifecycle.get("violations")):
        item = _as_dict(row)
        severity = str(item.get("severity", "MEDIUM"))
        candidates.append(
            {
                "candidate": str(item.get("code", "lifecycle_violation")),
                "origin": "lifecycle_violation_detector",
                "severity": severity,
                "confidence": 0.68 if severity.upper() == "MEDIUM" else 0.8,
                "details": str(item.get("details", "")),
                "evidence_links": ["lifecycle_violation_report", "runtime_sequence_drift"],
            }
        )

    drift_rows = [row for row in _as_list(drift.get("drifts")) if isinstance(row, dict)]
    if drift_rows:
        candidates.append(
            {
                "candidate": "runtime_sequence_drift",
                "origin": "runtime_sequence_drift_engine",
                "severity": "MEDIUM",
                "confidence": 0.66,
                "details": f"Detected {len(drift_rows)} drift signals in ordered runtime timeline.",
                "evidence_links": ["runtime_sequence_drift"],
            }
        )

    topo_inconsistency_rows = [
        row for row in _as_list(topology.get("inconsistencies")) if isinstance(row, dict)
    ]
    if topo_inconsistency_rows:
        high = len(
            [
                row
                for row in topo_inconsistency_rows
                if str(_as_dict(row).get("severity", "")).upper() == "HIGH"
            ]
        )
        candidates.append(
            {
                "candidate": "topology_runtime_dependency_break",
                "origin": "topology_runtime_failure_mapper",
                "severity": "HIGH" if high > 0 else "MEDIUM",
                "confidence": 0.78 if high > 0 else 0.64,
                "details": f"Detected {len(topo_inconsistency_rows)} topology/runtime inconsistencies.",
                "evidence_links": ["topology_runtime_causality"],
            }
        )

    unresolved_entries = 0
    for row in _as_list(equivalence.get("entries")):
        item = _as_dict(row)
        status = str(item.get("equivalence_status", "")).strip().upper()
        if status in {"UNRESOLVED", "INCOMPATIBLE", "MISSING"}:
            unresolved_entries += 1
    if unresolved_entries > 0:
        candidates.append(
            {
                "candidate": "upstream_downstream_abstraction_mismatch",
                "origin": "equivalence_analysis",
                "severity": "MEDIUM" if unresolved_entries < 3 else "HIGH",
                "confidence": 0.71,
                "details": f"Detected {unresolved_entries} unresolved upstream/downstream abstraction mappings.",
                "evidence_links": ["upstream_equivalence_map", "regression_causality_report"],
            }
        )

    candidates = sorted(
        candidates,
        key=lambda row: (
            0 if str(_as_dict(row).get("severity", "")).upper() == "HIGH" else 1,
            -float(_as_dict(row).get("confidence", 0.0) or 0.0),
            str(_as_dict(row).get("candidate", "")),
        ),
    )

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in candidates:
        item = _as_dict(row)
        key = str(item.get("candidate", "")).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    high = len(
        [row for row in deduped if str(_as_dict(row).get("severity", "")).upper() == "HIGH"]
    )
    medium = len(
        [row for row in deduped if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"]
    )

    top_conf = float(_as_dict(deduped[0]).get("confidence", 0.0) or 0.0) if deduped else 0.0
    root_cause_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * top_conf
                + 0.25 * min(1.0, len(deduped) / 6.0)
                + 0.20 * (1.0 - min(1.0, (high * 2 + medium) / 10.0)),
            ),
        ),
        3,
    )

    classification = "PASS"
    uncertain = len(deduped) == 0 or root_cause_confidence < 0.62
    if uncertain or high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "root_cause_candidates",
        "target_id": str(target_id),
        "classification": classification,
        "root_cause_confidence": root_cause_confidence,
        "candidates": deduped,
        "summary": {
            "candidate_count": len(deduped),
            "high_severity_count": high,
            "medium_severity_count": medium,
            "uncertain_classification": uncertain,
            "top_candidate": str(_as_dict(deduped[0]).get("candidate", "")) if deduped else "",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RootCauseCandidatesResult(
        root_cause_candidates=payload,
        root_cause_confidence=root_cause_confidence,
        deterministic_fingerprint=fingerprint,
    )
