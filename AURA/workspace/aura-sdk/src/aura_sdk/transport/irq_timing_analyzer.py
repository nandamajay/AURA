"""IRQ ordering and timing analysis for runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class IrqTimingReportResult:
    irq_timing_report: dict[str, Any]
    irq_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def analyze_irq_timing(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> IrqTimingReportResult:
    ingestion = _as_dict(runtime_event_ingestion)
    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]

    irq_events = [row for row in events if str(row.get("category", "")) == "irq"]

    ordered = sorted(irq_events, key=lambda row: float(row.get("timestamp_ms", 0.0) or 0.0))

    deltas: list[float] = []
    out_of_order = 0
    previous_ts = None
    for row in irq_events:
        ts = float(_as_dict(row).get("timestamp_ms", 0.0) or 0.0)
        if previous_ts is not None and ts < previous_ts:
            out_of_order += 1
        previous_ts = ts

    for idx in range(1, len(ordered)):
        prev = float(_as_dict(ordered[idx - 1]).get("timestamp_ms", 0.0) or 0.0)
        cur = float(_as_dict(ordered[idx]).get("timestamp_ms", 0.0) or 0.0)
        deltas.append(round(cur - prev, 3))

    max_delta = max(deltas) if deltas else 0.0
    avg_delta = round(sum(deltas) / len(deltas), 3) if deltas else 0.0
    latency_spikes = len([delta for delta in deltas if delta > 40.0])

    irq_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * min(1.0, len(irq_events) / 8.0)
                + 0.25 * (1.0 - min(1.0, out_of_order / 5.0))
                + 0.20 * (1.0 - min(1.0, latency_spikes / 4.0)),
            ),
        ),
        3,
    )

    classification = "PASS"
    if out_of_order > 0 and latency_spikes > 0:
        classification = "FAIL_CLOSED"
    elif out_of_order > 0 or latency_spikes > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "irq_timing_report",
        "target_id": str(target_id),
        "classification": classification,
        "irq_confidence": irq_confidence,
        "summary": {
            "irq_event_count": len(irq_events),
            "out_of_order_count": out_of_order,
            "latency_spike_count": latency_spikes,
            "max_delta_ms": round(max_delta, 3),
            "avg_delta_ms": avg_delta,
        },
        "ordered_irq_events": [
            {
                "event_id": str(row.get("event_id", "")),
                "timestamp_ms": float(row.get("timestamp_ms", 0.0) or 0.0),
                "detail": str(row.get("detail", "")),
            }
            for row in ordered
        ],
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return IrqTimingReportResult(
        irq_timing_report=payload,
        irq_confidence=irq_confidence,
        deterministic_fingerprint=fingerprint,
    )
