"""Governed downstream-to-upstream translation intelligence layer.

Produces evidence-backed, deterministic translation artifacts with fail-closed
governance and replay-safe lineage persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class GovernedTranslationIntelligenceResult:
    translation_bundle: dict[str, Any]


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "ok",
            "pass",
            "success",
            "supported",
        }
    return False


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _governance_clean(governance_state: Mapping[str, Any]) -> tuple[bool, list[str]]:
    governance = _as_dict(governance_state)
    reasons: list[str] = []

    if not bool(governance.get("fail_closed_posture", True)):
        reasons.append("fail_closed_posture_disabled")

    for flag in (
        "autonomous_patching_allowed",
        "autonomous_topology_rewrite_allowed",
        "autonomous_runtime_mutation_allowed",
        "autonomous_upstream_generation_allowed",
    ):
        if _is_true(governance.get(flag, False)):
            reasons.append(f"governance_violation:{flag}")

    return (len(reasons) == 0, reasons)


def _semantic_constructs(semantic_entities: Mapping[str, Any]) -> set[str]:
    nodes = _as_list(_as_dict(semantic_entities).get("nodes"))
    out: set[str] = set()
    for row in nodes:
        item = _as_dict(row)
        label = str(item.get("label", item.get("id", ""))).strip().lower()
        if label:
            out.add(label)
    return out


def _driver_constructs(downstream_driver_graph: Mapping[str, Any]) -> set[str]:
    extracted = _as_dict(_as_dict(downstream_driver_graph).get("extracted"))
    out: set[str] = set()
    for key in (
        "ops_structures",
        "vendor_extensions",
        "proprietary_runtime_hooks",
        "routing_structures",
        "pcm_dpcm_paths",
    ):
        for item in _as_list(extracted.get(key)):
            value = str(item).strip().lower()
            if value:
                out.add(value)
    for group in (
        _as_dict(extracted.get("dependencies")),
        _as_dict(extracted.get("dai_links")),
    ):
        for values in group.values():
            for item in _as_list(values):
                value = str(item).strip().lower()
                if value:
                    out.add(value)
    return out


def _runtime_signals(runtime_truth_graph: Mapping[str, Any], runtime_portability_analysis: Mapping[str, Any]) -> dict[str, Any]:
    truth = _as_dict(runtime_truth_graph)
    portability = _as_dict(runtime_portability_analysis)

    blockers = [row for row in _as_list(portability.get("runtime_portability_blockers", portability.get("portability_blockers"))) if isinstance(row, dict)]
    deps = [str(item).strip().lower() for item in _as_list(portability.get("unsupported_runtime_dependencies", portability.get("downstream_only_runtime_dependencies"))) if str(item).strip()]

    return {
        "runtime_truth_classification": str(truth.get("classification", "UNKNOWN")),
        "runtime_truth_fail_closed": str(truth.get("classification", "")).upper() == "FAIL_CLOSED",
        "runtime_blockers": blockers,
        "unsupported_runtime_dependencies": deps,
    }


def _find_equivalent_for_construct(
    construct: str,
    mapping_entries: list[dict[str, Any]],
    upstream_equivalence_entries: list[dict[str, Any]],
) -> tuple[str, float, str]:
    key = str(construct).strip().lower()
    for row in mapping_entries:
        item = _as_dict(row)
        if str(item.get("downstream_construct", "")).strip().lower() == key:
            mapped = str(item.get("upstream_equivalent", "")).strip()
            confidence = _to_float(item.get("equivalence_confidence", item.get("confidence", 0.0)), 0.0)
            return mapped, confidence, "downstream_upstream_mapping_graph"

    for row in upstream_equivalence_entries:
        item = _as_dict(row)
        if str(item.get("downstream_construct", "")).strip().lower() == key:
            mapped = str(item.get("upstream_equivalent", item.get("upstream_construct", ""))).strip()
            confidence = _to_float(item.get("equivalence_confidence", item.get("confidence", 0.0)), 0.0)
            return mapped, confidence, "upstream_equivalence_map"

    return "UNRESOLVED", 0.0, "none"


def _evidence_score_for_construct(
    construct: str,
    semantic_set: set[str],
    driver_set: set[str],
    runtime_data: Mapping[str, Any],
    topology_translation: Mapping[str, Any],
) -> tuple[float, list[str]]:
    key = str(construct).strip().lower()
    references: list[str] = []
    score = 0.0

    if key in semantic_set:
        score += 0.35
        references.append("artifact://semantic_entity_graph")

    if key in driver_set:
        score += 0.35
        references.append("artifact://downstream_driver_graph")

    if any(token in key for token in ("pcm", "dapm", "dai", "route", "soundwire", "swr", "callback", "hook", "ops")):
        score += 0.10
        references.append("artifact://structural_graph")

    topology_routes = _as_list(_as_dict(topology_translation).get("fe_be_route_equivalence"))
    if topology_routes and any(token in key for token in ("dai", "route", "fe", "be", "pcm", "dapm")):
        score += 0.10
        references.append("artifact://topology_translation_report")

    if not _as_dict(runtime_data).get("runtime_truth_fail_closed", False):
        score += 0.10
        references.append("artifact://runtime_truth_graph")

    return round(min(1.0, score), 3), sorted(set(references))


def _build_api_replacement_map(
    *,
    target_id: str,
    mapping_graph: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    downstream_driver_graph: Mapping[str, Any],
    semantic_entity_graph: Mapping[str, Any],
    topology_translation_report: Mapping[str, Any],
    runtime_data: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping_entries = [row for row in _as_list(_as_dict(mapping_graph).get("entries")) if isinstance(row, dict)]
    upstream_entries = [row for row in _as_list(_as_dict(upstream_equivalence_map).get("entries")) if isinstance(row, dict)]

    semantic_set = _semantic_constructs(semantic_entity_graph)
    driver_set = _driver_constructs(downstream_driver_graph)

    constructs: set[str] = set()
    for row in mapping_entries:
        c = str(_as_dict(row).get("downstream_construct", "")).strip()
        if c:
            constructs.add(c)
    for row in upstream_entries:
        c = str(_as_dict(row).get("downstream_construct", "")).strip()
        if c:
            constructs.add(c)

    replacements: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for construct in sorted(constructs, key=lambda s: s.lower()):
        mapped, map_conf, map_source = _find_equivalent_for_construct(construct, mapping_entries, upstream_entries)
        evidence_score, evidence_sources = _evidence_score_for_construct(
            construct,
            semantic_set,
            driver_set,
            runtime_data,
            topology_translation_report,
        )

        unsupported_runtime = any(dep in str(construct).lower() for dep in _as_list(runtime_data.get("unsupported_runtime_dependencies")))
        runtime_incompatible = bool(runtime_data.get("runtime_truth_fail_closed", False) and unsupported_runtime)

        if not mapped or mapped.upper() == "UNRESOLVED":
            unsupported.append(
                {
                    "construct": construct,
                    "reason": "no_upstream_equivalent",
                    "mapping_source": map_source,
                    "evidence_score": evidence_score,
                    "evidence_sources": evidence_sources,
                }
            )
            continue

        if evidence_score < 0.55:
            unsupported.append(
                {
                    "construct": construct,
                    "reason": "insufficient_evidence_backing",
                    "mapping_source": map_source,
                    "mapped_candidate": mapped,
                    "evidence_score": evidence_score,
                    "evidence_sources": evidence_sources,
                }
            )
            continue

        if runtime_incompatible:
            unsupported.append(
                {
                    "construct": construct,
                    "reason": "runtime_incompatible_dependency",
                    "mapping_source": map_source,
                    "mapped_candidate": mapped,
                    "evidence_score": evidence_score,
                    "evidence_sources": evidence_sources,
                }
            )
            continue

        confidence = round(max(0.0, min(1.0, 0.55 * map_conf + 0.45 * evidence_score)), 3)
        replacements.append(
            {
                "downstream_construct": construct,
                "upstream_replacement": mapped,
                "mapping_source": map_source,
                "mapping_confidence": round(map_conf, 3),
                "evidence_score": evidence_score,
                "runtime_safe": not bool(runtime_data.get("runtime_truth_fail_closed", False)),
                "transformation_class": "runtime_safe_api_substitution" if not bool(runtime_data.get("runtime_truth_fail_closed", False)) else "advisory_only_substitution",
                "candidate_confidence": confidence,
                "evidence_sources": sorted(set(evidence_sources + evidence_references)),
            }
        )

    api_map = {
        "schema_version": "1.0",
        "report_name": "api_replacement_map",
        "target_id": str(target_id),
        "classification": "PASS" if replacements else "FAIL_CLOSED",
        "replacements": sorted(replacements, key=lambda row: (-float(_as_dict(row).get("candidate_confidence", 0.0)), str(_as_dict(row).get("downstream_construct", "")))),
        "summary": {
            "replacement_count": len(replacements),
            "mean_candidate_confidence": round(
                sum(_to_float(_as_dict(row).get("candidate_confidence", 0.0)) for row in replacements) / max(1, len(replacements)),
                3,
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    api_map["deterministic_fingerprint"] = stable_fingerprint(api_map)

    unsupported_payload = {
        "schema_version": "1.0",
        "report_name": "unsupported_vendor_constructs",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if unsupported else "PASS",
        "unsupported": sorted(unsupported, key=lambda row: str(_as_dict(row).get("construct", "")).lower()),
        "summary": {
            "unsupported_count": len(unsupported),
            "no_equivalent_count": len([row for row in unsupported if str(_as_dict(row).get("reason", "")) == "no_upstream_equivalent"]),
            "insufficient_evidence_count": len([row for row in unsupported if str(_as_dict(row).get("reason", "")) == "insufficient_evidence_backing"]),
            "runtime_incompatible_count": len([row for row in unsupported if str(_as_dict(row).get("reason", "")) == "runtime_incompatible_dependency"]),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    unsupported_payload["deterministic_fingerprint"] = stable_fingerprint(unsupported_payload)

    return api_map, unsupported_payload


def _build_lifecycle_translation_graph(
    *,
    target_id: str,
    api_replacement_map: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    runtime_artifacts: Mapping[str, Any],
    topology_translation_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]
    upstream_entries = [row for row in _as_list(_as_dict(upstream_equivalence_map).get("entries")) if isinstance(row, dict)]

    runtime = _as_dict(runtime_artifacts)
    pcm_trace = _as_dict(runtime.get("pcm_lifecycle_trace", runtime.get("pcm_runtime_state")))

    observed_states = []
    if _as_list(_as_dict(pcm_trace).get("transitions")):
        for row in _as_list(_as_dict(pcm_trace).get("transitions")):
            stage = str(_as_dict(row).get("stage", "")).strip().upper()
            if stage:
                observed_states.append(stage)
    if _as_list(_as_dict(pcm_trace).get("states")):
        for row in _as_list(_as_dict(pcm_trace).get("states")):
            stage = str(_as_dict(row).get("dpcm_lifecycle_state", "")).strip().upper()
            if stage and stage != "UNKNOWN":
                observed_states.append(stage)

    if not observed_states:
        observed_states = ["OPEN", "PREPARE", "START", "DRAIN", "STOP", "CLOSE"]

    states = []
    seen_states = set()
    for state in observed_states:
        if state not in seen_states:
            seen_states.add(state)
            states.append(state)

    def find_stage_mapping(stage: str) -> tuple[str, float, str]:
        stage_l = stage.lower()
        for row in replacements:
            item = _as_dict(row)
            source = str(item.get("downstream_construct", "")).lower()
            if stage_l in source:
                return str(item.get("upstream_replacement", "")), _to_float(item.get("candidate_confidence", 0.0)), "api_replacement_map"
        for row in upstream_entries:
            item = _as_dict(row)
            source = str(item.get("downstream_construct", "")).lower()
            if stage_l in source:
                return (
                    str(item.get("upstream_equivalent", item.get("upstream_construct", ""))),
                    _to_float(item.get("equivalence_confidence", item.get("confidence", 0.0)), 0.0),
                    "upstream_equivalence_map",
                )
        return "UNRESOLVED", 0.0, "none"

    nodes = [{"id": f"target:{target_id}", "kind": "target"}]
    edges: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for idx, state in enumerate(states, start=1):
        mapped, conf, source = find_stage_mapping(state)
        node_state = f"lifecycle:{state}"
        node_up = f"upstream:{mapped}"
        nodes.append({"id": node_state, "kind": "lifecycle_state"})
        nodes.append({"id": node_up, "kind": "upstream_lifecycle_api"})
        edges.append({
            "from": node_state,
            "to": node_up,
            "relation": "translated_to",
            "mapping_source": source,
            "confidence": round(conf, 3),
        })
        if mapped == "UNRESOLVED" or conf < 0.55:
            unresolved.append(state)
        if idx > 1:
            prev = states[idx - 2]
            edges.append({"from": f"lifecycle:{prev}", "to": node_state, "relation": "runtime_sequence"})

    route_eq_count = len(_as_list(_as_dict(topology_translation_report).get("fe_be_route_equivalence")))

    payload = {
        "schema_version": "1.0",
        "graph_name": "lifecycle_translation_graph",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if unresolved else "PASS",
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "observed_lifecycle_states": states,
            "unresolved_states": unresolved,
            "route_equivalence_count": route_eq_count,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_runtime_equivalence_validation(
    *,
    target_id: str,
    api_replacement_map: Mapping[str, Any],
    lifecycle_translation_graph: Mapping[str, Any],
    runtime_truth_graph: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    topology_translation_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]
    runtime_truth = _as_dict(runtime_truth_graph)
    portability = _as_dict(runtime_portability_analysis)
    lifecycle = _as_dict(lifecycle_translation_graph)

    blockers = [row for row in _as_list(portability.get("runtime_portability_blockers", portability.get("portability_blockers"))) if isinstance(row, dict)]
    unresolved = _as_list(_as_dict(lifecycle.get("summary")).get("unresolved_states"))
    topology_conf = _to_float(_as_dict(topology_translation_report).get("translation_confidence", 0.0), 0.0)

    candidate_validations: list[dict[str, Any]] = []
    for row in replacements:
        item = _as_dict(row)
        runtime_safe = bool(item.get("runtime_safe", False))
        conf = _to_float(item.get("candidate_confidence", 0.0), 0.0)
        valid = runtime_safe and conf >= 0.62 and str(runtime_truth.get("classification", "")).upper() != "FAIL_CLOSED"
        candidate_validations.append(
            {
                "downstream_construct": str(item.get("downstream_construct", "")),
                "upstream_replacement": str(item.get("upstream_replacement", "")),
                "runtime_equivalent": valid,
                "validation_confidence": round(max(0.0, min(1.0, 0.7 * conf + 0.3 * topology_conf)), 3),
                "blocking_runtime_reasons": [
                    str(_as_dict(blocker).get("code", "runtime_blocker"))
                    for blocker in blockers
                ] if not valid else [],
            }
        )

    equivalent_count = len([row for row in candidate_validations if bool(_as_dict(row).get("runtime_equivalent", False))])
    coverage = round(equivalent_count / max(1, len(candidate_validations)), 3)

    classification = "PASS"
    fail_closed_justification = ""
    if str(runtime_truth.get("classification", "")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_truth_fail_closed"
    elif blockers:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_portability_blockers_present"
    elif unresolved:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "unresolved_lifecycle_translation_states"
    elif coverage < 0.5:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_equivalence_coverage_below_threshold"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_equivalence_validation",
        "target_id": str(target_id),
        "classification": classification,
        "candidate_validations": candidate_validations,
        "summary": {
            "candidate_count": len(candidate_validations),
            "runtime_equivalent_count": equivalent_count,
            "runtime_equivalence_coverage": coverage,
            "runtime_truth_classification": str(runtime_truth.get("classification", "UNKNOWN")),
            "runtime_blocker_count": len(blockers),
            "unresolved_lifecycle_state_count": len(unresolved),
        },
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_upstream_translation_plan(
    *,
    target_id: str,
    api_replacement_map: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    lifecycle_translation_graph: Mapping[str, Any],
    runtime_equivalence_validation: Mapping[str, Any],
    downstream_driver_graph: Mapping[str, Any],
    topology_translation_report: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]
    unsupported = [row for row in _as_list(_as_dict(unsupported_vendor_constructs).get("unsupported")) if isinstance(row, dict)]

    extracted = _as_dict(_as_dict(downstream_driver_graph).get("extracted"))
    ast_ops = [str(item) for item in _as_list(extracted.get("ops_structures")) if str(item).strip()][:80]
    ast_hooks = [str(item) for item in _as_list(extracted.get("proprietary_runtime_hooks")) if str(item).strip()][:120]
    ast_routes = [str(item) for item in _as_list(extracted.get("routing_structures")) if str(item).strip()][:80]
    ast_dai = [str(item) for item in _as_list(_as_dict(extracted.get("dai_links")).get("all")) if str(item).strip()][:80]

    route_equivalence = _as_list(_as_dict(topology_translation_report).get("fe_be_route_equivalence"))
    lifecycle_unresolved = _as_list(_as_dict(lifecycle_translation_graph).get("summary")).copy()
    unresolved_states = _as_list(_as_dict(_as_dict(lifecycle_translation_graph).get("summary")).get("unresolved_states"))

    governance_ok, governance_reasons = _governance_clean(governance_state)

    stages = [
        {
            "stage_id": "phase_pcm_lifecycle_translation",
            "focus": "PCM lifecycle translation",
            "ast_entities": ast_ops,
            "replacement_candidates": [
                _as_dict(row)
                for row in replacements
                if any(token in str(_as_dict(row).get("downstream_construct", "")).lower() for token in ("pcm", "open", "prepare", "start", "stop", "close"))
            ],
            "gates": {
                "requires_runtime_equivalence": True,
                "requires_unresolved_states_zero": True,
            },
        },
        {
            "stage_id": "phase_dapm_route_equivalence",
            "focus": "DAPM route equivalence + FE/BE topology conversion",
            "ast_entities": ast_routes + ast_dai,
            "route_equivalence": route_equivalence,
            "gates": {
                "requires_route_equivalence": True,
                "requires_runtime_truth": True,
            },
        },
        {
            "stage_id": "phase_soundwire_mapping",
            "focus": "SoundWire upstream mapping",
            "ast_entities": [
                str(item)
                for item in _as_list(_as_dict(extracted.get("dependencies")).get("soundwire"))
                if str(item).strip()
            ],
            "replacement_candidates": [
                _as_dict(row)
                for row in replacements
                if any(token in str(_as_dict(row).get("downstream_construct", "")).lower() for token in ("swr", "soundwire", "sdw"))
            ],
            "gates": {
                "requires_soundwire_runtime_equivalence": True,
            },
        },
        {
            "stage_id": "phase_vendor_callback_abstraction",
            "focus": "Vendor callback abstraction replacement",
            "ast_entities": ast_hooks,
            "replacement_candidates": [
                _as_dict(row)
                for row in replacements
                if any(token in str(_as_dict(row).get("downstream_construct", "")).lower() for token in ("hook", "callback", "ops", "vendor"))
            ],
            "gates": {
                "requires_no_unsupported_callbacks": True,
            },
        },
    ]

    runtime_equivalence_class = str(_as_dict(runtime_equivalence_validation).get("classification", "UNKNOWN"))

    classification = "PASS"
    fail_closed_justification = ""
    if not governance_ok:
        classification = "FAIL_CLOSED"
        fail_closed_justification = ";".join(governance_reasons)
    elif unsupported:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "unsupported_vendor_constructs_present"
    elif unresolved_states:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "lifecycle_translation_unresolved"
    elif runtime_equivalence_class == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = str(_as_dict(runtime_equivalence_validation).get("fail_closed_justification", "runtime_equivalence_fail_closed"))

    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_translation_plan",
        "target_id": str(target_id),
        "classification": classification,
        "ast_aware_conversion_plan": {
            "source": "artifact://downstream_driver_graph",
            "stages": stages,
            "ast_entity_counts": {
                "ops_structures": len(ast_ops),
                "proprietary_runtime_hooks": len(ast_hooks),
                "routing_structures": len(ast_routes),
                "dai_links": len(ast_dai),
            },
        },
        "summary": {
            "replacement_candidate_count": len(replacements),
            "unsupported_construct_count": len(unsupported),
            "lifecycle_unresolved_count": len(unresolved_states),
            "runtime_equivalence_classification": runtime_equivalence_class,
        },
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_translation_confidence_report(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    api_replacement_map: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    lifecycle_translation_graph: Mapping[str, Any],
    runtime_equivalence_validation: Mapping[str, Any],
    topology_translation_report: Mapping[str, Any],
    semantic_confidence_report: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    governance_ok, governance_reasons = _governance_clean(governance_state)

    replacement_count = int(_as_dict(_as_dict(api_replacement_map).get("summary")).get("replacement_count", 0) or 0)
    mean_candidate_conf = _to_float(_as_dict(_as_dict(api_replacement_map).get("summary")).get("mean_candidate_confidence", 0.0), 0.0)
    unsupported_count = int(_as_dict(_as_dict(unsupported_vendor_constructs).get("summary")).get("unsupported_count", 0) or 0)
    unresolved_states = int(len(_as_list(_as_dict(_as_dict(lifecycle_translation_graph).get("summary")).get("unresolved_states"))))
    runtime_coverage = _to_float(_as_dict(_as_dict(runtime_equivalence_validation).get("summary")).get("runtime_equivalence_coverage", 0.0), 0.0)
    topology_conf = _to_float(_as_dict(topology_translation_report).get("translation_confidence", 0.0), 0.0)

    semantic_scores = _as_dict(_as_dict(_as_dict(semantic_confidence_report).get("classification")).get("scores"))
    semantic_upstream = _to_float(semantic_scores.get("upstream_friendly", 0.0), 0.0)

    replay_signal = bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)) or bool(
        str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")).strip()
    )

    factors = {
        "api_candidate_confidence": mean_candidate_conf,
        "runtime_equivalence_coverage": runtime_coverage,
        "topology_translation_confidence": topology_conf,
        "semantic_upstream_friendly": semantic_upstream,
        "replacement_density": round(min(1.0, replacement_count / 25.0), 3),
        "unsupported_penalty": round(min(1.0, unsupported_count / 15.0), 3),
        "lifecycle_unresolved_penalty": round(min(1.0, unresolved_states / 6.0), 3),
        "governance_safety": 1.0 if governance_ok else 0.0,
        "replay_signal": 1.0 if replay_signal else 0.0,
    }

    score = round(
        max(
            0.0,
            min(
                1.0,
                0.18 * factors["api_candidate_confidence"]
                + 0.18 * factors["runtime_equivalence_coverage"]
                + 0.15 * factors["topology_translation_confidence"]
                + 0.10 * factors["semantic_upstream_friendly"]
                + 0.10 * factors["replacement_density"]
                + 0.10 * factors["governance_safety"]
                + 0.07 * factors["replay_signal"]
                + 0.12 * (1.0 - factors["unsupported_penalty"])
                + 0.10 * (1.0 - factors["lifecycle_unresolved_penalty"]),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not governance_ok:
        classification = "FAIL_CLOSED"
        fail_closed_justification = ";".join(governance_reasons)
    elif unsupported_count > 0:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "unsupported_vendor_constructs_present"
    elif unresolved_states > 0:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "lifecycle_translation_unresolved"
    elif str(_as_dict(runtime_equivalence_validation).get("classification", "")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_justification = str(_as_dict(runtime_equivalence_validation).get("fail_closed_justification", "runtime_equivalence_fail_closed"))
    elif score < 0.68:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "translation_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "translation_confidence": score,
        "factors": factors,
        "summary": {
            "replacement_count": replacement_count,
            "unsupported_count": unsupported_count,
            "runtime_equivalence_classification": str(_as_dict(runtime_equivalence_validation).get("classification", "UNKNOWN")),
            "lifecycle_unresolved_count": unresolved_states,
        },
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_deterministic_translation_replay(
    *,
    target_id: str,
    lineage_id: str,
    session_id: str,
    classification: str,
    artifacts: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    previous_history: list[Mapping[str, Any]] | None,
    evidence_references: list[str],
) -> dict[str, Any]:
    artifact_fingerprints = {
        name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
        for name, payload in sorted(_as_dict(artifacts).items())
    }

    history = [row for row in _as_list(previous_history or []) if isinstance(row, dict)]
    history.append(
        {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "classification": str(classification),
            "artifact_fingerprints": artifact_fingerprints,
        }
    )
    history = history[-4000:]

    replay_signal = bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)) or bool(
        str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")).strip()
    )

    replay_score = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * (1.0 if replay_signal else 0.0)
                + 0.35 * min(1.0, len(artifact_fingerprints) / 7.0)
                + 0.20 * (1.0 if classification != "FAIL_CLOSED" else 0.4),
            ),
        ),
        3,
    )

    payload = {
        "schema_version": "1.0",
        "report_name": "deterministic_translation_replay",
        "target_id": str(target_id),
        "lineage_id": str(lineage_id),
        "session_id": str(session_id),
        "classification": "PASS" if replay_score >= 0.72 else "ADVISORY_ONLY",
        "replay_score": replay_score,
        "artifact_fingerprints": artifact_fingerprints,
        "replay_signal": {
            "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": history,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class GovernedTranslationIntelligenceEngine:
    """Evidence-backed downstream->upstream translation intelligence engine."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        runtime_artifacts: Mapping[str, Any],
        topology_artifacts: Mapping[str, Any],
        semantic_artifacts: Mapping[str, Any],
        structural_artifacts: Mapping[str, Any],
        translation_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_translation_history: list[Mapping[str, Any]] | None,
    ) -> GovernedTranslationIntelligenceResult:
        plugin = self._plugins.load_plugin(target_id)

        runtime_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_translation_adapter(
                {
                    "topology_cognition": _as_dict(topology_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": _as_dict(topology_artifacts.get("dts_topology_graph")),
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                }
            )
        )
        semantic_adapter = _as_dict(
            plugin.downstream_upstream_adapter(
                {
                    "semantic_cognition": _as_dict(semantic_artifacts.get("semantic_cognition", semantic_artifacts.get("semantic_confidence_report"))),
                    "topology_cognition": _as_dict(topology_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": _as_dict(topology_artifacts.get("dts_topology_graph")),
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                }
            )
        )
        structural_adapter = _as_dict(
            plugin.structural_cognition_adapter(
                {
                    "downstream_root": str(_as_dict(structural_artifacts.get("downstream_driver_graph")).get("downstream_root", "")),
                    "upstream_root": str(_as_dict(translation_artifacts.get("upstream_equivalence_map")).get("upstream_root", "")),
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        mapping_graph = _as_dict(translation_artifacts.get("downstream_upstream_mapping_graph"))
        upstream_equivalence = _as_dict(translation_artifacts.get("upstream_equivalence_map"))
        downstream_driver_graph = _as_dict(structural_artifacts.get("downstream_driver_graph"))
        semantic_entity_graph = _as_dict(semantic_artifacts.get("semantic_entity_graph"))
        topology_translation_report = _as_dict(translation_artifacts.get("topology_translation_report"))
        runtime_truth_graph = _as_dict(runtime_artifacts.get("runtime_truth_graph"))
        runtime_portability = _as_dict(translation_artifacts.get("runtime_portability_analysis"))

        runtime_data = _runtime_signals(runtime_truth_graph, runtime_portability)

        api_replacement_map, unsupported_vendor_constructs = _build_api_replacement_map(
            target_id=target_id,
            mapping_graph=mapping_graph,
            upstream_equivalence_map=upstream_equivalence,
            downstream_driver_graph=downstream_driver_graph,
            semantic_entity_graph=semantic_entity_graph,
            topology_translation_report=topology_translation_report,
            runtime_data=runtime_data,
            evidence_references=evidence,
        )

        lifecycle_translation_graph = _build_lifecycle_translation_graph(
            target_id=target_id,
            api_replacement_map=api_replacement_map,
            upstream_equivalence_map=upstream_equivalence,
            runtime_artifacts=runtime_artifacts,
            topology_translation_report=topology_translation_report,
            evidence_references=evidence,
        )

        runtime_equivalence_validation = _build_runtime_equivalence_validation(
            target_id=target_id,
            api_replacement_map=api_replacement_map,
            lifecycle_translation_graph=lifecycle_translation_graph,
            runtime_truth_graph=runtime_truth_graph,
            runtime_portability_analysis=runtime_portability,
            topology_translation_report=topology_translation_report,
            evidence_references=evidence,
        )

        upstream_translation_plan = _build_upstream_translation_plan(
            target_id=target_id,
            api_replacement_map=api_replacement_map,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            lifecycle_translation_graph=lifecycle_translation_graph,
            runtime_equivalence_validation=runtime_equivalence_validation,
            downstream_driver_graph=downstream_driver_graph,
            topology_translation_report=topology_translation_report,
            governance_state=governance_state,
            evidence_references=evidence,
        )

        translation_confidence_report = _build_translation_confidence_report(
            target_id=target_id,
            governance_state=governance_state,
            api_replacement_map=api_replacement_map,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            lifecycle_translation_graph=lifecycle_translation_graph,
            runtime_equivalence_validation=runtime_equivalence_validation,
            topology_translation_report=topology_translation_report,
            semantic_confidence_report=_as_dict(semantic_artifacts.get("semantic_confidence_report")),
            replay_traces=replay_traces,
            evidence_references=evidence,
        )

        artifacts: dict[str, Any] = {
            "upstream_translation_plan": upstream_translation_plan,
            "api_replacement_map": api_replacement_map,
            "unsupported_vendor_constructs": unsupported_vendor_constructs,
            "lifecycle_translation_graph": lifecycle_translation_graph,
            "runtime_equivalence_validation": runtime_equivalence_validation,
            "translation_confidence_report": translation_confidence_report,
        }

        deterministic_translation_replay = _build_deterministic_translation_replay(
            target_id=target_id,
            lineage_id=lineage_id,
            session_id=session_id,
            classification=str(translation_confidence_report.get("classification", "UNKNOWN")),
            artifacts=artifacts,
            replay_traces=replay_traces,
            previous_history=previous_translation_history,
            evidence_references=evidence,
        )
        artifacts["deterministic_translation_replay"] = deterministic_translation_replay

        classification = str(translation_confidence_report.get("classification", "UNKNOWN"))

        bundle = {
            "schema_version": "1.0",
            "phase": "GOVERNED_DOWNSTREAM_TO_UPSTREAM_TRANSLATION_INTELLIGENCE",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime_conversion": runtime_adapter,
                "topology_translation": topology_adapter,
                "downstream_upstream": semantic_adapter,
                "structural": structural_adapter,
            },
            "evidence_references": evidence,
            "artifacts": artifacts,
        }

        bundle["governed_translation_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "adapter_fingerprints": {
                    "runtime_conversion": str(runtime_adapter.get("fingerprint", "")),
                    "topology_translation": str(topology_adapter.get("fingerprint", "")),
                    "downstream_upstream": str(semantic_adapter.get("fingerprint", "")),
                    "structural": str(structural_adapter.get("fingerprint", "")),
                },
            }
        )

        return GovernedTranslationIntelligenceResult(translation_bundle=bundle)


class GovernedTranslationIntelligenceRegistry:
    """Replay-safe persistence for governed translation intelligence artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "upstream_translation_plan": self._output_dir / "upstream_translation_plan.json",
            "api_replacement_map": self._output_dir / "api_replacement_map.json",
            "unsupported_vendor_constructs": self._output_dir / "unsupported_vendor_constructs.json",
            "lifecycle_translation_graph": self._output_dir / "lifecycle_translation_graph.json",
            "runtime_equivalence_validation": self._output_dir / "runtime_equivalence_validation.json",
            "translation_confidence_report": self._output_dir / "translation_confidence_report.json",
            "deterministic_translation_replay": self._output_dir / "deterministic_translation_replay.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("governed_translation_intelligence"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "governed_translation_fingerprint": str(payload.get("governed_translation_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-6000:]

        registry["governed_translation_intelligence"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineages = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "governed_translation_intelligence",
                "recorded_at": _utc_now_iso(),
                "governed_translation_fingerprint": str(payload.get("governed_translation_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-20000:]

        registry.setdefault("translation_lineage", [])
        trans_lineage = [row for row in _as_list(registry.get("translation_lineage")) if isinstance(row, dict)]
        trans_lineage.append(
            {
                "lineage_id": lineage_id,
                "session_id": entry["session_id"],
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "governed_translation_fingerprint": entry["governed_translation_fingerprint"],
            }
        )
        registry["translation_lineage"] = trans_lineage[-10000:]

        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "governed_translation_fingerprint": entry["governed_translation_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("governed_translation_intelligence"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "governed_translation_intelligence",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "governed_translation_fingerprint": str(_as_dict(selected).get("governed_translation_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "governed_translation_fingerprint": str(_as_dict(selected).get("governed_translation_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_translation_replay.json", replay_payload)
        return replay_payload
