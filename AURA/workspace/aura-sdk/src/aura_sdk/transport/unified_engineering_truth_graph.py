"""Unified engineering truth graph construction for fusion layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class UnifiedEngineeringTruthGraphResult:
    unified_engineering_truth_graph: dict[str, Any]
    graph_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def build_unified_engineering_truth_graph(
    *,
    target_id: str,
    runtime_topology_correlation: Mapping[str, Any],
    lifecycle_causality_map: Mapping[str, Any],
    migration_runtime_alignment: Mapping[str, Any],
    patch_runtime_lineage: Mapping[str, Any],
    dsp_runtime_causality_report: Mapping[str, Any],
    regression_rootcause_report: Mapping[str, Any],
    cross_domain_reasoning: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> UnifiedEngineeringTruthGraphResult:
    topo = _as_dict(runtime_topology_correlation)
    lifecycle = _as_dict(lifecycle_causality_map)
    migration = _as_dict(migration_runtime_alignment)
    patch = _as_dict(patch_runtime_lineage)
    dsp = _as_dict(dsp_runtime_causality_report)
    rootcause = _as_dict(regression_rootcause_report)
    reasoning = _as_dict(cross_domain_reasoning)

    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": "runtime_topology_correlation", "kind": "fusion_domain"},
        {"id": "lifecycle_causality_map", "kind": "fusion_domain"},
        {"id": "migration_runtime_alignment", "kind": "fusion_domain"},
        {"id": "patch_runtime_lineage", "kind": "fusion_domain"},
        {"id": "dsp_runtime_causality_report", "kind": "fusion_domain"},
        {"id": "cross_domain_reasoning", "kind": "fusion_domain"},
        {"id": "regression_rootcause_report", "kind": "fusion_domain"},
    ]

    edges = [
        {"from": f"target:{target_id}", "to": "runtime_topology_correlation", "relation": "observed"},
        {"from": "runtime_topology_correlation", "to": "lifecycle_causality_map", "relation": "constrains"},
        {"from": "lifecycle_causality_map", "to": "dsp_runtime_causality_report", "relation": "informs"},
        {"from": "runtime_topology_correlation", "to": "migration_runtime_alignment", "relation": "aligns"},
        {"from": "migration_runtime_alignment", "to": "patch_runtime_lineage", "relation": "contextualizes"},
        {"from": "patch_runtime_lineage", "to": "cross_domain_reasoning", "relation": "feeds"},
        {"from": "dsp_runtime_causality_report", "to": "cross_domain_reasoning", "relation": "feeds"},
        {"from": "cross_domain_reasoning", "to": "regression_rootcause_report", "relation": "explains"},
    ]

    graph_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.18 * float(topo.get("correlation_score", 0.0) or 0.0)
                + 0.16 * float(lifecycle.get("causality_score", 0.0) or 0.0)
                + 0.16 * float(migration.get("alignment_score", 0.0) or 0.0)
                + 0.16 * float(patch.get("lineage_score", 0.0) or 0.0)
                + 0.14 * float(dsp.get("causality_score", 0.0) or 0.0)
                + 0.10 * float(reasoning.get("reasoning_score", 0.0) or 0.0)
                + 0.10 * float(rootcause.get("rootcause_confidence", 0.0) or 0.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if str(rootcause.get("classification", "")) == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
    elif graph_confidence < 0.70:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "graph_name": "unified_engineering_truth_graph",
        "target_id": str(target_id),
        "classification": classification,
        "graph_confidence": graph_confidence,
        "nodes": nodes,
        "edges": edges,
        "domain_fingerprints": {
            "runtime_topology_correlation": str(topo.get("deterministic_fingerprint", "")),
            "lifecycle_causality_map": str(lifecycle.get("deterministic_fingerprint", "")),
            "migration_runtime_alignment": str(migration.get("deterministic_fingerprint", "")),
            "patch_runtime_lineage": str(patch.get("deterministic_fingerprint", "")),
            "dsp_runtime_causality_report": str(dsp.get("deterministic_fingerprint", "")),
            "cross_domain_reasoning": str(reasoning.get("deterministic_fingerprint", "")),
            "regression_rootcause_report": str(rootcause.get("deterministic_fingerprint", "")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return UnifiedEngineeringTruthGraphResult(
        unified_engineering_truth_graph=payload,
        graph_confidence=graph_confidence,
        deterministic_fingerprint=fingerprint,
    )
