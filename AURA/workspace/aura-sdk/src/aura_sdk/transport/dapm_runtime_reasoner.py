"""DAPM runtime transition reasoning for offline runtime truth phase."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DapmTransitionTraceResult:
    dapm_transition_trace: dict[str, Any]
    dapm_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _transition_type(detail: str) -> str:
    lowered = str(detail).lower()
    if any(token in lowered for token in ("power_up", "power up", "enable", "on")):
        return "POWER_UP"
    if any(token in lowered for token in ("power_down", "power down", "disable", "off")):
        return "POWER_DOWN"
    if "route" in lowered:
        return "ROUTE"
    return "STATE"


def build_dapm_transition_trace(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> DapmTransitionTraceResult:
    ingestion = _as_dict(runtime_event_ingestion)
    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]

    dapm_events = [row for row in events if str(row.get("category", "")) == "dapm_transition"]

    transitions: list[dict[str, Any]] = []
    for index, event in enumerate(dapm_events):
        detail = str(event.get("detail", ""))
        transitions.append(
            {
                "sequence": index + 1,
                "event_id": str(event.get("event_id", "")),
                "timestamp_ms": float(event.get("timestamp_ms", 0.0) or 0.0),
                "transition": _transition_type(detail),
                "detail": detail,
            }
        )

    power_up_count = len([row for row in transitions if str(row.get("transition", "")) == "POWER_UP"])
    power_down_count = len([row for row in transitions if str(row.get("transition", "")) == "POWER_DOWN"])

    dapm_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.6 * min(1.0, len(transitions) / 8.0)
                + 0.2 * min(1.0, power_up_count / 3.0)
                + 0.2 * min(1.0, power_down_count / 3.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if len(transitions) == 0:
        classification = "FAIL_CLOSED"
    elif power_up_count == 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "dapm_transition_trace",
        "target_id": str(target_id),
        "classification": classification,
        "dapm_confidence": dapm_confidence,
        "transitions": transitions,
        "summary": {
            "transition_count": len(transitions),
            "power_up_count": power_up_count,
            "power_down_count": power_down_count,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return DapmTransitionTraceResult(
        dapm_transition_trace=payload,
        dapm_confidence=dapm_confidence,
        deterministic_fingerprint=fingerprint,
    )
