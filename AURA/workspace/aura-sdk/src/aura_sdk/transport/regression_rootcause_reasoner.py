"""Regression root-cause reasoning for unified engineering truth model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RegressionRootcauseResult:
    regression_rootcause_report: dict[str, Any]
    rootcause_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def reason_regression_rootcause(
    *,
    target_id: str,
    runtime_drift_report: Mapping[str, Any],
    lifecycle_causality_map: Mapping[str, Any],
    migration_runtime_alignment: Mapping[str, Any],
    patch_runtime_lineage: Mapping[str, Any],
    dsp_runtime_causality_report: Mapping[str, Any],
    cross_domain_reasoning: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RegressionRootcauseResult:
    drift = _as_dict(runtime_drift_report)
    lifecycle = _as_dict(lifecycle_causality_map)
    migration = _as_dict(migration_runtime_alignment)
    patch = _as_dict(patch_runtime_lineage)
    dsp = _as_dict(dsp_runtime_causality_report)
    reasoning = _as_dict(cross_domain_reasoning)

    root_causes: list[dict[str, Any]] = []

    for row in _as_list(drift.get("drifts")):
        item = _as_dict(row)
        root_causes.append(
            {
                "domain": "runtime_drift",
                "cause": str(item.get("type", "unknown_drift")),
                "severity": str(item.get("severity", "MEDIUM")),
                "details": str(item.get("details", "")),
                "confidence": 0.75,
            }
        )

    if str(migration.get("classification", "")) == "FAIL_CLOSED":
        root_causes.append(
            {
                "domain": "migration_alignment",
                "cause": "blocked_transition_alignment",
                "severity": "HIGH",
                "details": "Migration transitions are blocked against current runtime behavior.",
                "confidence": 0.8,
            }
        )

    if str(dsp.get("classification", "")) in {"ADVISORY_ONLY", "FAIL_CLOSED"}:
        root_causes.append(
            {
                "domain": "dsp_runtime",
                "cause": "dsp_sync_causality_degradation",
                "severity": "MEDIUM" if str(dsp.get("classification", "")) == "ADVISORY_ONLY" else "HIGH",
                "details": "DSP synchronization anomalies influence runtime timing behavior.",
                "confidence": 0.72,
            }
        )

    if str(patch.get("classification", "")) == "FAIL_CLOSED":
        root_causes.append(
            {
                "domain": "patch_lineage",
                "cause": "patch_runtime_drift_mismatch",
                "severity": "HIGH",
                "details": "Patch groups with runtime impact correlate with drift signals.",
                "confidence": 0.78,
            }
        )

    lifecycle_low_edges = int(_as_dict(lifecycle.get("summary")).get("low_strength_edges", 0) or 0)
    if lifecycle_low_edges > 0:
        root_causes.append(
            {
                "domain": "lifecycle_causality",
                "cause": "weak_lifecycle_causality_edges",
                "severity": "MEDIUM",
                "details": f"Detected {lifecycle_low_edges} low-strength lifecycle edges.",
                "confidence": 0.65,
            }
        )

    root_causes = sorted(
        root_causes,
        key=lambda row: (0 if str(_as_dict(row).get("severity", "")).upper() == "HIGH" else 1, -float(_as_dict(row).get("confidence", 0.0) or 0.0), str(_as_dict(row).get("cause", ""))),
    )

    high = len([row for row in root_causes if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium = len([row for row in root_causes if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    reasoning_score = float(reasoning.get("reasoning_score", 0.0) or 0.0)
    rootcause_confidence = round(max(0.0, min(1.0, 0.55 * reasoning_score + 0.45 * (1.0 - min(1.0, (high * 2 + medium) / 10.0)))), 3)

    classification = "PASS"
    if high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0 or rootcause_confidence < 0.70:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "regression_rootcause_report",
        "target_id": str(target_id),
        "classification": classification,
        "rootcause_confidence": rootcause_confidence,
        "root_causes": root_causes,
        "summary": {
            "rootcause_count": len(root_causes),
            "high_severity_count": high,
            "medium_severity_count": medium,
            "cross_domain_reasoning_score": round(reasoning_score, 3),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RegressionRootcauseResult(
        regression_rootcause_report=payload,
        rootcause_confidence=rootcause_confidence,
        deterministic_fingerprint=fingerprint,
    )
