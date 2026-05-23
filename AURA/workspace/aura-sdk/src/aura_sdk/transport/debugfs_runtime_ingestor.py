"""debugfs runtime state ingestion (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DebugfsRuntimeIngestionResult:
    debugfs_runtime_ingestion: dict[str, Any]
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


def ingest_debugfs_runtime(payload: Mapping[str, Any]) -> DebugfsRuntimeIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        events.append(
            {
                "event_id": f"debugfs:{idx}",
                "source": "debugfs_state",
                "timestamp_ms": round(1000.0 + idx * 4.5, 3),
                "event_type": "debugfs_runtime_state",
                "message": text,
                "raw": text,
            }
        )

    payload_out = {
        "schema_version": "1.0",
        "source": "debugfs_state",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "asoc_related_count": len([row for row in events if "asoc" in str(_as_dict(row).get("message", "")).lower()]),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return DebugfsRuntimeIngestionResult(
        debugfs_runtime_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
