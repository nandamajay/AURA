"""Ontology-style relationship graph builder for semantic entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticRelationshipGraphResult:
    semantic_relationship_map: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _entity_index(entity_graph: Mapping[str, Any]) -> list[dict[str, str]]:
    payload = _as_dict(entity_graph)
    categories = _as_dict(payload.get("entity_categories"))
    out: list[dict[str, str]] = []
    for category, values in sorted(categories.items()):
        for entity in sorted([str(item).strip() for item in _as_list(values) if str(item).strip()]):
            out.append({"category": str(category), "entity": entity, "entity_lower": entity.lower()})
    return out


def _section_texts(parsed_document: Mapping[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for section in _as_list(_as_dict(parsed_document).get("sections")):
        row = _as_dict(section)
        text = " ".join([str(row.get("heading", ""))] + [str(item) for item in _as_list(row.get("text_chunks"))]).strip()
        out.append(
            {
                "section_id": str(row.get("section_id", "")),
                "text": text,
                "text_lower": text.lower(),
            }
        )
    return out


def _relation_type(cat_a: str, cat_b: str) -> str:
    pair = {str(cat_a), str(cat_b)}
    if pair == {"fe_be_topology_concepts", "dpcm_concepts"}:
        return "fe_be_dpcm_semantic_link"
    if pair == {"dapm_graph_semantics", "asoc_entities"}:
        return "dapm_asoc_link"
    if pair == {"runtime_lifecycle_relationships", "pcm_lifecycle_semantics"}:
        return "runtime_pcm_lifecycle_link"
    if pair == {"qcom_downstream_abstractions", "upstream_equivalence_mappings"}:
        return "downstream_upstream_equivalence_link"
    if pair == {"known_portability_blockers", "migration_equivalence_rules"}:
        return "migration_blocker_rule_link"
    return "semantic_co_occurrence"


def build_semantic_relationship_map(
    *,
    source_id: str,
    source_version: str,
    semantic_entity_graph: Mapping[str, Any],
    parsed_document: Mapping[str, Any],
) -> SemanticRelationshipGraphResult:
    entities = _entity_index(semantic_entity_graph)
    sections = _section_texts(parsed_document)

    relationship_counter: dict[tuple[str, str], dict[str, Any]] = {}

    for section in sections:
        text_lower = str(section.get("text_lower", ""))
        section_id = str(section.get("section_id", ""))
        matched = [row for row in entities if row["entity_lower"] in text_lower]

        for i in range(len(matched)):
            for j in range(i + 1, len(matched)):
                left = matched[i]
                right = matched[j]
                key_tokens = sorted([f"{left['category']}::{left['entity']}", f"{right['category']}::{right['entity']}"])
                key = (key_tokens[0], key_tokens[1])

                if key not in relationship_counter:
                    relationship_counter[key] = {
                        "left": left,
                        "right": right,
                        "count": 0,
                        "sections": [],
                    }
                relationship_counter[key]["count"] += 1
                if section_id and section_id not in relationship_counter[key]["sections"]:
                    relationship_counter[key]["sections"].append(section_id)

    edges: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = [{"id": f"source:{source_id}", "kind": "knowledge_source"}]
    seen_nodes: set[str] = {f"source:{source_id}"}

    for _, row in sorted(relationship_counter.items(), key=lambda item: (item[0][0], item[0][1])):
        left = _as_dict(row.get("left"))
        right = _as_dict(row.get("right"))

        left_id = f"entity:{left.get('category', '')}:{left.get('entity', '')}"
        right_id = f"entity:{right.get('category', '')}:{right.get('entity', '')}"

        if left_id not in seen_nodes:
            nodes.append({"id": left_id, "kind": "semantic_entity", "category": str(left.get("category", "")), "name": str(left.get("entity", ""))})
            seen_nodes.add(left_id)
        if right_id not in seen_nodes:
            nodes.append({"id": right_id, "kind": "semantic_entity", "category": str(right.get("category", "")), "name": str(right.get("entity", ""))})
            seen_nodes.add(right_id)

        relation = _relation_type(str(left.get("category", "")), str(right.get("category", "")))
        edges.append(
            {
                "from": left_id,
                "to": right_id,
                "relation": relation,
                "co_occurrence_count": int(row.get("count", 0)),
                "sections": sorted([str(item) for item in _as_list(row.get("sections")) if str(item).strip()]),
                "confidence": round(min(1.0, 0.35 + 0.1 * int(row.get("count", 0))), 3),
            }
        )

    payload = {
        "schema_version": "1.0",
        "graph_name": "semantic_relationship_map",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "classification": "PASS" if edges else "ADVISORY_ONLY_SPARSE_RELATIONSHIPS",
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticRelationshipGraphResult(
        semantic_relationship_map=payload,
        deterministic_fingerprint=fingerprint,
    )
