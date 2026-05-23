"""Governed translation execution layer.

Consumes translation intelligence artifacts and performs deterministic, AST-aware
source transformations under strict fail-closed governance.
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


@dataclass(frozen=True)
class GovernedTranslationExecutionResult:
    execution_bundle: dict[str, Any]


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
    violations: list[str] = []

    if not bool(governance.get("fail_closed_posture", True)):
        violations.append("fail_closed_posture_disabled")

    for flag in (
        "autonomous_patching_allowed",
        "autonomous_topology_rewrite_allowed",
        "autonomous_runtime_mutation_allowed",
        "autonomous_upstream_generation_allowed",
    ):
        if _is_true(governance.get(flag, False)):
            violations.append(f"governance_violation:{flag}")

    return (len(violations) == 0, violations)


def _category_for_construct(construct: str) -> str:
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


def _stage_index_map(upstream_translation_plan: Mapping[str, Any]) -> dict[str, int]:
    stages = _as_list(_as_dict(upstream_translation_plan).get("ast_aware_conversion_plan", {}).get("stages", []))
    mapping: dict[str, int] = {}
    for idx, row in enumerate(stages, start=1):
        stage_id = str(_as_dict(row).get("stage_id", "")).strip()
        if stage_id:
            mapping[stage_id] = idx
    if not mapping:
        mapping = {
            "phase_pcm_lifecycle_translation": 1,
            "phase_dapm_route_equivalence": 2,
            "phase_soundwire_mapping": 3,
            "phase_vendor_callback_abstraction": 4,
        }
    return mapping


def _stage_for_category(category: str) -> str:
    if category == "callback_replacement":
        return "phase_vendor_callback_abstraction"
    if category == "vendor_macro_elimination":
        return "phase_vendor_callback_abstraction"
    if category == "fe_be_topology_rewrite_scaffolding":
        return "phase_dapm_route_equivalence"
    if category == "dapm_route_conversion_generation":
        return "phase_dapm_route_equivalence"
    if category == "soundwire_upstream_adaptation":
        return "phase_soundwire_mapping"
    return "phase_pcm_lifecycle_translation"


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


def _replace_identifier_tokens(code: str, old: str, new: str) -> tuple[str, int]:
    """C-lexical token replacement (ignores comments/strings/chars)."""

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
    patch_chunks: list[str] = []
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
        patch_chunks.append("".join(diff))

    header = [
        "# Governed Translation Execution Patch",
        f"# mode={'dry-run' if dry_run else 'emit'}",
        "",
    ]

    patch_text = "\n".join(header) + "\n" + "\n".join(patch_chunks)
    return patch_text, changed_files


def _candidate_transformations(
    *,
    api_replacement_map: Mapping[str, Any],
    runtime_validation_map: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    replacements = [row for row in _as_list(_as_dict(api_replacement_map).get("replacements")) if isinstance(row, dict)]

    valid: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for row in replacements:
        item = _as_dict(row)
        construct = str(item.get("downstream_construct", "")).strip()
        replacement = str(item.get("upstream_replacement", "")).strip()
        candidate_confidence = _to_float(item.get("candidate_confidence", 0.0), 0.0)
        runtime_safe = bool(item.get("runtime_safe", False))

        key = construct.lower()
        validation = _as_dict(runtime_validation_map.get(key))

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

        if not _IDENT_RE.match(construct):
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "downstream_construct_not_ast_identifier",
                    "evidence_references": evidence_references,
                }
            )
            continue

        if not _IDENT_RE.match(replacement):
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "upstream_replacement_not_ast_identifier",
                    "evidence_references": evidence_references,
                }
            )
            continue

        if candidate_confidence < 0.70:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "candidate_confidence_below_threshold",
                    "candidate_confidence": candidate_confidence,
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

        if not validation:
            blocked.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "reason": "missing_runtime_equivalence_validation",
                    "evidence_references": evidence_references,
                }
            )
            continue

        if not bool(validation.get("runtime_equivalent", False)):
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

        validation_conf = _to_float(validation.get("validation_confidence", 0.0), 0.0)
        if validation_conf < 0.62:
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

        category = _category_for_construct(construct)
        valid.append(
            {
                "construct": construct,
                "replacement": replacement,
                "category": category,
                "candidate_confidence": round(candidate_confidence, 3),
                "validation_confidence": round(validation_conf, 3),
                "runtime_safe": True,
                "evidence_references": sorted(set(_as_list(item.get("evidence_sources")) + evidence_references)),
            }
        )

    return valid, blocked


def _apply_transformations(
    *,
    sources: Mapping[str, str],
    candidates: list[Mapping[str, Any]],
    stage_order: Mapping[str, int],
    dry_run: bool,
    evidence_references: list[str],
) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    original = {str(path): str(content) for path, content in sorted(_as_dict(sources).items())}
    transformed = dict(original)

    applied_segments: list[dict[str, Any]] = []
    unsafe_blocks: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []

    sorted_candidates = sorted(
        [_as_dict(row) for row in candidates],
        key=lambda row: (
            int(stage_order.get(_stage_for_category(str(row.get("category", ""))), 999)),
            str(_as_dict(row).get("category", "")),
            str(_as_dict(row).get("construct", "")),
        ),
    )

    segment_seq = 0
    chunk_seq = 0

    for cand in sorted_candidates:
        construct = str(cand.get("construct", ""))
        replacement = str(cand.get("replacement", ""))
        category = str(cand.get("category", "runtime_safe_api_substitution"))
        stage_id = _stage_for_category(category)

        found_any = False
        for path in sorted(transformed.keys()):
            before = transformed[path]
            after, count = _replace_identifier_tokens(before, construct, replacement)
            if count <= 0:
                continue

            found_any = True
            transformed[path] = after

            segment_seq += 1
            segment = {
                "segment_id": f"segment:{segment_seq}",
                "file": path,
                "stage_id": stage_id,
                "category": category,
                "downstream_construct": construct,
                "upstream_replacement": replacement,
                "replacement_count": int(count),
                "dry_run": bool(dry_run),
                "runtime_validation_confidence": _to_float(cand.get("validation_confidence", 0.0), 0.0),
                "candidate_confidence": _to_float(cand.get("candidate_confidence", 0.0), 0.0),
                "before_fingerprint": stable_fingerprint({"file": path, "content": before}),
                "after_fingerprint": stable_fingerprint({"file": path, "content": after}),
                "evidence_references": sorted(set(_as_list(cand.get("evidence_references")) + evidence_references)),
            }
            segment["deterministic_fingerprint"] = stable_fingerprint(segment)
            applied_segments.append(segment)

            chunk_seq += 1
            chunk = {
                "chunk_id": f"chunk:{chunk_seq}",
                "stage_id": stage_id,
                "file": path,
                "segment_id": segment["segment_id"],
                "rollback_order": chunk_seq,
                "deterministic_fingerprint": stable_fingerprint(
                    {
                        "chunk_id": f"chunk:{chunk_seq}",
                        "stage_id": stage_id,
                        "file": path,
                        "segment_fingerprint": segment["deterministic_fingerprint"],
                    }
                ),
            }
            chunks.append(chunk)

        if not found_any:
            unsafe_blocks.append(
                {
                    "construct": construct,
                    "replacement": replacement,
                    "category": category,
                    "reason": "source_construct_not_found",
                    "stage_id": stage_id,
                    "evidence_references": sorted(set(_as_list(cand.get("evidence_references")) + evidence_references)),
                }
            )

    return transformed, applied_segments, unsafe_blocks, chunks


class GovernedTranslationExecutionEngine:
    """Governed AST-aware translation execution engine."""

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
        runtime_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        dry_run: bool,
        evidence_references: list[str] | None,
        previous_patch_history: list[Mapping[str, Any]] | None,
    ) -> GovernedTranslationExecutionResult:
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

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        upstream_translation_plan = _as_dict(translation_artifacts.get("upstream_translation_plan"))
        api_replacement_map = _as_dict(translation_artifacts.get("api_replacement_map"))
        unsupported_vendor_constructs = _as_dict(translation_artifacts.get("unsupported_vendor_constructs"))
        runtime_equivalence_validation = _as_dict(translation_artifacts.get("runtime_equivalence_validation"))
        translation_confidence_report = _as_dict(translation_artifacts.get("translation_confidence_report"))

        governance_ok, governance_violations = _governance_clean(governance_state)

        unsupported_count = int(_as_dict(unsupported_vendor_constructs.get("summary")).get("unsupported_count", 0) or 0)
        runtime_equiv_class = str(runtime_equivalence_validation.get("classification", "UNKNOWN")).upper()
        translation_class = str(translation_confidence_report.get("classification", "UNKNOWN")).upper()
        translation_conf = _to_float(translation_confidence_report.get("translation_confidence", 0.0), 0.0)

        classification = "PASS"
        fail_closed_justification = ""

        hard_block = False
        if not governance_ok:
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = ";".join(governance_violations)
        elif unsupported_count > 0:
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = "unsupported_vendor_constructs_present"
        elif runtime_equiv_class == "FAIL_CLOSED":
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = str(runtime_equivalence_validation.get("fail_closed_justification", "runtime_equivalence_fail_closed"))
        elif translation_class == "FAIL_CLOSED":
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = str(translation_confidence_report.get("fail_closed_justification", "translation_confidence_fail_closed"))
        elif translation_conf < 0.68:
            hard_block = True
            classification = "FAIL_CLOSED"
            fail_closed_justification = "translation_confidence_below_threshold"

        runtime_validation_map = _build_runtime_validation_map(runtime_equivalence_validation)
        stage_order = _stage_index_map(upstream_translation_plan)

        valid_candidates, pre_blocks = _candidate_transformations(
            api_replacement_map=api_replacement_map,
            runtime_validation_map=runtime_validation_map,
            evidence_references=evidence,
        )

        transformed_sources = {str(path): str(content) for path, content in _as_dict(source_snapshots).items()}
        applied_segments: list[dict[str, Any]] = []
        apply_blocks: list[dict[str, Any]] = []
        patch_chunks: list[dict[str, Any]] = []

        if hard_block:
            valid_candidates = []
        elif not valid_candidates:
            classification = "FAIL_CLOSED"
            fail_closed_justification = "no_runtime_validated_transformations"

        if valid_candidates:
            transformed_sources, applied_segments, apply_blocks, patch_chunks = _apply_transformations(
                sources=source_snapshots,
                candidates=valid_candidates,
                stage_order=stage_order,
                dry_run=bool(dry_run),
                evidence_references=evidence,
            )

        unsafe_blocks = pre_blocks + apply_blocks

        if not hard_block and not applied_segments:
            classification = "FAIL_CLOSED"
            fail_closed_justification = "no_transformations_applied"

        patch_text, changed_files = _build_patch(
            {str(path): str(content) for path, content in _as_dict(source_snapshots).items()},
            transformed_sources,
            dry_run=bool(dry_run),
        )

        if classification == "FAIL_CLOSED":
            changed_files = []
            patch_text = "\n".join(
                [
                    "# Governed Translation Execution Patch",
                    "# mode=blocked",
                    f"# fail_closed_justification={fail_closed_justification}",
                    "",
                ]
            )
            applied_segments = []
            patch_chunks = []

        runtime_validated_patch_segments = {
            "schema_version": "1.0",
            "report_name": "runtime_validated_patch_segments",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "PASS" if applied_segments else "FAIL_CLOSED",
            "segments": applied_segments,
            "summary": {
                "segment_count": len(applied_segments),
                "changed_file_count": len(changed_files),
                "runtime_validated_candidate_count": len(valid_candidates),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        runtime_validated_patch_segments["deterministic_fingerprint"] = stable_fingerprint(runtime_validated_patch_segments)

        unsafe_transformation_blocks = {
            "schema_version": "1.0",
            "report_name": "unsafe_transformation_blocks",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "FAIL_CLOSED" if unsafe_blocks else "PASS",
            "blocks": unsafe_blocks,
            "summary": {
                "block_count": len(unsafe_blocks),
                "hard_block": hard_block,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        unsafe_transformation_blocks["deterministic_fingerprint"] = stable_fingerprint(unsafe_transformation_blocks)

        transformation_lineage = {
            "schema_version": "1.0",
            "report_name": "transformation_lineage",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "dry_run": bool(dry_run),
            "migration_staging_boundaries": {
                "stage_order": stage_order,
                "applied_stage_ids": sorted(set(str(_as_dict(seg).get("stage_id", "")) for seg in applied_segments if str(_as_dict(seg).get("stage_id", "")).strip())),
            },
            "patch_chunks": patch_chunks,
            "rollback_safe_chunking": {
                "enabled": True,
                "chunk_count": len(patch_chunks),
                "rollback_sequence": [str(_as_dict(chunk).get("chunk_id", "")) for chunk in reversed(patch_chunks)],
            },
            "summary": {
                "applied_segment_count": len(applied_segments),
                "blocked_segment_count": len(unsafe_blocks),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        transformation_lineage["deterministic_fingerprint"] = stable_fingerprint(transformation_lineage)

        translation_execution_report = {
            "schema_version": "1.0",
            "report_name": "translation_execution_report",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "dry_run": bool(dry_run),
            "patch_emitted": bool((not dry_run) and classification != "FAIL_CLOSED" and len(changed_files) > 0),
            "fail_closed_justification": fail_closed_justification,
            "summary": {
                "changed_file_count": len(changed_files),
                "applied_segment_count": len(applied_segments),
                "unsafe_block_count": len(unsafe_blocks),
                "runtime_validated_candidate_count": len(valid_candidates),
                "translation_confidence": translation_conf,
            },
            "governance_state": dict(governance_state),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        translation_execution_report["deterministic_fingerprint"] = stable_fingerprint(translation_execution_report)

        deterministic_patch_generation_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_patch_generation_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "PASS" if classification != "FAIL_CLOSED" else "ADVISORY_ONLY",
            "artifact_fingerprints": {
                "transformation_lineage": str(transformation_lineage.get("deterministic_fingerprint", "")),
                "unsafe_transformation_blocks": str(unsafe_transformation_blocks.get("deterministic_fingerprint", "")),
                "runtime_validated_patch_segments": str(runtime_validated_patch_segments.get("deterministic_fingerprint", "")),
                "translation_execution_report": str(translation_execution_report.get("deterministic_fingerprint", "")),
            },
            "replay_signal": {
                "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            "lineage_history": [
                row for row in _as_list(previous_patch_history or []) if isinstance(row, dict)
            ]
            + [
                {
                    "lineage_id": str(lineage_id),
                    "session_id": str(session_id),
                    "classification": classification,
                    "execution_fingerprint": str(translation_execution_report.get("deterministic_fingerprint", "")),
                }
            ],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_patch_generation_replay["deterministic_fingerprint"] = stable_fingerprint(
            deterministic_patch_generation_replay
        )

        generated_upstream_patch = {
            "schema_version": "1.0",
            "report_name": "generated_upstream_patch",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "changed_files": changed_files,
            "patch_text": patch_text,
            "dry_run": bool(dry_run),
            "deterministic_fingerprint": stable_fingerprint(
                {
                    "target_id": str(target_id),
                    "session_id": str(session_id),
                    "lineage_id": str(lineage_id),
                    "classification": classification,
                    "changed_files": changed_files,
                    "patch_text": patch_text,
                    "dry_run": bool(dry_run),
                }
            ),
        }

        artifacts = {
            "generated_upstream_patch": generated_upstream_patch,
            "transformation_lineage": transformation_lineage,
            "unsafe_transformation_blocks": unsafe_transformation_blocks,
            "runtime_validated_patch_segments": runtime_validated_patch_segments,
            "deterministic_patch_generation_replay": deterministic_patch_generation_replay,
            "translation_execution_report": translation_execution_report,
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "GOVERNED_TRANSLATION_EXECUTION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "dry_run": bool(dry_run),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime_conversion": runtime_adapter,
            },
            "evidence_references": evidence,
            "artifacts": artifacts,
        }

        bundle["governed_translation_execution_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "dry_run": bool(dry_run),
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "adapter_fingerprints": {
                    "runtime_conversion": str(runtime_adapter.get("fingerprint", "")),
                },
            }
        )

        return GovernedTranslationExecutionResult(execution_bundle=bundle)


class GovernedTranslationExecutionRegistry:
    """Replay-safe persistence for translation execution artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "generated_upstream_patch": self._output_dir / "generated_upstream_patch.diff",
            "transformation_lineage": self._output_dir / "transformation_lineage.json",
            "unsafe_transformation_blocks": self._output_dir / "unsafe_transformation_blocks.json",
            "runtime_validated_patch_segments": self._output_dir / "runtime_validated_patch_segments.json",
            "deterministic_patch_generation_replay": self._output_dir / "deterministic_patch_generation_replay.json",
            "translation_execution_report": self._output_dir / "translation_execution_report.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()

        patch_payload = _as_dict(artifacts.get("generated_upstream_patch"))
        patch_text = str(patch_payload.get("patch_text", ""))
        paths["generated_upstream_patch"].parent.mkdir(parents=True, exist_ok=True)
        paths["generated_upstream_patch"].write_text(patch_text, encoding="utf-8")

        for key in (
            "transformation_lineage",
            "unsafe_transformation_blocks",
            "runtime_validated_patch_segments",
            "deterministic_patch_generation_replay",
            "translation_execution_report",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("governed_translation_execution"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "governed_translation_execution_fingerprint": str(payload.get("governed_translation_execution_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-6000:]

        registry["governed_translation_execution"] = {
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
                "type": "governed_translation_execution",
                "recorded_at": _utc_now_iso(),
                "governed_translation_execution_fingerprint": str(payload.get("governed_translation_execution_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-22000:]

        registry.setdefault("patch_generation_lineage", [])
        patch_lineage = [row for row in _as_list(registry.get("patch_generation_lineage")) if isinstance(row, dict)]
        patch_lineage.append(
            {
                "lineage_id": lineage_id,
                "session_id": entry["session_id"],
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "governed_translation_execution_fingerprint": entry["governed_translation_execution_fingerprint"],
            }
        )
        registry["patch_generation_lineage"] = patch_lineage[-12000:]

        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "governed_translation_execution_fingerprint": entry["governed_translation_execution_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("governed_translation_execution"))
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
            "replay_type": "governed_translation_execution",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "governed_translation_execution_fingerprint": str(_as_dict(selected).get("governed_translation_execution_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "governed_translation_execution_fingerprint": str(_as_dict(selected).get("governed_translation_execution_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_patch_generation_replay.json", replay_payload)
        return replay_payload
