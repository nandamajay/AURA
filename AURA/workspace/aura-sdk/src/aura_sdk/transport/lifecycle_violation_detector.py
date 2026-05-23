"""Lifecycle violation detection for runtime incident reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class LifecycleViolationReportResult:
    lifecycle_violation_report: dict[str, Any]
    violation_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _stage_index(stages: list[str], stage: str) -> int:
    try:
        return stages.index(stage)
    except ValueError:
        return -1


def detect_lifecycle_violations(
    *,
    target_id: str,
    pcm_lifecycle_trace: Mapping[str, Any],
    dapm_transition_trace: Mapping[str, Any],
    runtime_sequence_drift: Mapping[str, Any],
    dsp_sync_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> LifecycleViolationReportResult:
    pcm = _as_dict(pcm_lifecycle_trace)
    dapm = _as_dict(dapm_transition_trace)
    drift = _as_dict(runtime_sequence_drift)
    dsp = _as_dict(dsp_sync_report)

    stages = [
        str(_as_dict(row).get("stage", "")).strip().upper()
        for row in _as_list(pcm.get("transitions"))
        if str(_as_dict(row).get("stage", "")).strip()
    ]
    dapm_transitions = [
        str(_as_dict(row).get("transition", "")).strip().upper()
        for row in _as_list(dapm.get("transitions"))
        if str(_as_dict(row).get("transition", "")).strip()
    ]

    violations: list[dict[str, Any]] = []

    start_idx = _stage_index(stages, "START")
    prepare_idx = _stage_index(stages, "PREPARE")
    close_idx = _stage_index(stages, "CLOSE")

    if start_idx < 0:
        violations.append(
            {
                "code": "pcm_start_missing",
                "severity": "HIGH",
                "details": "PCM START stage is missing from lifecycle transitions.",
            }
        )
    if prepare_idx < 0:
        violations.append(
            {
                "code": "pcm_prepare_missing",
                "severity": "MEDIUM",
                "details": "PCM PREPARE stage is missing from lifecycle transitions.",
            }
        )
    if close_idx < 0:
        violations.append(
            {
                "code": "pcm_close_missing",
                "severity": "MEDIUM",
                "details": "PCM CLOSE stage is missing from lifecycle transitions.",
            }
        )

    if start_idx >= 0 and prepare_idx >= 0 and start_idx < prepare_idx:
        violations.append(
            {
                "code": "pcm_prepare_start_order_violation",
                "severity": "HIGH",
                "details": "PCM START occurred before PREPARE.",
            }
        )

    if close_idx >= 0 and start_idx >= 0 and close_idx < start_idx:
        violations.append(
            {
                "code": "pcm_close_before_start",
                "severity": "HIGH",
                "details": "PCM CLOSE occurred before START.",
            }
        )

    if "POWER_UP" not in dapm_transitions and "STATE" not in dapm_transitions:
        violations.append(
            {
                "code": "dapm_activation_missing",
                "severity": "MEDIUM",
                "details": "No DAPM activation transition observed.",
            }
        )

    dsp_failures = int(_as_dict(dsp.get("summary")).get("sync_failure_count", 0) or 0)
    if dsp_failures > 0:
        violations.append(
            {
                "code": "dsp_sync_lifecycle_violation",
                "severity": "HIGH" if dsp_failures > 2 else "MEDIUM",
                "details": f"Detected {dsp_failures} DSP sync failures affecting lifecycle stability.",
            }
        )

    drift_signals = [row for row in _as_list(drift.get("drifts")) if isinstance(row, dict)]
    if len(drift_signals) > 0:
        violations.append(
            {
                "code": "runtime_drift_linked_violation",
                "severity": "MEDIUM",
                "details": f"Runtime sequence drift contributed {len(drift_signals)} lifecycle risk signals.",
            }
        )

    high = len([row for row in violations if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium = len([row for row in violations if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    violation_score = round(
        max(0.0, min(1.0, 0.55 * min(1.0, high / 3.0) + 0.45 * min(1.0, medium / 5.0))),
        3,
    )

    classification = "PASS"
    if high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "lifecycle_violation_report",
        "target_id": str(target_id),
        "classification": classification,
        "violation_score": violation_score,
        "violations": violations,
        "summary": {
            "violation_count": len(violations),
            "high_severity_count": high,
            "medium_severity_count": medium,
            "pcm_stage_count": len(stages),
            "dapm_transition_count": len(dapm_transitions),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return LifecycleViolationReportResult(
        lifecycle_violation_report=payload,
        violation_score=violation_score,
        deterministic_fingerprint=fingerprint,
    )
