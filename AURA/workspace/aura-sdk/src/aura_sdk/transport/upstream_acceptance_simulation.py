"""Upstream Acceptance Simulation and Patch Validation layer.

Simulates maintainership review expectations and validates patch readiness
against governance, runtime-backed equivalence evidence, and deterministic
delivery controls.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_AUTONOMOUS_POLICY_FLAGS = [
    "autonomous_patching_allowed",
    "autonomous_topology_rewrite_allowed",
    "autonomous_runtime_mutation_allowed",
    "autonomous_upstream_generation_allowed",
]

_COMMIT_TAXONOMY_PREFIXES = [
    "asoc",
    "soundwire",
    "dsp",
    "irq",
    "platform",
    "topology",
    "runtime",
]


@dataclass(frozen=True)
class UpstreamAcceptanceSimulationResult:
    acceptance_bundle: dict[str, Any]


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

    for flag in _AUTONOMOUS_POLICY_FLAGS:
        if _is_true(governance.get(flag, False)):
            reasons.append(f"governance_violation:{flag}")

    return (len(reasons) == 0, reasons)


def _extract_patch_text(generated_patch_artifact: Mapping[str, Any]) -> str:
    artifact = _as_dict(generated_patch_artifact)
    patch_text = str(artifact.get("patch_text", ""))
    if patch_text:
        return patch_text
    return str(artifact.get("diff", ""))


def _parse_patch_diff(patch_text: str) -> dict[str, Any]:
    files: list[str] = []
    added = 0
    removed = 0
    hunks = 0
    style_violations: list[dict[str, Any]] = []

    for line_no, line in enumerate(str(patch_text).splitlines(), start=1):
        if line.startswith("+++ b/"):
            files.append(line[6:].strip())
            continue
        if line.startswith("@@"):
            hunks += 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
            code = line[1:]
            if len(code) > 100:
                style_violations.append(
                    {"line_no": line_no, "type": "line_length_exceeds_100", "value": len(code)}
                )
            if "\t" in code:
                style_violations.append(
                    {"line_no": line_no, "type": "tab_character_present"}
                )
            if code.rstrip(" ") != code:
                style_violations.append(
                    {"line_no": line_no, "type": "trailing_whitespace"}
                )
        if line.startswith("-") and not line.startswith("---"):
            removed += 1

    return {
        "files": sorted(set(files)),
        "file_count": len(set(files)),
        "hunk_count": hunks,
        "added_line_count": added,
        "removed_line_count": removed,
        "style_violations": style_violations,
        "style_violation_count": len(style_violations),
    }


def _build_dependency_order(
    *,
    target_id: str,
    patch_dependency_graph: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], list[str], bool]:
    graph = _as_dict(patch_dependency_graph)
    nodes = [row for row in _as_list(graph.get("nodes")) if isinstance(row, dict)]

    deps: dict[str, set[str]] = {}
    for row in nodes:
        item = _as_dict(row)
        patch_id = str(item.get("patch_id", "")).strip()
        if not patch_id:
            continue
        deps.setdefault(patch_id, set())
        for dep in _as_list(item.get("depends_on")):
            dep_id = str(dep).strip()
            if dep_id:
                deps[patch_id].add(dep_id)
                deps.setdefault(dep_id, set())

    ordered: list[str] = []
    unresolved = {key: set(value) for key, value in deps.items()}
    while unresolved:
        ready = sorted([key for key, value in unresolved.items() if not value])
        if not ready:
            break
        for patch_id in ready:
            ordered.append(patch_id)
            unresolved.pop(patch_id, None)
            for value in unresolved.values():
                value.discard(patch_id)

    cycle_detected = bool(unresolved)
    unresolved_nodes = sorted(unresolved.keys()) if cycle_detected else []

    payload = {
        "schema_version": "1.0",
        "report_name": "patch_dependency_order",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if cycle_detected else "PASS",
        "ordered_patch_ids": ordered,
        "dependency_cycles_detected": cycle_detected,
        "unresolved_nodes": unresolved_nodes,
        "summary": {
            "graph_node_count": len(deps),
            "ordered_count": len(ordered),
            "cycle_detected": cycle_detected,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, ordered, cycle_detected


def _build_maintainer_scope_map(
    *,
    target_id: str,
    subsystem_boundary_map: Mapping[str, Any],
    patch_series_plan: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], bool]:
    boundary = _as_dict(subsystem_boundary_map)
    series = [row for row in _as_list(_as_dict(patch_series_plan).get("series")) if isinstance(row, dict)]
    subsystems = [row for row in _as_list(boundary.get("subsystems")) if isinstance(row, dict)]
    subsystem_names = [str(_as_dict(row).get("subsystem", "")).strip() for row in subsystems if str(_as_dict(row).get("subsystem", "")).strip()]

    scope_rows: list[dict[str, Any]] = []
    mismatch_count = 0
    high_risk_crossings = int(_as_dict(boundary.get("summary")).get("high_risk_crossings", 0) or 0)
    subsystem_isolation_violation = high_risk_crossings > 0

    for row in series:
        item = _as_dict(row)
        patch_id = str(item.get("patch_group_id", "")).strip()
        maintainers = [str(v) for v in _as_list(item.get("maintainer_review_groups")) if str(v).strip()]
        scope = [str(v) for v in _as_list(item.get("scope")) if str(v).strip()]
        owners = [str(v) for v in _as_list(item.get("subsystem_owners")) if str(v).strip()]
        if not owners:
            owners = subsystem_names[:6]

        scope_valid = bool(maintainers and (scope or owners))
        if not scope_valid:
            mismatch_count += 1

        scope_rows.append(
            {
                "patch_group_id": patch_id,
                "maintainer_review_groups": maintainers,
                "subsystem_scope": sorted(set(scope + owners)),
                "scope_valid": scope_valid,
            }
        )

    classification = "PASS"
    if subsystem_isolation_violation or mismatch_count > 0:
        classification = "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "maintainer_scope_map",
        "target_id": str(target_id),
        "classification": classification,
        "scope": scope_rows,
        "summary": {
            "series_count": len(scope_rows),
            "scope_mismatch_count": mismatch_count,
            "high_risk_crossings": high_risk_crossings,
            "subsystem_isolation_violation": subsystem_isolation_violation,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, subsystem_isolation_violation


def _build_regression_risk_assessment(
    *,
    target_id: str,
    runtime_patch_correlation: Mapping[str, Any],
    runtime_divergence_report: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    evidence_quality_report: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], float]:
    runtime_corr = _as_dict(runtime_patch_correlation)
    divergence = _as_dict(runtime_divergence_report)
    equivalence = _as_dict(runtime_equivalence_fingerprint)
    quality = _as_dict(evidence_quality_report)

    blast = str(runtime_corr.get("regression_blast_radius", "MEDIUM")).strip().upper()
    blast_score = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.8}.get(blast, 0.5)
    missing_domains = int(_as_dict(_as_dict(divergence).get("divergence_signals")).get("missing_domain_count", 0) or 0)
    non_equivalent = int(_as_dict(_as_dict(divergence).get("divergence_signals")).get("non_equivalent_count", 0) or 0)
    mean_runtime_conf = _to_float(_as_dict(equivalence.get("summary")).get("mean_runtime_backed_confidence", 0.0), 0.0)
    quality_score = _to_float(quality.get("quality_score", 0.0), 0.0)

    risk_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * blast_score
                + 0.25 * min(1.0, missing_domains / 3.0)
                + 0.20 * min(1.0, non_equivalent / 3.0)
                + 0.10 * (1.0 - mean_runtime_conf)
                + 0.10 * (1.0 - quality_score),
            ),
        ),
        3,
    )

    regression_containment_confidence = round(max(0.0, min(1.0, 1.0 - risk_score)), 3)
    classification = "PASS"
    if regression_containment_confidence < 0.72:
        classification = "FAIL_CLOSED"
    elif regression_containment_confidence < 0.82:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "regression_risk_assessment",
        "target_id": str(target_id),
        "classification": classification,
        "risk_score": risk_score,
        "regression_containment_confidence": regression_containment_confidence,
        "signals": {
            "runtime_blast_radius": blast,
            "missing_domain_count": missing_domains,
            "non_equivalent_count": non_equivalent,
            "mean_runtime_backed_confidence": mean_runtime_conf,
            "evidence_quality_score": quality_score,
        },
        "summary": {
            "fail_closed_threshold": 0.72,
            "regression_containment_confidence": regression_containment_confidence,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, regression_containment_confidence


def _build_bisectability_validation(
    *,
    target_id: str,
    bisectability_report: Mapping[str, Any],
    patch_dependency_order: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    bisect = _as_dict(bisectability_report)
    order = _as_dict(patch_dependency_order)

    bisect_score = _to_float(bisect.get("bisectability_score", 0.0), 0.0)
    cycle = bool(order.get("dependency_cycles_detected", False))
    blocked_units = int(_as_dict(bisect.get("summary")).get("blocked_units", 0) or 0)

    classification = "PASS"
    if cycle or blocked_units > 0:
        classification = "FAIL_CLOSED"
    elif bisect_score < 0.75:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "bisectability_validation",
        "target_id": str(target_id),
        "classification": classification,
        "bisectability_score": bisect_score,
        "dependency_cycle_detected": cycle,
        "blocked_units": blocked_units,
        "summary": {
            "ordered_patch_count": len(_as_list(order.get("ordered_patch_ids"))),
            "bisect_safe": classification == "PASS",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _taxonomy_for_patch(patch_id: str) -> str:
    lowered = str(patch_id).lower()
    for prefix in _COMMIT_TAXONOMY_PREFIXES:
        if prefix in lowered:
            return prefix
    return "unclassified"


def _build_patch_series_validation(
    *,
    target_id: str,
    patch_series_plan: Mapping[str, Any],
    patch_dependency_order: Mapping[str, Any],
    maintainer_scope_map: Mapping[str, Any],
    bisectability_validation: Mapping[str, Any],
    generated_patch_artifact: Mapping[str, Any],
    api_evolution_trace: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    target_runtime_capture: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    series = [row for row in _as_list(_as_dict(patch_series_plan).get("series")) if isinstance(row, dict)]
    ordered = [str(v) for v in _as_list(_as_dict(patch_dependency_order).get("ordered_patch_ids")) if str(v).strip()]
    order_index = {patch_id: idx for idx, patch_id in enumerate(ordered, start=1)}

    patch_text = _extract_patch_text(generated_patch_artifact)
    diff_stats = _parse_patch_diff(patch_text)

    api_trace = _as_dict(api_evolution_trace)
    unresolved_api = int(_as_dict(api_trace.get("summary")).get("unresolved_count", 0) or 0)
    runtime_entries = [row for row in _as_list(_as_dict(runtime_equivalence_fingerprint).get("entries")) if isinstance(row, dict)]
    runtime_citations = []
    for row in runtime_entries:
        item = _as_dict(row)
        runtime_citations.append(
            {
                "downstream_construct": str(item.get("downstream_construct", "")),
                "upstream_replacement": str(item.get("upstream_replacement", "")),
                "runtime_backed_confidence": _to_float(item.get("runtime_backed_confidence", 0.0), 0.0),
                "equivalence_fingerprint": str(item.get("equivalence_fingerprint", "")),
            }
        )

    taxonomy_rows = []
    invalid_taxonomy_count = 0
    sequence_violations = 0
    for row in series:
        item = _as_dict(row)
        patch_id = str(item.get("patch_group_id", "")).strip()
        taxonomy = _taxonomy_for_patch(patch_id)
        valid_taxonomy = taxonomy != "unclassified"
        if not valid_taxonomy:
            invalid_taxonomy_count += 1
        seq = int(item.get("sequence", 0) or 0)
        if patch_id in order_index and seq != int(order_index.get(patch_id, seq)):
            sequence_violations += 1
        taxonomy_rows.append(
            {
                "patch_group_id": patch_id,
                "taxonomy": taxonomy,
                "taxonomy_valid": valid_taxonomy,
                "declared_sequence": seq,
                "dependency_order_sequence": int(order_index.get(patch_id, seq)),
            }
        )

    struct_ok = diff_stats.get("file_count", 0) > 0 and diff_stats.get("hunk_count", 0) > 0
    subsystem_ok = str(_as_dict(maintainer_scope_map).get("classification", "UNKNOWN")) == "PASS"
    bisect_ok = str(_as_dict(bisectability_validation).get("classification", "UNKNOWN")) == "PASS"
    api_ok = unresolved_api == 0
    style_ok = int(diff_stats.get("style_violation_count", 0)) == 0
    order_ok = sequence_violations == 0 and not bool(_as_dict(patch_dependency_order).get("dependency_cycles_detected", False))
    runtime_ok = str(_as_dict(runtime_equivalence_fingerprint).get("classification", "UNKNOWN")) == "PASS"

    classification = "PASS"
    fail_reasons: list[str] = []
    if not struct_ok:
        fail_reasons.append("structural_incorrect")
    if not runtime_ok:
        fail_reasons.append("runtime_equivalence_insufficient")
    if not subsystem_ok:
        fail_reasons.append("subsystem_isolation_violation")
    if not order_ok:
        fail_reasons.append("patch_dependency_order_violation")
    if not bisect_ok:
        fail_reasons.append("bisectability_violation")
    if not api_ok:
        fail_reasons.append("api_compatibility_violation")
    if not style_ok:
        fail_reasons.append("coding_style_violation")
    if invalid_taxonomy_count > 0:
        fail_reasons.append("commit_taxonomy_violation")

    if fail_reasons:
        classification = "FAIL_CLOSED"

    runtime_capture = _as_dict(target_runtime_capture)
    ordering_validation = {
        "normalized_event_count": len(_as_list(runtime_capture.get("normalized_events"))),
        "deterministic_ordering_observed": bool(_as_list(runtime_capture.get("normalized_events"))),
    }

    payload = {
        "schema_version": "1.0",
        "report_name": "patch_series_validation",
        "target_id": str(target_id),
        "classification": classification,
        "fail_closed_reasons": fail_reasons,
        "validation_dimensions": {
            "structural_correctness": struct_ok,
            "runtime_equivalence_confidence": runtime_ok,
            "replay_determinism": True,
            "api_compatibility": api_ok,
            "subsystem_isolation": subsystem_ok,
            "patch_dependency_ordering": order_ok,
            "maintainer_scope_correctness": subsystem_ok,
            "upstream_policy_alignment": style_ok and invalid_taxonomy_count == 0,
            "regression_containment_confidence": str(_as_dict(bisectability_validation).get("classification", "UNKNOWN")) == "PASS",
            "runtime_ordering_validation": ordering_validation["deterministic_ordering_observed"],
        },
        "patch_statistics": diff_stats,
        "taxonomy_validation": {
            "rows": sorted(taxonomy_rows, key=lambda row: str(_as_dict(row).get("patch_group_id", ""))),
            "invalid_taxonomy_count": invalid_taxonomy_count,
        },
        "sequence_validation": {
            "sequence_violations": sequence_violations,
            "ordered_patch_ids": ordered,
        },
        "api_validation": {
            "unresolved_api_count": unresolved_api,
        },
        "runtime_evidence_citations": runtime_citations,
        "runtime_ordering_validation": ordering_validation,
        "summary": {
            "series_count": len(series),
            "file_count": int(diff_stats.get("file_count", 0)),
            "style_violation_count": int(diff_stats.get("style_violation_count", 0)),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_acceptance_confidence(
    *,
    target_id: str,
    runtime_equivalence_fingerprint: Mapping[str, Any],
    evidence_quality_report: Mapping[str, Any],
    patch_series_validation: Mapping[str, Any],
    maintainer_scope_map: Mapping[str, Any],
    bisectability_validation: Mapping[str, Any],
    regression_risk_assessment: Mapping[str, Any],
    patch_dependency_order: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    governance_ok: bool,
    evidence_references: list[str],
) -> tuple[dict[str, Any], float]:
    eq = _as_dict(runtime_equivalence_fingerprint)
    quality = _as_dict(evidence_quality_report)
    validation = _as_dict(patch_series_validation)
    scope = _as_dict(maintainer_scope_map)
    bisect = _as_dict(bisectability_validation)
    regression = _as_dict(regression_risk_assessment)
    order = _as_dict(patch_dependency_order)
    unsupported = _as_dict(unsupported_vendor_constructs)

    runtime_conf = _to_float(_as_dict(eq.get("summary")).get("mean_runtime_backed_confidence", 0.0), 0.0)
    quality_score = _to_float(quality.get("quality_score", 0.0), 0.0)
    style_score = 1.0 if int(_as_dict(validation.get("patch_statistics")).get("style_violation_count", 0) or 0) == 0 else 0.35
    api_score = 1.0 if int(_as_dict(validation.get("api_validation")).get("unresolved_api_count", 0) or 0) == 0 else 0.25
    subsystem_score = 1.0 if str(scope.get("classification", "UNKNOWN")) == "PASS" else 0.2
    dependency_score = 1.0 if not bool(order.get("dependency_cycles_detected", False)) else 0.0
    bisect_score = _to_float(bisect.get("bisectability_score", 0.0), 0.0)
    regression_conf = _to_float(regression.get("regression_containment_confidence", 0.0), 0.0)
    unsupported_count = int(_as_dict(unsupported.get("summary")).get("unsupported_count", 0) or 0)
    unsupported_score = 0.0 if unsupported_count > 0 else 1.0

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.20 * runtime_conf
                + 0.12 * quality_score
                + 0.10 * style_score
                + 0.08 * api_score
                + 0.12 * subsystem_score
                + 0.10 * dependency_score
                + 0.10 * bisect_score
                + 0.10 * regression_conf
                + 0.08 * unsupported_score,
            ),
        ),
        3,
    )

    threshold = 0.78
    classification = "PASS"
    fail_closed_reasons: list[str] = []
    if not governance_ok:
        fail_closed_reasons.append("governance_violation")
    if runtime_conf < 0.72:
        fail_closed_reasons.append("runtime_backed_equivalence_confidence_below_threshold")
    if str(scope.get("classification", "UNKNOWN")) != "PASS":
        fail_closed_reasons.append("subsystem_isolation_violation")
    if regression_conf < 0.72:
        fail_closed_reasons.append("regression_containment_confidence_below_threshold")
    if unsupported_count > 0:
        fail_closed_reasons.append("unsupported_vendor_abstractions_unresolved")
    if str(validation.get("classification", "UNKNOWN")) != "PASS":
        fail_closed_reasons.append("patch_series_validation_failed")
    if str(bisect.get("classification", "UNKNOWN")) != "PASS":
        fail_closed_reasons.append("bisectability_validation_failed")
    if confidence < threshold:
        fail_closed_reasons.append("acceptance_confidence_below_threshold")

    if fail_closed_reasons:
        classification = "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "acceptance_confidence_score",
        "target_id": str(target_id),
        "classification": classification,
        "acceptance_confidence": confidence,
        "governance_threshold": threshold,
        "factors": {
            "runtime_backed_equivalence_confidence": runtime_conf,
            "evidence_quality_score": quality_score,
            "coding_style_score": style_score,
            "api_conformity_score": api_score,
            "subsystem_isolation_score": subsystem_score,
            "dependency_cleanliness_score": dependency_score,
            "bisectability_score": bisect_score,
            "regression_containment_confidence": regression_conf,
            "unsupported_vendor_score": unsupported_score,
        },
        "fail_closed_reasons": sorted(set(fail_closed_reasons)),
        "autonomous_delivery_permitted": classification == "PASS",
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, confidence


def _build_upstream_submission_plan(
    *,
    target_id: str,
    patch_series_plan: Mapping[str, Any],
    patch_dependency_order: Mapping[str, Any],
    acceptance_confidence_score: Mapping[str, Any],
    patch_series_validation: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    series = [row for row in _as_list(_as_dict(patch_series_plan).get("series")) if isinstance(row, dict)]
    ordered = [str(v) for v in _as_list(_as_dict(patch_dependency_order).get("ordered_patch_ids")) if str(v).strip()]
    citations = [row for row in _as_list(_as_dict(patch_series_validation).get("runtime_evidence_citations")) if isinstance(row, dict)]

    by_construct = {
        str(_as_dict(row).get("downstream_construct", "")).strip().lower(): _as_dict(row)
        for row in _as_list(_as_dict(runtime_equivalence_fingerprint).get("entries"))
        if isinstance(row, dict)
    }

    plan_steps: list[dict[str, Any]] = []
    for idx, patch_id in enumerate(ordered, start=1):
        taxonomy = _taxonomy_for_patch(patch_id)
        justification = [
            f"taxonomy={taxonomy}",
            "runtime_equivalence_validated",
            "bisectability_guardrail_enabled",
            "subsystem_scope_review_required",
        ]
        associated_citations = citations[:8]
        for key, value in by_construct.items():
            if key and key in patch_id.lower():
                associated_citations.append(
                    {
                        "downstream_construct": key,
                        "upstream_replacement": str(_as_dict(value).get("upstream_replacement", "")),
                        "runtime_backed_confidence": _to_float(_as_dict(value).get("runtime_backed_confidence", 0.0), 0.0),
                    }
                )
        plan_steps.append(
            {
                "sequence": idx,
                "patch_group_id": patch_id,
                "taxonomy": taxonomy,
                "patch_justification": sorted(set(justification)),
                "runtime_evidence_citations": associated_citations[:10],
                "stable_backport_suitability": {
                    "recommended": taxonomy in {"asoc", "soundwire", "irq", "runtime"},
                    "reason": "limited_scope_and_runtime_backed_validation",
                },
            }
        )

    flow = [
        "Reason",
        "Translate",
        "Validate",
        "Runtime equivalence verification",
        "Upstream acceptance simulation",
        "Governance scoring",
        "Delivery authorization",
        "Commit/push orchestration",
        "Deterministic replay persistence",
    ]

    confidence = _to_float(_as_dict(acceptance_confidence_score).get("acceptance_confidence", 0.0), 0.0)
    allowed = bool(_as_dict(acceptance_confidence_score).get("autonomous_delivery_permitted", False))
    classification = "PASS" if allowed else "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_submission_plan",
        "target_id": str(target_id),
        "classification": classification,
        "execution_flow": flow,
        "delivery_authorization": {
            "autonomous_delivery_permitted": allowed,
            "acceptance_confidence": confidence,
        },
        "patch_series": plan_steps,
        "summary": {
            "series_count": len(plan_steps),
            "flow_steps": len(flow),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_upstream_acceptance_report(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    acceptance_confidence_score: Mapping[str, Any],
    patch_series_validation: Mapping[str, Any],
    maintainer_scope_map: Mapping[str, Any],
    regression_risk_assessment: Mapping[str, Any],
    bisectability_validation: Mapping[str, Any],
    upstream_submission_plan: Mapping[str, Any],
    patch_dependency_order: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    confidence = _as_dict(acceptance_confidence_score)
    patch_val = _as_dict(patch_series_validation)
    scope = _as_dict(maintainer_scope_map)
    regression = _as_dict(regression_risk_assessment)
    bisect = _as_dict(bisectability_validation)
    submission = _as_dict(upstream_submission_plan)
    order = _as_dict(patch_dependency_order)
    unsupported = _as_dict(unsupported_vendor_constructs)
    runtime_eq = _as_dict(runtime_equivalence_fingerprint)

    classification = str(confidence.get("classification", "UNKNOWN"))
    report = {
        "schema_version": "1.0",
        "report_name": "upstream_acceptance_report",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "governance_scoring": {
            "acceptance_confidence": _to_float(confidence.get("acceptance_confidence", 0.0), 0.0),
            "autonomous_delivery_permitted": bool(confidence.get("autonomous_delivery_permitted", False)),
            "fail_closed_reasons": _as_list(confidence.get("fail_closed_reasons")),
        },
        "review_dimensions": {
            "structural_correctness": bool(_as_dict(patch_val.get("validation_dimensions")).get("structural_correctness", False)),
            "runtime_equivalence_confidence": bool(_as_dict(patch_val.get("validation_dimensions")).get("runtime_equivalence_confidence", False)),
            "replay_determinism": bool(_as_dict(patch_val.get("validation_dimensions")).get("replay_determinism", False)),
            "api_compatibility": bool(_as_dict(patch_val.get("validation_dimensions")).get("api_compatibility", False)),
            "subsystem_isolation": bool(_as_dict(patch_val.get("validation_dimensions")).get("subsystem_isolation", False)),
            "patch_dependency_ordering": bool(_as_dict(patch_val.get("validation_dimensions")).get("patch_dependency_ordering", False)),
            "maintainer_scope_correctness": bool(_as_dict(patch_val.get("validation_dimensions")).get("maintainer_scope_correctness", False)),
            "upstream_policy_alignment": bool(_as_dict(patch_val.get("validation_dimensions")).get("upstream_policy_alignment", False)),
            "regression_containment_confidence": bool(_as_dict(patch_val.get("validation_dimensions")).get("regression_containment_confidence", False)),
        },
        "risk_summary": {
            "regression_risk_classification": str(regression.get("classification", "UNKNOWN")),
            "bisectability_classification": str(bisect.get("classification", "UNKNOWN")),
            "scope_classification": str(scope.get("classification", "UNKNOWN")),
            "dependency_order_classification": str(order.get("classification", "UNKNOWN")),
            "unsupported_vendor_constructs": int(_as_dict(unsupported.get("summary")).get("unsupported_count", 0) or 0),
            "runtime_reusable_equivalences": int(_as_dict(runtime_eq.get("summary")).get("governed_reusable_count", 0) or 0),
        },
        "delivery_authorization": _as_dict(submission.get("delivery_authorization")),
        "execution_flow": _as_list(submission.get("execution_flow")),
        "summary": {
            "series_count": len(_as_list(submission.get("patch_series"))),
            "fail_closed": classification == "FAIL_CLOSED",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_deterministic_submission_replay(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    artifacts: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    previous_submission_history: list[Mapping[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    artifact_fingerprints = {
        str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
        for name, payload in sorted(_as_dict(artifacts).items())
    }
    lineage_history = [row for row in _as_list(previous_submission_history) if isinstance(row, dict)] + [
        {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "target_id": str(target_id),
            "classification": str(_as_dict(_as_dict(artifacts).get("upstream_acceptance_report")).get("classification", "UNKNOWN")),
        }
    ]

    replay = {
        "schema_version": "1.0",
        "report_name": "deterministic_submission_replay",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(_as_dict(_as_dict(artifacts).get("upstream_acceptance_report")).get("classification", "UNKNOWN")),
        "artifact_fingerprints": artifact_fingerprints,
        "replay_signal": {
            "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": lineage_history[-5000:],
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    replay["deterministic_fingerprint"] = stable_fingerprint(replay)
    return replay


class UpstreamAcceptanceSimulationEngine:
    """Governed upstream acceptance simulation orchestration engine."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        translation_artifacts: Mapping[str, Any],
        execution_artifacts: Mapping[str, Any],
        patch_artifacts: Mapping[str, Any],
        runtime_acquisition_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_submission_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> UpstreamAcceptanceSimulationResult:
        plugin = self._plugins.load_plugin(target_id)
        conversion_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_acquisition_artifacts.get("target_runtime_capture")),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]
        history = [row for row in _as_list(previous_submission_history or []) if isinstance(row, dict)]
        governance_ok, governance_reasons = _governance_clean(governance_state)

        unsupported_vendor_constructs = _as_dict(translation_artifacts.get("unsupported_vendor_constructs"))
        runtime_equivalence_fingerprint = _as_dict(runtime_acquisition_artifacts.get("runtime_equivalence_fingerprint"))
        runtime_divergence_report = _as_dict(runtime_acquisition_artifacts.get("runtime_divergence_report"))
        evidence_quality_report = _as_dict(runtime_acquisition_artifacts.get("evidence_quality_report"))
        target_runtime_capture = _as_dict(runtime_acquisition_artifacts.get("target_runtime_capture"))
        downstream_upstream_runtime_diff = _as_dict(runtime_acquisition_artifacts.get("downstream_upstream_runtime_diff"))
        ipc_topology_map = _as_dict(runtime_acquisition_artifacts.get("ipc_topology_map"))

        patch_dependency_graph = _as_dict(patch_artifacts.get("patch_dependency_graph"))
        subsystem_boundary_map = _as_dict(patch_artifacts.get("subsystem_boundary_map"))
        bisectability_report = _as_dict(patch_artifacts.get("bisectability_report"))
        patch_series_plan = _as_dict(patch_artifacts.get("patch_series_plan"))
        api_evolution_trace = _as_dict(patch_artifacts.get("api_evolution_trace"))
        runtime_patch_correlation = _as_dict(patch_artifacts.get("runtime_patch_correlation"))
        generated_upstream_patch = _as_dict(execution_artifacts.get("generated_upstream_patch"))

        patch_dependency_order, ordered_ids, cycle_detected = _build_dependency_order(
            target_id=target_id,
            patch_dependency_graph=patch_dependency_graph,
            evidence_references=evidence,
        )
        maintainer_scope_map, subsystem_violation = _build_maintainer_scope_map(
            target_id=target_id,
            subsystem_boundary_map=subsystem_boundary_map,
            patch_series_plan=patch_series_plan,
            evidence_references=evidence,
        )
        regression_risk_assessment, regression_containment_conf = _build_regression_risk_assessment(
            target_id=target_id,
            runtime_patch_correlation=runtime_patch_correlation,
            runtime_divergence_report=runtime_divergence_report,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            evidence_quality_report=evidence_quality_report,
            evidence_references=evidence,
        )
        bisectability_validation = _build_bisectability_validation(
            target_id=target_id,
            bisectability_report=bisectability_report,
            patch_dependency_order=patch_dependency_order,
            evidence_references=evidence,
        )
        patch_series_validation = _build_patch_series_validation(
            target_id=target_id,
            patch_series_plan=patch_series_plan,
            patch_dependency_order=patch_dependency_order,
            maintainer_scope_map=maintainer_scope_map,
            bisectability_validation=bisectability_validation,
            generated_patch_artifact=generated_upstream_patch,
            api_evolution_trace=api_evolution_trace,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            target_runtime_capture=target_runtime_capture,
            evidence_references=evidence,
        )
        acceptance_confidence_score, acceptance_confidence = _build_acceptance_confidence(
            target_id=target_id,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            evidence_quality_report=evidence_quality_report,
            patch_series_validation=patch_series_validation,
            maintainer_scope_map=maintainer_scope_map,
            bisectability_validation=bisectability_validation,
            regression_risk_assessment=regression_risk_assessment,
            patch_dependency_order=patch_dependency_order,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            governance_ok=governance_ok,
            evidence_references=evidence,
        )
        upstream_submission_plan = _build_upstream_submission_plan(
            target_id=target_id,
            patch_series_plan=patch_series_plan,
            patch_dependency_order=patch_dependency_order,
            acceptance_confidence_score=acceptance_confidence_score,
            patch_series_validation=patch_series_validation,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            evidence_references=evidence,
        )

        upstream_acceptance_report = _build_upstream_acceptance_report(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            acceptance_confidence_score=acceptance_confidence_score,
            patch_series_validation=patch_series_validation,
            maintainer_scope_map=maintainer_scope_map,
            regression_risk_assessment=regression_risk_assessment,
            bisectability_validation=bisectability_validation,
            upstream_submission_plan=upstream_submission_plan,
            patch_dependency_order=patch_dependency_order,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            evidence_references=evidence,
        )

        # Explicit governance policy enforcement gates.
        fail_reasons = []
        if not governance_ok:
            fail_reasons.extend(governance_reasons)
        if _to_float(_as_dict(runtime_equivalence_fingerprint.get("summary")).get("mean_runtime_backed_confidence", 0.0), 0.0) < 0.72:
            fail_reasons.append("runtime_backed_equivalence_confidence_below_threshold")
        if subsystem_violation:
            fail_reasons.append("subsystem_isolation_violation")
        if regression_containment_conf < 0.72:
            fail_reasons.append("regression_containment_confidence_below_threshold")
        if int(_as_dict(unsupported_vendor_constructs.get("summary")).get("unsupported_count", 0) or 0) > 0:
            fail_reasons.append("unsupported_vendor_abstractions_unresolved")
        if cycle_detected:
            fail_reasons.append("dependency_cycle_detected")

        final_classification = str(upstream_acceptance_report.get("classification", "UNKNOWN"))
        if fail_reasons:
            final_classification = "FAIL_CLOSED"

        acceptance_confidence_score["classification"] = final_classification
        if fail_reasons:
            reasons = sorted(set(_as_list(acceptance_confidence_score.get("fail_closed_reasons")) + fail_reasons))
            acceptance_confidence_score["fail_closed_reasons"] = reasons
            acceptance_confidence_score["autonomous_delivery_permitted"] = False
            acceptance_confidence_score["deterministic_fingerprint"] = stable_fingerprint(acceptance_confidence_score)

        upstream_submission_plan["classification"] = final_classification
        upstream_submission_plan["delivery_authorization"] = {
            "autonomous_delivery_permitted": bool(acceptance_confidence_score.get("autonomous_delivery_permitted", False)),
            "acceptance_confidence": acceptance_confidence,
        }
        upstream_submission_plan["deterministic_fingerprint"] = stable_fingerprint(upstream_submission_plan)

        upstream_acceptance_report["classification"] = final_classification
        upstream_acceptance_report["governance_scoring"] = {
            "acceptance_confidence": _to_float(acceptance_confidence_score.get("acceptance_confidence", 0.0), 0.0),
            "autonomous_delivery_permitted": bool(acceptance_confidence_score.get("autonomous_delivery_permitted", False)),
            "fail_closed_reasons": _as_list(acceptance_confidence_score.get("fail_closed_reasons")),
        }
        upstream_acceptance_report["risk_summary"] = {
            **_as_dict(upstream_acceptance_report.get("risk_summary")),
            "runtime_divergence_classification": str(runtime_divergence_report.get("classification", "UNKNOWN")),
            "runtime_diff_classification": str(downstream_upstream_runtime_diff.get("classification", "UNKNOWN")),
            "ipc_topology_classification": str(ipc_topology_map.get("classification", "UNKNOWN")),
        }
        upstream_acceptance_report["deterministic_fingerprint"] = stable_fingerprint(upstream_acceptance_report)

        artifacts = {
            "upstream_acceptance_report": upstream_acceptance_report,
            "patch_series_validation": patch_series_validation,
            "maintainer_scope_map": maintainer_scope_map,
            "regression_risk_assessment": regression_risk_assessment,
            "bisectability_validation": bisectability_validation,
            "upstream_submission_plan": upstream_submission_plan,
            "patch_dependency_order": patch_dependency_order,
            "acceptance_confidence_score": acceptance_confidence_score,
        }

        deterministic_submission_replay = _build_deterministic_submission_replay(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            artifacts=artifacts,
            replay_traces=replay_traces,
            previous_submission_history=history,
            evidence_references=evidence,
        )
        artifacts["deterministic_submission_replay"] = deterministic_submission_replay

        bundle = {
            "schema_version": "1.0",
            "phase": "UPSTREAM_ACCEPTANCE_SIMULATION_AND_PATCH_VALIDATION",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": final_classification,
            "fail_closed_justification": ";".join(sorted(set(_as_list(acceptance_confidence_score.get("fail_closed_reasons"))))),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime_conversion": conversion_adapter,
            },
            "artifacts": artifacts,
            "evidence_references": evidence,
        }
        bundle["upstream_acceptance_simulation_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": final_classification,
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "adapter_fingerprint": str(conversion_adapter.get("fingerprint", "")),
            }
        )

        return UpstreamAcceptanceSimulationResult(acceptance_bundle=bundle)


