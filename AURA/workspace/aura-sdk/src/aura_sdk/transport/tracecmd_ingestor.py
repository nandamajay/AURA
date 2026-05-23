"""trace-cmd/perf runtime evidence ingestion (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TracecmdIngestionResult:
    tracecmd_ingestion: dict[str, Any]
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


def _event_type(text: str) -> str:
    lowered = text.lower()
    if "perf" in lowered:
        return "perf_trace"
    if "irq" in lowered:
        return "irq_trace"
    if "soundwire" in lowered or "swr" in lowered:
        return "soundwire_trace"
    if "mailbox" in lowered or "dsp" in lowered:
        return "dsp_trace"
    if "dapm" in lowered:
        return "dapm_trace"
    if any(token in lowered for token in ("pcm", "dpcm", "fe", "be")):
        return "pcm_trace"
    return "tracecmd_generic"


def ingest_tracecmd(payload: Mapping[str, Any]) -> TracecmdIngestionResult:
    data = _as_dict(payload)
    raw_events = [row for row in _as_list(data.get("events")) if isinstance(row, dict)]
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    events: list[dict[str, Any]] = []
    if raw_events:
        for idx, row in enumerate(raw_events, start=1):
            item = _as_dict(row)
            detail = str(item.get("detail", item.get("message", ""))).strip()
            events.append(
                {
                    "event_id": f"tracecmd:{idx}",
                    "source": "trace_cmd",
                    "timestamp_ms": round(float(item.get("timestamp_ms", 1000.0 + idx * 4.0) or 1000.0 + idx * 4.0), 3),
                    "event_type": str(item.get("event_type", _event_type(detail))),
                    "message": detail,
                    "raw": item,
                }
            )
    else:
        for idx, line in enumerate(lines, start=1):
            events.append(
                {
                    "event_id": f"tracecmd:{idx}",
                    "source": "trace_cmd",
                    "timestamp_ms": round(1000.0 + idx * 4.0, 3),
                    "event_type": _event_type(line),
                    "message": line.strip(),
                    "raw": line,
                }
            )

    payload_out = {
        "schema_version": "1.0",
        "source": "trace_cmd",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "perf_event_count": len([row for row in events if str(_as_dict(row).get("event_type", "")) == "perf_trace"]),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return TracecmdIngestionResult(
        tracecmd_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
