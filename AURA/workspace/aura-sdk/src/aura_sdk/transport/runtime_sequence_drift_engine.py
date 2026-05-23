"""Runtime sequence drift reconstruction and detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeSequenceDriftResult:
    runtime_sequence_drift: dict[str, Any]
    drift_score: float
    deterministic_fingerprint: str


_TS_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _line_timestamp_ms(line: str, fallback_ms: float) -> float:
    match = _TS_RE.search(line)
    if not match:
        return fallback_ms
    try:
        return round(float(match.group(1)) * 1000.0, 3)
    except (TypeError, ValueError):
        return fallback_ms


def _source_events(runtime_sources: Mapping[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seq = 0

    for source in sorted(runtime_sources.keys()):
        payload = _as_dict(runtime_sources.get(source))

        for row in _as_list(payload.get("events")):
            item = _as_dict(row)
            seq += 1
            events.append(
                {
                    "event_id": f"{source}:event:{seq}",
                    "domain": str(item.get("category", source)).strip() or source,
                    "source": str(source),
                    "timestamp_ms": round(float(item.get("timestamp_ms", 1000.0 + seq * 5.0) or 1000.0 + seq * 5.0), 3),
                    "label": str(item.get("detail", item.get("message", source))).strip() or source,
                }
            )

        for line in _as_list(payload.get("lines")):
            text = str(line)
            if not text.strip():
                continue
            seq += 1
            fallback = 1000.0 + seq * 4.0
            events.append(
                {
                    "event_id": f"{source}:line:{seq}",
                    "domain": str(source),
                    "source": str(source),
                    "timestamp_ms": _line_timestamp_ms(text, fallback),
                    "label": text.strip(),
                }
            )

    return sorted(events, key=lambda row: (float(_as_dict(row).get("timestamp_ms", 0.0)), str(_as_dict(row).get("event_id", ""))))


def reconstruct_runtime_sequence_drift(
    *,
    target_id: str,
    runtime_sources: Mapping[str, Any],
    pcm_lifecycle_trace: Mapping[str, Any],
    dapm_transition_trace: Mapping[str, Any],
    soundwire_runtime_graph: Mapping[str, Any],
    irq_timing_report: Mapping[str, Any],
    dsp_sync_report: Mapping[str, Any],
    expected_sequence: list[str] | None,
    evidence_references: list[str] | None,
) -> RuntimeSequenceDriftResult:
    pcm = _as_dict(pcm_lifecycle_trace)
    dapm = _as_dict(dapm_transition_trace)
    soundwire = _as_dict(soundwire_runtime_graph)
    irq = _as_dict(irq_timing_report)
    dsp = _as_dict(dsp_sync_report)

    timeline = _source_events(runtime_sources)

    for row in _as_list(pcm.get("transitions")):
        item = _as_dict(row)
        timeline.append(
            {
                "event_id": str(item.get("event_id", "pcm:unknown")),
                "domain": "pcm",
                "source": "pcm_lifecycle_trace",
                "timestamp_ms": round(float(item.get("timestamp_ms", 0.0) or 0.0), 3),
                "label": str(item.get("stage", "STATE")),
            }
        )

    for row in _as_list(dapm.get("transitions")):
        item = _as_dict(row)
        timeline.append(
            {
                "event_id": str(item.get("event_id", "dapm:unknown")),
                "domain": "dapm",
                "source": "dapm_transition_trace",
                "timestamp_ms": round(float(item.get("timestamp_ms", 0.0) or 0.0), 3),
                "label": str(item.get("transition", "STATE")),
            }
        )

    for row in _as_list(irq.get("ordered_irq_events")):
        item = _as_dict(row)
        timeline.append(
            {
                "event_id": str(item.get("event_id", "irq:unknown")),
                "domain": "irq",
                "source": "irq_timing_report",
                "timestamp_ms": round(float(item.get("timestamp_ms", 0.0) or 0.0), 3),
                "label": "IRQ",
            }
        )

    latencies = []
    for val in _as_list(dsp.get("pair_latencies_ms")):
        try:
            latencies.append(float(val))
        except (TypeError, ValueError):
            continue
    for idx, latency in enumerate(latencies, start=1):
        timeline.append(
            {
                "event_id": f"dsp:pair:{idx}",
                "domain": "dsp",
                "source": "dsp_sync_report",
                "timestamp_ms": round(1020.0 + idx * 9.0 + latency, 3),
                "label": "DSP_SYNC",
            }
        )

    timeline = sorted(
        timeline,
        key=lambda row: (float(_as_dict(row).get("timestamp_ms", 0.0)), str(_as_dict(row).get("event_id", ""))),
    )

    subsystem_activation_ordering: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    for row in timeline:
        item = _as_dict(row)
        domain = str(item.get("domain", "")).strip()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        subsystem_activation_ordering.append(
            {
                "domain": domain,
                "first_event_id": str(item.get("event_id", "")),
                "first_timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
            }
        )

    pcm_stages = [str(_as_dict(row).get("stage", "")).strip() for row in _as_list(pcm.get("transitions")) if str(_as_dict(row).get("stage", "")).strip()]

    fe_be_dependency_sequence = [
        {
            "sequence": index,
            "dependency": stage,
            "source": "pcm_lifecycle_trace",
        }
        for index, stage in enumerate(pcm_stages, start=1)
    ]

    dpcm_lifecycle_transitions = [
        {
            "sequence": index,
            "transition": stage,
            "classification": "STATE" if stage == "STATE" else "TRANSITION",
        }
        for index, stage in enumerate(pcm_stages, start=1)
    ]

    dsp_sync_timing = {
        "pair_latencies_ms": latencies,
        "sync_failure_count": int(_as_dict(dsp.get("summary")).get("sync_failure_count", 0) or 0),
    }

    soundwire_activation_graph = {
        "soundwire_event_count": int(_as_dict(soundwire.get("summary")).get("runtime_soundwire_events", 0) or 0),
        "soundwire_nodes": _as_list(soundwire.get("nodes")),
        "soundwire_edges": _as_list(soundwire.get("edges")),
    }

    irq_runtime_causality_chains: list[dict[str, Any]] = []
    irq_events = [_as_dict(row) for row in _as_list(irq.get("ordered_irq_events"))]
    for idx, row in enumerate(irq_events, start=1):
        cur_ts = float(row.get("timestamp_ms", 0.0) or 0.0)
        nearest = None
        nearest_delta = None
        for point in timeline:
            event_ts = float(_as_dict(point).get("timestamp_ms", 0.0) or 0.0)
            delta = abs(event_ts - cur_ts)
            if nearest_delta is None or delta < nearest_delta:
                nearest_delta = delta
                nearest = _as_dict(point)
        irq_runtime_causality_chains.append(
            {
                "chain_id": f"irq_chain:{idx}",
                "irq_event_id": str(row.get("event_id", f"irq:{idx}")),
                "nearest_runtime_event_id": str(_as_dict(nearest).get("event_id", "")),
                "delta_ms": round(float(nearest_delta or 0.0), 3),
                "causality_strength": "HIGH" if float(nearest_delta or 0.0) <= 15.0 else ("MEDIUM" if float(nearest_delta or 0.0) <= 40.0 else "LOW"),
            }
        )

    drifts: list[dict[str, Any]] = []
    expected = [str(item).strip().upper() for item in (expected_sequence or []) if str(item).strip()]
    observed_upper = [stage.upper() for stage in pcm_stages]
    missing_expected = [item for item in expected if item not in observed_upper]
    if missing_expected:
        drifts.append(
            {
                "type": "expected_sequence_drift",
                "severity": "HIGH" if len(missing_expected) > 2 else "MEDIUM",
                "details": f"Missing expected sequence stages: {', '.join(missing_expected)}",
            }
        )

    monotonic_violations = 0
    for idx in range(1, len(timeline)):
        prev_ts = float(_as_dict(timeline[idx - 1]).get("timestamp_ms", 0.0) or 0.0)
        cur_ts = float(_as_dict(timeline[idx]).get("timestamp_ms", 0.0) or 0.0)
        if cur_ts < prev_ts:
            monotonic_violations += 1
    if monotonic_violations > 0:
        drifts.append(
            {
                "type": "timeline_ordering_drift",
                "severity": "HIGH",
                "details": f"Detected {monotonic_violations} non-monotonic timeline transitions.",
            }
        )

    long_gaps = 0
    for idx in range(1, len(timeline)):
        prev_ts = float(_as_dict(timeline[idx - 1]).get("timestamp_ms", 0.0) or 0.0)
        cur_ts = float(_as_dict(timeline[idx]).get("timestamp_ms", 0.0) or 0.0)
        if (cur_ts - prev_ts) > 120.0:
            long_gaps += 1
    if long_gaps > 0:
        drifts.append(
            {
                "type": "timing_gap_drift",
                "severity": "MEDIUM",
                "details": f"Detected {long_gaps} long timeline gaps above 120ms.",
            }
        )

    drift_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * min(1.0, len(drifts) / 4.0)
                + 0.25 * min(1.0, len(missing_expected) / max(1, len(expected) or 1))
                + 0.20 * min(1.0, long_gaps / 5.0)
                + 0.20 * min(1.0, int(_as_dict(dsp_sync_timing).get("sync_failure_count", 0) or 0) / 4.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if any(str(_as_dict(item).get("severity", "")).upper() == "HIGH" for item in drifts):
        classification = "FAIL_CLOSED"
    elif drifts:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_sequence_drift",
        "target_id": str(target_id),
        "classification": classification,
        "drift_score": drift_score,
        "ordered_runtime_timeline": timeline,
        "subsystem_activation_ordering": subsystem_activation_ordering,
        "fe_be_dependency_sequence": fe_be_dependency_sequence,
        "dpcm_lifecycle_transitions": dpcm_lifecycle_transitions,
        "dsp_synchronization_timing": dsp_sync_timing,
        "soundwire_activation_graph": soundwire_activation_graph,
        "irq_runtime_causality_chains": irq_runtime_causality_chains,
        "drifts": drifts,
        "summary": {
            "timeline_event_count": len(timeline),
            "drift_count": len(drifts),
            "missing_expected_count": len(missing_expected),
            "long_gap_count": long_gaps,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimeSequenceDriftResult(
        runtime_sequence_drift=payload,
        drift_score=drift_score,
        deterministic_fingerprint=fingerprint,
    )
