"""Runtime trace ingestion cognition with deterministic normalization."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_REQUIRED_TRACE_SOURCES = [
    "dmesg",
    "ftrace",
    "trace_cmd",
    "tinymix",
    "procfs",
    "debugfs",
    "soundwire",
    "dsp_mailbox",
    "irq",
    "clock",
    "regulator",
]

_SOURCE_EVENT_TYPES = {
    "dmesg": "kernel_log",
    "ftrace": "ftrace",
    "trace_cmd": "trace_cmd",
    "tinymix": "tinymix_state",
    "procfs": "procfs_state",
    "debugfs": "debugfs_state",
    "soundwire": "soundwire_state",
    "dsp_mailbox": "dsp_mailbox",
    "irq": "irq_event",
    "clock": "clock_state",
    "regulator": "regulator_state",
}

_RUNTIME_SENSITIVE_TOKENS = (
    "irq",
    "interrupt",
    "dsp",
    "mailbox",
    "pcm",
    "dapm",
    "soundwire",
    "swr",
    "clock",
    "clk",
    "regulator",
    "pm_runtime",
    "runtime_pm",
    "suspend",
    "resume",
)

_TIMESTAMP_PATTERNS = [
    re.compile(r"^\[\s*(\d+(?:\.\d+)?)\]"),
    re.compile(r"^(\d+(?:\.\d+)?):"),
    re.compile(r"\bts=(\d+(?:\.\d+)?)\b", re.IGNORECASE),
]

_FE_RE = re.compile(r"\b(?:fe|frontend|multimedia)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)
_BE_RE = re.compile(r"\b(?:be|backend)\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)
_IRQ_RE = re.compile(r"\birq\s*[_:-]?\s*([0-9]+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RuntimeTraceIngestionResult:
    ingestion_bundle: dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _domain_for(message: str, source: str) -> str:
    text = f"{source} {message}".lower()
    if "pcm" in text or "dpcm" in text:
        return "PCM"
    if "dapm" in text or "widget" in text or "route" in text:
        return "DAPM"
    if "soundwire" in text or "swr" in text:
        return "SOUNDWIRE"
    if "dsp" in text or "mailbox" in text or "apr" in text:
        return "DSP"
    if "irq" in text or "interrupt" in text:
        return "IRQ"
    if "clock" in text or "clk" in text:
        return "CLOCK"
    if "regulator" in text or "vreg" in text:
        return "REGULATOR"
    if "tinymix" in text or "mixer" in text:
        return "MIXER"
    if "proc" in text or "debugfs" in text:
        return "KERNEL_STATE"
    return "GENERIC"


def _extract_timestamp_ms(line: str, *, sequence_idx: int, source_offset_ms: float) -> float:
    text = str(line).strip()
    for pattern in _TIMESTAMP_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        raw = _to_float(match.group(1), -1.0)
        if raw < 0:
            continue
        # treat small values as seconds, larger values as milliseconds
        if raw < 10000:
            return round(raw * 1000.0, 3)
        return round(raw, 3)
    return round(source_offset_ms + sequence_idx * 5.0, 3)


def _event_tags(message: str) -> list[str]:
    low = str(message).lower()
    return sorted({token for token in _RUNTIME_SENSITIVE_TOKENS if token in low})


def _extract_fe(message: str) -> str:
    match = _FE_RE.search(message)
    if not match:
        return ""
    return f"FE{match.group(1)}"


def _extract_be(message: str) -> str:
    match = _BE_RE.search(message)
    if not match:
        return ""
    return f"BE{match.group(1)}"


def _extract_irq(message: str) -> str:
    match = _IRQ_RE.search(message)
    if not match:
        return ""
    return f"IRQ{match.group(1)}"


def _payload_lines(payload: Mapping[str, Any]) -> list[str]:
    data = _as_dict(payload)
    if isinstance(data.get("events"), list):
        lines: list[str] = []
        for row in _as_list(data.get("events")):
            item = _as_dict(row)
            detail = str(item.get("detail", item.get("message", ""))).strip()
            ts = item.get("timestamp_ms")
            if detail:
                if ts is None:
                    lines.append(detail)
                else:
                    lines.append(f"{ts}: {detail}")
        return lines

    if isinstance(data.get("lines"), list):
        return [str(line).strip() for line in _as_list(data.get("lines")) if str(line).strip()]

    text = str(data.get("text", "")).strip()
    if text:
        return [line.strip() for line in text.splitlines() if line.strip()]
    return []


def build_mock_runtime_trace_payloads(*, transformed: bool = False) -> dict[str, dict[str, Any]]:
    """Qualcomm-style mocked trace payloads for offline runtime cognition."""
    pcm_start = "1.230: pcm start FE0->BE0"
    irq_line = "1.260: irq 21 handled"
    if transformed:
        pcm_start = "1.245: pcm start FE0->BE0"
        irq_line = "1.285: irq 21 handled delayed"

    return {
        "dmesg": {"lines": ["[1.200] ALSA machine init", "[1.205] dapm route FE0->BE0 enable"]},
        "ftrace": {
            "events": [
                {"timestamp_ms": 1210.0, "detail": "pcm open FE0"},
                {"timestamp_ms": 1220.0, "detail": pcm_start},
                {"timestamp_ms": 1310.0, "detail": "pcm stop FE0"},
            ]
        },
        "trace_cmd": {"lines": ["1.210: dapm widget RX_MACRO power_up", "1.240: dapm route enabled FE0->BE0"]},
        "tinymix": {"lines": ["WSA RX0 MUX=AIF1_PB", "SpkrLeft DAC Switch=on"]},
        "procfs": {"lines": ["00-00: MultiMedia1 Playback", "00-01: MultiMedia2 Capture"]},
        "debugfs": {"lines": ["asoc route FE0 -> BE0 active", "asoc widget RX_MACRO on"]},
        "soundwire": {"lines": ["1.250: soundwire link swr0:master0 active", "1.255: swr slave codec:wsa883x online"]},
        "dsp_mailbox": {"lines": ["1.252: dsp mailbox tx graph_open", "1.258: dsp mailbox rx graph_ack"]},
        "irq": {"lines": [irq_line, "1.300: irq 21 complete"]},
        "clock": {"lines": ["1.190: clock audio_core enabled", "1.215: clk mi2s0 enabled"]},
        "regulator": {"lines": ["1.180: regulator vdd_audio enabled", "1.182: regulator vdd_codec enabled"]},
    }


class RuntimeTraceIngestionEngine:
    """Ingest runtime evidence traces into a deterministic normalized schema."""

    def ingest(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        trace_payloads: Mapping[str, Any],
        evidence_references: list[str] | None,
    ) -> RuntimeTraceIngestionResult:
        payloads = _as_dict(trace_payloads)
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        raw_events: list[dict[str, Any]] = []
        source_summaries: list[dict[str, Any]] = []
        missing_sources: list[str] = []

        for source_idx, source in enumerate(_REQUIRED_TRACE_SOURCES, start=1):
            source_payload = _as_dict(payloads.get(source))
            lines = _payload_lines(source_payload)
            if not lines:
                missing_sources.append(source)

            source_offset_ms = 1000.0 + source_idx * 100.0
            for line_idx, line in enumerate(lines, start=1):
                ts_ms = _extract_timestamp_ms(line, sequence_idx=line_idx, source_offset_ms=source_offset_ms)
                msg = str(line).strip()
                entry = {
                    "event_id": f"{source}:{line_idx}",
                    "source": source,
                    "source_event_type": _SOURCE_EVENT_TYPES.get(source, "runtime_event"),
                    "timestamp_ms": ts_ms,
                    "message": msg,
                    "domain": _domain_for(msg, source),
                    "runtime_sensitive_tags": _event_tags(msg),
                    "runtime_sensitive": bool(_event_tags(msg)),
                    "fe_reference": _extract_fe(msg),
                    "be_reference": _extract_be(msg),
                    "irq_reference": _extract_irq(msg),
                    "lineage_id": str(lineage_id),
                }
                raw_events.append(entry)

            source_summaries.append(
                {
                    "source": source,
                    "event_count": len(lines),
                    "classification": "PRESENT" if lines else "MISSING",
                }
            )

        normalized_events = sorted(
            raw_events,
            key=lambda row: (
                _to_float(row.get("timestamp_ms"), 0.0),
                str(row.get("source", "")),
                str(row.get("event_id", "")),
            ),
        )
        for idx, row in enumerate(normalized_events, start=1):
            row["normalized_index"] = idx

        domain_counts: dict[str, int] = {}
        for row in normalized_events:
            domain = str(row.get("domain", "GENERIC"))
            domain_counts[domain] = int(domain_counts.get(domain, 0)) + 1

        fail_reasons: list[str] = []
        if missing_sources:
            fail_reasons.append("runtime_trace_source_incomplete")
        if not normalized_events:
            fail_reasons.append("runtime_trace_events_missing")

        classification = "FAIL_CLOSED" if fail_reasons else "PASS"
        summary = {
            "required_source_count": len(_REQUIRED_TRACE_SOURCES),
            "missing_source_count": len(missing_sources),
            "event_count": len(normalized_events),
            "runtime_sensitive_event_count": sum(1 for row in normalized_events if bool(row.get("runtime_sensitive", False))),
            "domain_counts": domain_counts,
        }

        bundle = {
            "schema_version": "1.0",
            "report_name": "runtime_trace_ingestion",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": fail_reasons,
            "summary": summary,
            "sources": source_summaries,
            "missing_sources": missing_sources,
            "normalized_event_schema": {
                "fields": [
                    "event_id",
                    "source",
                    "source_event_type",
                    "timestamp_ms",
                    "message",
                    "domain",
                    "runtime_sensitive_tags",
                    "runtime_sensitive",
                    "fe_reference",
                    "be_reference",
                    "irq_reference",
                    "normalized_index",
                    "lineage_id",
                ]
            },
            "events": normalized_events,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "replay_safe_persistence": True,
            "lineage_persistence": True,
            "evidence_references": evidence,
        }
        bundle["deterministic_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "fail_closed_reasons": fail_reasons,
                "events": [
                    {
                        "event_id": str(row.get("event_id", "")),
                        "source": str(row.get("source", "")),
                        "timestamp_ms": _to_float(row.get("timestamp_ms"), 0.0),
                        "domain": str(row.get("domain", "")),
                        "message": str(row.get("message", "")),
                    }
                    for row in normalized_events
                ],
            }
        )

        return RuntimeTraceIngestionResult(ingestion_bundle=bundle)


def save_runtime_trace_ingestion(path: str | Path, payload: Mapping[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")
