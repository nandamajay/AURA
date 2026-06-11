"""Track B-specific stage execution built on reusable stage engine primitives."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from aura_agents.stage_engine import (
    DeterministicStageEngine,
    StageDefinition,
    StageExecutionError,
    canonical_json_sha256,
    write_json_deterministic,
)


TRACK_B_STAGE_ORDER = ("DISCOVERED", "INDEXED", "STATIC_ANALYZED")
CONTROL_PLANE_FILES = (
    "architecture_plan.md",
    "track_boundary_report.json",
    "learning_progress_model.json",
    "readiness_assessment.json",
)


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            normalized.append(text)
    seen: dict[str, None] = {}
    for item in normalized:
        seen[item] = None
    return sorted(seen.keys())


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(64 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _repo_root_from_context(context: dict[str, Any]) -> Path:
    candidate = str(context.get("repository_root") or "").strip()
    if candidate:
        path = Path(candidate).resolve()
        if path.exists():
            return path
    return Path(__file__).resolve().parents[4]


def _readiness_value(context: dict[str, Any], key: str) -> str:
    readiness = _safe_dict(context.get("track_b_readiness"))
    return str(readiness.get(key) or "").strip().upper()


def _validate_control_plane_integrity(context: dict[str, Any]) -> list[str]:
    assets = _safe_dict(context.get("control_plane_assets"))
    expected = _safe_dict(context.get("control_plane_sha256"))
    errors: list[str] = []

    for required in CONTROL_PLANE_FILES:
        if required not in assets:
            errors.append(f"control-plane asset missing in input: {required}")

    if errors:
        return errors

    for name in CONTROL_PLANE_FILES:
        raw_path = str(assets.get(name) or "").strip()
        if not raw_path:
            errors.append(f"control-plane asset path empty: {name}")
            continue
        path = Path(raw_path)
        if not path.exists():
            errors.append(f"control-plane asset path does not exist: {name} -> {raw_path}")
            continue
        observed = _sha256_file(path)
        expected_hash = str(expected.get(name) or "").strip().lower()
        if not expected_hash:
            errors.append(f"control-plane expected sha256 missing: {name}")
            continue
        if observed.lower() != expected_hash:
            errors.append(
                f"control-plane sha256 mismatch: {name} expected={expected_hash} observed={observed.lower()}"
            )
    return errors


def _validate_common_header(
    payload: dict[str, Any],
    *,
    expected_artifact_name: str,
    expected_stage_id: str,
) -> list[str]:
    errors: list[str] = []
    artifact_name = str(payload.get("artifact_name") or "").strip()
    if artifact_name != expected_artifact_name:
        errors.append(f"artifact_name expected {expected_artifact_name!r}, got {artifact_name!r}")
    schema_version = str(payload.get("schema_version") or "").strip()
    if schema_version != "1.0":
        errors.append(f"schema_version expected '1.0', got {schema_version!r}")
    stage_id = str(payload.get("stage_id") or "").strip().upper()
    if stage_id != expected_stage_id:
        errors.append(f"stage_id expected {expected_stage_id!r}, got {stage_id!r}")
    classification = str(payload.get("classification") or "").strip().upper()
    if classification != "PASS":
        errors.append(f"classification must be PASS, got {classification!r}")
    reasons = payload.get("fail_closed_reasons", [])
    if not isinstance(reasons, list):
        errors.append("fail_closed_reasons must be a list")
    return errors


def _validate_discovered_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_STAGE_DISCOVERED",
        expected_stage_id="DISCOVERED",
    )
    platform = str(payload.get("platform") or "").strip().lower()
    if not platform:
        errors.append("platform must be non-empty")

    scope = payload.get("scope_declaration")
    if not isinstance(scope, dict):
        errors.append("scope_declaration must be an object")
        scope = {}

    for key in ("source_roots", "include_patterns", "exclude_patterns"):
        value = scope.get(key, [])
        if not isinstance(value, list):
            errors.append(f"scope_declaration.{key} must be a list")
    source_roots = scope.get("source_roots", [])
    if isinstance(source_roots, list) and not source_roots:
        errors.append("scope_declaration.source_roots must be non-empty")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
        evidence = {}
    source_locator = evidence.get("source_locator", [])
    if not isinstance(source_locator, list) or not source_locator:
        errors.append("evidence.source_locator must be a non-empty list")
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    if not isinstance(satisfied, list):
        errors.append("evidence.required_evidence_types_satisfied must be a list")
    else:
        required = {"source_locator", "scope_declaration"}
        if not required.issubset({str(item).strip() for item in satisfied}):
            errors.append("required discovered evidence types are not fully satisfied")
    return errors


def _validate_indexed_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_STAGE_INDEXED",
        expected_stage_id="INDEXED",
    )
    families = payload.get("file_families")
    counts = payload.get("counts")
    fingerprints = payload.get("fingerprints")
    evidence = payload.get("evidence")

    family_keys = ("driver_files", "dts_files", "yaml_files", "kconfig_files", "makefile_files")
    if not isinstance(families, dict):
        errors.append("file_families must be an object")
        families = {}
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
        counts = {}
    if not isinstance(fingerprints, dict):
        errors.append("fingerprints must be an object")
        fingerprints = {}

    for key in family_keys:
        files = families.get(key, [])
        if not isinstance(files, list) or not files:
            errors.append(f"file_families.{key} must be a non-empty list")
            continue
        count = counts.get(key)
        if not isinstance(count, int) or count != len(files):
            errors.append(f"counts.{key} must equal len(file_families.{key})")
        digest = str(fingerprints.get(key) or "").strip()
        if not digest:
            errors.append(f"fingerprints.{key} must be non-empty")

    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        if not isinstance(satisfied, list):
            errors.append("evidence.required_evidence_types_satisfied must be a list")
        else:
            required = {
                "driver_file_index",
                "dts_index",
                "yaml_index",
                "kconfig_index",
                "makefile_index",
            }
            if required != {str(item).strip() for item in satisfied}:
                errors.append("indexed evidence set must contain all required evidence types")
    return errors


def _validate_static_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_STAGE_STATIC_ANALYZED",
        expected_stage_id="STATIC_ANALYZED",
    )
    structure = payload.get("driver_structure_map")
    if not isinstance(structure, dict):
        errors.append("driver_structure_map must be an object")
        structure = {}
    nodes = structure.get("nodes", [])
    edges = structure.get("edges", [])
    if not isinstance(nodes, list) or not nodes:
        errors.append("driver_structure_map.nodes must be a non-empty list")
    if not isinstance(edges, list):
        errors.append("driver_structure_map.edges must be a list")

    relationships = payload.get("symbol_relationship_map", [])
    if not isinstance(relationships, list) or not relationships:
        errors.append("symbol_relationship_map must be a non-empty list")

    indexed_hash = str(payload.get("indexed_artifact_sha256") or "").strip()
    if not indexed_hash:
        errors.append("indexed_artifact_sha256 must be non-empty")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        required = {"driver_structure_map", "symbol_relationship_map"}
        if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
            errors.append("static evidence set must contain driver_structure_map and symbol_relationship_map")
    return errors


def _validate_execution_schema(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("artifact_name") or "").strip() != "TRACK_B_STAGE_EXECUTION":
        errors.append("execution artifact_name mismatch")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        errors.append("execution schema_version mismatch")
    classification = str(payload.get("classification") or "").strip().upper()
    if classification not in {"PASS", "FAIL_CLOSED"}:
        errors.append("execution classification must be PASS or FAIL_CLOSED")
    transitions = payload.get("transitions", [])
    if not isinstance(transitions, list):
        errors.append("execution transitions must be a list")
    confidence = payload.get("stage_confidence", {})
    if not isinstance(confidence, dict):
        errors.append("execution stage_confidence must be an object")
    else:
        for stage in TRACK_B_STAGE_ORDER:
            if stage in confidence:
                value = confidence.get(stage)
                if not isinstance(value, (int, float)):
                    errors.append(f"stage_confidence.{stage} must be numeric")
    return errors


def _validate_manifest_schema(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("artifact_name") or "").strip() != "TRACK_B_STAGE_ARTIFACT_MANIFEST":
        errors.append("manifest artifact_name mismatch")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        errors.append("manifest schema_version mismatch")
    classification = str(payload.get("classification") or "").strip().upper()
    if classification not in {"PASS", "FAIL_CLOSED"}:
        errors.append("manifest classification must be PASS or FAIL_CLOSED")
    artifacts = payload.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("manifest artifacts must be a non-empty list")
    else:
        for item in artifacts:
            if not isinstance(item, dict):
                errors.append("manifest artifact entries must be objects")
                continue
            for key in ("name", "path", "sha256"):
                value = str(item.get(key) or "").strip()
                if not value:
                    errors.append(f"manifest artifact entry missing {key}")
            schema_valid = item.get("schema_valid")
            if not isinstance(schema_valid, bool):
                errors.append("manifest artifact entry schema_valid must be bool")
    digest = str(payload.get("deterministic_bundle_hash") or "").strip()
    if not digest:
        errors.append("manifest deterministic_bundle_hash must be non-empty")
    replay_ready = payload.get("replay_ready")
    if not isinstance(replay_ready, bool):
        errors.append("manifest replay_ready must be bool")
    return errors


def _build_discovered(context: dict[str, Any], _stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    platform = str(context.get("platform") or "").strip().lower()
    source_roots = _normalize_string_list(context.get("source_roots"))
    if not source_roots:
        source_roots = [
            "sound/soc/qcom",
            "arch/arm64/boot/dts/qcom",
            "Documentation/devicetree/bindings/sound",
        ]
    include_patterns = _normalize_string_list(
        context.get("include_patterns")
        or ["*.c", "*.h", "*.dts", "*.dtsi", "*.yaml", "*.yml", "Kconfig*", "Makefile"]
    )
    exclude_patterns = _normalize_string_list(context.get("exclude_patterns") or [".git", "__pycache__"])

    assets = _safe_dict(context.get("control_plane_assets"))
    source_locator = _normalize_string_list(list(assets.values()))

    return {
        "artifact_name": "TRACK_B_STAGE_DISCOVERED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "DISCOVERED",
        "platform": platform,
        "scope_declaration": {
            "source_roots": source_roots,
            "include_patterns": include_patterns,
            "exclude_patterns": exclude_patterns,
        },
        "evidence": {
            "source_locator": source_locator,
            "required_evidence_types_satisfied": ["source_locator", "scope_declaration"],
        },
        "fail_closed_reasons": [],
    }


def _family_sha(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _build_indexed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    discovered = _safe_dict(stage_payloads.get("DISCOVERED"))
    scope = _safe_dict(discovered.get("scope_declaration"))
    source_roots = _normalize_string_list(scope.get("source_roots"))
    repo_root = _repo_root_from_context(context)

    families: dict[str, list[str]] = {
        "driver_files": [],
        "dts_files": [],
        "yaml_files": [],
        "kconfig_files": [],
        "makefile_files": [],
    }

    for root in source_roots:
        base = (repo_root / root).resolve()
        if not base.exists() or not base.is_dir():
            continue
        for dirpath, _, filenames in os.walk(base, topdown=True, followlinks=False):
            for name in filenames:
                path = Path(dirpath) / name
                rel = str(path.resolve().relative_to(repo_root))
                lower_name = name.lower()
                if rel.endswith(".c") or rel.endswith(".h"):
                    families["driver_files"].append(rel)
                if rel.endswith(".dts") or rel.endswith(".dtsi"):
                    families["dts_files"].append(rel)
                if lower_name.endswith(".yaml") or lower_name.endswith(".yml"):
                    families["yaml_files"].append(rel)
                if name.startswith("Kconfig"):
                    families["kconfig_files"].append(rel)
                if name == "Makefile":
                    families["makefile_files"].append(rel)

    for key in list(families.keys()):
        families[key] = sorted(set(families[key]))

    counts = {key: len(values) for key, values in families.items()}
    fingerprints = {key: _family_sha(values) for key, values in families.items()}
    satisfied = []
    if families["driver_files"]:
        satisfied.append("driver_file_index")
    if families["dts_files"]:
        satisfied.append("dts_index")
    if families["yaml_files"]:
        satisfied.append("yaml_index")
    if families["kconfig_files"]:
        satisfied.append("kconfig_index")
    if families["makefile_files"]:
        satisfied.append("makefile_index")

    return {
        "artifact_name": "TRACK_B_STAGE_INDEXED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "INDEXED",
        "repository_root": str(repo_root),
        "file_families": families,
        "counts": counts,
        "fingerprints": fingerprints,
        "evidence": {
            "required_evidence_types_satisfied": sorted(satisfied),
        },
        "fail_closed_reasons": [],
    }


_INCLUDE_RE = re.compile(r'^\s*#include\s+[<"]([^">]+)[">]\s*$')
_FUNC_RE = re.compile(
    r"^\s*(?:static\s+)?[A-Za-z_][\w\s\*]*?\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
)


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def _build_static_analyzed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    indexed = _safe_dict(stage_payloads.get("INDEXED"))
    families = _safe_dict(indexed.get("file_families"))
    repo_root = Path(str(indexed.get("repository_root") or _repo_root_from_context(context))).resolve()
    driver_files = _normalize_string_list(families.get("driver_files"))

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []

    for rel in driver_files:
        file_node_id = f"file:{rel}"
        nodes[file_node_id] = {"node_id": file_node_id, "node_type": "driver_file", "path": rel}
        lines = _read_lines(repo_root / rel)
        for line in lines:
            include_match = _INCLUDE_RE.match(line)
            if include_match:
                header = include_match.group(1).strip()
                include_node = f"include:{header}"
                nodes.setdefault(
                    include_node,
                    {"node_id": include_node, "node_type": "include_header", "header": header},
                )
                edges.append(
                    {
                        "source_node_id": file_node_id,
                        "target_node_id": include_node,
                        "relation": "includes",
                    }
                )

            func_match = _FUNC_RE.match(line)
            if func_match:
                relationships.append({"file": rel, "symbol": func_match.group(1), "relation": "defines"})

    structure_map = {
        "nodes": sorted(nodes.values(), key=lambda item: (str(item.get("node_type")), str(item.get("node_id")))),
        "edges": sorted(
            edges,
            key=lambda item: (
                str(item.get("source_node_id")),
                str(item.get("target_node_id")),
                str(item.get("relation")),
            ),
        ),
    }
    relationships = sorted(
        relationships,
        key=lambda item: (str(item.get("file")), str(item.get("symbol")), str(item.get("relation"))),
    )

    return {
        "artifact_name": "TRACK_B_STAGE_STATIC_ANALYZED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "STATIC_ANALYZED",
        "driver_structure_map": structure_map,
        "symbol_relationship_map": relationships,
        "indexed_artifact_sha256": canonical_json_sha256(indexed),
        "evidence": {
            "required_evidence_types_satisfied": ["driver_structure_map", "symbol_relationship_map"],
        },
        "fail_closed_reasons": [],
    }


class TrackBStageExecutor:
    """M2 deterministic Track B stage execution: DISCOVERED -> INDEXED -> STATIC_ANALYZED."""

    def __init__(self, *, output_dir: Path):
        self._output_dir = output_dir

    def execute(self, *, context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(context, dict):
            raise RuntimeError("track_b_stage_execution fail-closed: context must be an object")

        self._output_dir.mkdir(parents=True, exist_ok=True)

        fail_reasons: list[str] = []
        control_plane_errors = _validate_control_plane_integrity(context)
        fail_reasons.extend(control_plane_errors)

        go_no_go = _readiness_value(context, "go_no_go")
        if go_no_go != "GO_DISCOVERY_ONLY":
            fail_reasons.append(f"readiness go/no-go must be GO_DISCOVERY_ONLY, got {go_no_go!r}")
        scope_mode = _readiness_value(context, "scope_mode")
        if scope_mode != "DISCOVERY_ONLY":
            fail_reasons.append(f"readiness scope_mode must be DISCOVERY_ONLY, got {scope_mode!r}")
        hard_blockers = context.get("track_b_hard_blockers", [])
        if isinstance(hard_blockers, list) and hard_blockers:
            fail_reasons.append(f"hard blockers present: {hard_blockers}")

        if fail_reasons:
            self._write_fail_closed_execution(context=context, reasons=fail_reasons)
            raise RuntimeError("track_b_stage_execution fail-closed: " + "; ".join(fail_reasons))

        initial_stage = str(context.get("track_b_initial_stage") or "DISCOVERED").strip().upper()
        target_stage = str(context.get("track_b_target_stage") or "STATIC_ANALYZED").strip().upper()

        stage_definitions = [
            StageDefinition(
                stage_id="DISCOVERED",
                artifact_name="TRACK_B_STAGE_DISCOVERED",
                artifact_filename="track_b_discovered.json",
                required_evidence_types=("source_locator", "scope_declaration"),
                build=_build_discovered,
                validate=_validate_discovered_schema,
            ),
            StageDefinition(
                stage_id="INDEXED",
                artifact_name="TRACK_B_STAGE_INDEXED",
                artifact_filename="track_b_indexed.json",
                required_evidence_types=(
                    "driver_file_index",
                    "dts_index",
                    "yaml_index",
                    "kconfig_index",
                    "makefile_index",
                ),
                build=_build_indexed,
                validate=_validate_indexed_schema,
            ),
            StageDefinition(
                stage_id="STATIC_ANALYZED",
                artifact_name="TRACK_B_STAGE_STATIC_ANALYZED",
                artifact_filename="track_b_static_analyzed.json",
                required_evidence_types=("driver_structure_map", "symbol_relationship_map"),
                build=_build_static_analyzed,
                validate=_validate_static_schema,
            ),
        ]

        engine = DeterministicStageEngine(stage_definitions)

        try:
            execution = engine.execute(
                initial_stage=initial_stage,
                target_stage=target_stage,
                context=context,
                output_dir=self._output_dir,
            )
        except StageExecutionError as exc:
            self._write_fail_closed_execution(context=context, reasons=[str(exc)])
            raise RuntimeError(f"track_b_stage_execution fail-closed: {exc}") from exc

        session_payload = {
            "task_id": str(context.get("task_id") or "").strip(),
            "track": "B",
            "ownership": "track_b",
            "platform": str(context.get("platform") or "").strip().lower(),
            "workflow_kind": str(context.get("workflow_kind") or "track_b_discovery").strip(),
        }

        execution_payload = {
            "artifact_name": "TRACK_B_STAGE_EXECUTION",
            "schema_version": "1.0",
            "classification": "PASS",
            "session": session_payload,
            "initial_stage": execution["initial_stage"],
            "target_stage": execution["target_stage"],
            "terminal_stage": execution["terminal_stage"],
            "transitions": execution["transitions"],
            "stage_confidence": execution["stage_confidence"],
            "fail_closed_reasons": [],
        }
        execution_errors = _validate_execution_schema(execution_payload)
        if execution_errors:
            raise RuntimeError(
                "track_b_stage_execution fail-closed: execution schema invalid: "
                + "; ".join(execution_errors)
            )

        execution_path = self._output_dir / "track_b_stage_execution.json"
        execution_sha = write_json_deterministic(execution_path, execution_payload)

        manifest_artifacts = [
            {
                "name": entry["artifact_name"],
                "path": entry["artifact_path"],
                "sha256": entry["artifact_sha256"],
                "schema_valid": True,
            }
            for entry in execution["stage_artifacts"]
        ]
        manifest_artifacts.append(
            {
                "name": execution_payload["artifact_name"],
                "path": execution_path.name,
                "sha256": execution_sha,
                "schema_valid": True,
            }
        )
        manifest_artifacts = sorted(manifest_artifacts, key=lambda item: str(item["name"]))
        bundle_basis = {item["name"]: item["sha256"] for item in manifest_artifacts}
        deterministic_bundle_hash = hashlib.sha256(
            str(sorted(bundle_basis.items())).encode("utf-8")
        ).hexdigest()
        manifest_payload = {
            "artifact_name": "TRACK_B_STAGE_ARTIFACT_MANIFEST",
            "schema_version": "1.0",
            "classification": "PASS",
            "artifacts": manifest_artifacts,
            "deterministic_bundle_hash": deterministic_bundle_hash,
            "replay_ready": True,
            "fail_closed_reasons": [],
        }
        manifest_errors = _validate_manifest_schema(manifest_payload)
        if manifest_errors:
            raise RuntimeError(
                "track_b_stage_execution fail-closed: manifest schema invalid: "
                + "; ".join(manifest_errors)
            )

        manifest_path = self._output_dir / "track_b_artifact_manifest.json"
        manifest_sha = write_json_deterministic(manifest_path, manifest_payload)

        return {
            "classification": "PASS",
            "initial_stage": execution["initial_stage"],
            "target_stage": execution["target_stage"],
            "terminal_stage": execution["terminal_stage"],
            "transitions": execution["transitions"],
            "stage_confidence": execution["stage_confidence"],
            "execution_artifact_path": str(execution_path),
            "execution_artifact_sha256": execution_sha,
            "artifact_manifest_path": str(manifest_path),
            "artifact_manifest_sha256": manifest_sha,
            "artifact_manifest": manifest_payload,
            "stage_artifacts": execution["stage_artifacts"],
        }

    def _write_fail_closed_execution(self, *, context: dict[str, Any], reasons: list[str]) -> None:
        payload = {
            "artifact_name": "TRACK_B_STAGE_EXECUTION",
            "schema_version": "1.0",
            "classification": "FAIL_CLOSED",
            "session": {
                "task_id": str(context.get("task_id") or "").strip(),
                "track": "B",
                "ownership": "track_b",
                "platform": str(context.get("platform") or "").strip().lower(),
                "workflow_kind": str(context.get("workflow_kind") or "track_b_discovery").strip(),
            },
            "initial_stage": str(context.get("track_b_initial_stage") or "DISCOVERED").strip().upper(),
            "target_stage": str(context.get("track_b_target_stage") or "STATIC_ANALYZED").strip().upper(),
            "terminal_stage": str(context.get("track_b_initial_stage") or "DISCOVERED").strip().upper(),
            "transitions": [],
            "stage_confidence": {},
            "fail_closed_reasons": [str(reason).strip() for reason in reasons if str(reason).strip()],
        }
        write_json_deterministic(self._output_dir / "track_b_stage_execution.json", payload)
