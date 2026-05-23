"""Causal lineage graph generation for unified cognition correlation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class CausalLineageResult:
    causal_reasoning_graph: dict[str, Any]
    causal_strength: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_causal_lineage(
    *,
    target_id: str,
    dts_cognition: Mapping[str, Any],
    topology_cognition: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    pcm_activity: Mapping[str, Any],
    regression_history: list[Mapping[str, Any]],
    semantic_cognition: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
) -> CausalLineageResult:
    dts = _as_dict(dts_cognition)
    topology = _as_dict(topology_cognition)
    runtime = _as_dict(runtime_evidence)
    pcm = _as_dict(pcm_activity)
    semantic = _as_dict(semantic_cognition)
    replay = _as_dict(replay_traces)

    overlay_candidates = _as_list(_as_dict(dts.get("overlay_inheritance", dts)).get("overlay_candidates"))
    overlay_id = str(overlay_candidates[0]) if overlay_candidates else "overlay:unknown"

    topology_conf = _to_float(
        _as_dict(topology.get("confidence")).get("topology_confidence", topology.get("topology_confidence", 0.0))
    )
    routes = _as_list(_as_dict(topology.get("runtime_route_graph", topology)).get("runtime_paths"))
    if not routes:
        routes = _as_list(_as_dict(topology.get("procedural_route_memory")).get("validated_route_fingerprints"))
    route_id = f"route:{stable_fingerprint({'routes': routes})[:16]}"

    backend_chain = _as_list(_as_dict(topology.get("procedural_route_memory")).get("backend_activation_orderings"))
    backend_id = f"backend:{stable_fingerprint({'backend_chain': backend_chain})[:16]}"

    pcm_id = str(pcm.get("pcm_signature", pcm.get("signature_sha256", ""))).strip()
    if not pcm_id:
        pcm_id = stable_fingerprint(pcm)[:16]
    pcm_node = f"pcm:{pcm_id}"

    run_id = str(runtime.get("run_id", runtime.get("trace_id", "runtime_unknown"))).strip() or "runtime_unknown"
    runtime_node = f"runtime:{run_id}"

    regression_fingerprint = stable_fingerprint({"regression_history": list(regression_history)})[:16]
    regression_node = f"regression:{regression_fingerprint}"

    semantic_primary = str(_as_dict(semantic.get("classification")).get("primary_classification", "unknown"))
    replay_fingerprint = str(replay.get("deterministic_replay_fingerprint", "")).strip() or stable_fingerprint(replay)[:16]

    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": f"dts:{overlay_id}", "kind": "dts_node"},
        {"id": route_id, "kind": "route_graph"},
        {"id": backend_id, "kind": "backend_activation"},
        {"id": pcm_node, "kind": "pcm_behavior"},
        {"id": runtime_node, "kind": "runtime_evidence"},
        {"id": regression_node, "kind": "regression_confidence"},
        {"id": f"semantic:{semantic_primary}", "kind": "semantic_classification"},
        {"id": f"replay:{replay_fingerprint}", "kind": "replay_trace"},
    ]

    edges = [
        {"from": f"dts:{overlay_id}", "to": route_id, "relation": "defines_route_graph"},
        {"from": route_id, "to": backend_id, "relation": "activates_backend_chain"},
        {"from": backend_id, "to": pcm_node, "relation": "drives_pcm_behavior"},
        {"from": pcm_node, "to": runtime_node, "relation": "produces_runtime_evidence"},
        {"from": runtime_node, "to": regression_node, "relation": "updates_regression_confidence"},
        {"from": f"semantic:{semantic_primary}", "to": route_id, "relation": "constrains_route_interpretation"},
        {"from": f"replay:{replay_fingerprint}", "to": regression_node, "relation": "stabilizes_confidence"},
        {"from": f"target:{target_id}", "to": f"dts:{overlay_id}", "relation": "owns"},
    ]

    causal_steps_available = [
        bool(dts),
        bool(routes) or bool(topology),
        bool(backend_chain) or bool(topology),
        bool(pcm),
        bool(runtime),
        bool(regression_history),
    ]
    causal_strength = round(sum(1 for item in causal_steps_available if item) / len(causal_steps_available), 3)

    graph = {
        "schema_version": "1.0",
        "graph_name": "causal_reasoning_graph",
        "target_id": target_id,
        "causal_chain": [
            "dts_node",
            "route_graph",
            "backend_activation",
            "pcm_behavior",
            "runtime_evidence",
            "regression_confidence",
        ],
        "causal_strength": causal_strength,
        "topology_confidence": topology_conf,
        "semantic_primary_classification": semantic_primary,
        "nodes": nodes,
        "edges": edges,
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "nodes": nodes,
            "edges": edges,
            "causal_strength": causal_strength,
            "semantic_primary": semantic_primary,
        }
    )

    return CausalLineageResult(
        causal_reasoning_graph=graph,
        causal_strength=causal_strength,
        deterministic_fingerprint=fingerprint,
    )
