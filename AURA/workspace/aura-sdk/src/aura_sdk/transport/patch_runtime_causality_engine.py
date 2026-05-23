"""Patch/migration/runtime causality correlation engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RegressionCausalityReportResult:
    regression_causality_report: dict[str, Any]
    causality_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_patch_runtime_causality(
    *,
    target_id: str,
    patch_series_plan: Mapping[str, Any],
    runtime_patch_correlation: Mapping[str, Any],
    runtime_drift_report: Mapping[str, Any],
    migration_runtime_alignment: Mapping[str, Any],
    portability_blockers: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    vendor_contamination_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RegressionCausalityReportResult:
    patch_plan = _as_dict(patch_series_plan)
    runtime_corr = _as_dict(runtime_patch_correlation)
    drift = _as_dict(runtime_drift_report)
    migration = _as_dict(migration_runtime_alignment)
    blockers = _as_dict(portability_blockers)
    equivalence = _as_dict(upstream_equivalence_map)
    vendor = _as_dict(vendor_contamination_report)

    drifts = [row for row in _as_list(drift.get("drifts")) if isinstance(row, dict)]
    mappings = [row for row in _as_list(runtime_corr.get("command_patch_mappings")) if isinstance(row, dict)]

    patch_causal_links: list[dict[str, Any]] = []
    patch_risk_map: dict[str, str] = {}
    for row in _as_list(patch_plan.get("series")):
        item = _as_dict(row)
        patch_id = str(item.get("patch_group_id", "")).strip()
        if not patch_id:
            continue
        patch_risk_map[patch_id] = str(item.get("risk", "UNKNOWN"))

    for row in mappings:
        item = _as_dict(row)
        runtime_command = str(item.get("runtime_command", "")).strip()
        impacted = [str(val) for val in _as_list(item.get("impacted_patch_nodes")) if str(val).strip()]
        correlation_confidence = float(item.get("correlation_confidence", 0.0) or 0.0)
        if not runtime_command or not impacted:
            continue
        for patch_id in impacted:
            patch_causal_links.append(
                {
                    "patch_group_id": patch_id,
                    "runtime_command": runtime_command,
                    "risk": patch_risk_map.get(patch_id, "UNKNOWN"),
                    "correlation_confidence": round(correlation_confidence, 3),
                }
            )

    high_drift = len([row for row in drifts if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium_drift = len([row for row in drifts if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    unresolved_equivalence = 0
    for row in _as_list(equivalence.get("entries")):
        item = _as_dict(row)
        status = str(item.get("equivalence_status", "")).strip().upper()
        if status in {"UNRESOLVED", "MISSING", "INCOMPATIBLE"}:
            unresolved_equivalence += 1

    blocked_unsafe = int(_as_dict(blockers.get("summary")).get("blocked_unsafe_count", 0) or 0)
    contamination_score = float(vendor.get("contamination_score", 0.0) or 0.0)

    causes: list[dict[str, Any]] = []

    if high_drift > 0 and len(patch_causal_links) > 0:
        causes.append(
            {
                "cause": "patch_induced_runtime_regression",
                "severity": "HIGH",
                "details": f"{high_drift} high-severity runtime drifts overlap with patch/runtime causal links.",
                "confidence": 0.82,
            }
        )
    elif medium_drift > 0 and len(patch_causal_links) > 0:
        causes.append(
            {
                "cause": "patch_runtime_drift_overlap",
                "severity": "MEDIUM",
                "details": f"{medium_drift} medium runtime drifts overlap with patch/runtime causal links.",
                "confidence": 0.7,
            }
        )

    migration_class = str(migration.get("classification", "")).strip().upper()
    if migration_class == "FAIL_CLOSED":
        causes.append(
            {
                "cause": "migration_induced_incompatibility",
                "severity": "HIGH",
                "details": "Migration/runtime alignment is FAIL_CLOSED.",
                "confidence": 0.85,
            }
        )

    if unresolved_equivalence > 0:
        causes.append(
            {
                "cause": "upstream_downstream_abstraction_mismatch",
                "severity": "MEDIUM" if unresolved_equivalence <= 2 else "HIGH",
                "details": f"Detected {unresolved_equivalence} unresolved upstream equivalence mappings.",
                "confidence": 0.74,
            }
        )

    if blocked_unsafe > 0:
        causes.append(
            {
                "cause": "unsupported_upstream_abstraction",
                "severity": "HIGH",
                "details": f"Detected {blocked_unsafe} blocked portability blockers.",
                "confidence": 0.79,
            }
        )

    if contamination_score > 0.45:
        causes.append(
            {
                "cause": "vendor_dependency_contamination",
                "severity": "MEDIUM" if contamination_score < 0.7 else "HIGH",
                "details": f"Vendor contamination score is {contamination_score:.3f}.",
                "confidence": 0.72,
            }
        )

    causes = sorted(
        causes,
        key=lambda row: (
            0 if str(_as_dict(row).get("severity", "")).upper() == "HIGH" else 1,
            -float(_as_dict(row).get("confidence", 0.0) or 0.0),
            str(_as_dict(row).get("cause", "")),
        ),
    )

    high = len([row for row in causes if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium = len([row for row in causes if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    causality_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.30 * min(1.0, len(patch_causal_links) / 20.0)
                + 0.25 * (1.0 - min(1.0, (high * 2 + medium) / 10.0))
                + 0.20 * min(1.0, max(0, medium_drift + high_drift) / 6.0)
                + 0.15 * min(1.0, unresolved_equivalence / 6.0)
                + 0.10 * min(1.0, contamination_score),
            ),
        ),
        3,
    )

    classification = "PASS"
    if high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "regression_causality_report",
        "target_id": str(target_id),
        "classification": classification,
        "causality_confidence": causality_confidence,
        "patch_runtime_causal_links": patch_causal_links,
        "causes": causes,
        "summary": {
            "patch_causal_link_count": len(patch_causal_links),
            "high_severity_cause_count": high,
            "medium_severity_cause_count": medium,
            "runtime_drift_high_count": high_drift,
            "runtime_drift_medium_count": medium_drift,
            "unresolved_equivalence_count": unresolved_equivalence,
            "blocked_unsafe_count": blocked_unsafe,
            "vendor_contamination_score": round(contamination_score, 3),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "preserve_migration_governance_rules": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RegressionCausalityReportResult(
        regression_causality_report=payload,
        causality_confidence=causality_confidence,
        deterministic_fingerprint=fingerprint,
    )
