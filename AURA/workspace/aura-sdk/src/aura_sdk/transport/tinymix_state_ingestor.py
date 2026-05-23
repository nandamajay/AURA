"""tinyalsa/tinymix snapshot ingestion (read-only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TinymixStateIngestionResult:
    tinymix_state_ingestion: dict[str, Any]
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


def ingest_tinymix_state(payload: Mapping[str, Any]) -> TinymixStateIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    controls: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        events.append(
            {
                "event_id": f"tinymix:{idx}",
                "source": "tinyalsa_tinymix_snapshots",
                "timestamp_ms": round(1000.0 + idx * 3.0, 3),
                "event_type": "tinymix_snapshot",
                "message": text,
                "raw": text,
            }
        )
        if ":" in text:
            name, value = text.split(":", 1)
            controls.append({"control": name.strip(), "value": value.strip()})

    payload_out = {
        "schema_version": "1.0",
        "source": "tinyalsa_tinymix_snapshots",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "controls": controls,
        "summary": {
            "event_count": len(events),
            "control_count": len(controls),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return TinymixStateIngestionResult(
        tinymix_state_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
