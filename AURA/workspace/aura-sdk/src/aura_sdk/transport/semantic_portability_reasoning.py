"""Portability reasoning using semantic entity and equivalence knowledge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticPortabilityReasoningResult:
    semantic_portability_rules: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_semantic_portability_rules(
    *,
    source_id: str,
    source_version: str,
    semantic_entity_graph: Mapping[str, Any],
    semantic_equivalence_map: Mapping[str, Any],
    semantic_relationship_map: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
) -> SemanticPortabilityReasoningResult:
    entities = _as_dict(_as_dict(semantic_entity_graph).get("entity_categories"))
    equivalence = [row for row in _as_list(_as_dict(semantic_equivalence_map).get("mappings")) if isinstance(row, dict)]
    relationships = [row for row in _as_list(_as_dict(semantic_relationship_map).get("edges")) if isinstance(row, dict)]
    adapter = _as_dict(adapter_payload)

    portability_blockers = [str(item) for item in _as_list(entities.get("known_portability_blockers")) if str(item).strip()]
    workaround_patterns = [str(item) for item in _as_list(entities.get("vendor_workaround_patterns")) if str(item).strip()]

    unresolved = [row for row in equivalence if str(_as_dict(row).get("equivalence_status", "")).upper() == "UNRESOLVED"]
    partial = [row for row in equivalence if str(_as_dict(row).get("equivalence_status", "")).upper() == "PARTIAL"]

    vendor_blockers = [
        {
            "code": "unresolved_downstream_equivalence",
            "severity": "HIGH",
            "evidence": [str(_as_dict(row).get("downstream_construct", "")) for row in unresolved[:50]],
            "classification": "blocked_unsafe",
        }
    ] if unresolved else []

    advisory_blockers = [
        {
            "code": "partial_equivalence_requires_manual_review",
            "severity": "MEDIUM",
            "evidence": [str(_as_dict(row).get("downstream_construct", "")) for row in partial[:50]],
            "classification": "advisory_only",
        }
    ] if partial else []

    known_blockers = [
        {
            "code": "known_portability_blocker_pattern",
            "severity": "MEDIUM",
            "evidence": portability_blockers[:80],
            "classification": "advisory_only",
        }
    ] if portability_blockers else []

    adapter_blockers = [
        {
            "code": "plugin_blocker_pattern",
            "severity": "MEDIUM",
            "evidence": [str(item) for item in _as_list(adapter.get("portability_blocker_patterns")) if str(item).strip()],
            "classification": "advisory_only",
        }
    ] if _as_list(adapter.get("portability_blocker_patterns")) else []

    blocked = vendor_blockers
    advisory = advisory_blockers + known_blockers + adapter_blockers

    replay_safe_transformations = [
        "normalize_entity_labels",
        "normalize_route_terms",
        "preserve_runtime_truth_precedence",
    ]
    advisory_transformations = [
        "manual_equivalence_validation",
        "manual_vendor_workaround_refactor",
        "manual_topology_route_confirmation",
    ]
    forbidden_transformations = [
        "autonomous_patch_generation",
        "autonomous_runtime_mutation",
        "autonomous_topology_mutation",
    ]

    score = 1.0 - (0.2 * len(blocked) + 0.06 * len(advisory))
    score = round(max(0.0, min(1.0, score)), 3)

    classification = "PASS"
    if blocked:
        classification = "FAIL_CLOSED"
    elif advisory:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "semantic_portability_rules",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "classification": classification,
        "portability_score": score,
        "relationship_density": len(relationships),
        "workaround_patterns": workaround_patterns,
        "rules": {
            "blocked_unsafe": blocked,
            "advisory_only": advisory,
            "replay_safe_transformations": replay_safe_transformations,
            "advisory_transformations": advisory_transformations,
            "forbidden_transformations": forbidden_transformations,
        },
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticPortabilityReasoningResult(
        semantic_portability_rules=payload,
        deterministic_fingerprint=fingerprint,
    )
