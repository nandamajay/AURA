"""Topology investigation question resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TopologyQuestionResolutionResult:
    topology_question_resolution: dict[str, Any]
    confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def resolve_topology_question(
    *,
    target_id: str,
    question: str,
    topology_artifacts: Mapping[str, Any],
    runtime_artifacts: Mapping[str, Any],
    incident_artifacts: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> TopologyQuestionResolutionResult:
    topology = _as_dict(topology_artifacts)
    runtime = _as_dict(runtime_artifacts)
    incident = _as_dict(incident_artifacts)
    lowered = str(question).strip().lower()

    topology_graph = _as_dict(topology.get("topology_runtime_graph", topology.get("runtime_route_graph")))
    topo_corr = _as_dict(topology.get("runtime_topology_correlation"))
    topo_fail = _as_dict(incident.get("topology_runtime_causality", runtime.get("topology_runtime_causality")))
    dts_graph = _as_dict(topology.get("dts_topology_graph"))

    inconsistencies = [row for row in _as_list(topo_fail.get("inconsistencies")) if isinstance(row, dict)]
    invalid_edges = [
        row
        for row in _as_list(topo_corr.get("route_mismatches", topo_corr.get("inconsistencies")))
        if isinstance(row, dict)
    ]
    fe_be_routes = _as_list(_as_dict(topology_graph.get("normalized_portable_audio_graph")).get("fe_be_routes"))

    evidence_sources = []
    if _as_dict(topology_graph):
        evidence_sources.append("artifact://topology_runtime_graph")
    if _as_dict(topo_corr):
        evidence_sources.append("artifact://runtime_topology_correlation")
    if _as_dict(topo_fail):
        evidence_sources.append("artifact://topology_runtime_causality")
    if _as_dict(dts_graph):
        evidence_sources.append("artifact://dts_topology_graph")

    answer = "Insufficient topology evidence to resolve the question."
    causality_chain: list[dict[str, Any]] = []

    if "invalid" in lowered or "topology path" in lowered or "route" in lowered:
        answer = (
            f"Topology path validity is degraded: runtime/topology inconsistency_count={len(inconsistencies)} "
            f"and route_mismatch_count={len(invalid_edges)}."
        )
        causality_chain = [
            {"node": "dts_topology_graph", "relation": "defines_expected_routes", "weight": 0.76},
            {"node": "topology_runtime_graph", "relation": "maps_runtime_routes", "weight": 0.82},
            {"node": "topology_runtime_causality", "relation": "reports_inconsistencies", "weight": 0.84},
        ]
    elif "contradict" in lowered or "topology expectations" in lowered:
        answer = (
            f"Runtime evidence contradicts topology expectations via {len(invalid_edges)} mismatch signal(s) "
            f"against {len(fe_be_routes)} FE/BE route definition(s)."
        )
        causality_chain = [
            {"node": "runtime_topology_correlation", "relation": "detects_contradiction", "weight": 0.83},
            {"node": "fe_be_route_model", "relation": "expected_reference", "weight": 0.74},
        ]
    else:
        answer = (
            f"Topology remains partially constrained with fe_be_routes={len(fe_be_routes)}, "
            f"runtime_mismatch={len(invalid_edges)}, inconsistency={len(inconsistencies)}."
        )
        causality_chain = [
            {"node": "topology_runtime_graph", "relation": "provides_route_context", "weight": 0.72},
            {"node": "runtime_topology_correlation", "relation": "validates_routes", "weight": 0.78},
        ]

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.43 * min(1.0, len(evidence_sources) / 4.0)
                + 0.25 * min(1.0, len(causality_chain) / 3.0)
                + 0.20 * min(1.0, (len(inconsistencies) + len(invalid_edges) + len(fe_be_routes)) / 10.0)
                + 0.12 * (1.0 if _as_dict(topo_corr) else 0.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not evidence_sources:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "insufficient_topology_evidence"
    elif confidence < 0.6:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "topology_evidence_confidence_below_threshold"

    payload = {
        "schema_version": "1.0",
        "resolver": "topology_question_resolver",
        "target_id": str(target_id),
        "question": str(question).strip(),
        "classification": classification,
        "answer": answer,
        "confidence_score": confidence,
        "evidence_sources": sorted(set(evidence_sources + [str(item) for item in (evidence_references or []) if str(item).strip()])),
        "causality_chain": causality_chain,
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return TopologyQuestionResolutionResult(
        topology_question_resolution=payload,
        confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
