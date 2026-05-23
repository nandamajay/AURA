"""Semantic ontology builder for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticOntologyResult:
    semantic_ontology: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_semantic_ontology(
    *,
    source_id: str,
    source_version: str,
    semantic_entity_graph: Mapping[str, Any],
    semantic_relationship_map: Mapping[str, Any],
) -> SemanticOntologyResult:
    entity_graph = _as_dict(semantic_entity_graph)
    relation_map = _as_dict(semantic_relationship_map)

    categories = _as_dict(entity_graph.get("entity_categories"))
    edges = [item for item in _as_list(relation_map.get("edges")) if isinstance(item, dict)]

    classes: list[dict[str, Any]] = []
    instances: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = [
        {"name": "contains_entity", "domain": "entity_category", "range": "semantic_entity"},
        {"name": "semantic_co_occurrence", "domain": "semantic_entity", "range": "semantic_entity"},
        {"name": "equivalent_to", "domain": "qcom_downstream_abstraction", "range": "upstream_abstraction"},
        {"name": "blocked_by", "domain": "migration_rule", "range": "portability_blocker"},
    ]

    for category, values in sorted(categories.items()):
        class_id = f"class:{category}"
        classes.append(
            {
                "id": class_id,
                "name": str(category),
                "kind": "entity_category",
            }
        )

        for value in sorted([str(item).strip() for item in _as_list(values) if str(item).strip()]):
            instances.append(
                {
                    "id": f"instance:{category}:{value}",
                    "name": value,
                    "class_id": class_id,
                }
            )

    ontology_edges: list[dict[str, Any]] = []
    for edge in edges:
        row = _as_dict(edge)
        ontology_edges.append(
            {
                "from": str(row.get("from", "")),
                "to": str(row.get("to", "")),
                "predicate": str(row.get("relation", "semantic_co_occurrence")),
                "confidence": float(row.get("confidence", 0.0)),
            }
        )

    rules = [
        {
            "rule_id": "R1_runtime_truth_precedence",
            "statement": "Runtime evidence is authoritative execution truth over semantic advisory knowledge.",
            "classification": "MANDATORY",
        },
        {
            "rule_id": "R2_no_runtime_mutation",
            "statement": "Semantic layer outputs are advisory only and cannot mutate runtime state.",
            "classification": "MANDATORY",
        },
        {
            "rule_id": "R3_fail_closed_governance",
            "statement": "Any governance violation in semantic advisory flow must fail closed.",
            "classification": "MANDATORY",
        },
        {
            "rule_id": "R4_plugin_isolation",
            "statement": "Target-specific semantic hints must be consumed via plugin adapters only.",
            "classification": "MANDATORY",
        },
    ]

    payload = {
        "schema_version": "1.0",
        "ontology_name": "kernel_semantic_ontology",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "classes": classes,
        "instances": instances,
        "predicates": predicates,
        "ontology_edges": ontology_edges,
        "governance_rules": rules,
        "classification": "PASS" if classes and instances else "ADVISORY_ONLY_SPARSE_ONTOLOGY",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticOntologyResult(
        semantic_ontology=payload,
        deterministic_fingerprint=fingerprint,
    )
