"""Topology reconstruction cognition from real downstream ingestion outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TopologyReconstructionResult:
    topology_runtime_graph: dict[str, Any]
    topology_reconstruction_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _normalize_route_name(name: str) -> str:
    text = str(name).strip().replace(" ", "_")
    if not text:
        return "UNKNOWN"
    return text.upper()


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def reconstruct_topology_runtime_graph(
    *,
    target_id: str,
    downstream_driver_graph: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
) -> TopologyReconstructionResult:
    graph = _as_dict(downstream_driver_graph)
    extracted = _as_dict(graph.get("extracted"))
    dai_links = _as_dict(extracted.get("dai_links"))
    adapter = _as_dict(adapter_payload)

    frontend = _dedupe([str(item) for item in _as_list(dai_links.get("frontend"))])
    backend = _dedupe([str(item) for item in _as_list(dai_links.get("backend"))])

    if not frontend:
        frontend = _dedupe([str(item) for item in _as_list(adapter.get("frontend_hints"))])
    if not backend:
        backend = _dedupe([str(item) for item in _as_list(adapter.get("backend_hints"))])

    inferred_links = [item for item in _as_list(dai_links.get("inferred_fe_be_links")) if isinstance(item, dict)]

    route_edges: list[dict[str, Any]] = []
    if inferred_links:
        for row in inferred_links:
            fe = str(_as_dict(row).get("frontend", "")).strip()
            candidates = [str(item) for item in _as_list(_as_dict(row).get("backend_candidates")) if str(item).strip()]
            confidence = _safe_float(_as_dict(row).get("confidence"), 0.5)
            for be in candidates:
                route_edges.append(
                    {
                        "from": f"fe:{fe}",
                        "to": f"be:{be}",
                        "relation": "dpcm_route",
                        "confidence": round(confidence, 3),
                    }
                )
    elif frontend and backend:
        for fe_name, be_name in zip(frontend, backend):
            route_edges.append(
                {
                    "from": f"fe:{fe_name}",
                    "to": f"be:{be_name}",
                    "relation": "dpcm_route",
                    "confidence": 0.55,
                }
            )

    routing_structures = [str(item) for item in _as_list(extracted.get("routing_structures")) if str(item).strip()]
    mixer_dependencies = [
        {
            "route_structure": item,
            "normalized_route": _normalize_route_name(item),
            "dependency_type": "dapm_route",
        }
        for item in routing_structures
    ]

    runtime = _as_dict(runtime_evidence)
    command_sequence = [str(item) for item in _as_list(runtime.get("command_sequence")) if str(item).strip()]
    adapter_sequence = [str(item) for item in _as_list(adapter.get("expected_activation_order")) if str(item).strip()]
    if not command_sequence and adapter_sequence:
        command_sequence = adapter_sequence

    normalized_routes = [
        {
            "frontend": edge["from"].replace("fe:", "", 1),
            "backend": edge["to"].replace("be:", "", 1),
            "normalized": _normalize_route_name(f"{edge['from']}->{edge['to']}"),
        }
        for edge in route_edges
    ]

    topology_confidence = 0.0
    topology_confidence += 0.35 if frontend else 0.0
    topology_confidence += 0.35 if backend else 0.0
    topology_confidence += 0.2 if route_edges else 0.0
    topology_confidence += 0.1 if command_sequence else 0.0
    topology_confidence = round(min(1.0, topology_confidence), 3)

    nodes = [{"id": f"target:{target_id}", "kind": "target"}]
    nodes.extend({"id": f"fe:{name}", "kind": "frontend_dai"} for name in frontend)
    nodes.extend({"id": f"be:{name}", "kind": "backend_dai"} for name in backend)

    payload = {
        "schema_version": "1.0",
        "graph_name": "topology_runtime_graph",
        "target_id": str(target_id),
        "classification": "PASS" if topology_confidence >= 0.55 else "ADVISORY_ONLY",
        "topology_reconstruction_confidence": topology_confidence,
        "nodes": nodes,
        "edges": route_edges,
        "normalized_portable_audio_graph": {
            "frontend_dai": frontend,
            "backend_dai": backend,
            "fe_be_routes": normalized_routes,
            "mixer_dependencies": mixer_dependencies,
            "runtime_activation_order": command_sequence,
        },
        "runtime_activation": {
            "playback_runtime_seconds": _safe_float(runtime.get("playback_runtime_seconds"), 0.0),
            "playback_completion": bool(runtime.get("playback_completion", False)),
            "process_success": bool(runtime.get("process_success", False)),
        },
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": str(target_id),
            "frontend": frontend,
            "backend": backend,
            "edges": route_edges,
            "mixer_dependencies": mixer_dependencies,
            "runtime_activation_order": command_sequence,
            "classification": payload["classification"],
        }
    )
    payload["deterministic_fingerprint"] = fingerprint

    return TopologyReconstructionResult(
        topology_runtime_graph=payload,
        topology_reconstruction_confidence=topology_confidence,
        deterministic_fingerprint=fingerprint,
    )
