"""DSP synchronization reasoning for runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DspSyncReportResult:
    dsp_sync_report: dict[str, Any]
    dsp_sync_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def analyze_dsp_sync(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> DspSyncReportResult:
    ingestion = _as_dict(runtime_event_ingestion)
    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]

    dsp_events = [row for row in events if str(row.get("category", "")) == "dsp_sync"]

    tx_events = [row for row in dsp_events if "tx" in str(_as_dict(row).get("detail", "")).lower()]
    rx_events = [row for row in dsp_events if "rx" in str(_as_dict(row).get("detail", "")).lower() or "ack" in str(_as_dict(row).get("detail", "")).lower()]

    pair_count = min(len(tx_events), len(rx_events))
    latencies: list[float] = []
    for idx in range(pair_count):
        tx_ts = float(_as_dict(tx_events[idx]).get("timestamp_ms", 0.0) or 0.0)
        rx_ts = float(_as_dict(rx_events[idx]).get("timestamp_ms", 0.0) or 0.0)
        latencies.append(round(max(0.0, rx_ts - tx_ts), 3))

    avg_latency = round(sum(latencies) / len(latencies), 3) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    sync_failures = len([delta for delta in latencies if delta > 80.0]) + max(0, len(tx_events) - len(rx_events))

    dsp_sync_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.50 * min(1.0, len(dsp_events) / 10.0)
                + 0.30 * (1.0 - min(1.0, sync_failures / 5.0))
                + 0.20 * (1.0 - min(1.0, avg_latency / 120.0)),
            ),
        ),
        3,
    )

    classification = "PASS"
    if sync_failures > 2:
        classification = "FAIL_CLOSED"
    elif sync_failures > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "dsp_sync_report",
        "target_id": str(target_id),
        "classification": classification,
        "dsp_sync_confidence": dsp_sync_confidence,
        "summary": {
            "dsp_event_count": len(dsp_events),
            "tx_count": len(tx_events),
            "rx_count": len(rx_events),
            "paired_count": pair_count,
            "sync_failure_count": sync_failures,
            "avg_latency_ms": avg_latency,
            "max_latency_ms": round(max_latency, 3),
        },
        "pair_latencies_ms": latencies,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return DspSyncReportResult(
        dsp_sync_report=payload,
        dsp_sync_confidence=dsp_sync_confidence,
        deterministic_fingerprint=fingerprint,
    )
