"""Patch dependency graph modeling for governed upstream readiness planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PatchDependencyGraphResult:
    patch_dependency_graph: dict[str, Any]
    dependency_stability_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(values: list[Any]) -> list[str]:
    return sorted({str(item).strip() for item in values if str(item).strip()})


def build_patch_dependency_graph(
    *,
    target_id: str,
    downstream_driver_graph: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    subsystem_boundary_map: Mapping[str, Any],
    vendor_contamination_report: Mapping[str, Any],
    api_evolution_trace: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> PatchDependencyGraphResult:
    downstream = _as_dict(downstream_driver_graph)
    equivalence = _as_dict(upstream_equivalence_map)
    topology = _as_dict(topology_runtime_graph)
    boundaries = _as_dict(subsystem_boundary_map)
    contamination = _as_dict(vendor_contamination_report)
    api_trace = _as_dict(api_evolution_trace)

    unresolved = int(_as_dict(equivalence.get("summary", {})).get("unresolved", 0) or 0)
    blocked_vendor = int(_as_dict(contamination.get("summary", {})).get("downstream_only_api_count", 0) or 0)
    high_crossings = int(_as_dict(boundaries.get("summary", {})).get("high_risk_crossings", 0) or 0)
    be_count = len(_as_list(_as_dict(_as_dict(topology.get("normalized_portable_audio_graph")).get("backend_dai"))))
    api_drift_count = int(_as_dict(api_trace.get("summary", {})).get("api_drift_count", 0) or 0)

    nodes = [
        {
            "patch_id": "patch_01_subsystem_boundary_prep",
            "depends_on": [],
            "risk": "MEDIUM" if high_crossings > 0 else "LOW",
            "scope": ["subsystem_boundary"],
        },
        {
            "patch_id": "patch_02_topology_fe_be_normalization",
            "depends_on": ["patch_01_subsystem_boundary_prep"],
            "risk": "MEDIUM" if be_count > 4 else "LOW",
            "scope": ["fe_be_topology", "dpcm_links"],
        },
        {
            "patch_id": "patch_03_api_evolution_alignment",
            "depends_on": ["patch_01_subsystem_boundary_prep"],
            "risk": "HIGH" if api_drift_count > 0 else "MEDIUM",
            "scope": ["api_evolution", "registration_lifecycle"],
        },
        {
            "patch_id": "patch_04_vendor_contamination_isolation",
            "depends_on": ["patch_03_api_evolution_alignment"],
            "risk": "HIGH" if blocked_vendor > 0 else "MEDIUM",
            "scope": ["vendor_hooks", "downstream_only_apis"],
        },
        {
            "patch_id": "patch_05_soundwire_and_dsp_decoupling",
            "depends_on": [
                "patch_02_topology_fe_be_normalization",
                "patch_04_vendor_contamination_isolation",
            ],
            "risk": "HIGH" if unresolved > 0 else "MEDIUM",
            "scope": ["soundwire", "dsp_coupling"],
        },
        {
            "patch_id": "patch_06_runtime_correlation_guardrails",
            "depends_on": [
                "patch_02_topology_fe_be_normalization",
                "patch_03_api_evolution_alignment",
            ],
            "risk": "MEDIUM",
            "scope": ["runtime_correlation", "regression_guardrails"],
        },
        {
            "patch_id": "patch_07_upstream_equivalence_refinement",
            "depends_on": [
                "patch_04_vendor_contamination_isolation",
                "patch_05_soundwire_and_dsp_decoupling",
            ],
            "risk": "HIGH" if unresolved > 30 else "MEDIUM",
            "scope": ["upstream_equivalence"],
        },
        {
            "patch_id": "patch_08_bisectability_and_series_finalize",
            "depends_on": [
                "patch_06_runtime_correlation_guardrails",
                "patch_07_upstream_equivalence_refinement",
            ],
            "risk": "MEDIUM",
            "scope": ["bisectability", "maintainership_series"],
        },
    ]

    edges: list[dict[str, Any]] = []
    for row in nodes:
        patch_id = str(row.get("patch_id", "")).strip()
        for dep in _dedupe_sorted(_as_list(row.get("depends_on"))):
            edges.append({"from": dep, "to": patch_id, "relation": "depends_on"})

    high_risk_count = len([row for row in nodes if str(row.get("risk", "")) == "HIGH"])
    dependency_stability_score = round(max(0.0, min(1.0, 1.0 - 0.07 * high_risk_count - 0.01 * len(edges))), 3)

    classification = "PASS"
    if high_risk_count > 4:
        classification = "FAIL_CLOSED"
    elif high_risk_count > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "graph_name": "patch_dependency_graph",
        "target_id": str(target_id),
        "classification": classification,
        "dependency_stability_score": dependency_stability_score,
        "nodes": [
            {
                "patch_id": str(row.get("patch_id", "")),
                "depends_on": _dedupe_sorted(_as_list(row.get("depends_on"))),
                "risk": str(row.get("risk", "")),
                "scope": _dedupe_sorted(_as_list(row.get("scope"))),
            }
            for row in nodes
        ],
        "edges": sorted(
            edges,
            key=lambda row: (str(row.get("from", "")), str(row.get("to", ""))),
        ),
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "high_risk_count": high_risk_count,
            "unresolved_upstream_equivalence": unresolved,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PatchDependencyGraphResult(
        patch_dependency_graph=payload,
        dependency_stability_score=dependency_stability_score,
        deterministic_fingerprint=fingerprint,
    )
