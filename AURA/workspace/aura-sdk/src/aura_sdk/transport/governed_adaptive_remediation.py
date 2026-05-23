"""Governed adaptive remediation and translation-learning layer.

Learns from prior governed translation outcomes while preserving strict
fail-closed governance and runtime-truth precedence.
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


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


@dataclass(frozen=True)
class GovernedAdaptiveRemediationResult:
    learning_bundle: dict[str, Any]


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
            "resolved",
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


def _tokenize(text: str) -> set[str]:
    return {tok.lower() for tok in _TOKEN_RE.findall(str(text)) if tok.strip()}


def _infer_category(construct: str, row: Mapping[str, Any]) -> str:
    category = str(_as_dict(row).get("transformation_class", "")).strip()
    if category:
        return category
    key = str(construct).lower()
    if any(token in key for token in ("callback", "hook", "ops", "vendor")):
        return "callback_replacement"
    if any(token in key for token in ("macro", "msm_", "qcom_", "vendor_")) or str(construct).isupper():
        return "vendor_macro_elimination"
    if any(token in key for token in ("fe", "be", "dai_link", "topology")):
        return "fe_be_topology_rewrite_scaffolding"
    if any(token in key for token in ("dapm", "route", "widget")):
        return "dapm_route_conversion_generation"
    if any(token in key for token in ("swr", "soundwire", "sdw")):
        return "soundwire_upstream_adaptation"
    return "runtime_safe_api_substitution"


def _infer_subsystem(*, file_path: str, construct: str, category: str) -> str:
    path = str(file_path).strip().lower()
    ckey = str(construct).lower()
    cat = str(category).lower()
    if "sound/soc" in path or "asoc" in path or any(k in ckey for k in ("snd_soc", "dai", "dapm", "fe", "be")):
        return "asoc"
    if "soundwire" in path or any(k in ckey for k in ("soundwire", "sdw", "swr")):
        return "soundwire"
    if "pcm" in path or "pcm" in ckey:
        return "pcm"
    if any(k in cat for k in ("topology", "route")):
        return "topology"
    if "codec" in path:
        return "codec"
    return "audio_core"


def _extract_manual_resolutions(manual_remediation_outcomes: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _as_list(_as_dict(manual_remediation_outcomes).get("entries")) if isinstance(row, dict)]
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", item.get("construct", ""))).strip()
        replacement = str(item.get("upstream_replacement", item.get("replacement", ""))).strip()
        if not construct or not replacement:
            continue
        out.append(
            {
                "downstream_construct": construct,
                "upstream_replacement": replacement,
                "resolution_status": str(item.get("resolution_status", "resolved")),
                "runtime_validated": bool(item.get("runtime_validated", False)),
                "outcome": str(item.get("outcome", "success")),
                "subsystem": str(item.get("subsystem", "")),
                "evidence_references": [
                    str(entry) for entry in _as_list(item.get("evidence_references")) if str(entry).strip()
                ],
            }
        )
    return out


def _runtime_validation_map(runtime_equivalence_validation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _as_list(_as_dict(runtime_equivalence_validation).get("candidate_validations")):
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip().lower()
        if not construct:
            continue
        out[construct] = {
            "runtime_equivalent": bool(item.get("runtime_equivalent", False)),
            "validation_confidence": _to_float(item.get("validation_confidence", 0.0), 0.0),
            "blocking_runtime_reasons": [
                str(reason) for reason in _as_list(item.get("blocking_runtime_reasons")) if str(reason).strip()
            ],
        }
    return out


def _segment_maps(runtime_validated_patch_segments: Mapping[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_construct: dict[str, list[dict[str, Any]]] = {}
    by_replacement: dict[str, list[dict[str, Any]]] = {}
    for row in _as_list(_as_dict(runtime_validated_patch_segments).get("segments")):
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip().lower()
        replacement = str(item.get("upstream_replacement", "")).strip().lower()
        if construct:
            by_construct.setdefault(construct, []).append(item)
        if replacement:
            by_replacement.setdefault(replacement, []).append(item)
    return by_construct, by_replacement


def _history_stats(previous_learning_history: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in previous_learning_history:
        item = _as_dict(row)
        patterns = _as_list(_as_dict(item.get("learned_translation_patterns")).get("patterns"))
        for pattern in patterns:
            p = _as_dict(pattern)
            key = str(p.get("pattern_id", "")).strip()
            if not key:
                continue
            state = stats.setdefault(
                key,
                {
                    "observed_runs": 0,
                    "runtime_backed_successes": 0,
                    "runtime_backed_failures": 0,
                    "manual_resolved_successes": 0,
                },
            )
            state["observed_runs"] += 1
            if bool(_as_dict(p.get("runtime_feedback")).get("runtime_backed_success", False)):
                state["runtime_backed_successes"] += 1
            if bool(_as_dict(p.get("runtime_feedback")).get("runtime_backed_failure", False)):
                state["runtime_backed_failures"] += 1
            if bool(_as_dict(p.get("manual_feedback")).get("manual_resolved_success", False)):
                state["manual_resolved_successes"] += 1
    return stats


def _build_learned_translation_patterns(
    *,
    target_id: str,
    api_replacement_map: Mapping[str, Any],
    runtime_equivalence_validation: Mapping[str, Any],
    runtime_validated_patch_segments: Mapping[str, Any],
    translation_execution_report: Mapping[str, Any],
    transformation_lineage: Mapping[str, Any],
    manual_entries: list[Mapping[str, Any]],
    previous_learning_history: list[Mapping[str, Any]],
    governance_ok: bool,
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]
    runtime_map = _runtime_validation_map(runtime_equivalence_validation)
    by_construct, _ = _segment_maps(runtime_validated_patch_segments)
    manual_map: dict[str, list[dict[str, Any]]] = {}
    for row in manual_entries:
        item = _as_dict(row)
        key = f"{str(item.get('downstream_construct', '')).strip().lower()}->{str(item.get('upstream_replacement', '')).strip().lower()}"
        if key:
            manual_map.setdefault(key, []).append(item)

    stage_order = _as_dict(_as_dict(transformation_lineage).get("migration_staging_boundaries")).get("stage_order", {})
    stage_index = {str(k): int(v) for k, v in _as_dict(stage_order).items()}
    history_state = _history_stats(previous_learning_history)

    execution_pass = str(translation_execution_report.get("classification", "UNKNOWN")).upper() == "PASS"

    patterns: list[dict[str, Any]] = []
    calibration_rows: list[dict[str, Any]] = []
    for row in sorted(replacements, key=lambda item: str(_as_dict(item).get("downstream_construct", "")).lower()):
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip()
        replacement = str(item.get("upstream_replacement", "")).strip()
        if not construct or not replacement:
            continue

        construct_key = construct.lower()
        link_key = f"{construct.lower()}->{replacement.lower()}"

        category = _infer_category(construct, item)
        linked_segments = [seg for seg in by_construct.get(construct_key, []) if str(_as_dict(seg).get("upstream_replacement", "")).strip().lower() == replacement.lower()]
        stage_id = str(_as_dict(linked_segments[0]).get("stage_id", "")) if linked_segments else ""
        subsystem = _infer_subsystem(
            file_path=str(_as_dict(linked_segments[0]).get("file", "")) if linked_segments else "",
            construct=construct,
            category=category,
        )
        if not subsystem:
            subsystem = "audio_core"

        manual_rows = manual_map.get(link_key, [])
        runtime_validation = _as_dict(runtime_map.get(construct_key))
        runtime_equivalent = bool(runtime_validation.get("runtime_equivalent", False))
        runtime_validation_confidence = _to_float(runtime_validation.get("validation_confidence", 0.0), 0.0)
        runtime_backed_success = bool(execution_pass and linked_segments and runtime_equivalent and runtime_validation_confidence >= 0.62)
        runtime_backed_failure = bool((not runtime_equivalent) or runtime_validation_confidence < 0.62)
        manual_resolved_success = any(
            _is_true(_as_dict(entry).get("runtime_validated", False))
            and str(_as_dict(entry).get("outcome", "success")).strip().lower() == "success"
            for entry in manual_rows
        )
        runtime_backed_evidence = runtime_backed_success or manual_resolved_success

        pattern_id = stable_fingerprint(
            {
                "downstream_construct": construct.lower(),
                "upstream_replacement": replacement.lower(),
                "subsystem": subsystem,
                "category": category,
            }
        )
        previous = _as_dict(history_state.get(pattern_id))

        historical_success = int(previous.get("runtime_backed_successes", 0)) + int(previous.get("manual_resolved_successes", 0))
        historical_failure = int(previous.get("runtime_backed_failures", 0))

        current_success = int(runtime_backed_success) + int(manual_resolved_success)
        current_failure = int(runtime_backed_failure and not runtime_backed_success)

        observed_success = historical_success + current_success
        observed_failure = historical_failure + current_failure
        observed_total = max(1, observed_success + observed_failure)

        base_conf = _to_float(item.get("candidate_confidence", item.get("mapping_confidence", 0.0)), 0.0)
        runtime_ratio = round(observed_success / observed_total, 3)
        calibrated = round(max(0.0, min(1.0, 0.6 * base_conf + 0.4 * runtime_ratio)), 3)
        if not runtime_backed_evidence:
            calibrated = min(calibrated, round(base_conf, 3))
        drift = round(calibrated - round(base_conf, 3), 3)

        eligible_for_reuse = bool(
            governance_ok
            and runtime_backed_evidence
            and runtime_equivalent
            and runtime_validation_confidence >= 0.62
            and calibrated >= 0.72
        )

        pattern = {
            "pattern_id": pattern_id,
            "downstream_construct": construct,
            "upstream_replacement": replacement,
            "category": category,
            "stage_id": stage_id,
            "stage_order": int(stage_index.get(stage_id, 999)),
            "subsystem": subsystem,
            "runtime_feedback": {
                "runtime_backed_success": runtime_backed_success,
                "runtime_backed_failure": runtime_backed_failure,
                "runtime_equivalent": runtime_equivalent,
                "runtime_validation_confidence": runtime_validation_confidence,
                "linked_segment_count": len(linked_segments),
                "blocking_runtime_reasons": [
                    str(reason)
                    for reason in _as_list(runtime_validation.get("blocking_runtime_reasons"))
                    if str(reason).strip()
                ],
            },
            "manual_feedback": {
                "manual_resolution_count": len(manual_rows),
                "manual_resolved_success": manual_resolved_success,
            },
            "confidence": {
                "base_candidate_confidence": round(base_conf, 3),
                "runtime_success_ratio": runtime_ratio,
                "calibrated_confidence": calibrated,
                "confidence_drift": drift,
            },
            "governance_gate": {
                "requires_runtime_backed_evidence": True,
                "runtime_backed_evidence": runtime_backed_evidence,
                "eligible_for_reuse": eligible_for_reuse,
                "fail_closed_without_runtime_evidence": True,
            },
            "evidence_references": sorted(
                set(
                    [
                        *[str(entry) for entry in _as_list(item.get("evidence_sources")) if str(entry).strip()],
                        *[str(entry) for entry in evidence_references if str(entry).strip()],
                    ]
                )
            ),
        }
        pattern["deterministic_fingerprint"] = stable_fingerprint(pattern)
        patterns.append(pattern)

        calibration_rows.append(
            {
                "pattern_id": pattern_id,
                "downstream_construct": construct,
                "upstream_replacement": replacement,
                "subsystem": subsystem,
                "base_confidence": round(base_conf, 3),
                "calibrated_confidence": calibrated,
                "confidence_drift": drift,
                "runtime_backed_evidence": runtime_backed_evidence,
            }
        )

    patterns = sorted(
        patterns,
        key=lambda row: (
            str(_as_dict(row).get("subsystem", "")),
            int(_as_dict(row).get("stage_order", 999)),
            str(_as_dict(row).get("downstream_construct", "")).lower(),
        ),
    )

    learned = {
        "schema_version": "1.0",
        "report_name": "learned_translation_patterns",
        "target_id": str(target_id),
        "classification": "PASS" if patterns else "FAIL_CLOSED",
        "patterns": patterns,
        "summary": {
            "pattern_count": len(patterns),
            "runtime_backed_pattern_count": len(
                [p for p in patterns if bool(_as_dict(_as_dict(p).get("governance_gate")).get("runtime_backed_evidence", False))]
            ),
            "eligible_for_reuse_count": len(
                [p for p in patterns if bool(_as_dict(_as_dict(p).get("governance_gate")).get("eligible_for_reuse", False))]
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    learned["deterministic_fingerprint"] = stable_fingerprint(learned)

    confidence_report = {
        "schema_version": "1.0",
        "report_name": "confidence_calibration_report",
        "target_id": str(target_id),
        "classification": "PASS" if calibration_rows else "FAIL_CLOSED",
        "patterns": sorted(calibration_rows, key=lambda row: str(_as_dict(row).get("downstream_construct", "")).lower()),
        "summary": {
            "calibration_count": len(calibration_rows),
            "mean_base_confidence": round(
                sum(_to_float(_as_dict(row).get("base_confidence", 0.0), 0.0) for row in calibration_rows)
                / max(1, len(calibration_rows)),
                3,
            ),
            "mean_calibrated_confidence": round(
                sum(_to_float(_as_dict(row).get("calibrated_confidence", 0.0), 0.0) for row in calibration_rows)
                / max(1, len(calibration_rows)),
                3,
            ),
            "positive_drift_count": len([row for row in calibration_rows if _to_float(_as_dict(row).get("confidence_drift", 0.0), 0.0) > 0.0]),
            "negative_drift_count": len([row for row in calibration_rows if _to_float(_as_dict(row).get("confidence_drift", 0.0), 0.0) < 0.0]),
            "runtime_backed_count": len([row for row in calibration_rows if bool(_as_dict(row).get("runtime_backed_evidence", False))]),
        },
        "governance_gate": {
            "learned_patterns_cannot_bypass_fail_closed_without_runtime_evidence": True
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    confidence_report["deterministic_fingerprint"] = stable_fingerprint(confidence_report)
    return learned, confidence_report


def _collect_blockers(
    *,
    unsafe_transformation_blocks: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in _as_list(_as_dict(unsafe_transformation_blocks).get("blocks")):
        item = _as_dict(row)
        construct = str(item.get("construct", item.get("downstream_construct", ""))).strip()
        reason = str(item.get("reason", "unsafe_transformation")).strip()
        out.append(
            {
                "construct": construct,
                "reason": reason,
                "category": str(item.get("category", "runtime_safe_api_substitution")),
                "tokens": sorted(_tokenize(f"{construct} {reason}")),
                "source": "unsafe_transformation_blocks",
            }
        )
    for row in _as_list(_as_dict(unsupported_vendor_constructs).get("unsupported")):
        item = _as_dict(row)
        construct = str(item.get("construct", item.get("downstream_construct", ""))).strip()
        reason = str(item.get("reason", "unsupported_construct")).strip()
        out.append(
            {
                "construct": construct,
                "reason": reason,
                "category": "unsupported_vendor_constructs",
                "tokens": sorted(_tokenize(f"{construct} {reason}")),
                "source": "unsupported_vendor_constructs",
            }
        )
    return out


def _build_historical_blocker_similarity_map(
    *,
    target_id: str,
    unsafe_transformation_blocks: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    blockers = _collect_blockers(
        unsafe_transformation_blocks=unsafe_transformation_blocks,
        unsupported_vendor_constructs=unsupported_vendor_constructs,
    )
    signatures: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        item = _as_dict(blocker)
        reason = str(item.get("reason", "unknown_reason")).strip().lower()
        tokens = [str(token) for token in _as_list(item.get("tokens")) if str(token).strip()]
        key_tokens = sorted(tokens)[:6]
        sig_seed = {"reason": reason, "tokens": key_tokens}
        sig_id = f"blocker:{stable_fingerprint(sig_seed)[:16]}"
        state = signatures.setdefault(
            sig_id,
            {
                "signature_id": sig_id,
                "reason": reason,
                "tokens": key_tokens,
                "count": 0,
                "example_constructs": [],
            },
        )
        state["count"] += 1
        c = str(item.get("construct", "")).strip()
        if c and c not in state["example_constructs"] and len(state["example_constructs"]) < 5:
            state["example_constructs"].append(c)

    signature_rows = sorted(signatures.values(), key=lambda row: (-int(_as_dict(row).get("count", 0)), str(_as_dict(row).get("signature_id", ""))))
    compare_rows = signature_rows[:220]
    edges: list[dict[str, Any]] = []
    for i, left in enumerate(compare_rows):
        l = _as_dict(left)
        set_l = set(str(token) for token in _as_list(l.get("tokens")) if str(token).strip())
        if not set_l:
            continue
        reason_l = str(l.get("reason", ""))
        for right in compare_rows[i + 1 :]:
            r = _as_dict(right)
            set_r = set(str(token) for token in _as_list(r.get("tokens")) if str(token).strip())
            if not set_r:
                continue
            inter = len(set_l.intersection(set_r))
            union = len(set_l.union(set_r))
            if union <= 0:
                continue
            score = inter / union
            if reason_l == str(r.get("reason", "")):
                score += 0.2
            score = round(min(1.0, score), 3)
            if score < 0.45:
                continue
            edges.append(
                {
                    "left_signature_id": str(l.get("signature_id", "")),
                    "right_signature_id": str(r.get("signature_id", "")),
                    "similarity_score": score,
                    "similarity_basis": {
                        "reason_match": reason_l == str(r.get("reason", "")),
                        "token_overlap_count": inter,
                    },
                }
            )

    report = {
        "schema_version": "1.0",
        "report_name": "historical_blocker_similarity_map",
        "target_id": str(target_id),
        "classification": "PASS" if signature_rows else "FAIL_CLOSED",
        "blocker_signatures": signature_rows,
        "recurring_similarity_edges": sorted(
            edges,
            key=lambda row: (
                -_to_float(_as_dict(row).get("similarity_score", 0.0), 0.0),
                str(_as_dict(row).get("left_signature_id", "")),
                str(_as_dict(row).get("right_signature_id", "")),
            ),
        ),
        "summary": {
            "total_blockers": len(blockers),
            "signature_count": len(signature_rows),
            "recurring_edge_count": len(edges),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_remediation_templates(
    *,
    target_id: str,
    learned_patterns: Mapping[str, Any],
    blocker_similarity_map: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    patterns = [row for row in _as_list(_as_dict(learned_patterns).get("patterns")) if isinstance(row, dict)]
    signatures = [row for row in _as_list(_as_dict(blocker_similarity_map).get("blocker_signatures")) if isinstance(row, dict)]

    templates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in patterns:
        item = _as_dict(row)
        category = str(item.get("category", "runtime_safe_api_substitution"))
        subsystem = str(item.get("subsystem", "audio_core"))
        runtime_backed = bool(_as_dict(item.get("governance_gate")).get("runtime_backed_evidence", False))
        key = f"{category}:{subsystem}"
        if key in seen:
            continue
        seen.add(key)
        template = {
            "template_id": f"template:{stable_fingerprint({'category': category, 'subsystem': subsystem})[:16]}",
            "category": category,
            "subsystem": subsystem,
            "applicability": "runtime_backed" if runtime_backed else "advisory_only",
            "template_steps": [
                "validate runtime equivalence evidence",
                "verify fail-closed governance posture",
                "apply AST-aware identifier substitution",
                "re-run runtime validation and update confidence",
            ],
            "requires_runtime_backed_evidence": True,
            "governance_guardrail": "never_bypass_fail_closed_without_runtime_validation",
        }
        template["deterministic_fingerprint"] = stable_fingerprint(template)
        templates.append(template)

    for row in signatures[:20]:
        item = _as_dict(row)
        reason = str(item.get("reason", "unknown_reason"))
        tid = f"blocker_template:{stable_fingerprint({'reason': reason, 'tokens': _as_list(item.get('tokens'))})[:16]}"
        if tid in seen:
            continue
        seen.add(tid)
        template = {
            "template_id": tid,
            "category": "blocker_remediation",
            "subsystem": "multi",
            "trigger_reason": reason,
            "template_steps": [
                "collect runtime evidence for blocked construct",
                "collect manual remediation outcome",
                "re-run confidence calibration",
                "remain fail-closed if runtime validation missing",
            ],
            "requires_runtime_backed_evidence": True,
            "governance_guardrail": "block_until_runtime_supported",
        }
        template["deterministic_fingerprint"] = stable_fingerprint(template)
        templates.append(template)

    report = {
        "schema_version": "1.0",
        "report_name": "remediation_template_registry",
        "target_id": str(target_id),
        "classification": "PASS" if templates else "FAIL_CLOSED",
        "templates": sorted(templates, key=lambda row: str(_as_dict(row).get("template_id", ""))),
        "summary": {
            "template_count": len(templates),
            "runtime_backed_template_count": len([row for row in templates if bool(_as_dict(row).get("requires_runtime_backed_evidence", False))]),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_reusable_equivalence_library(
    *,
    target_id: str,
    learned_patterns: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    patterns = [row for row in _as_list(_as_dict(learned_patterns).get("patterns")) if isinstance(row, dict)]
    grouped: dict[str, dict[str, Any]] = {}
    for row in patterns:
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip()
        replacement = str(item.get("upstream_replacement", "")).strip()
        if not construct or not replacement:
            continue
        key = f"{construct.lower()}->{replacement.lower()}"
        state = grouped.setdefault(
            key,
            {
                "downstream_construct": construct,
                "upstream_replacement": replacement,
                "subsystems": set(),
                "usage_count": 0,
                "runtime_backed_count": 0,
                "eligible_for_reuse_count": 0,
                "confidence_sum": 0.0,
            },
        )
        state["usage_count"] += 1
        state["subsystems"].add(str(item.get("subsystem", "audio_core")))
        state["confidence_sum"] += _to_float(_as_dict(item.get("confidence")).get("calibrated_confidence", 0.0), 0.0)
        if bool(_as_dict(item.get("governance_gate")).get("runtime_backed_evidence", False)):
            state["runtime_backed_count"] += 1
        if bool(_as_dict(item.get("governance_gate")).get("eligible_for_reuse", False)):
            state["eligible_for_reuse_count"] += 1

    library_rows: list[dict[str, Any]] = []
    for row in grouped.values():
        item = _as_dict(row)
        usage_count = int(item.get("usage_count", 0))
        reuse_conf = round(_to_float(item.get("confidence_sum", 0.0), 0.0) / max(1, usage_count), 3)
        entry = {
            "equivalence_id": stable_fingerprint(
                {
                    "downstream_construct": item.get("downstream_construct", ""),
                    "upstream_replacement": item.get("upstream_replacement", ""),
                }
            ),
            "downstream_construct": item.get("downstream_construct", ""),
            "upstream_replacement": item.get("upstream_replacement", ""),
            "subsystems": sorted(str(v) for v in item.get("subsystems", set()) if str(v).strip()),
            "usage_count": usage_count,
            "runtime_backed_count": int(item.get("runtime_backed_count", 0)),
            "eligible_for_reuse_count": int(item.get("eligible_for_reuse_count", 0)),
            "calibrated_reuse_confidence": reuse_conf,
            "governance_gate": {
                "requires_runtime_backed_evidence": True,
                "reusable_in_governed_execution": bool(
                    int(item.get("eligible_for_reuse_count", 0)) > 0 and int(item.get("runtime_backed_count", 0)) > 0
                ),
            },
        }
        entry["deterministic_fingerprint"] = stable_fingerprint(entry)
        library_rows.append(entry)

    report = {
        "schema_version": "1.0",
        "report_name": "reusable_equivalence_library",
        "target_id": str(target_id),
        "classification": "PASS" if library_rows else "FAIL_CLOSED",
        "equivalences": sorted(
            library_rows,
            key=lambda row: (
                -int(_as_dict(row).get("eligible_for_reuse_count", 0)),
                str(_as_dict(row).get("downstream_construct", "")).lower(),
            ),
        ),
        "summary": {
            "equivalence_count": len(library_rows),
            "governed_reusable_count": len(
                [row for row in library_rows if bool(_as_dict(_as_dict(row).get("governance_gate")).get("reusable_in_governed_execution", False))]
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_subsystem_translation_memory(
    *,
    target_id: str,
    learned_patterns: Mapping[str, Any],
    remediation_templates: Mapping[str, Any],
    blocker_similarity_map: Mapping[str, Any],
    reusable_equivalence_library: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    patterns = [row for row in _as_list(_as_dict(learned_patterns).get("patterns")) if isinstance(row, dict)]
    templates = [row for row in _as_list(_as_dict(remediation_templates).get("templates")) if isinstance(row, dict)]
    blockers = [row for row in _as_list(_as_dict(blocker_similarity_map).get("blocker_signatures")) if isinstance(row, dict)]
    equivalences = [row for row in _as_list(_as_dict(reusable_equivalence_library).get("equivalences")) if isinstance(row, dict)]

    memory: dict[str, dict[str, Any]] = {}
    for row in patterns:
        item = _as_dict(row)
        subsystem = str(item.get("subsystem", "audio_core"))
        state = memory.setdefault(
            subsystem,
            {
                "subsystem": subsystem,
                "pattern_count": 0,
                "runtime_backed_pattern_count": 0,
                "eligible_for_reuse_pattern_count": 0,
                "recommended_templates": set(),
                "reusable_equivalences": set(),
            },
        )
        state["pattern_count"] += 1
        if bool(_as_dict(item.get("governance_gate")).get("runtime_backed_evidence", False)):
            state["runtime_backed_pattern_count"] += 1
        if bool(_as_dict(item.get("governance_gate")).get("eligible_for_reuse", False)):
            state["eligible_for_reuse_pattern_count"] += 1

    for row in templates:
        item = _as_dict(row)
        subsystem = str(item.get("subsystem", "multi"))
        if subsystem == "multi":
            for state in memory.values():
                state["recommended_templates"].add(str(item.get("template_id", "")))
            continue
        state = memory.setdefault(
            subsystem,
            {
                "subsystem": subsystem,
                "pattern_count": 0,
                "runtime_backed_pattern_count": 0,
                "eligible_for_reuse_pattern_count": 0,
                "recommended_templates": set(),
                "reusable_equivalences": set(),
            },
        )
        state["recommended_templates"].add(str(item.get("template_id", "")))

    for row in equivalences:
        item = _as_dict(row)
        eq_key = f"{str(item.get('downstream_construct', '')).strip()}->{str(item.get('upstream_replacement', '')).strip()}"
        for subsystem in [str(v) for v in _as_list(item.get("subsystems")) if str(v).strip()]:
            state = memory.setdefault(
                subsystem,
                {
                    "subsystem": subsystem,
                    "pattern_count": 0,
                    "runtime_backed_pattern_count": 0,
                    "eligible_for_reuse_pattern_count": 0,
                    "recommended_templates": set(),
                    "reusable_equivalences": set(),
                },
            )
            if eq_key:
                state["reusable_equivalences"].add(eq_key)

    blocker_count = len(blockers)
    for state in memory.values():
        state["blocker_signal_count"] = blocker_count

    rows: list[dict[str, Any]] = []
    for subsystem, state in sorted(memory.items()):
        item = _as_dict(state)
        payload = {
            "subsystem": subsystem,
            "pattern_count": int(item.get("pattern_count", 0)),
            "runtime_backed_pattern_count": int(item.get("runtime_backed_pattern_count", 0)),
            "eligible_for_reuse_pattern_count": int(item.get("eligible_for_reuse_pattern_count", 0)),
            "blocker_signal_count": int(item.get("blocker_signal_count", 0)),
            "recommended_templates": sorted(str(v) for v in item.get("recommended_templates", set()) if str(v).strip()),
            "reusable_equivalences": sorted(str(v) for v in item.get("reusable_equivalences", set()) if str(v).strip()),
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        rows.append(payload)

    report = {
        "schema_version": "1.0",
        "report_name": "subsystem_translation_memory",
        "target_id": str(target_id),
        "classification": "PASS" if rows else "FAIL_CLOSED",
        "subsystems": rows,
        "summary": {
            "subsystem_count": len(rows),
            "total_pattern_count": sum(int(_as_dict(row).get("pattern_count", 0)) for row in rows),
            "total_runtime_backed_patterns": sum(int(_as_dict(row).get("runtime_backed_pattern_count", 0)) for row in rows),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return report


def _build_adaptive_trace(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    classification: str,
    fail_closed_justification: str,
    artifacts: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    previous_learning_history: list[Mapping[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    ordered_artifacts = [
        "learned_translation_patterns",
        "remediation_template_registry",
        "historical_blocker_similarity_map",
        "confidence_calibration_report",
        "reusable_equivalence_library",
        "subsystem_translation_memory",
    ]
    events: list[dict[str, Any]] = []
    for idx, key in enumerate(ordered_artifacts, start=1):
        item = _as_dict(artifacts.get(key))
        events.append(
            {
                "event_index": idx,
                "event_type": key,
                "artifact_fingerprint": str(item.get("deterministic_fingerprint", "")),
                "classification": str(item.get("classification", "UNKNOWN")),
            }
        )

    trace = {
        "schema_version": "1.0",
        "report_name": "adaptive_remediation_trace",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(classification),
        "fail_closed_justification": str(fail_closed_justification),
        "deterministic_event_ordering": True,
        "events": events,
        "replay_signal": {
            "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": [
            row for row in _as_list(previous_learning_history) if isinstance(row, dict)
        ]
        + [
            {
                "lineage_id": str(lineage_id),
                "session_id": str(session_id),
                "classification": str(classification),
            }
        ],
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    trace["deterministic_fingerprint"] = stable_fingerprint(trace)
    return trace


class GovernedAdaptiveRemediationEngine:
    """Governed adaptive remediation and translation-learning engine."""

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
        runtime_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        manual_remediation_outcomes: Mapping[str, Any],
        previous_learning_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> GovernedAdaptiveRemediationResult:
        plugin = self._plugins.load_plugin(target_id)
        learning_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                    "mode": "adaptive_learning",
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]
        history = [row for row in _as_list(previous_learning_history or []) if isinstance(row, dict)]

        governance_ok, governance_violations = _governance_clean(governance_state)
        fail_closed_justification = ""
        classification = "PASS"
        hard_block = False
        if not governance_ok:
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = ";".join(governance_violations)

        api_replacement_map = _as_dict(translation_artifacts.get("api_replacement_map"))
        unsupported_vendor_constructs = _as_dict(translation_artifacts.get("unsupported_vendor_constructs"))
        runtime_equivalence_validation = _as_dict(translation_artifacts.get("runtime_equivalence_validation"))
        runtime_validated_patch_segments = _as_dict(execution_artifacts.get("runtime_validated_patch_segments"))
        translation_execution_report = _as_dict(execution_artifacts.get("translation_execution_report"))
        unsafe_transformation_blocks = _as_dict(execution_artifacts.get("unsafe_transformation_blocks"))
        transformation_lineage = _as_dict(execution_artifacts.get("transformation_lineage"))

        manual_entries = _extract_manual_resolutions(manual_remediation_outcomes)

        learned_patterns, confidence_report = _build_learned_translation_patterns(
            target_id=target_id,
            api_replacement_map=api_replacement_map,
            runtime_equivalence_validation=runtime_equivalence_validation,
            runtime_validated_patch_segments=runtime_validated_patch_segments,
            translation_execution_report=translation_execution_report,
            transformation_lineage=transformation_lineage,
            manual_entries=manual_entries,
            previous_learning_history=history,
            governance_ok=governance_ok,
            evidence_references=evidence,
        )
        blocker_similarity_map = _build_historical_blocker_similarity_map(
            target_id=target_id,
            unsafe_transformation_blocks=unsafe_transformation_blocks,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            evidence_references=evidence,
        )
        remediation_templates = _build_remediation_templates(
            target_id=target_id,
            learned_patterns=learned_patterns,
            blocker_similarity_map=blocker_similarity_map,
            evidence_references=evidence,
        )
        reusable_equivalence_library = _build_reusable_equivalence_library(
            target_id=target_id,
            learned_patterns=learned_patterns,
            evidence_references=evidence,
        )
        subsystem_memory = _build_subsystem_translation_memory(
            target_id=target_id,
            learned_patterns=learned_patterns,
            remediation_templates=remediation_templates,
            blocker_similarity_map=blocker_similarity_map,
            reusable_equivalence_library=reusable_equivalence_library,
            evidence_references=evidence,
        )

        runtime_backed_count = int(_as_dict(learned_patterns.get("summary")).get("runtime_backed_pattern_count", 0))
        execution_fail_closed = str(translation_execution_report.get("classification", "UNKNOWN")).upper() == "FAIL_CLOSED"
        if not hard_block and runtime_backed_count <= 0:
            classification = "FAIL_CLOSED"
            fail_closed_justification = "insufficient_runtime_backed_learning_evidence"
        if not hard_block and execution_fail_closed and runtime_backed_count <= 0:
            classification = "FAIL_CLOSED"
            fail_closed_justification = "translation_execution_fail_closed_without_runtime_backed_patterns"

        artifacts = {
            "learned_translation_patterns": learned_patterns,
            "remediation_template_registry": remediation_templates,
            "historical_blocker_similarity_map": blocker_similarity_map,
            "confidence_calibration_report": confidence_report,
            "reusable_equivalence_library": reusable_equivalence_library,
            "subsystem_translation_memory": subsystem_memory,
        }

        adaptive_trace = _build_adaptive_trace(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            classification=classification,
            fail_closed_justification=fail_closed_justification,
            artifacts=artifacts,
            replay_traces=replay_traces,
            previous_learning_history=history,
            evidence_references=evidence,
        )
        artifacts["adaptive_remediation_trace"] = adaptive_trace

        bundle = {
            "schema_version": "1.0",
            "phase": "GOVERNED_ADAPTIVE_REMEDIATION_TRANSLATION_LEARNING",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_justification": fail_closed_justification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {"runtime_conversion": learning_adapter},
            "artifacts": artifacts,
            "evidence_references": evidence,
        }
        bundle["governed_adaptive_remediation_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "fail_closed_justification": fail_closed_justification,
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "adapter_fingerprint": str(learning_adapter.get("fingerprint", "")),
            }
        )

        return GovernedAdaptiveRemediationResult(learning_bundle=bundle)


class GovernedAdaptiveRemediationRegistry:
    """Replay-safe persistence for adaptive remediation artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "learned_translation_patterns": self._output_dir / "learned_translation_patterns.json",
            "remediation_template_registry": self._output_dir / "remediation_template_registry.json",
            "historical_blocker_similarity_map": self._output_dir / "historical_blocker_similarity_map.json",
            "confidence_calibration_report": self._output_dir / "confidence_calibration_report.json",
            "reusable_equivalence_library": self._output_dir / "reusable_equivalence_library.json",
            "subsystem_translation_memory": self._output_dir / "subsystem_translation_memory.json",
            "adaptive_remediation_trace": self._output_dir / "adaptive_remediation_trace.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("governed_adaptive_remediation"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_justification": str(payload.get("fail_closed_justification", "")),
            "governed_adaptive_remediation_fingerprint": str(payload.get("governed_adaptive_remediation_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "learned_translation_patterns": _as_dict(artifacts.get("learned_translation_patterns")),
            "evidence_references": [
                str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-6000:]

        registry["governed_adaptive_remediation"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        cognition_lineage = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        cognition_lineage.append(
            {
                "lineage_id": lineage_id,
                "type": "governed_adaptive_remediation",
                "recorded_at": _utc_now_iso(),
                "governed_adaptive_remediation_fingerprint": str(
                    payload.get("governed_adaptive_remediation_fingerprint", "")
                ),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = cognition_lineage[-22000:]

        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "governed_adaptive_remediation_fingerprint": entry["governed_adaptive_remediation_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("governed_adaptive_remediation"))
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
            "replay_type": "governed_adaptive_remediation",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "governed_adaptive_remediation_fingerprint": str(
                _as_dict(selected).get("governed_adaptive_remediation_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "governed_adaptive_remediation_fingerprint": str(
                        _as_dict(selected).get("governed_adaptive_remediation_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "adaptive_remediation_replay.json", replay_payload)
        return replay_payload
