"""dmesg runtime evidence ingestion (read-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_TS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")
_SEV_RE = re.compile(r"<([0-7])>")


@dataclass(frozen=True)
class DmesgIngestionResult:
    dmesg_ingestion: dict[str, Any]
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


def ingest_dmesg(payload: Mapping[str, Any]) -> DmesgIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        sev_match = _SEV_RE.search(text)
        severity = int(sev_match.group(1)) if sev_match else 6
        events.append(
            {
                "event_id": f"dmesg:{idx}",
                "source": "dmesg",
                "timestamp_ms": _timestamp_ms(text, 1000.0 + idx * 7.0),
                "severity": severity,
                "event_type": "kernel_log",
                "message": text,
                "raw": text,
            }
        )

    payload_out = {
        "schema_version": "1.0",
        "source": "dmesg",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "critical_count": len([row for row in events if int(_as_dict(row).get("severity", 6)) <= 3]),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return DmesgIngestionResult(
        dmesg_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
