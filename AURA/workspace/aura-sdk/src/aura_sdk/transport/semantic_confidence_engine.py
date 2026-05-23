"""Confidence engine for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticConfidenceResult:
    semantic_confidence_report: dict[str, Any]
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


def build_semantic_confidence_report(
    *,
    source_id: str,
    source_version: str,
    semantic_entity_graph: Mapping[str, Any],
    semantic_relationship_map: Mapping[str, Any],
    semantic_portability_rules: Mapping[str, Any],
    semantic_equivalence_map: Mapping[str, Any],
    semantic_replay_compatibility: Mapping[str, Any],
    semantic_governance_boundary: Mapping[str, Any],
) -> SemanticConfidenceResult:
    entities = _as_dict(semantic_entity_graph)
    relationships = _as_dict(semantic_relationship_map)
    portability = _as_dict(semantic_portability_rules)
    equivalence = _as_dict(semantic_equivalence_map)
    replay = _as_dict(semantic_replay_compatibility)
    governance = _as_dict(semantic_governance_boundary)

    entity_total = int(entities.get("total_entities", 0))
    edge_total = int(relationships.get("edge_count", 0))

    entity_coverage = min(1.0, entity_total / 80.0)
    relationship_coverage = min(1.0, edge_total / 120.0)
    portability_score = _to_float(portability.get("portability_score", 0.0))
    equivalence_score = _to_float(equivalence.get("average_equivalence_confidence", 0.0))
    replay_score = 1.0 if str(replay.get("classification", "")) == "PASS" else 0.0
    governance_score = 1.0 if str(governance.get("classification", "")) == "PASS" else 0.0

    factors = {
        "entity_coverage": round(entity_coverage, 3),
        "relationship_coverage": round(relationship_coverage, 3),
        "portability_score": round(portability_score, 3),
        "equivalence_score": round(equivalence_score, 3),
        "replay_score": round(replay_score, 3),
        "governance_score": round(governance_score, 3),
    }

    overall = round(
        0.20 * factors["entity_coverage"]
        + 0.15 * factors["relationship_coverage"]
        + 0.20 * factors["portability_score"]
        + 0.20 * factors["equivalence_score"]
        + 0.15 * factors["replay_score"]
        + 0.10 * factors["governance_score"],
        3,
    )

    classification = "PASS"
    if factors["governance_score"] < 1.0 or factors["replay_score"] < 1.0:
        classification = "FAIL_CLOSED"
    elif overall < 0.55:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "semantic_confidence_report",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "classification": classification,
        "overall_confidence": overall,
        "factors": factors,
        "explanation": {
            "runtime_truth_precedence": "Runtime evidence remains primary truth; semantic layer contributes advisory confidence only.",
            "determinism_constraint": "Confidence is computed solely from deterministic artifacts and governance/replay checks.",
        },
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticConfidenceResult(
        semantic_confidence_report=payload,
        deterministic_fingerprint=fingerprint,
    )
