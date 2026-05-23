"""Runtime drift detection against expected lineage for runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeDriftReportResult:
    runtime_drift_report: dict[str, Any]
    drift_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def detect_runtime_drift(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    runtime_event_ingestion: Mapping[str, Any],
    trace_correlation: Mapping[str, Any],
    expected_lineage: list[Mapping[str, Any]] | None,
    evidence_references: list[str] | None,
) -> RuntimeDriftReportResult:
    runtime = _as_dict(runtime_evidence)
    ingestion = _as_dict(runtime_event_ingestion)
    correlation = _as_dict(trace_correlation)
    lineage = [row for row in _as_list(expected_lineage or []) if isinstance(row, dict)]

    expected_seconds = float(runtime.get("expected_runtime_seconds", 25.0) or 25.0)
    observed_seconds = float(runtime.get("playback_runtime_seconds", 0.0) or 0.0)
    runtime_delta = abs(observed_seconds - expected_seconds)

    expected_sequence = [str(item) for item in _as_list(runtime.get("expected_sequence")) if str(item).strip()]
    observed_sequence = [
        str(_as_dict(event).get("category", ""))
        for event in _as_list(ingestion.get("events"))
        if isinstance(event, dict)
    ]

    drifts: list[dict[str, Any]] = []

    if runtime_delta > 3.0:
        drifts.append(
            {
                "type": "playback_timing_drift",
                "severity": "MEDIUM" if runtime_delta <= 8.0 else "HIGH",
                "details": f"Observed runtime delta {runtime_delta:.3f}s exceeds threshold.",
            }
        )

    if expected_sequence:
        mismatch = [step for step in expected_sequence if step not in observed_sequence]
        if mismatch:
            drifts.append(
                {
                    "type": "execution_sequence_drift",
                    "severity": "MEDIUM",
                    "details": f"Missing expected sequence steps: {', '.join(mismatch)}",
                }
            )

    warning_count = len(_as_list(correlation.get("ordering_warnings")))
    if warning_count > 0:
        drifts.append(
            {
                "type": "ordering_warning_drift",
                "severity": "MEDIUM" if warning_count < 3 else "HIGH",
                "details": f"Detected {warning_count} trace ordering warnings.",
            }
        )

    if lineage:
        previous_class = str(_as_dict(lineage[-1]).get("classification", "UNKNOWN"))
        current_class = str(correlation.get("classification", "UNKNOWN"))
        if previous_class == "PASS" and current_class != "PASS":
            drifts.append(
                {
                    "type": "lineage_classification_drift",
                    "severity": "HIGH",
                    "details": f"Classification regressed from {previous_class} to {current_class}.",
                }
            )

    high = len([row for row in drifts if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium = len([row for row in drifts if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    drift_score = round(max(0.0, min(1.0, 0.28 * high + 0.12 * medium + min(0.4, runtime_delta / 20.0))), 3)

    classification = "PASS"
    if high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_drift_report",
        "target_id": str(target_id),
        "classification": classification,
        "drift_score": drift_score,
        "drifts": drifts,
        "summary": {
            "high_drift_count": high,
            "medium_drift_count": medium,
            "runtime_delta_seconds": round(runtime_delta, 3),
            "lineage_entries_compared": len(lineage),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimeDriftReportResult(
        runtime_drift_report=payload,
        drift_score=drift_score,
        deterministic_fingerprint=fingerprint,
    )
