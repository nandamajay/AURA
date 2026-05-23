"""SoundWire runtime dump ingestion (read-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ENTITY_RE = re.compile(r"\b(swr\w*|soundwire\w*)\b", re.IGNORECASE)


@dataclass(frozen=True)
class SoundwireRuntimeIngestionResult:
    soundwire_runtime_ingestion: dict[str, Any]
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


def ingest_soundwire_runtime(payload: Mapping[str, Any]) -> SoundwireRuntimeIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    entities: list[str] = []
    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        entity = ""
        match = _ENTITY_RE.search(text)
        if match:
            entity = match.group(1)
            entities.append(entity)

        events.append(
            {
                "event_id": f"soundwire:{idx}",
                "source": "soundwire_runtime_dumps",
                "timestamp_ms": round(1000.0 + idx * 4.2, 3),
                "event_type": "soundwire_runtime",
                "entity": entity,
                "message": text,
                "raw": text,
            }
        )

    payload_out = {
        "schema_version": "1.0",
        "source": "soundwire_runtime_dumps",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "entity_count": len([item for item in entities if item]),
            "unique_entities": sorted(set([item for item in entities if item])),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return SoundwireRuntimeIngestionResult(
        soundwire_runtime_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
