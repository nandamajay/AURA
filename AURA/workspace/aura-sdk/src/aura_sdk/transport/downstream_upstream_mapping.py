"""Downstream to upstream semantic mapping engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DownstreamUpstreamMappingResult:
    mapping_graph: dict[str, Any]
    semantic_equivalence_confidence: float
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


def _semantic_vendor_constructs(semantic_cognition: Mapping[str, Any]) -> list[str]:
    semantic = _as_dict(semantic_cognition)
    adapters = _as_dict(semantic.get("adapters"))
    vendor_api = _as_dict(_as_dict(adapters.get("vendor_api")).get("semantic_driver"))

    constructs: list[str] = []
    for key in ("downstream_only_apis", "vendor_hooks", "wrapper_layers", "platform_assumptions"):
        constructs.extend(str(item) for item in _as_list(vendor_api.get(key)) if str(item).strip())

    dts = _as_dict(_as_dict(adapters.get("dts")).get("semantic_dts"))
    constructs.extend(str(item) for item in _as_list(dts.get("vendor_only_nodes")) if str(item).strip())

    out: list[str] = []
    seen: set[str] = set()
    for item in constructs:
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def build_downstream_upstream_mapping(
    *,
    target_id: str,
    semantic_cognition: Mapping[str, Any],
    topology_cognition: Mapping[str, Any],
    adapter_payload: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> DownstreamUpstreamMappingResult:
    adapter = _as_dict(adapter_payload)

    vendor_constructs = [str(item) for item in _as_list(adapter.get("vendor_constructs")) if str(item).strip()]
    if not vendor_constructs:
        vendor_constructs = _semantic_vendor_constructs(semantic_cognition)

    upstream_map = _as_dict(adapter.get("upstream_equivalents"))
    confidence_map = _as_dict(adapter.get("equivalence_confidence"))

    entries: list[dict[str, Any]] = []
    nodes = [{"id": f"target:{target_id}", "kind": "target"}]
    edges: list[dict[str, Any]] = []

    for construct in vendor_constructs:
        mapped = str(upstream_map.get(construct, "")).strip()
        if not mapped:
            mapped = "UNRESOLVED"
        base_conf = _to_float(confidence_map.get(construct, 0.0))
        if base_conf <= 0.0:
            base_conf = 0.9 if mapped != "UNRESOLVED" else 0.2

        semantic_score = _to_float(_as_dict(_as_dict(semantic_cognition).get("classification", {})).get("scores", {}).get("upstream_friendly", 0.5))
        topology_conf = _to_float(
            _as_dict(_as_dict(topology_cognition).get("confidence", {})).get(
                "topology_confidence",
                _as_dict(topology_cognition).get("topology_confidence", 0.5),
            )
        )
        adjusted_conf = round(max(0.0, min(1.0, 0.7 * base_conf + 0.2 * semantic_score + 0.1 * topology_conf)), 3)

        status = "EXACT" if mapped != "UNRESOLVED" and adjusted_conf >= 0.75 else ("PARTIAL" if mapped != "UNRESOLVED" else "UNMAPPED")

        entries.append(
            {
                "downstream_construct": construct,
                "upstream_equivalent": mapped,
                "equivalence_status": status,
                "equivalence_confidence": adjusted_conf,
            }
        )

        down_id = f"downstream:{construct}"
        up_id = f"upstream:{mapped}"
        nodes.append({"id": down_id, "kind": "downstream_construct"})
        nodes.append({"id": up_id, "kind": "upstream_construct"})
        edges.append({"from": f"target:{target_id}", "to": down_id, "relation": "uses"})
        edges.append({"from": down_id, "to": up_id, "relation": "maps_to", "status": status})

    if not entries:
        entries.append(
            {
                "downstream_construct": "NONE_DETECTED",
                "upstream_equivalent": "UNKNOWN",
                "equivalence_status": "UNMAPPED",
                "equivalence_confidence": 0.0,
            }
        )

    confidence = round(
        sum(_to_float(item.get("equivalence_confidence", 0.0)) for item in entries) / max(1, len(entries)),
        3,
    )

    graph = {
        "schema_version": "1.0",
        "graph_name": "downstream_upstream_mapping_graph",
        "target_id": target_id,
        "semantic_equivalence_confidence": confidence,
        "entries": entries,
        "nodes": nodes,
        "edges": edges,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "entries": entries,
            "confidence": confidence,
            "evidence_references": graph["evidence_references"],
        }
    )

    graph["deterministic_fingerprint"] = fingerprint

    return DownstreamUpstreamMappingResult(
        mapping_graph=graph,
        semantic_equivalence_confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
