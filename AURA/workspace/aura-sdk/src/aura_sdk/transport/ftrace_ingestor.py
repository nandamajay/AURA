"""ftrace runtime evidence ingestion (read-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_TS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class FtraceIngestionResult:
    ftrace_ingestion: dict[str, Any]
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


def _timestamp_ms(text: str, fallback_ms: float) -> float:
    match = _TS_RE.search(text)
    if not match:
        return round(fallback_ms, 3)
    try:
        value = float(match.group(1))
        return round(value * 1000.0 if value < 10000 else value, 3)
    except (TypeError, ValueError):
        return round(fallback_ms, 3)


def _event_type(text: str) -> str:
    lowered = text.lower()
    if "irq" in lowered:
        return "irq_trace"
    if "dapm" in lowered:
        return "dapm_trace"
    if any(token in lowered for token in ("pcm", "aplay", "prepare", "start", "stop", "close")):
        return "pcm_trace"
    if "soundwire" in lowered or "swr" in lowered:
        return "soundwire_trace"
    return "ftrace_generic"


def ingest_ftrace(payload: Mapping[str, Any]) -> FtraceIngestionResult:
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
                    "event_id": f"ftrace:{idx}",
                    "source": "ftrace",
                    "timestamp_ms": round(float(item.get("timestamp_ms", 1000.0 + idx * 5.0) or 1000.0 + idx * 5.0), 3),
                    "event_type": str(item.get("event_type", _event_type(detail))),
                    "message": detail,
                    "raw": item,
                }
            )
    else:
        for idx, line in enumerate(lines, start=1):
            text = line.strip()
            events.append(
                {
                    "event_id": f"ftrace:{idx}",
                    "source": "ftrace",
                    "timestamp_ms": _timestamp_ms(text, 1000.0 + idx * 5.0),
                    "event_type": _event_type(text),
                    "message": text,
                    "raw": text,
                }
            )

    payload_out = {
        "schema_version": "1.0",
        "source": "ftrace",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "pcm_trace_count": len([row for row in events if str(_as_dict(row).get("event_type", "")) == "pcm_trace"]),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return FtraceIngestionResult(
        ftrace_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
