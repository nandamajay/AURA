"""Lifecycle causality mapper across FE/BE, PCM, DAPM, IRQ and DSP domains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class LifecycleCausalityMapResult:
    lifecycle_causality_map: dict[str, Any]
    causality_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _timeline_entries(pcm_trace: Mapping[str, Any], dapm_trace: Mapping[str, Any], irq_report: Mapping[str, Any], dsp_report: Mapping[str, Any]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []

    for row in _as_list(_as_dict(pcm_trace).get("transitions")):
        item = _as_dict(row)
        timeline.append(
            {
                "domain": "pcm",
                "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                "label": str(item.get("stage", "")),
                "event_id": str(item.get("event_id", "")),
            }
        )

    for row in _as_list(_as_dict(dapm_trace).get("transitions")):
        item = _as_dict(row)
        timeline.append(
            {
                "domain": "dapm",
                "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                "label": str(item.get("transition", "")),
                "event_id": str(item.get("event_id", "")),
            }
        )

    for row in _as_list(_as_dict(irq_report).get("ordered_irq_events")):
        item = _as_dict(row)
        timeline.append(
            {
                "domain": "irq",
                "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                "label": "IRQ",
                "event_id": str(item.get("event_id", "")),
            }
        )

    # DSP report exposes latencies, derive pseudo-events for causality window.
    for index, latency in enumerate(_as_list(_as_dict(dsp_report).get("pair_latencies_ms")), start=1):
        try:
            latency_ms = float(latency)
        except (TypeError, ValueError):
            latency_ms = 0.0
        timeline.append(
            {
                "domain": "dsp",
                "timestamp_ms": round(1000.0 + index * 7.0 + latency_ms, 3),
                "label": "DSP_SYNC",
                "event_id": f"dsp_pair:{index}",
            }
        )

    return sorted(timeline, key=lambda row: (float(row.get("timestamp_ms", 0.0)), str(row.get("event_id", ""))))


def build_lifecycle_causality_map(
    *,
    target_id: str,
    pcm_lifecycle_trace: Mapping[str, Any],
    dapm_transition_trace: Mapping[str, Any],
    irq_timing_report: Mapping[str, Any],
    dsp_sync_report: Mapping[str, Any],
    runtime_topology_correlation: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> LifecycleCausalityMapResult:
    pcm = _as_dict(pcm_lifecycle_trace)
    dapm = _as_dict(dapm_transition_trace)
    irq = _as_dict(irq_timing_report)
    dsp = _as_dict(dsp_sync_report)
    topo = _as_dict(runtime_topology_correlation)

    timeline = _timeline_entries(pcm, dapm, irq, dsp)

    causal_edges: list[dict[str, Any]] = []
    for idx in range(1, len(timeline)):
        prev = _as_dict(timeline[idx - 1])
        cur = _as_dict(timeline[idx])
        delta = round(float(cur.get("timestamp_ms", 0.0) or 0.0) - float(prev.get("timestamp_ms", 0.0) or 0.0), 3)
        causal_edges.append(
            {
                "from": str(prev.get("event_id", "")),
                "to": str(cur.get("event_id", "")),
                "from_domain": str(prev.get("domain", "")),
                "to_domain": str(cur.get("domain", "")),
                "delta_ms": delta,
                "causal_strength": "HIGH" if delta <= 20.0 else ("MEDIUM" if delta <= 60.0 else "LOW"),
            }
        )

    high_edges = len([row for row in causal_edges if str(_as_dict(row).get("causal_strength", "")) == "HIGH"])
    low_edges = len([row for row in causal_edges if str(_as_dict(row).get("causal_strength", "")) == "LOW"])

    topo_score = float(topo.get("correlation_score", 0.0) or 0.0)
    causality_score = round(
        max(0.0, min(1.0, 0.45 * min(1.0, high_edges / max(1, len(causal_edges))) + 0.25 * topo_score + 0.30 * (1.0 - min(1.0, low_edges / max(1, len(causal_edges)))))),
        3,
    )

    classification = "PASS"
    if low_edges > max(3, len(causal_edges) // 3):
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "lifecycle_causality_map",
        "target_id": str(target_id),
        "classification": classification,
        "causality_score": causality_score,
        "timeline": timeline,
        "causal_edges": causal_edges,
        "summary": {
            "timeline_event_count": len(timeline),
            "causal_edge_count": len(causal_edges),
            "high_strength_edges": high_edges,
            "low_strength_edges": low_edges,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return LifecycleCausalityMapResult(
        lifecycle_causality_map=payload,
        causality_score=causality_score,
        deterministic_fingerprint=fingerprint,
    )
