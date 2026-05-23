"""Offline-first runtime event ingestion for runtime truth cognition."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint

_REQUIRED_SOURCES = [
    "dmesg",
    "ftrace",
    "trace_cmd",
    "tinyalsa_dump",
    "procfs_sysfs",
    "soundwire_debugfs",
    "alsa_topology_runtime",
    "mailbox_trace",
    "dsp_response_log",
]


@dataclass(frozen=True)
class RuntimeEventIngestionResult:
    runtime_event_ingestion: dict[str, Any]
    ingestion_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _normalize_timestamp_ms(value: Any, fallback_ms: float) -> float:
    try:
        ts = float(value)
        if ts < 0:
            return fallback_ms
        # Accept seconds-like values and normalize to ms.
        if ts < 10_000:
            return round(ts * 1000.0, 3)
        return round(ts, 3)
    except (TypeError, ValueError):
        return round(fallback_ms, 3)


def _infer_category(source: str, line: str) -> str:
    lowered = f"{source} {line}".lower()
    if any(token in lowered for token in ("pcm", "aplay", "multimedia", "open", "prepare", "start", "drain", "close")):
        return "pcm_lifecycle"
    if any(token in lowered for token in ("dapm", "power", "widget", "route")):
        return "dapm_transition"
    if any(token in lowered for token in ("swr", "soundwire")):
        return "soundwire"
    if any(token in lowered for token in ("irq", "interrupt")):
        return "irq"
    if any(token in lowered for token in ("mailbox", "mbox", "apr", "adsp", "dsp")):
        return "dsp_sync"
    if any(token in lowered for token in ("suspend", "resume")):
        return "power_transition"
    return "runtime_generic"


def _line_to_event(source: str, line: str, index: int, base_ms: float) -> dict[str, Any]:
    text = str(line).strip()
    if not text:
        text = f"{source}:empty"

    # Common trace prefixes like: "123.456: ..."
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[:\]]", text)
    ts = _normalize_timestamp_ms(match.group(1), base_ms + index * 5.0) if match else round(base_ms + index * 5.0, 3)

    return {
        "event_id": f"{source}:{index}",
        "source": source,
        "timestamp_ms": ts,
        "category": _infer_category(source, text),
        "detail": text,
    }


def _synthetic_events(source: str, start_index: int, base_ms: float) -> list[dict[str, Any]]:
    templates = {
        "dmesg": ["deferred probe resolved", "ALSA card registered"],
        "ftrace": ["pcm_prepare", "pcm_start", "pcm_drain", "pcm_close"],
        "trace_cmd": ["dapm_widget_power_up", "route_enable", "dapm_widget_power_down"],
        "tinyalsa_dump": ["tinymix snapshot captured"],
        "procfs_sysfs": ["/proc/asound/pcm read", "/sys/kernel/debug/asoc dapm read"],
        "soundwire_debugfs": ["soundwire port active", "soundwire lane stable"],
        "alsa_topology_runtime": ["FE->BE path active", "DPCM route stable"],
        "mailbox_trace": ["mailbox tx cmd", "mailbox rx ack"],
        "dsp_response_log": ["dsp sync ack", "dsp response complete"],
    }
    lines = templates.get(source, [f"{source} synthetic event"])
    events: list[dict[str, Any]] = []
    for offset, line in enumerate(lines):
        idx = start_index + offset
        events.append(_line_to_event(source, line, idx, base_ms))
    return events


def ingest_runtime_events(
    *,
    target_id: str,
    source_payloads: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    archived_runtime_lineage: list[Mapping[str, Any]] | None,
    evidence_references: list[str] | None,
) -> RuntimeEventIngestionResult:
    payloads = _as_dict(source_payloads)
    adapter = _as_dict(adapter_payload)
    archived = [row for row in _as_list(archived_runtime_lineage or []) if isinstance(row, dict)]

    events: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = []

    index_cursor = 0
    synthetic_count = 0

    for source in _REQUIRED_SOURCES:
        src_payload = _as_dict(payloads.get(source))
        src_events = [row for row in _as_list(src_payload.get("events")) if isinstance(row, dict)]
        src_lines = [str(item) for item in _as_list(src_payload.get("lines")) if str(item).strip()]

        parsed: list[dict[str, Any]] = []
        if src_events:
            for row in src_events:
                parsed.append(
                    {
                        "event_id": f"{source}:{index_cursor}",
                        "source": source,
                        "timestamp_ms": _normalize_timestamp_ms(row.get("timestamp_ms", row.get("timestamp", 0.0)), 1000.0 + index_cursor * 5.0),
                        "category": str(row.get("category", _infer_category(source, str(row.get("detail", ""))))),
                        "detail": str(row.get("detail", "")),
                    }
                )
                index_cursor += 1
        elif src_lines:
            for line_index, line in enumerate(src_lines):
                parsed.append(_line_to_event(source, line, index_cursor + line_index, 1000.0))
            index_cursor += len(src_lines)
        else:
            synth = _synthetic_events(source, index_cursor, 1000.0)
            synthetic_count += len(synth)
            parsed.extend(synth)
            index_cursor += len(synth)

        events.extend(parsed)
        source_stats.append(
            {
                "source": source,
                "event_count": len(parsed),
                "synthetic": not bool(src_events or src_lines),
            }
        )

    events_sorted = sorted(events, key=lambda row: (float(row.get("timestamp_ms", 0.0)), str(row.get("event_id", ""))))

    required_coverage = len([row for row in source_stats if int(row.get("event_count", 0) or 0) > 0])
    synthetic_sources = len([row for row in source_stats if bool(row.get("synthetic", False))])

    ingestion_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.55 * (required_coverage / max(1, len(_REQUIRED_SOURCES)))
                + 0.25 * (1.0 - synthetic_sources / max(1, len(_REQUIRED_SOURCES)))
                + 0.20 * min(1.0, len(archived) / 15.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if required_coverage < len(_REQUIRED_SOURCES) // 2:
        classification = "FAIL_CLOSED"
    elif synthetic_sources > 0:
        classification = "ADVISORY_ONLY"

    ingestion = {
        "schema_version": "1.0",
        "report_name": "runtime_event_ingestion",
        "target_id": str(target_id),
        "classification": classification,
        "ingestion_confidence": ingestion_confidence,
        "required_sources": list(_REQUIRED_SOURCES),
        "source_stats": source_stats,
        "events": events_sorted,
        "summary": {
            "total_events": len(events_sorted),
            "synthetic_event_count": synthetic_count,
            "synthetic_source_count": synthetic_sources,
            "archived_lineage_count": len(archived),
        },
        "adapter_hints": {
            "provider": str(adapter.get("provider", "")),
            "fingerprint": str(adapter.get("fingerprint", "")),
            "expected_sequence": _as_list(adapter.get("expected_sequence")),
        },
        "offline_foundation_mode": True,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(ingestion)
    ingestion["deterministic_fingerprint"] = fingerprint

    return RuntimeEventIngestionResult(
        runtime_event_ingestion=ingestion,
        ingestion_confidence=ingestion_confidence,
        deterministic_fingerprint=fingerprint,
    )
