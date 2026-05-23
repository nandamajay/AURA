"""Topology/runtime correlation for unified runtime evidence fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeTopologyCorrelationResult:
    runtime_topology_correlation: dict[str, Any]
    correlation_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def correlate_topology_runtime(
    *,
    target_id: str,
    topology_runtime_graph: Mapping[str, Any],
    runtime_truth_graph: Mapping[str, Any],
    pcm_lifecycle_trace: Mapping[str, Any],
    dapm_transition_trace: Mapping[str, Any],
    soundwire_runtime_graph: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RuntimeTopologyCorrelationResult:
    topology = _as_dict(topology_runtime_graph)
    runtime_graph = _as_dict(runtime_truth_graph)
    pcm = _as_dict(pcm_lifecycle_trace)
    dapm = _as_dict(dapm_transition_trace)
    soundwire = _as_dict(soundwire_runtime_graph)

    fe_be_routes = _as_list(_as_dict(topology.get("normalized_portable_audio_graph")).get("fe_be_routes"))
    topology_edges = len(_as_list(topology.get("edges")))
    runtime_edges = len(_as_list(runtime_graph.get("edges")))

    pcm_stages = {str(_as_dict(row).get("stage", "")) for row in _as_list(pcm.get("transitions"))}
    dapm_transitions = len(_as_list(dapm.get("transitions")))
    swr_events = int(_as_dict(soundwire.get("summary")).get("runtime_soundwire_events", 0) or 0)

    sequencing_alerts: list[dict[str, Any]] = []
    if "START" not in pcm_stages:
        sequencing_alerts.append(
            {
                "code": "pcm_start_missing",
                "severity": "HIGH",
                "details": "PCM lifecycle does not contain START stage.",
            }
        )
    if dapm_transitions == 0:
        sequencing_alerts.append(
            {
                "code": "dapm_transitions_missing",
                "severity": "MEDIUM",
                "details": "No DAPM transitions observed in runtime trace.",
            }
        )
    if swr_events == 0:
        sequencing_alerts.append(
            {
                "code": "soundwire_runtime_events_missing",
                "severity": "MEDIUM",
                "details": "No SoundWire runtime events observed.",
            }
        )

    route_coverage = min(1.0, len(fe_be_routes) / 6.0)
    graph_alignment = min(1.0, runtime_edges / max(1, topology_edges))

    penalty = 0.0
    for row in sequencing_alerts:
        severity = str(_as_dict(row).get("severity", "")).upper()
        penalty += 0.2 if severity == "HIGH" else 0.08

    correlation_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * route_coverage
                + 0.30 * graph_alignment
                + 0.20 * min(1.0, dapm_transitions / 5.0)
                + 0.15 * min(1.0, len(pcm_stages) / 4.0)
                - penalty,
            ),
        ),
        3,
    )

    classification = "PASS"
    if any(str(_as_dict(row).get("severity", "")).upper() == "HIGH" for row in sequencing_alerts):
        classification = "FAIL_CLOSED"
    elif sequencing_alerts:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_topology_correlation",
        "target_id": str(target_id),
        "classification": classification,
        "correlation_score": correlation_score,
        "summary": {
            "topology_edge_count": topology_edges,
            "runtime_edge_count": runtime_edges,
            "fe_be_route_count": len(fe_be_routes),
            "pcm_stage_count": len(pcm_stages),
            "dapm_transition_count": dapm_transitions,
            "soundwire_event_count": swr_events,
        },
        "sequencing_alerts": sequencing_alerts,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimeTopologyCorrelationResult(
        runtime_topology_correlation=payload,
        correlation_score=correlation_score,
        deterministic_fingerprint=fingerprint,
    )
