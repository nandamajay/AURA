"""Controlled downstream-to-upstream pilot conversion framework.

Executes small, runtime-backed, governance-approved pilot transformations under
strict fail-closed policy and deterministic replay lineage persistence.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_AUTONOMOUS_POLICY_FLAGS = [
    "autonomous_patching_allowed",
    "autonomous_topology_rewrite_allowed",
    "autonomous_runtime_mutation_allowed",
    "autonomous_upstream_generation_allowed",
]

_SUPPORTED_PILOT_CATEGORIES = {
    "logging_wrapper_replacement",
    "vendor_macro_normalization",
    "simple_helper_abstraction_removal",
    "pcm_capability_mapping_cleanup",
    "small_topology_normalization",
    "static_downstream_wrapper_elimination",
    "trivial_api_replacement_equivalence",
    "isolated_subsystem_utility_conversion",
}


@dataclass(frozen=True)
class ControlledPilotConversionResult:
    pilot_bundle: dict[str, Any]


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


def _parse_patch_diff(patch_text: str) -> dict[str, Any]:
    files: list[str] = []
    added = 0
    removed = 0
    hunks = 0
    for line in str(patch_text).splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:].strip())
            continue
        if line.startswith("@@"):
            hunks += 1
            continue
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return {
        "files": sorted(set(files)),
        "file_count": len(set(files)),
        "hunk_count": hunks,
        "added_line_count": added,
        "removed_line_count": removed,
    }


def _pilot_category(construct: str, replacement: str, transform_class: str) -> str:
    key = f"{construct} {replacement} {transform_class}".lower()
    if any(tok in key for tok in ("log", "printk", "pr_", "trace", "dbg")):
        return "logging_wrapper_replacement"
    if any(tok in key for tok in ("macro", "msm_", "qcom_", "vendor_", "_flag")) or str(construct).isupper():
        return "vendor_macro_normalization"
    if any(tok in key for tok in ("helper", "util", "wrapper", "shim")):
        return "simple_helper_abstraction_removal"
    if any(tok in key for tok in ("pcm", "hw_params", "capability", "buffer")):
        return "pcm_capability_mapping_cleanup"
    if any(tok in key for tok in ("route", "widget", "dapm", "topology", "dai_link", "fe", "be")):
        return "small_topology_normalization"
    if any(tok in key for tok in ("callback", "ops", "hook", "wrapper_static")):
        return "static_downstream_wrapper_elimination"
    if any(tok in key for tok in ("snd_", "api", "replace", "equivalent")):
        return "trivial_api_replacement_equivalence"
    return "isolated_subsystem_utility_conversion"


def _infer_subsystem(file_path: str, construct: str, category: str) -> str:
    path = str(file_path).lower()
    key = f"{construct} {category}".lower()
    if "sound/soc" in path or any(tok in key for tok in ("asoc", "dapm", "dai", "pcm", "route", "fe", "be")):
        return "asoc"
    if "soundwire" in path or any(tok in key for tok in ("soundwire", "swr", "sdw")):
        return "soundwire"
    if "irq" in path or "irq" in key:
        return "irq"
    if "dsp" in path or any(tok in key for tok in ("dsp", "mailbox", "apr")):
        return "dsp"
    if "include/" in path:
        return "headers"
    return "audio_core"


def _build_runtime_validation_map(runtime_equivalence_validation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in _as_list(_as_dict(runtime_equivalence_validation).get("candidate_validations")):
        item = _as_dict(row)
        key = str(item.get("downstream_construct", "")).strip().lower()
        if not key:
            continue
        out[key] = {
            "runtime_equivalent": bool(item.get("runtime_equivalent", False)),
            "validation_confidence": _to_float(item.get("validation_confidence", 0.0), 0.0),
            "blocking_runtime_reasons": [
                str(reason)
                for reason in _as_list(item.get("blocking_runtime_reasons"))
                if str(reason).strip()
            ],
        }
    return out


def _segment_map(runtime_validated_patch_segments: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _as_list(_as_dict(runtime_validated_patch_segments).get("segments")):
        item = _as_dict(row)
        key = str(item.get("downstream_construct", "")).strip().lower()
        if not key:
            continue
        out.setdefault(key, []).append(item)
    return out


def _replace_identifier_tokens(code: str, old: str, new: str) -> tuple[str, int]:
    if old == new:
        return code, 0

    out: list[str] = []
    i = 0
    n = len(code)
    count = 0
    state = "normal"

    while i < n:
        ch = code[i]

        if state == "normal":
            if ch == "/" and i + 1 < n and code[i + 1] == "/":
                state = "line_comment"
                out.append(ch)
                i += 1
                out.append(code[i])
                i += 1
                continue
            if ch == "/" and i + 1 < n and code[i + 1] == "*":
                state = "block_comment"
                out.append(ch)
                i += 1
                out.append(code[i])
                i += 1
                continue
            if ch == '"':
                state = "string"
                out.append(ch)
                i += 1
                continue
            if ch == "'":
                state = "char"
                out.append(ch)
                i += 1
                continue
            if ch.isalpha() or ch == "_":
                j = i + 1
                while j < n and (code[j].isalnum() or code[j] == "_"):
                    j += 1
                token = code[i:j]
                if token == old:
                    out.append(new)
                    count += 1
                else:
                    out.append(token)
                i = j
                continue
            out.append(ch)
            i += 1
            continue

        if state == "line_comment":
            out.append(ch)
            i += 1
            if ch == "\n":
                state = "normal"
            continue

        if state == "block_comment":
            out.append(ch)
            i += 1
            if ch == "*" and i < n and code[i] == "/":
                out.append(code[i])
                i += 1
                state = "normal"
            continue

        if state == "string":
            out.append(ch)
            i += 1
            if ch == "\\" and i < n:
                out.append(code[i])
                i += 1
                continue
            if ch == '"':
                state = "normal"
            continue

        if state == "char":
            out.append(ch)
            i += 1
            if ch == "\\" and i < n:
                out.append(code[i])
                i += 1
                continue
            if ch == "'":
                state = "normal"
            continue

    return "".join(out), count


def _build_patch(
    original_sources: Mapping[str, str],
    transformed_sources: Mapping[str, str],
    *,
    dry_run: bool,
) -> tuple[str, list[str]]:
    chunks: list[str] = []
    changed_files: list[str] = []
    for path in sorted(original_sources.keys()):
        before = str(original_sources.get(path, ""))
        after = str(transformed_sources.get(path, ""))
        if before == after:
            continue
        changed_files.append(path)
        diff = difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
        chunks.append("".join(diff))
    header = [
        "# Controlled Pilot Conversion Patch",
        f"# mode={'dry-run' if dry_run else 'proposal'}",
        "",
    ]
    return "\n".join(header) + "\n" + "\n".join(chunks), changed_files


def _derive_candidates(
    *,
    api_replacement_map: Mapping[str, Any],
    runtime_validation_map: Mapping[str, Any],
    segment_hints: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]
    selected: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in replacements:
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip()
        replacement = str(item.get("upstream_replacement", "")).strip()
        if not construct or not replacement:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "incomplete_mapping",
                    "evidence_references": evidence_references,
                }
            )
            continue
        if not _IDENT_RE.match(construct) or not _IDENT_RE.match(replacement):
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "non_ast_identifier_mapping",
                    "evidence_references": evidence_references,
                }
            )
            continue
        runtime_safe = bool(item.get("runtime_safe", False))
        conf = _to_float(item.get("candidate_confidence", 0.0), 0.0)
        validation = _as_dict(runtime_validation_map.get(construct.lower()))
        validation_conf = _to_float(validation.get("validation_confidence", 0.0), 0.0)
        runtime_equivalent = bool(validation.get("runtime_equivalent", False))
        category = _pilot_category(
            construct=construct,
            replacement=replacement,
            transform_class=str(item.get("transformation_class", "")),
        )
        hints = [h for h in _as_list(segment_hints.get(construct.lower())) if isinstance(h, dict)]
        file_hints = [str(_as_dict(h).get("file", "")) for h in hints if str(_as_dict(h).get("file", "")).strip()]
        subsystem = _infer_subsystem(
            file_path=file_hints[0] if file_hints else "",
            construct=construct,
            category=category,
        )

        if category not in _SUPPORTED_PILOT_CATEGORIES:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "unsupported_pilot_category",
                    "pilot_category": category,
                    "evidence_references": evidence_references,
                }
            )
            continue
        if conf < 0.76:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "candidate_confidence_below_threshold",
                    "candidate_confidence": conf,
                    "evidence_references": evidence_references,
                }
            )
            continue
        if not runtime_safe:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "runtime_safe_flag_false",
                    "evidence_references": evidence_references,
                }
            )
            continue
        if not runtime_equivalent:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "runtime_equivalence_false",
                    "blocking_runtime_reasons": _as_list(validation.get("blocking_runtime_reasons")),
                    "evidence_references": evidence_references,
                }
            )
            continue
        if validation_conf < 0.72:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "runtime_validation_confidence_below_threshold",
                    "validation_confidence": validation_conf,
                    "evidence_references": evidence_references,
                }
            )
            continue

        selected.append(
            {
                "construct": construct,
                "replacement": replacement,
                "pilot_category": category,
                "candidate_confidence": round(conf, 3),
                "validation_confidence": round(validation_conf, 3),
                "runtime_equivalent": runtime_equivalent,
                "runtime_safe": runtime_safe,
                "file_hints": file_hints,
                "subsystem": subsystem,
                "evidence_references": sorted(set(_as_list(item.get("evidence_sources")) + evidence_references)),
            }
        )
    selected = sorted(
        selected,
        key=lambda row: (
            str(_as_dict(row).get("pilot_category", "")),
            str(_as_dict(row).get("construct", "")),
        ),
    )
    return selected[:12], blocked


def _apply_pilot_transformations(
    *,
    source_snapshots: Mapping[str, str],
    selected_candidates: list[Mapping[str, Any]],
    constrained_subsystem: str,
    evidence_references: list[str],
    dry_run: bool,
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    original = {str(path): str(content) for path, content in sorted(_as_dict(source_snapshots).items())}
    transformed = dict(original)

    segments: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    patch_chunks: list[dict[str, Any]] = []
    seg_id = 0
    chunk_id = 0

    for row in selected_candidates:
        item = _as_dict(row)
        construct = str(item.get("construct", ""))
        replacement = str(item.get("replacement", ""))
        category = str(item.get("pilot_category", "isolated_subsystem_utility_conversion"))
        found_any = False
        for path in sorted(transformed.keys()):
            before = transformed[path]
            file_subsystem = _infer_subsystem(path, construct, category)
            if constrained_subsystem and file_subsystem != constrained_subsystem:
                continue
            after, count = _replace_identifier_tokens(before, construct, replacement)
            if count <= 0:
                continue
            if count > 20:
                blocked.append(
                    {
                        "construct": construct,
                        "replacement": replacement,
                        "reason": "replacement_count_exceeds_pilot_limit",
                        "file": path,
                        "replacement_count": int(count),
                        "evidence_references": sorted(
                            set(_as_list(item.get("evidence_references")) + evidence_references)
                        ),
                    }
                )
                continue
            found_any = True
            transformed[path] = after
            seg_id += 1
            segment = {
                "segment_id": f"pilot_segment:{seg_id}",
                "file": path,
                "subsystem": file_subsystem,
                "pilot_category": category,
                "downstream_construct": construct,
                "upstream_replacement": replacement,
                "replacement_count": int(count),
                "dry_run": bool(dry_run),
                "runtime_validation_confidence": _to_float(item.get("validation_confidence", 0.0), 0.0),
                "candidate_confidence": _to_float(item.get("candidate_confidence", 0.0), 0.0),
                "before_fingerprint": stable_fingerprint({"file": path, "content": before}),
                "after_fingerprint": stable_fingerprint({"file": path, "content": after}),
                "evidence_references": sorted(set(_as_list(item.get("evidence_references")) + evidence_references)),
            }
            segment["deterministic_fingerprint"] = stable_fingerprint(segment)
            segments.append(segment)

            chunk_id += 1
            chunk = {
                "chunk_id": f"pilot_chunk:{chunk_id}",
                "segment_id": segment["segment_id"],
                "file": path,
                "subsystem": file_subsystem,
                "rollback_order": chunk_id,
                "deterministic_fingerprint": stable_fingerprint(
                    {
                        "chunk_id": f"pilot_chunk:{chunk_id}",
                        "segment_fingerprint": segment["deterministic_fingerprint"],
                    }
                ),
            }
            patch_chunks.append(chunk)
        if not found_any:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "source_construct_not_found",
                    "pilot_category": category,
                    "evidence_references": sorted(set(_as_list(item.get("evidence_references")) + evidence_references)),
                }
            )

    return transformed, segments, blocked, patch_chunks


def _build_runtime_equivalence_validation(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    selected_candidates: list[Mapping[str, Any]],
    applied_segments: list[Mapping[str, Any]],
    acceptance_confidence_score: Mapping[str, Any],
    regression_risk_assessment: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    cross_subsystem_violation: bool,
    evidence_references: list[str],
) -> dict[str, Any]:
    acceptance_class = str(_as_dict(acceptance_confidence_score).get("classification", "UNKNOWN"))
    acceptance_confidence = _to_float(_as_dict(acceptance_confidence_score).get("acceptance_confidence", 0.0), 0.0)
    regression_conf = _to_float(_as_dict(regression_risk_assessment).get("regression_containment_confidence", 0.0), 0.0)
    topology_class = str(_as_dict(topology_runtime_graph).get("classification", "UNKNOWN")).upper()
    runtime_conf = _to_float(_as_dict(_as_dict(runtime_equivalence_fingerprint).get("summary")).get("mean_runtime_backed_confidence", 0.0), 0.0)

    replay_ok = bool(_as_dict(replay_traces).get("deterministic_event_ordering", False))
    runtime_ok = all(bool(_as_dict(row).get("runtime_equivalent", False)) for row in selected_candidates)
    structure_ok = len(applied_segments) > 0 and not cross_subsystem_violation
    topology_ok = topology_class in {"PASS", "ADVISORY_ONLY", "UNKNOWN"}
    acceptance_ok = acceptance_class == "PASS" and acceptance_confidence >= 0.78
    regression_ok = regression_conf >= 0.72
    validation_conf_ok = all(_to_float(_as_dict(row).get("validation_confidence", 0.0), 0.0) >= 0.72 for row in selected_candidates)

    fail_reasons: list[str] = []
    if not runtime_ok:
        fail_reasons.append("runtime_equivalence_validation_failed")
    if not validation_conf_ok:
        fail_reasons.append("runtime_validation_confidence_below_threshold")
    if not structure_ok:
        fail_reasons.append("structural_topology_consistency_violation")
    if not acceptance_ok:
        fail_reasons.append("upstream_acceptance_simulation_failed")
    if not regression_ok:
        fail_reasons.append("regression_containment_verification_failed")
    if not replay_ok:
        fail_reasons.append("runtime_equivalence_replay_validation_failed")
    if runtime_conf < 0.72:
        fail_reasons.append("runtime_backed_equivalence_confidence_below_threshold")

    classification = "PASS" if not fail_reasons else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_equivalence_validation",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "candidate_validations": [
            {
                "downstream_construct": str(_as_dict(row).get("construct", "")),
                "upstream_replacement": str(_as_dict(row).get("replacement", "")),
                "pilot_category": str(_as_dict(row).get("pilot_category", "")),
                "runtime_equivalent": bool(_as_dict(row).get("runtime_equivalent", False)),
                "validation_confidence": _to_float(_as_dict(row).get("validation_confidence", 0.0), 0.0),
            }
            for row in selected_candidates
        ],
        "validation_dimensions": {
            "runtime_equivalence_replay_validation": replay_ok and runtime_ok and validation_conf_ok,
            "structural_topology_consistency_validation": structure_ok and topology_ok,
            "upstream_acceptance_simulation_validation": acceptance_ok,
            "regression_containment_verification": regression_ok,
            "rollback_replay_integrity_validation": len(applied_segments) > 0 and replay_ok,
            "governance_threshold_enforcement": acceptance_ok and regression_ok and runtime_conf >= 0.72,
        },
        "summary": {
            "candidate_count": len(selected_candidates),
            "applied_segment_count": len(applied_segments),
            "acceptance_confidence": acceptance_confidence,
            "regression_containment_confidence": regression_conf,
            "runtime_backed_equivalence_confidence": runtime_conf,
            "cross_subsystem_violation": bool(cross_subsystem_violation),
        },
        "fail_closed_reasons": sorted(set(fail_reasons)),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_pilot_risk_assessment(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    selected_candidates: list[Mapping[str, Any]],
    changed_files: list[str],
    acceptance_confidence_score: Mapping[str, Any],
    regression_risk_assessment: Mapping[str, Any],
    runtime_equivalence_fingerprint: Mapping[str, Any],
    cross_subsystem_violation: bool,
    evidence_references: list[str],
) -> dict[str, Any]:
    acceptance_conf = _to_float(_as_dict(acceptance_confidence_score).get("acceptance_confidence", 0.0), 0.0)
    regression_conf = _to_float(_as_dict(regression_risk_assessment).get("regression_containment_confidence", 0.0), 0.0)
    runtime_conf = _to_float(_as_dict(_as_dict(runtime_equivalence_fingerprint).get("summary")).get("mean_runtime_backed_confidence", 0.0), 0.0)
    candidate_count = len(selected_candidates)
    file_count = len(changed_files)

    risk_score = round(
        max(
            0.0,
            min(
                1.0,
                0.30 * min(1.0, candidate_count / 8.0)
                + 0.15 * min(1.0, file_count / 3.0)
                + 0.20 * (1.0 - acceptance_conf)
                + 0.20 * (1.0 - regression_conf)
                + 0.10 * (1.0 - runtime_conf)
                + 0.05 * (1.0 if cross_subsystem_violation else 0.0),
            ),
        ),
        3,
    )

    risk_class = "LOW"
    if risk_score >= 0.58:
        risk_class = "HIGH"
    elif risk_score >= 0.34:
        risk_class = "MEDIUM"

    classification = "PASS" if risk_score < 0.45 and not cross_subsystem_violation else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "pilot_risk_assessment",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "risk_score": risk_score,
        "risk_classification": risk_class,
        "signals": {
            "candidate_count": candidate_count,
            "changed_file_count": file_count,
            "acceptance_confidence": acceptance_conf,
            "regression_containment_confidence": regression_conf,
            "runtime_backed_equivalence_confidence": runtime_conf,
            "cross_subsystem_violation": bool(cross_subsystem_violation),
        },
        "summary": {
            "low_risk_targeted_scope": candidate_count <= 12 and file_count <= 3,
            "pilot_mode": True,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_governance_decision_report(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    governance_state: Mapping[str, Any],
    governance_ok: bool,
    governance_violations: list[str],
    runtime_equivalence_validation: Mapping[str, Any],
    pilot_risk_assessment: Mapping[str, Any],
    acceptance_confidence_score: Mapping[str, Any],
    unsupported_vendor_constructs: Mapping[str, Any],
    cross_subsystem_violation: bool,
    blocked_candidates: list[Mapping[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    runtime_class = str(_as_dict(runtime_equivalence_validation).get("classification", "UNKNOWN"))
    risk_class = str(_as_dict(pilot_risk_assessment).get("classification", "UNKNOWN"))
    acceptance_class = str(_as_dict(acceptance_confidence_score).get("classification", "UNKNOWN"))
    unsupported_count = int(_as_dict(_as_dict(unsupported_vendor_constructs).get("summary")).get("unsupported_count", 0) or 0)

    fail_reasons: list[str] = []
    if not governance_ok:
        fail_reasons.extend(governance_violations)
    if runtime_class != "PASS":
        fail_reasons.append("runtime_equivalence_validation_failed")
    if risk_class != "PASS":
        fail_reasons.append("pilot_risk_above_threshold")
    if acceptance_class != "PASS":
        fail_reasons.append("upstream_acceptance_threshold_not_met")
    if unsupported_count > 0:
        fail_reasons.append("unsupported_vendor_abstractions_unresolved")
    if cross_subsystem_violation:
        fail_reasons.append("cross_subsystem_transformations_prohibited")
    if blocked_candidates:
        fail_reasons.append("pilot_scope_limiter_rejections_present")

    classification = "PASS" if not fail_reasons else "FAIL_CLOSED"
    escalation_required = classification == "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "governance_decision_report",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "governance_policy": {
            "default_mode": "FAIL_CLOSED",
            "human_review_required": True,
            "autonomous_patch_application_allowed": False,
            "unsupported_vendor_blocks_execution": True,
            "cross_subsystem_pilot_forbidden": True,
            "runtime_backed_equivalence_required": True,
        },
        "decision": {
            "pilot_transformation_authorized": classification == "PASS",
            "delivery_authorization": False,
            "escalation_required": escalation_required,
            "escalation_level": "L2_ENGINEERING_REVIEW" if escalation_required else "NONE",
            "escalation_reasons": sorted(set(fail_reasons)),
        },
        "summary": {
            "blocked_candidate_count": len(blocked_candidates),
            "unsupported_vendor_count": unsupported_count,
            "cross_subsystem_violation": bool(cross_subsystem_violation),
        },
        "governance_state": dict(governance_state),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_transformation_explainability_report(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    selected_candidates: list[Mapping[str, Any]],
    applied_segments: list[Mapping[str, Any]],
    blocked_candidates: list[Mapping[str, Any]],
    runtime_equivalence_validation: Mapping[str, Any],
    governance_decision_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    segment_by_key = {
        f"{str(_as_dict(seg).get('downstream_construct', '')).lower()}->{str(_as_dict(seg).get('upstream_replacement', '')).lower()}": _as_dict(seg)
        for seg in applied_segments
    }
    explain_rows: list[dict[str, Any]] = []
    for row in selected_candidates:
        item = _as_dict(row)
        key = f"{str(item.get('construct', '')).lower()}->{str(item.get('replacement', '')).lower()}"
        seg = _as_dict(segment_by_key.get(key))
        explain_rows.append(
            {
                "downstream_construct": str(item.get("construct", "")),
                "upstream_replacement": str(item.get("replacement", "")),
                "pilot_category": str(item.get("pilot_category", "")),
                "applied": bool(seg),
                "file": str(seg.get("file", "")),
                "replacement_count": int(seg.get("replacement_count", 0) or 0),
                "reasoning_chain": [
                    "runtime_evidence_correlation",
                    "translation_proposal_validation",
                    "upstream_acceptance_simulation_gate",
                    "governance_scoring_gate",
                    "scope_limiter_enforcement",
                    "human_review_packaging",
                ],
                "confidence": round(
                    max(
                        0.0,
                        min(
                            1.0,
                            0.5 * _to_float(item.get("candidate_confidence", 0.0), 0.0)
                            + 0.5 * _to_float(item.get("validation_confidence", 0.0), 0.0),
                        ),
                    ),
                    3,
                ),
                "evidence_references": sorted(set(_as_list(item.get("evidence_references")) + evidence_references)),
            }
        )

    payload = {
        "schema_version": "1.0",
        "report_name": "transformation_explainability_report",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
        "explanations": explain_rows,
        "scope_rejections": [
            {
                "construct": str(_as_dict(row).get("construct", "")),
                "replacement": str(_as_dict(row).get("replacement", "")),
                "reason": str(_as_dict(row).get("reason", "")),
            }
            for row in blocked_candidates
        ],
        "validation_linkage": {
            "runtime_equivalence_validation_fingerprint": str(
                _as_dict(runtime_equivalence_validation).get("deterministic_fingerprint", "")
            ),
            "governance_decision_fingerprint": str(
                _as_dict(governance_decision_report).get("deterministic_fingerprint", "")
            ),
        },
        "summary": {
            "candidate_count": len(selected_candidates),
            "applied_count": len([row for row in explain_rows if bool(_as_dict(row).get("applied", False))]),
            "scope_rejection_count": len(blocked_candidates),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_transformation_lineage(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    applied_segments: list[Mapping[str, Any]],
    patch_chunks: list[Mapping[str, Any]],
    dry_run: bool,
    evidence_references: list[str],
) -> dict[str, Any]:
    ordered_segments = sorted(
        [_as_dict(row) for row in applied_segments],
        key=lambda row: (
            str(_as_dict(row).get("subsystem", "")),
            str(_as_dict(row).get("file", "")),
            str(_as_dict(row).get("downstream_construct", "")),
        ),
    )
    payload = {
        "schema_version": "1.0",
        "report_name": "transformation_lineage",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": "PASS" if ordered_segments else "FAIL_CLOSED",
        "dry_run": bool(dry_run),
        "execution_flow": [
            "Reason",
            "Runtime evidence correlation",
            "Translation proposal",
            "Acceptance simulation",
            "Governance scoring",
            "Pilot transformation generation",
            "Human review packaging",
            "Replay persistence",
            "Rollback validation",
        ],
        "segments": ordered_segments,
        "patch_chunks": [dict(_as_dict(row)) for row in patch_chunks],
        "summary": {
            "segment_count": len(ordered_segments),
            "chunk_count": len(patch_chunks),
            "rollback_safe_chunking": len(ordered_segments) == len(patch_chunks) and len(ordered_segments) > 0,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_rollback_validation_report(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    transformation_lineage: Mapping[str, Any],
    runtime_equivalence_validation: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    lineage = _as_dict(transformation_lineage)
    segments = [_as_dict(row) for row in _as_list(lineage.get("segments")) if isinstance(row, dict)]
    chunks = [_as_dict(row) for row in _as_list(lineage.get("patch_chunks")) if isinstance(row, dict)]
    replay_ok = bool(_as_dict(replay_traces).get("deterministic_event_ordering", False))

    integrity = (
        len(segments) > 0
        and len(segments) == len(chunks)
        and all(str(seg.get("before_fingerprint", "")).strip() and str(seg.get("after_fingerprint", "")).strip() for seg in segments)
    )
    validation_class = str(_as_dict(runtime_equivalence_validation).get("classification", "UNKNOWN"))
    classification = "PASS" if integrity and replay_ok and validation_class == "PASS" else "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "rollback_validation_report",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "rollback_steps": [
            {
                "step": idx,
                "chunk_id": str(_as_dict(chunk).get("chunk_id", "")),
                "segment_id": str(_as_dict(chunk).get("segment_id", "")),
                "rollback_order": idx,
            }
            for idx, chunk in enumerate(reversed(chunks), start=1)
        ],
        "summary": {
            "segment_count": len(segments),
            "chunk_count": len(chunks),
            "replay_ordering_stable": replay_ok,
            "rollback_integrity": integrity,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_upstream_review_package(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    patch_text: str,
    changed_files: list[str],
    transformation_lineage: Mapping[str, Any],
    runtime_equivalence_validation: Mapping[str, Any],
    governance_decision_report: Mapping[str, Any],
    acceptance_confidence_score: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    patch_stats = _parse_patch_diff(patch_text)
    governance_class = str(_as_dict(governance_decision_report).get("classification", "UNKNOWN"))
    runtime_class = str(_as_dict(runtime_equivalence_validation).get("classification", "UNKNOWN"))
    acceptance_conf = _to_float(_as_dict(acceptance_confidence_score).get("acceptance_confidence", 0.0), 0.0)

    classification = "PASS" if governance_class == "PASS" and runtime_class == "PASS" else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_review_package",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "patch_proposal": {
            "changed_files": changed_files,
            "patch_statistics": patch_stats,
            "lineage_fingerprint": str(_as_dict(transformation_lineage).get("deterministic_fingerprint", "")),
        },
        "review_checklist": [
            "validate runtime-backed equivalence evidence citations",
            "validate subsystem isolation and maintainership scope",
            "validate bisect-safe ordering and rollback chunks",
            "validate no unresolved unsupported vendor abstractions",
            "validate acceptance confidence and governance decision",
            "approve/reject human-reviewed upstream proposal",
        ],
        "patch_justification_synthesis": {
            "acceptance_confidence": acceptance_conf,
            "runtime_equivalence_classification": runtime_class,
            "governance_classification": governance_class,
            "human_review_required": True,
        },
        "runtime_evidence_citations": [
            {
                "source": "artifact://runtime_equivalence_validation",
                "fingerprint": str(_as_dict(runtime_equivalence_validation).get("deterministic_fingerprint", "")),
            },
            {
                "source": "artifact://governance_decision_report",
                "fingerprint": str(_as_dict(governance_decision_report).get("deterministic_fingerprint", "")),
            },
        ],
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class ControlledPilotConversionEngine:
    """Governed pilot conversion orchestration engine."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        source_snapshots: Mapping[str, str],
        translation_artifacts: Mapping[str, Any],
        execution_artifacts: Mapping[str, Any],
        acceptance_artifacts: Mapping[str, Any],
        runtime_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        dry_run: bool,
        evidence_references: list[str] | None,
        previous_pilot_history: list[Mapping[str, Any]] | None,
    ) -> ControlledPilotConversionResult:
        plugin = self._plugins.load_plugin(target_id)
        runtime_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_equivalence_fingerprint")),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                }
            )
        )
        validation_adapter = _as_dict(
            plugin.validation_provider(
                {
                    "target_id": str(target_id),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        api_replacement_map = _as_dict(translation_artifacts.get("api_replacement_map"))
        unsupported_vendor_constructs = _as_dict(translation_artifacts.get("unsupported_vendor_constructs"))
        translation_runtime_equivalence = _as_dict(translation_artifacts.get("runtime_equivalence_validation"))

        runtime_validated_patch_segments = _as_dict(execution_artifacts.get("runtime_validated_patch_segments"))
        translation_execution_report = _as_dict(execution_artifacts.get("translation_execution_report"))
        acceptance_confidence_score = _as_dict(acceptance_artifacts.get("acceptance_confidence_score"))
        upstream_acceptance_report = _as_dict(acceptance_artifacts.get("upstream_acceptance_report"))
        regression_risk_assessment = _as_dict(acceptance_artifacts.get("regression_risk_assessment"))

        runtime_equivalence_fingerprint = _as_dict(runtime_artifacts.get("runtime_equivalence_fingerprint"))
        topology_runtime_graph = _as_dict(runtime_artifacts.get("topology_runtime_graph"))

        governance_ok, governance_violations = _governance_clean(governance_state)

        hard_block_reasons: list[str] = []
        unsupported_count = int(_as_dict(unsupported_vendor_constructs.get("summary")).get("unsupported_count", 0) or 0)
        acceptance_class = str(acceptance_confidence_score.get("classification", "UNKNOWN"))
        acceptance_conf = _to_float(acceptance_confidence_score.get("acceptance_confidence", 0.0), 0.0)
        translation_exec_class = str(translation_execution_report.get("classification", "UNKNOWN"))
        translation_runtime_class = str(translation_runtime_equivalence.get("classification", "UNKNOWN"))

        if not governance_ok:
            hard_block_reasons.extend(governance_violations)
        if unsupported_count > 0:
            hard_block_reasons.append("unsupported_vendor_abstractions_unresolved")
        if acceptance_class != "PASS" or acceptance_conf < 0.78:
            hard_block_reasons.append("upstream_acceptance_threshold_not_met")
        if translation_exec_class != "PASS":
            hard_block_reasons.append("translation_execution_not_pass")
        if translation_runtime_class == "FAIL_CLOSED":
            hard_block_reasons.append("runtime_equivalence_fail_closed")

        runtime_validation_map = _build_runtime_validation_map(translation_runtime_equivalence)
        segment_hints = _segment_map(runtime_validated_patch_segments)
        selected_candidates, blocked_candidates = _derive_candidates(
            api_replacement_map=api_replacement_map,
            runtime_validation_map=runtime_validation_map,
            segment_hints=segment_hints,
            evidence_references=evidence,
        )

        selected_subsystems = {
            str(_as_dict(row).get("subsystem", "")).strip()
            for row in selected_candidates
            if str(_as_dict(row).get("subsystem", "")).strip()
        }
        cross_subsystem_violation = len(selected_subsystems) > 1
        constrained_subsystem = next(iter(selected_subsystems)) if len(selected_subsystems) == 1 else ""
        if cross_subsystem_violation:
            hard_block_reasons.append("cross_subsystem_transformations_prohibited")
        if not selected_candidates:
            hard_block_reasons.append("no_runtime_validated_low_risk_candidates")
        if not _as_dict(source_snapshots):
            hard_block_reasons.append("source_snapshots_missing")

        transformed_sources = {str(path): str(content) for path, content in _as_dict(source_snapshots).items()}
        applied_segments: list[dict[str, Any]] = []
        apply_blocked: list[dict[str, Any]] = []
        patch_chunks: list[dict[str, Any]] = []

        if not hard_block_reasons:
            transformed_sources, applied_segments, apply_blocked, patch_chunks = _apply_pilot_transformations(
                source_snapshots=source_snapshots,
                selected_candidates=selected_candidates,
                constrained_subsystem=constrained_subsystem,
                evidence_references=evidence,
                dry_run=bool(dry_run),
            )
        blocked_candidates = blocked_candidates + apply_blocked
        if not applied_segments:
            hard_block_reasons.append("no_transformations_applied")

        patch_text, changed_files = _build_patch(
            original_sources={str(path): str(content) for path, content in _as_dict(source_snapshots).items()},
            transformed_sources=transformed_sources,
            dry_run=bool(dry_run),
        )
        classification = "PASS" if not hard_block_reasons else "FAIL_CLOSED"
        if classification == "FAIL_CLOSED":
            changed_files = []
            patch_text = "\n".join(
                [
                    "# Controlled Pilot Conversion Patch",
                    "# mode=blocked",
                    f"# fail_closed_justification={';'.join(sorted(set(hard_block_reasons)))}",
                    "",
                ]
            )
            applied_segments = []
            patch_chunks = []

        runtime_equivalence_validation = _build_runtime_equivalence_validation(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            selected_candidates=selected_candidates,
            applied_segments=applied_segments,
            acceptance_confidence_score=acceptance_confidence_score,
            regression_risk_assessment=regression_risk_assessment,
            topology_runtime_graph=topology_runtime_graph,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            replay_traces=replay_traces,
            cross_subsystem_violation=cross_subsystem_violation,
            evidence_references=evidence,
        )

        pilot_risk_assessment = _build_pilot_risk_assessment(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            selected_candidates=selected_candidates,
            changed_files=changed_files,
            acceptance_confidence_score=acceptance_confidence_score,
            regression_risk_assessment=regression_risk_assessment,
            runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
            cross_subsystem_violation=cross_subsystem_violation,
            evidence_references=evidence,
        )

        governance_decision_report = _build_governance_decision_report(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            governance_state=governance_state,
            governance_ok=governance_ok,
            governance_violations=governance_violations,
            runtime_equivalence_validation=runtime_equivalence_validation,
            pilot_risk_assessment=pilot_risk_assessment,
            acceptance_confidence_score=acceptance_confidence_score,
            unsupported_vendor_constructs=unsupported_vendor_constructs,
            cross_subsystem_violation=cross_subsystem_violation,
            blocked_candidates=blocked_candidates,
            evidence_references=evidence,
        )

        transformation_lineage = _build_transformation_lineage(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            applied_segments=applied_segments,
            patch_chunks=patch_chunks,
            dry_run=bool(dry_run),
            evidence_references=evidence,
        )

        rollback_validation_report = _build_rollback_validation_report(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            transformation_lineage=transformation_lineage,
            runtime_equivalence_validation=runtime_equivalence_validation,
            replay_traces=replay_traces,
            evidence_references=evidence,
        )

        transformation_explainability_report = _build_transformation_explainability_report(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            selected_candidates=selected_candidates,
            applied_segments=applied_segments,
            blocked_candidates=blocked_candidates,
            runtime_equivalence_validation=runtime_equivalence_validation,
            governance_decision_report=governance_decision_report,
            evidence_references=evidence,
        )

        upstream_review_package = _build_upstream_review_package(
            target_id=str(target_id),
            session_id=str(session_id),
            lineage_id=str(lineage_id),
            patch_text=patch_text,
            changed_files=changed_files,
            transformation_lineage=transformation_lineage,
            runtime_equivalence_validation=runtime_equivalence_validation,
            governance_decision_report=governance_decision_report,
            acceptance_confidence_score=acceptance_confidence_score,
            evidence_references=evidence,
        )

        deterministic_pilot_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_pilot_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
            "artifact_fingerprints": {
                "transformation_explainability_report": str(
                    _as_dict(transformation_explainability_report).get("deterministic_fingerprint", "")
                ),
                "runtime_equivalence_validation": str(
                    _as_dict(runtime_equivalence_validation).get("deterministic_fingerprint", "")
                ),
                "upstream_review_package": str(_as_dict(upstream_review_package).get("deterministic_fingerprint", "")),
                "pilot_risk_assessment": str(_as_dict(pilot_risk_assessment).get("deterministic_fingerprint", "")),
                "transformation_lineage": str(_as_dict(transformation_lineage).get("deterministic_fingerprint", "")),
                "rollback_validation_report": str(
                    _as_dict(rollback_validation_report).get("deterministic_fingerprint", "")
                ),
                "governance_decision_report": str(
                    _as_dict(governance_decision_report).get("deterministic_fingerprint", "")
                ),
            },
            "replay_signal": {
                "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            "history": [row for row in _as_list(previous_pilot_history or []) if isinstance(row, dict)]
            + [
                {
                    "lineage_id": str(lineage_id),
                    "session_id": str(session_id),
                    "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
                    "pilot_fingerprint": "",
                }
            ],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_pilot_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_pilot_replay)

        pilot_conversion_patch = {
            "schema_version": "1.0",
            "report_name": "pilot_conversion_patch",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
            "changed_files": changed_files,
            "dry_run": bool(dry_run),
            "patch_text": patch_text,
            "deterministic_fingerprint": stable_fingerprint(
                {
                    "target_id": str(target_id),
                    "session_id": str(session_id),
                    "lineage_id": str(lineage_id),
                    "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
                    "changed_files": changed_files,
                    "patch_text": patch_text,
                    "dry_run": bool(dry_run),
                }
            ),
        }

        artifacts = {
            "pilot_conversion_patch": pilot_conversion_patch,
            "transformation_explainability_report": transformation_explainability_report,
            "runtime_equivalence_validation": runtime_equivalence_validation,
            "upstream_review_package": upstream_review_package,
            "pilot_risk_assessment": pilot_risk_assessment,
            "transformation_lineage": transformation_lineage,
            "rollback_validation_report": rollback_validation_report,
            "deterministic_pilot_replay": deterministic_pilot_replay,
            "governance_decision_report": governance_decision_report,
        }

        pilot_fingerprint = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
                "dry_run": bool(dry_run),
                "artifact_fingerprints": {
                    key: str(_as_dict(value).get("deterministic_fingerprint", ""))
                    for key, value in sorted(artifacts.items())
                },
                "adapter_fingerprints": {
                    "runtime_conversion": str(runtime_adapter.get("fingerprint", "")),
                    "validation_provider": str(validation_adapter.get("fingerprint", "")),
                },
            }
        )
        deterministic_pilot_replay["history"] = [
            dict(_as_dict(row), pilot_fingerprint=str(_as_dict(row).get("pilot_fingerprint", "")))
            for row in _as_list(deterministic_pilot_replay.get("history"))
        ]
        if deterministic_pilot_replay["history"]:
            deterministic_pilot_replay["history"][-1]["pilot_fingerprint"] = pilot_fingerprint
        deterministic_pilot_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_pilot_replay)

        bundle = {
            "schema_version": "1.0",
            "phase": "CONTROLLED_DOWNSTREAM_TO_UPSTREAM_PILOT_CONVERSION_FRAMEWORK",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(governance_decision_report).get("classification", "UNKNOWN")),
            "dry_run": bool(dry_run),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime_conversion": runtime_adapter,
                "validation_provider": validation_adapter,
            },
            "upstream_acceptance_validation": {
                "classification": str(_as_dict(upstream_acceptance_report).get("classification", "UNKNOWN")),
                "acceptance_confidence": acceptance_conf,
            },
            "flow": [
                "Reason",
                "Runtime evidence correlation",
                "Translation proposal",
                "Acceptance simulation",
                "Governance scoring",
                "Pilot transformation generation",
                "Human review packaging",
                "Replay persistence",
                "Rollback validation",
            ],
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["controlled_pilot_conversion_fingerprint"] = pilot_fingerprint
        return ControlledPilotConversionResult(pilot_bundle=bundle)