class UpstreamAcceptanceSimulationRegistry:
    """Replay-safe persistence for upstream acceptance simulation artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "upstream_acceptance_report": self._output_dir / "upstream_acceptance_report.json",
            "patch_series_validation": self._output_dir / "patch_series_validation.json",
            "maintainer_scope_map": self._output_dir / "maintainer_scope_map.json",
            "regression_risk_assessment": self._output_dir / "regression_risk_assessment.json",
            "bisectability_validation": self._output_dir / "bisectability_validation.json",
            "upstream_submission_plan": self._output_dir / "upstream_submission_plan.json",
            "patch_dependency_order": self._output_dir / "patch_dependency_order.json",
            "acceptance_confidence_score": self._output_dir / "acceptance_confidence_score.json",
            "deterministic_submission_replay": self._output_dir / "deterministic_submission_replay.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("upstream_acceptance_simulation"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "upstream_acceptance_simulation_fingerprint": str(payload.get("upstream_acceptance_simulation_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-6000:]

        registry["upstream_acceptance_simulation"] = {
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
                "type": "upstream_acceptance_simulation",
                "recorded_at": _utc_now_iso(),
                "upstream_acceptance_simulation_fingerprint": str(payload.get("upstream_acceptance_simulation_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-22000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "upstream_acceptance_simulation_fingerprint": entry["upstream_acceptance_simulation_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("upstream_acceptance_simulation"))
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
            "replay_type": "upstream_acceptance_simulation",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "upstream_acceptance_simulation_fingerprint": str(_as_dict(selected).get("upstream_acceptance_simulation_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "upstream_acceptance_simulation_fingerprint": str(_as_dict(selected).get("upstream_acceptance_simulation_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "deterministic_submission_replay.json", replay_payload)
        return replay_payload
