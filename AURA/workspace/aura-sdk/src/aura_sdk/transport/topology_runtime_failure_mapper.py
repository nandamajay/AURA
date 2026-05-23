"""Topology/runtime failure causality mapper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TopologyRuntimeCausalityResult:
    topology_runtime_causality: dict[str, Any]
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


def map_topology_runtime_failures(
    *,
    target_id: str,
    topology_runtime_graph: Mapping[str, Any],
    runtime_truth_graph: Mapping[str, Any],
    pcm_lifecycle_trace: Mapping[str, Any],
    dapm_transition_trace: Mapping[str, Any],
    soundwire_runtime_graph: Mapping[str, Any],
    runtime_sequence_drift: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> TopologyRuntimeCausalityResult:
    topology = _as_dict(topology_runtime_graph)
    runtime_graph = _as_dict(runtime_truth_graph)
    pcm = _as_dict(pcm_lifecycle_trace)
    dapm = _as_dict(dapm_transition_trace)
    soundwire = _as_dict(soundwire_runtime_graph)
    drift = _as_dict(runtime_sequence_drift)

    topology_edges = [row for row in _as_list(topology.get("edges")) if isinstance(row, dict)]
    runtime_edges = [row for row in _as_list(runtime_graph.get("edges")) if isinstance(row, dict)]

    fe_be_routes = _as_list(_as_dict(topology.get("normalized_portable_audio_graph")).get("fe_be_routes"))
    if not fe_be_routes:
        fe_be_routes = _as_list(_as_dict(topology.get("normalized_portable_audio_graph")).get("backend_dai"))

    pcm_transitions = [row for row in _as_list(pcm.get("transitions")) if isinstance(row, dict)]
    dapm_transitions = [row for row in _as_list(dapm.get("transitions")) if isinstance(row, dict)]

    inconsistencies: list[dict[str, Any]] = []
    if len(topology_edges) == 0:
        inconsistencies.append(
            {
                "code": "topology_edges_missing",
                "severity": "HIGH",
                "details": "No topology edges available for runtime causality mapping.",
            }
        )

    if len(runtime_edges) == 0:
        inconsistencies.append(
            {
                "code": "runtime_edges_missing",
                "severity": "HIGH",
                "details": "No runtime truth edges available for causality mapping.",
            }
        )

    if len(fe_be_routes) == 0:
        inconsistencies.append(
            {
                "code": "fe_be_routes_missing",
                "severity": "HIGH",
                "details": "No FE/BE route definitions found in topology graph.",
            }
        )

    if len(pcm_transitions) == 0:
        inconsistencies.append(
            {
                "code": "pcm_runtime_activation_missing",
                "severity": "MEDIUM",
                "details": "No PCM lifecycle transitions found for FE/BE dependency correlation.",
            }
        )

    if len(dapm_transitions) == 0:
        inconsistencies.append(
            {
                "code": "dapm_runtime_activation_missing",
                "severity": "MEDIUM",
                "details": "No DAPM transitions found for power-domain causality mapping.",
            }
        )

    soundwire_events = int(_as_dict(soundwire.get("summary")).get("runtime_soundwire_events", 0) or 0)
    if soundwire_events == 0:
        inconsistencies.append(
            {
                "code": "soundwire_activation_missing",
                "severity": "MEDIUM",
                "details": "No SoundWire runtime events available for topology activation graph.",
            }
        )

    drift_signals = [row for row in _as_list(drift.get("drifts")) if isinstance(row, dict)]
    if len(drift_signals) > 0:
        inconsistencies.append(
            {
                "code": "runtime_sequence_drift_present",
                "severity": "MEDIUM",
                "details": f"Detected {len(drift_signals)} runtime sequence drift signals.",
            }
        )

    route_activation_links: list[dict[str, Any]] = []
    pcm_count = max(1, len(pcm_transitions))
    for index, route in enumerate(fe_be_routes, start=1):
        route_activation_links.append(
            {
                "route_id": str(route),
                "activation_index": index,
                "runtime_activation_probability": round(min(1.0, pcm_count / max(1, index + 1)), 3),
                "status": "ACTIVE" if index <= pcm_count else "UNCONFIRMED",
            }
        )

    high = len([row for row in inconsistencies if str(_as_dict(row).get("severity", "")).upper() == "HIGH"])
    medium = len([row for row in inconsistencies if str(_as_dict(row).get("severity", "")).upper() == "MEDIUM"])

    causality_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * min(1.0, len(route_activation_links) / 6.0)
                + 0.20 * min(1.0, len(runtime_edges) / max(1, len(topology_edges)))
                + 0.20 * min(1.0, len(pcm_transitions) / 6.0)
                + 0.15 * min(1.0, soundwire_events / 4.0)
                + 0.10 * (1.0 - min(1.0, (high * 2 + medium) / 10.0)),
            ),
        ),
        3,
    )

    classification = "PASS"
    if high > 0:
        classification = "FAIL_CLOSED"
    elif medium > 0 or causality_score < 0.65:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "topology_runtime_causality",
        "target_id": str(target_id),
        "classification": classification,
        "causality_score": causality_score,
        "route_activation_links": route_activation_links,
        "inconsistencies": inconsistencies,
        "summary": {
            "topology_edge_count": len(topology_edges),
            "runtime_edge_count": len(runtime_edges),
            "fe_be_route_count": len(fe_be_routes),
            "pcm_transition_count": len(pcm_transitions),
            "dapm_transition_count": len(dapm_transitions),
            "soundwire_event_count": soundwire_events,
            "high_inconsistency_count": high,
            "medium_inconsistency_count": medium,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return TopologyRuntimeCausalityResult(
        topology_runtime_causality=payload,
        causality_score=causality_score,
        deterministic_fingerprint=fingerprint,
    )
