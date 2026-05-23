"""PCM lifecycle tracking for runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PcmLifecycleTraceResult:
    pcm_lifecycle_trace: dict[str, Any]
    pcm_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _stage(detail: str) -> str:
    lowered = str(detail).lower()
    if "open" in lowered:
        return "OPEN"
    if "prepare" in lowered:
        return "PREPARE"
    if "start" in lowered:
        return "START"
    if "drain" in lowered or "stop" in lowered:
        return "DRAIN_STOP"
    if "close" in lowered:
        return "CLOSE"
    return "STATE"


def build_pcm_lifecycle_trace(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> PcmLifecycleTraceResult:
    ingestion = _as_dict(runtime_event_ingestion)
    runtime = _as_dict(runtime_evidence)
    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]

    pcm_events = [row for row in events if str(row.get("category", "")) == "pcm_lifecycle"]

    transitions: list[dict[str, Any]] = []
    for index, event in enumerate(pcm_events):
        detail = str(event.get("detail", ""))
        transitions.append(
            {
                "sequence": index + 1,
                "event_id": str(event.get("event_id", "")),
                "timestamp_ms": float(event.get("timestamp_ms", 0.0) or 0.0),
                "stage": _stage(detail),
                "detail": detail,
            }
        )

    required_stages = {"OPEN", "PREPARE", "START", "CLOSE"}
    observed_stages = {str(row.get("stage", "")) for row in transitions}
    missing_stages = sorted(required_stages.difference(observed_stages))

    runtime_seconds = float(runtime.get("playback_runtime_seconds", 0.0) or 0.0)
    expected_seconds = float(runtime.get("expected_runtime_seconds", 25.0) or 25.0)
    drift = abs(runtime_seconds - expected_seconds)

    pcm_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * (len(observed_stages) / max(1, len(required_stages)))
                + 0.30 * (1.0 - min(1.0, drift / 10.0))
                + 0.15 * min(1.0, len(transitions) / 10.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if "START" not in observed_stages or "CLOSE" not in observed_stages:
        classification = "FAIL_CLOSED"
    elif missing_stages:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "pcm_lifecycle_trace",
        "target_id": str(target_id),
        "classification": classification,
        "pcm_confidence": pcm_confidence,
        "transitions": transitions,
        "summary": {
            "transition_count": len(transitions),
            "observed_stages": sorted(observed_stages),
            "missing_stages": missing_stages,
            "runtime_seconds": round(runtime_seconds, 3),
            "expected_seconds": round(expected_seconds, 3),
            "runtime_drift_seconds": round(drift, 3),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PcmLifecycleTraceResult(
        pcm_lifecycle_trace=payload,
        pcm_confidence=pcm_confidence,
        deterministic_fingerprint=fingerprint,
    )
