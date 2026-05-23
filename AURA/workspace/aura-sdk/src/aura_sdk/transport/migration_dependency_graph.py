"""Migration dependency graph modeling for incremental orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationDependencyGraphResult:
    migration_dependency_graph: dict[str, Any]
    dependency_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def build_migration_dependency_graph(
    *,
    target_id: str,
    structural_artifacts: Mapping[str, Any],
    conversion_reasoning_artifacts: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> MigrationDependencyGraphResult:
    structural = _as_dict(structural_artifacts)
    reasoning = _as_dict(conversion_reasoning_artifacts)
    adapter = _as_dict(adapter_payload)

    topology = _as_dict(structural.get("topology_structure_graph"))
    callbacks = _as_dict(structural.get("callback_chain_graph"))
    upstream = _as_dict(structural.get("upstream_equivalence_trace"))

    lifecycle = _as_dict(reasoning.get("lifecycle_incompatibility_report"))
    vendor = _as_dict(reasoning.get("vendor_dependency_graph"))
    runtime = _as_dict(reasoning.get("runtime_portability_analysis"))

    unresolved_upstream = int(_as_dict(upstream.get("summary")).get("unresolved", 0) or 0)

    fe_count = len(_as_list(_as_dict(topology.get("fe_be_topology")).get("frontend_dais")))
    be_count = len(_as_list(_as_dict(topology.get("fe_be_topology")).get("backend_dais")))
    inferred_link_count = len(_as_list(_as_dict(topology.get("fe_be_topology")).get("inferred_links")))

    vendor_hooks = len(_as_list(_as_dict(vendor).get("unsupported_proprietary_hooks")))
    dsp_coupling = len(_as_list(_as_dict(vendor).get("dsp_coupling")))
    soundwire_gap_count = len(_as_list(_as_dict(vendor).get("soundwire_portability_gaps")))

    lifecycle_items = [
        row for row in _as_list(lifecycle.get("lifecycle_incompatibilities")) if isinstance(row, dict)
    ]
    lifecycle_mismatch_count = len(
        [
            row
            for row in lifecycle_items
            if str(row.get("type", "")) in {"component_lifecycle_mismatch", "ops_lifecycle_mismatch"}
        ]
    )
    api_drift_count = len([row for row in lifecycle_items if str(row.get("type", "")) == "api_drift"])

    callback_count = len(
        [
            row
            for row in _as_list(callbacks.get("nodes"))
            if isinstance(row, dict) and str(row.get("kind", "")) == "callback_function"
        ]
    )

    runtime_dep_count = len(_as_list(runtime.get("unsupported_runtime_dependencies")))

    dependency_items: list[dict[str, Any]] = [
        {
            "id": "fe_be_separation_staging",
            "depends_on": [],
            "risk": "HIGH" if inferred_link_count == 0 and fe_count > 0 and be_count > 0 else "MEDIUM",
            "signals": {
                "frontend_count": fe_count,
                "backend_count": be_count,
                "inferred_link_count": inferred_link_count,
            },
        },
        {
            "id": "dpcm_lifecycle_migration",
            "depends_on": ["fe_be_separation_staging"],
            "risk": "HIGH" if lifecycle_mismatch_count > 0 else "MEDIUM",
            "signals": {
                "lifecycle_mismatch_count": lifecycle_mismatch_count,
            },
        },
        {
            "id": "soundwire_abstraction_replacement",
            "depends_on": ["fe_be_separation_staging"],
            "risk": "HIGH" if soundwire_gap_count > 0 else "MEDIUM",
            "signals": {
                "soundwire_gap_count": soundwire_gap_count,
            },
        },
        {
            "id": "vendor_hook_elimination",
            "depends_on": ["dpcm_lifecycle_migration", "soundwire_abstraction_replacement"],
            "risk": "HIGH" if vendor_hooks > 0 else "MEDIUM",
            "signals": {
                "vendor_hook_count": vendor_hooks,
            },
        },
        {
            "id": "dsp_dependency_reduction",
            "depends_on": ["vendor_hook_elimination"],
            "risk": "HIGH" if dsp_coupling > 0 else "MEDIUM",
            "signals": {
                "dsp_coupling_count": dsp_coupling,
            },
        },
        {
            "id": "topology_portability_sequencing",
            "depends_on": ["fe_be_separation_staging", "dpcm_lifecycle_migration"],
            "risk": "MEDIUM",
            "signals": {
                "topology_classification": str(topology.get("classification", "UNKNOWN")),
            },
        },
        {
            "id": "callback_migration_ordering",
            "depends_on": ["dpcm_lifecycle_migration", "vendor_hook_elimination"],
            "risk": "HIGH" if callback_count > 0 and vendor_hooks > 0 else "MEDIUM",
            "signals": {
                "callback_count": callback_count,
            },
        },
        {
            "id": "component_registration_migration",
            "depends_on": ["callback_migration_ordering", "topology_portability_sequencing"],
            "risk": "HIGH" if api_drift_count > 0 else "MEDIUM",
            "signals": {
                "api_drift_count": api_drift_count,
            },
        },
        {
            "id": "runtime_capability_parity",
            "depends_on": ["component_registration_migration", "dsp_dependency_reduction"],
            "risk": "HIGH" if runtime_dep_count > 0 else "MEDIUM",
            "signals": {
                "runtime_dependency_count": runtime_dep_count,
            },
        },
        {
            "id": "upstream_api_compatibility_windows",
            "depends_on": ["component_registration_migration"],
            "risk": "HIGH" if unresolved_upstream > 0 else "MEDIUM",
            "signals": {
                "unresolved_upstream_constructs": unresolved_upstream,
            },
        },
    ]

    edges: list[dict[str, Any]] = []
    for item in dependency_items:
        node_id = str(item.get("id", "")).strip()
        if not node_id:
            continue
        for dep in [str(dep).strip() for dep in _as_list(item.get("depends_on")) if str(dep).strip()]:
            edges.append(
                {
                    "from": dep,
                    "to": node_id,
                    "relation": "dependency",
                }
            )

    high_risk_count = len([item for item in dependency_items if str(item.get("risk", "")).upper() == "HIGH"])
    dependency_confidence = round(max(0.0, min(1.0, 1.0 - 0.06 * high_risk_count)), 3)

    payload = {
        "schema_version": "1.0",
        "graph_name": "migration_dependency_graph",
        "target_id": str(target_id),
        "classification": "ADVISORY_ONLY",
        "dependency_confidence": dependency_confidence,
        "nodes": [
            {
                "id": str(item.get("id", "")),
                "risk": str(item.get("risk", "")),
                "depends_on": _dedupe_sorted([str(dep) for dep in _as_list(item.get("depends_on"))]),
                "signals": _as_dict(item.get("signals")),
            }
            for item in dependency_items
        ],
        "edges": sorted(edges, key=lambda row: (str(row.get("from", "")), str(row.get("to", "")), str(row.get("relation", "")))),
        "adapter_hints": {
            "runtime_conversion": _as_dict(adapter.get("runtime_conversion")),
            "topology_translation": _as_dict(adapter.get("topology_translation")),
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationDependencyGraphResult(
        migration_dependency_graph=payload,
        dependency_confidence=dependency_confidence,
        deterministic_fingerprint=fingerprint,
    )
