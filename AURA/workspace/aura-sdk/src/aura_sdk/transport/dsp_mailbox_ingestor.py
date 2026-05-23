"""DSP mailbox/runtime log ingestion (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DspMailboxIngestionResult:
    dsp_mailbox_ingestion: dict[str, Any]
    event_count: int
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def ingest_dsp_mailbox(payload: Mapping[str, Any]) -> DspMailboxIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    events: list[dict[str, Any]] = []
    lineage_counter = 0
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        lowered = text.lower()
        if "mailbox" in lowered or "dsp" in lowered:
            lineage_counter += 1
        events.append(
            {
                "event_id": f"dsp_mailbox:{idx}",
                "source": "dsp_mailbox_logs",
                "timestamp_ms": round(1000.0 + idx * 4.1, 3),
                "event_type": "dsp_mailbox_runtime",
                "dsp_lineage_id": f"dsp_lineage:{lineage_counter}" if lineage_counter > 0 else "",
                "message": text,
                "raw": text,
            }
        )

    payload_out = {
        "schema_version": "1.0",
        "source": "dsp_mailbox_logs",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "lineage_count": len(
                {
                    str(_as_dict(row).get("dsp_lineage_id", ""))
                    for row in events
                    if str(_as_dict(row).get("dsp_lineage_id", "")).strip()
                }
            ),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return DspMailboxIngestionResult(
        dsp_mailbox_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
