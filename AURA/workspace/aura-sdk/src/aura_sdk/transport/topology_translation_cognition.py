"""Topology translation cognition for downstream to upstream conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TopologyTranslationResult:
    topology_translation_report: dict[str, Any]
    translation_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _normalize_route(route: str) -> str:
    text = str(route).strip().replace(" ", "")
    if not text:
        return "UNKNOWN"
    text = text.replace("->", "_")
    return text.upper()


def build_topology_translation_report(
    *,
    target_id: str,
    topology_cognition: Mapping[str, Any],
    dts_cognition: Mapping[str, Any],
    adapter_payload: Mapping[str, Any],
) -> TopologyTranslationResult:
    topology = _as_dict(topology_cognition)
    dts = _as_dict(dts_cognition)
    adapter = _as_dict(adapter_payload)

    fe_be_routes = [str(item) for item in _as_list(adapter.get("fe_be_routes")) if str(item).strip()]
    if not fe_be_routes:
        fe_be_routes = [str(item) for item in _as_list(dts.get("backend_frontend_mappings")) if str(item).strip()]

    runtime_paths = _as_list(_as_dict(topology.get("runtime_route_graph")).get("runtime_paths"))
    if not fe_be_routes and runtime_paths:
        fe_be_routes = [str(item) for item in runtime_paths if str(item).strip()]

    route_equivalence: list[dict[str, Any]] = []
    normalized_routes: list[str] = []

    for route in fe_be_routes:
        normalized = _normalize_route(route)
        normalized_routes.append(normalized)
        route_equivalence.append(
            {
                "downstream_route": route,
                "normalized_route": normalized,
                "equivalence": "MATCH" if normalized != "UNKNOWN" else "UNRESOLVED",
            }
        )

    vendor_abstractions = [str(item) for item in _as_list(adapter.get("vendor_topology_abstractions")) if str(item).strip()]
    if not vendor_abstractions:
        vendor_abstractions = [str(item) for item in _as_list(dts.get("qcom_audio_routing")) if str(item).strip()]

    pcm_nodes = [str(item) for item in _as_list(adapter.get("pcm_nodes")) if str(item).strip()]
    if not pcm_nodes:
        pcm_nodes = [str(item) for item in _as_list(_as_dict(topology.get("procedural_route_memory")).get("stable_pcm_fingerprints")) if str(item).strip()]

    dpcm_links = [str(item) for item in _as_list(adapter.get("dpcm_links")) if str(item).strip()]
    if not dpcm_links:
        dpcm_links = [str(item) for item in normalized_routes if str(item).strip()]

    portable_runtime_topology_model = {
        "model_type": "portable_runtime_topology",
        "target_id": target_id,
        "normalized_routes": normalized_routes,
        "pcm_nodes": pcm_nodes,
        "dpcm_links": dpcm_links,
        "vendor_abstractions": vendor_abstractions,
    }

    route_match = sum(1 for row in route_equivalence if str(row.get("equivalence", "")) == "MATCH")
    translation_confidence = round(route_match / max(1, len(route_equivalence)), 3)

    report = {
        "schema_version": "1.0",
        "report_name": "topology_translation_report",
        "target_id": target_id,
        "fe_be_route_equivalence": route_equivalence,
        "pcm_dpcm_graph_normalization": {
            "pcm_nodes": pcm_nodes,
            "dpcm_links": dpcm_links,
            "normalized": True,
        },
        "vendor_topology_abstraction": vendor_abstractions,
        "portable_runtime_topology_model": portable_runtime_topology_model,
        "translation_confidence": translation_confidence,
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "route_equivalence": route_equivalence,
            "portable_runtime_topology_model": portable_runtime_topology_model,
            "translation_confidence": translation_confidence,
        }
    )
    report["deterministic_fingerprint"] = fingerprint

    return TopologyTranslationResult(
        topology_translation_report=report,
        translation_confidence=translation_confidence,
        deterministic_fingerprint=fingerprint,
    )
