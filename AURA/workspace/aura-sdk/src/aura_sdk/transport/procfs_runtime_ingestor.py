"""ALSA procfs runtime state ingestion (read-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_PCM_RE = re.compile(r"(\d{1,2}-\d{1,2})")


@dataclass(frozen=True)
class ProcfsRuntimeIngestionResult:
    procfs_runtime_ingestion: dict[str, Any]
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


def ingest_procfs_runtime(payload: Mapping[str, Any]) -> ProcfsRuntimeIngestionResult:
    data = _as_dict(payload)
    lines = [str(item) for item in _as_list(data.get("lines")) if str(item).strip()]

    pcm_refs: list[str] = []
    events: list[dict[str, Any]] = []
    for idx, line in enumerate(lines, start=1):
        text = line.strip()
        pcm_match = _PCM_RE.search(text)
        if pcm_match:
            pcm_refs.append(pcm_match.group(1))
        events.append(
            {
                "event_id": f"procfs:{idx}",
                "source": "alsa_procfs_state",
                "timestamp_ms": round(1000.0 + idx * 4.0, 3),
                "event_type": "procfs_runtime_state",
                "message": text,
                "pcm_ref": pcm_match.group(1) if pcm_match else "",
                "raw": text,
            }
        )

    payload_out = {
        "schema_version": "1.0",
        "source": "alsa_procfs_state",
        "classification": "PRESENT" if events else "MISSING",
        "events": events,
        "summary": {
            "event_count": len(events),
            "pcm_ref_count": len([item for item in pcm_refs if item]),
            "unique_pcm_refs": sorted(set([item for item in pcm_refs if item])),
        },
        "read_only_ingestion": True,
    }
    fp = stable_fingerprint(payload_out)
    payload_out["deterministic_fingerprint"] = fp

    return ProcfsRuntimeIngestionResult(
        procfs_runtime_ingestion=payload_out,
        event_count=len(events),
        deterministic_fingerprint=fp,
    )
