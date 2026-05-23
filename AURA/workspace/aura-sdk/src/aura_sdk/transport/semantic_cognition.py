"""Portable semantic kernel cognition engine.

Core runtime remains target-agnostic and consumes plugin semantic adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import (
    SemanticFingerprintResult,
    build_vendor_dependency_fingerprint,
    stable_fingerprint,
)


_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "fingerprint",
    "replay",
    "recommend",
]

_FORBIDDEN_ACTIONS = [
    "generate_final_patches",
    "rewrite_dts",
    "mutate_drivers",
    "fabricate_compatibility",
]


@dataclass(frozen=True)
class SemanticCognitionResult:
    semantic_bundle: dict[str, Any]


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


class SemanticCognitionEngine:
    """Plugin-driven semantic cognition with deterministic outputs."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _classify(
        self,
        *,
        dts_semantic: Mapping[str, Any],
        driver_semantic: Mapping[str, Any],
        replay_compatibility: str,
    ) -> dict[str, Any]:
        dts = _as_dict(dts_semantic)
        drv = _as_dict(driver_semantic)

        vendor_nodes = len(_as_list(dts.get("vendor_only_nodes")))
        reusable_nodes = len(_as_list(dts.get("reusable_upstream_nodes")))
        downstream_apis = len(_as_list(drv.get("downstream_only_apis")))
        vendor_hooks = len(_as_list(drv.get("vendor_hooks")))
        wrapper_layers = len(_as_list(drv.get("wrapper_layers")))
        codec_coupling = bool(drv.get("codec_coupling", False))
        duplicated_vendor_abstractions = bool(drv.get("duplicated_vendor_abstractions", False))

        scores = {
            "upstream_friendly": max(0.0, min(1.0, 0.75 + 0.04 * reusable_nodes - 0.12 * vendor_nodes - 0.10 * downstream_apis)),
            "vendor_coupled": max(0.0, min(1.0, 0.10 + 0.20 * vendor_nodes + 0.16 * downstream_apis + 0.12 * vendor_hooks)),
            "partially_portable": max(0.0, min(1.0, 0.25 + 0.05 * reusable_nodes + 0.08 * wrapper_layers - 0.06 * vendor_nodes)),
            "replay_sensitive": 1.0 if replay_compatibility == "INCOMPATIBLE" else (0.65 if replay_compatibility == "PARTIAL" else 0.15),
            "topology_sensitive": max(0.0, min(1.0, 0.20 + 0.12 * len(_as_list(dts.get("fe_be_route_topology"))) + (0.15 if codec_coupling else 0.0))),
            "governance_risky": max(
                0.0,
                min(
                    1.0,
                    0.05
                    + 0.17 * vendor_hooks
                    + 0.12 * downstream_apis
                    + (0.10 if duplicated_vendor_abstractions else 0.0)
                    + (0.10 if replay_compatibility == "INCOMPATIBLE" else 0.0),
                ),
            ),
        }
        scores = {key: round(value, 3) for key, value in scores.items()}

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        primary = ordered[0][0] if ordered else "partially_portable"

        return {
            "primary_classification": primary,
            "scores": scores,
            "ordered": [{"category": key, "score": value} for key, value in ordered],
        }

    def _build_graphs(
        self,
        *,
        target_id: str,
        dts_semantic: Mapping[str, Any],
        topology_semantic: Mapping[str, Any],
        driver_semantic: Mapping[str, Any],
        subsystem_descriptor: Mapping[str, Any],
        classification: Mapping[str, Any],
        vendor_fp: SemanticFingerprintResult,
    ) -> dict[str, Any]:
        dts = _as_dict(dts_semantic)
        topo = _as_dict(topology_semantic)
        drv = _as_dict(driver_semantic)
        subsys = _as_dict(subsystem_descriptor)

        downstream_graph = {
            "schema_version": "1.0",
            "graph_name": "downstream_semantic_graph",
            "target_id": target_id,
            "nodes": [
                {"id": f"target:{target_id}", "kind": "target"},
                {"id": "dts", "kind": "dts_semantics"},
                {"id": "driver", "kind": "driver_semantics"},
                {"id": "classification", "kind": "semantic_classification"},
            ],
            "edges": [
                {"from": f"target:{target_id}", "to": "dts", "relation": "described_by"},
                {"from": f"target:{target_id}", "to": "driver", "relation": "implemented_by"},
                {"from": "dts", "to": "classification", "relation": "influences"},
                {"from": "driver", "to": "classification", "relation": "influences"},
            ],
            "dts_semantic": dts,
            "driver_semantic": drv,
            "classification": classification,
        }

        subsystem_graph = {
            "schema_version": "1.0",
            "graph_name": "subsystem_mapping_graph",
            "target_id": target_id,
            "subsystems": subsys,
            "dependencies": {
                "codec_bindings": _as_list(dts.get("codec_bindings")),
                "fe_be_route_topology": _as_list(dts.get("fe_be_route_topology")),
            },
        }

        dts_topology_graph = {
            "schema_version": "1.0",
            "graph_name": "dts_topology_graph",
            "target_id": target_id,
            "overlay_hierarchy": _as_list(dts.get("overlay_hierarchy")),
            "fe_be_route_topology": _as_list(dts.get("fe_be_route_topology")),
            "codec_bindings": _as_list(dts.get("codec_bindings")),
            "dependencies": _as_dict(dts.get("dependencies")),
            "adapter_topology": topo,
        }

        semantic_confidence = {
            "schema_version": "1.0",
            "target_id": target_id,
            "semantic_confidence": round(
                max(0.0, min(1.0, 0.5 * float(_as_dict(classification).get("scores", {}).get("upstream_friendly", 0.0))
                                 + 0.5 * (1.0 - float(_as_dict(classification).get("scores", {}).get("governance_risky", 1.0)))),
                ),
                3,
            ),
            "classification": classification,
            "governance": {
                "allowed_actions": list(_ALLOWED_ACTIONS),
                "forbidden_actions": list(_FORBIDDEN_ACTIONS),
                "fail_closed": True,
            },
            "vendor_dependency_fingerprint": vendor_fp.fingerprint,
        }

        return {
            "downstream_semantic_graph": downstream_graph,
            "subsystem_mapping_graph": subsystem_graph,
            "dts_topology_graph": dts_topology_graph,
            "vendor_dependency_fingerprint": {
                "schema_version": "1.0",
                "target_id": target_id,
                "fingerprint": vendor_fp.fingerprint,
                "payload": vendor_fp.payload,
            },
            "semantic_confidence_report": semantic_confidence,
        }

    def analyze(
        self,
        *,
        target_id: str,
        entry_dts: str | None,
        driver_context: str,
        static_context: Mapping[str, Any] | None,
        replay_compatibility: str,
        evidence_references: list[str] | None,
        governance_state: Mapping[str, Any] | None,
        lineage_id: str,
    ) -> SemanticCognitionResult:
        plugin = self._plugins.load_plugin(target_id)

        dts_adapter = _as_dict(
            plugin.dts_adapter(
                {
                    "entry_dts": entry_dts,
                    "static_context": dict(static_context or {}),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_adapter(
                {
                    "entry_dts": entry_dts,
                    "static_context": dict(static_context or {}),
                }
            )
        )
        vendor_adapter = _as_dict(
            plugin.vendor_api_adapter(
                {
                    "driver_context": driver_context,
                }
            )
        )
        subsystem_adapter = _as_dict(
            plugin.subsystem_descriptor_provider(
                {
                    "static_context": dict(static_context or {}),
                }
            )
        )

        dts_semantic = _as_dict(dts_adapter.get("semantic_dts"))
        topology_semantic = _as_dict(topology_adapter.get("topology_graph"))
        driver_semantic = _as_dict(vendor_adapter.get("semantic_driver"))
        subsystem_descriptor = _as_dict(subsystem_adapter.get("descriptors"))

        classification = self._classify(
            dts_semantic=dts_semantic,
            driver_semantic=driver_semantic,
            replay_compatibility=replay_compatibility,
        )
        vendor_fp = build_vendor_dependency_fingerprint(
            target_id=target_id,
            dts_semantics=dts_semantic,
            driver_semantics=driver_semantic,
        )

        graphs = self._build_graphs(
            target_id=target_id,
            dts_semantic=dts_semantic,
            topology_semantic=topology_semantic,
            driver_semantic=driver_semantic,
            subsystem_descriptor=subsystem_descriptor,
            classification=classification,
            vendor_fp=vendor_fp,
        )

        bundle = {
            "schema_version": "1.0",
            "target_id": target_id,
            "lineage_id": str(lineage_id),
            "created_at": _utc_now_iso(),
            "governance_state": dict(governance_state or {}),
            "governance_boundaries": {
                "allowed": list(_ALLOWED_ACTIONS),
                "forbidden": list(_FORBIDDEN_ACTIONS),
                "fail_closed": True,
            },
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
            "adapters": {
                "dts": dts_adapter,
                "topology": topology_adapter,
                "vendor_api": vendor_adapter,
                "subsystem": subsystem_adapter,
            },
            "classification": classification,
            "replay_compatibility": replay_compatibility,
            "artifacts": graphs,
        }
        bundle["semantic_fingerprint"] = stable_fingerprint(bundle)
        return SemanticCognitionResult(semantic_bundle=bundle)