class ControlledPilotConversionRegistry:
    """Replay-safe persistence for pilot conversion artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "pilot_conversion_patch": self._output_dir / "pilot_conversion_patch.diff",
            "transformation_explainability_report": self._output_dir / "transformation_explainability_report.json",
            "runtime_equivalence_validation": self._output_dir / "runtime_equivalence_validation.json",
            "upstream_review_package": self._output_dir / "upstream_review_package.json",
            "pilot_risk_assessment": self._output_dir / "pilot_risk_assessment.json",
            "transformation_lineage": self._output_dir / "transformation_lineage.json",
            "rollback_validation_report": self._output_dir / "rollback_validation_report.json",
            "deterministic_pilot_replay": self._output_dir / "deterministic_pilot_replay.json",
            "governance_decision_report": self._output_dir / "governance_decision_report.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        patch_payload = _as_dict(artifacts.get("pilot_conversion_patch"))
        patch_text = str(patch_payload.get("patch_text", ""))
        paths["pilot_conversion_patch"].parent.mkdir(parents=True, exist_ok=True)
        paths["pilot_conversion_patch"].write_text(patch_text, encoding="utf-8")

        for key in (
            "transformation_explainability_report",
            "runtime_equivalence_validation",
            "upstream_review_package",
            "pilot_risk_assessment",
            "transformation_lineage",
            "rollback_validation_report",
            "deterministic_pilot_replay",
            "governance_decision_report",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("controlled_pilot_conversion"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "controlled_pilot_conversion_fingerprint": str(payload.get("controlled_pilot_conversion_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-8000:]

        registry["controlled_pilot_conversion"] = {
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
                "type": "controlled_pilot_conversion",
                "recorded_at": _utc_now_iso(),
                "controlled_pilot_conversion_fingerprint": str(payload.get("controlled_pilot_conversion_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-26000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "controlled_pilot_conversion_fingerprint": entry["controlled_pilot_conversion_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("controlled_pilot_conversion"))
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
            "replay_type": "controlled_pilot_conversion",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "controlled_pilot_conversion_fingerprint": str(
                _as_dict(selected).get("controlled_pilot_conversion_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "controlled_pilot_conversion_fingerprint": str(
                        _as_dict(selected).get("controlled_pilot_conversion_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_pilot_replay.json", replay_payload)
        return replay_payload
