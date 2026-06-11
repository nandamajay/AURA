"""Track B-specific stage execution built on reusable stage engine primitives."""

from __future__ import annotations

import fnmatch
import hashlib
import json
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
CLASSIFICATION_KEYS = (
    "driver_files",
    "dts_files",
    "yaml_files",
    "config_files",
    "makefile_files",
)
DEFAULT_DISCOVERY_CONFIG = {
    "source_roots": ["."],
    "include_patterns": [
        "*.c",
        "*.h",
        "*.dts",
        "*.dtsi",
        "*.yaml",
        "*.yml",
        "Kconfig",
        "Kconfig.*",
        "Makefile",
        "*.mk",
    ],
    "exclude_patterns": [".git", "__pycache__", "*.pyc"],
    "classification_rules": {
        "driver_files": ["*.c", "*.h"],
        "dts_files": ["*.dts", "*.dtsi"],
        "yaml_files": ["*.yaml", "*.yml"],
        "config_files": ["Kconfig", "Kconfig.*", "*.config"],
        "makefile_files": ["Makefile", "*.mk"],
    },
}


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


def _required_repo_root(context: dict[str, Any]) -> Path:
    raw = str(context.get("repository_root") or "").strip()
    if not raw:
        raise RuntimeError("repository_root is required for Track B discovery execution")
    repo_root = Path(raw).resolve()
    if not repo_root.exists() or not repo_root.is_dir():
        raise RuntimeError(f"repository_root does not exist or is not a directory: {raw}")
    return repo_root


def _readiness_value(context: dict[str, Any], key: str) -> str:
    readiness = _safe_dict(context.get("track_b_readiness"))
    return str(readiness.get(key) or "").strip().upper()


def _normalize_classification_rules(value: Any) -> dict[str, list[str]]:
    base = {
        key: _normalize_string_list(DEFAULT_DISCOVERY_CONFIG["classification_rules"].get(key, []))
        for key in CLASSIFICATION_KEYS
    }
    candidate = _safe_dict(value)
    for key in CLASSIFICATION_KEYS:
        if key in candidate:
            normalized = _normalize_string_list(candidate.get(key))
            if normalized:
                base[key] = normalized
    return base


def _discovery_config_from_context(context: dict[str, Any]) -> dict[str, Any]:
    cfg = _safe_dict(context.get("discovery_config"))

    source_roots = _normalize_string_list(
        context.get("source_roots")
        if "source_roots" in context
        else cfg.get("source_roots", DEFAULT_DISCOVERY_CONFIG["source_roots"])
    )
    if not source_roots:
        source_roots = _normalize_string_list(DEFAULT_DISCOVERY_CONFIG["source_roots"])

    include_patterns = _normalize_string_list(
        context.get("include_patterns")
        if "include_patterns" in context
        else cfg.get("include_patterns", DEFAULT_DISCOVERY_CONFIG["include_patterns"])
    )
    if not include_patterns:
        include_patterns = _normalize_string_list(DEFAULT_DISCOVERY_CONFIG["include_patterns"])

    exclude_patterns = _normalize_string_list(
        context.get("exclude_patterns")
        if "exclude_patterns" in context
        else cfg.get("exclude_patterns", DEFAULT_DISCOVERY_CONFIG["exclude_patterns"])
    )
    if not exclude_patterns:
        exclude_patterns = _normalize_string_list(DEFAULT_DISCOVERY_CONFIG["exclude_patterns"])

    classification_rules = _normalize_classification_rules(
        context.get("classification_rules")
        if "classification_rules" in context
        else cfg.get("classification_rules", DEFAULT_DISCOVERY_CONFIG["classification_rules"])
    )

    return {
        "source_roots": source_roots,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "classification_rules": classification_rules,
    }


def _matches_any_pattern(*, relative_path: str, basename: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(relative_path, pattern):
            return True
        if fnmatch.fnmatch(basename, pattern):
            return True
        if fnmatch.fnmatch("/" + relative_path, pattern):
            return True
    return False


def _file_fingerprint(values: list[str]) -> str:
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def _canonical_value_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _classify_file(relative_path: str, basename: str, rules: dict[str, list[str]]) -> set[str]:
    matches: set[str] = set()
    for key in CLASSIFICATION_KEYS:
        patterns = rules.get(key, [])
        if patterns and _matches_any_pattern(
            relative_path=relative_path, basename=basename, patterns=patterns
        ):
            matches.add(key)
    return matches


def _build_discovery_inventory(context: dict[str, Any]) -> dict[str, Any]:
    repo_root = _required_repo_root(context)
    cfg = _discovery_config_from_context(context)
    source_roots = cfg["source_roots"]
    include_patterns = cfg["include_patterns"]
    exclude_patterns = cfg["exclude_patterns"]
    classification_rules = cfg["classification_rules"]

    families = {key: [] for key in CLASSIFICATION_KEYS}
    all_files: list[str] = []

    for root in source_roots:
        base = (repo_root / root).resolve()
        if not base.exists() or not base.is_dir():
            raise RuntimeError(f"declared source_root does not exist or is not a directory: {root}")
        try:
            base.relative_to(repo_root)
        except ValueError as exc:
            raise RuntimeError(f"source_root escapes repository_root: {root}") from exc

        for dirpath, dirnames, filenames in os.walk(base, topdown=True, followlinks=False):
            rel_dir = str(Path(dirpath).resolve().relative_to(repo_root)).replace("\\", "/")
            keep_dirs: list[str] = []
            for dirname in sorted(dirnames):
                rel_child = str((Path(rel_dir) / dirname).as_posix()) if rel_dir != "." else dirname
                if _matches_any_pattern(
                    relative_path=rel_child,
                    basename=dirname,
                    patterns=exclude_patterns,
                ):
                    continue
                keep_dirs.append(dirname)
            dirnames[:] = keep_dirs

            for filename in sorted(filenames):
                path = Path(dirpath) / filename
                rel = str(path.resolve().relative_to(repo_root)).replace("\\", "/")
                if _matches_any_pattern(relative_path=rel, basename=filename, patterns=exclude_patterns):
                    continue
                if not _matches_any_pattern(relative_path=rel, basename=filename, patterns=include_patterns):
                    continue
                all_files.append(rel)
                for key in sorted(
                    _classify_file(
                        relative_path=rel,
                        basename=filename,
                        rules=classification_rules,
                    )
                ):
                    families[key].append(rel)

    all_files = sorted(set(all_files))
    for key in CLASSIFICATION_KEYS:
        families[key] = sorted(set(families[key]))

    counts = {"all_files": len(all_files)}
    counts.update({key: len(values) for key, values in families.items()})
    fingerprints = {"all_files": _file_fingerprint(all_files)}
    fingerprints.update({key: _file_fingerprint(values) for key, values in families.items()})

    return {
        "repository_root": str(repo_root),
        "source_roots": source_roots,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "classification_rules": classification_rules,
        "all_files": all_files,
        "file_families": families,
        "counts": counts,
        "fingerprints": fingerprints,
    }


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

    inventory = payload.get("discovery_inventory")
    if not isinstance(inventory, dict):
        errors.append("discovery_inventory must be an object")
        inventory = {}

    repo_root = str(inventory.get("repository_root") or "").strip()
    if not repo_root:
        errors.append("discovery_inventory.repository_root must be non-empty")
    all_files = inventory.get("all_files", [])
    if not isinstance(all_files, list):
        errors.append("discovery_inventory.all_files must be a list")
        all_files = []
    if isinstance(all_files, list) and not all_files:
        errors.append("discovery_inventory.all_files must be non-empty")

    families = inventory.get("file_families", {})
    counts = inventory.get("counts", {})
    fingerprints = inventory.get("fingerprints", {})
    if not isinstance(families, dict):
        errors.append("discovery_inventory.file_families must be an object")
        families = {}
    if not isinstance(counts, dict):
        errors.append("discovery_inventory.counts must be an object")
        counts = {}
    if not isinstance(fingerprints, dict):
        errors.append("discovery_inventory.fingerprints must be an object")
        fingerprints = {}

    for key in CLASSIFICATION_KEYS:
        files = families.get(key, [])
        if not isinstance(files, list):
            errors.append(f"discovery_inventory.file_families.{key} must be a list")
            continue
        count = counts.get(key)
        if not isinstance(count, int) or count != len(files):
            errors.append(f"discovery_inventory.counts.{key} must equal len(file_families.{key})")
        digest = str(fingerprints.get(key) or "").strip()
        if not digest:
            errors.append(f"discovery_inventory.fingerprints.{key} must be non-empty")

    all_count = counts.get("all_files")
    if not isinstance(all_count, int) or all_count != len(all_files):
        errors.append("discovery_inventory.counts.all_files must equal len(all_files)")
    all_digest = str(fingerprints.get("all_files") or "").strip()
    if not all_digest:
        errors.append("discovery_inventory.fingerprints.all_files must be non-empty")

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
        required = {"source_locator", "scope_declaration", "discovery_inventory"}
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
    analysis_inputs = payload.get("analysis_inputs")
    evidence = payload.get("evidence")

    if not isinstance(families, dict):
        errors.append("file_families must be an object")
        families = {}
    if not isinstance(counts, dict):
        errors.append("counts must be an object")
        counts = {}
    if not isinstance(fingerprints, dict):
        errors.append("fingerprints must be an object")
        fingerprints = {}

    for key in CLASSIFICATION_KEYS:
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

    discovered_hash = str(payload.get("discovered_artifact_sha256") or "").strip()
    if not discovered_hash:
        errors.append("discovered_artifact_sha256 must be non-empty")
    repository_root = str(payload.get("repository_root") or "").strip()
    if not repository_root:
        errors.append("repository_root must be non-empty")

    if not isinstance(analysis_inputs, dict):
        errors.append("analysis_inputs must be an object")
        analysis_inputs = {}

    source_records = analysis_inputs.get("source_records", [])
    input_counts = analysis_inputs.get("counts", {})
    input_fingerprints = analysis_inputs.get("fingerprints", {})
    if not isinstance(source_records, list) or not source_records:
        errors.append("analysis_inputs.source_records must be a non-empty list")
        source_records = []
    if not isinstance(input_counts, dict):
        errors.append("analysis_inputs.counts must be an object")
        input_counts = {}
    if not isinstance(input_fingerprints, dict):
        errors.append("analysis_inputs.fingerprints must be an object")
        input_fingerprints = {}

    include_directive_count = 0
    function_symbol_count = 0
    struct_symbol_count = 0
    unique_function_symbols: set[str] = set()
    unique_struct_symbols: set[str] = set()
    for index, record in enumerate(source_records):
        if not isinstance(record, dict):
            errors.append(f"analysis_inputs.source_records[{index}] must be an object")
            continue

        source_path = str(record.get("source_path") or "").strip()
        if not source_path:
            errors.append(f"analysis_inputs.source_records[{index}].source_path must be non-empty")
        file_sha256 = str(record.get("file_sha256") or "").strip()
        if not file_sha256:
            errors.append(f"analysis_inputs.source_records[{index}].file_sha256 must be non-empty")
        line_count = record.get("line_count")
        if not isinstance(line_count, int) or line_count < 0:
            errors.append(f"analysis_inputs.source_records[{index}].line_count must be a non-negative integer")

        source_kind = str(record.get("source_kind") or "").strip().lower()
        if source_kind not in {"source", "header"}:
            errors.append(f"analysis_inputs.source_records[{index}].source_kind must be source|header")

        include_directives = record.get("include_directives", [])
        if not isinstance(include_directives, list):
            errors.append(f"analysis_inputs.source_records[{index}].include_directives must be a list")
            include_directives = []
        include_directive_count += len(include_directives)
        for include_index, include in enumerate(include_directives):
            if not isinstance(include, dict):
                errors.append(
                    f"analysis_inputs.source_records[{index}].include_directives[{include_index}] must be an object"
                )
                continue
            include_header = str(include.get("included_header") or "").strip()
            include_style = str(include.get("include_style") or "").strip().lower()
            if not include_header:
                errors.append(
                    f"analysis_inputs.source_records[{index}].include_directives[{include_index}].included_header must be non-empty"
                )
            if include_style not in {"quote", "angle"}:
                errors.append(
                    f"analysis_inputs.source_records[{index}].include_directives[{include_index}].include_style must be quote|angle"
                )

        functions = record.get("functions", [])
        if not isinstance(functions, list):
            errors.append(f"analysis_inputs.source_records[{index}].functions must be a list")
            functions = []
        function_symbol_count += len(functions)
        for symbol in functions:
            text = str(symbol).strip()
            if text:
                unique_function_symbols.add(text)

        structs = record.get("structs", [])
        if not isinstance(structs, list):
            errors.append(f"analysis_inputs.source_records[{index}].structs must be a list")
            structs = []
        struct_symbol_count += len(structs)
        for symbol in structs:
            text = str(symbol).strip()
            if text:
                unique_struct_symbols.add(text)

    if input_counts.get("source_records") != len(source_records):
        errors.append("analysis_inputs.counts.source_records must equal len(source_records)")
    if input_counts.get("include_directives") != include_directive_count:
        errors.append("analysis_inputs.counts.include_directives must equal total include_directives")
    if input_counts.get("function_symbols") != function_symbol_count:
        errors.append("analysis_inputs.counts.function_symbols must equal total functions")
    if input_counts.get("struct_symbols") != struct_symbol_count:
        errors.append("analysis_inputs.counts.struct_symbols must equal total structs")
    if input_counts.get("unique_function_symbols") != len(unique_function_symbols):
        errors.append("analysis_inputs.counts.unique_function_symbols must equal unique function symbol count")
    if input_counts.get("unique_struct_symbols") != len(unique_struct_symbols):
        errors.append("analysis_inputs.counts.unique_struct_symbols must equal unique struct symbol count")

    expected_source_hash = _canonical_value_sha256(source_records)
    observed_source_hash = str(input_fingerprints.get("source_records") or "").strip()
    if not observed_source_hash:
        errors.append("analysis_inputs.fingerprints.source_records must be non-empty")
    elif observed_source_hash != expected_source_hash:
        errors.append("analysis_inputs.fingerprints.source_records mismatch")

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
                "config_index",
                "makefile_index",
                "static_input_index",
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

    symbol_inventory = payload.get("symbol_inventory", [])
    function_inventory = payload.get("function_inventory", [])
    struct_inventory = payload.get("struct_inventory", [])
    include_relationships = payload.get("include_relationships", [])
    source_header_relationships = payload.get("source_header_relationships", [])
    dependency_graph_metadata = payload.get("dependency_graph_metadata", {})

    if not isinstance(symbol_inventory, list):
        errors.append("symbol_inventory must be a list")
        symbol_inventory = []
    if not isinstance(function_inventory, list):
        errors.append("function_inventory must be a list")
        function_inventory = []
    if not isinstance(struct_inventory, list):
        errors.append("struct_inventory must be a list")
        struct_inventory = []
    if not isinstance(include_relationships, list):
        errors.append("include_relationships must be a list")
        include_relationships = []
    if not isinstance(source_header_relationships, list):
        errors.append("source_header_relationships must be a list")
        source_header_relationships = []
    if not isinstance(dependency_graph_metadata, dict):
        errors.append("dependency_graph_metadata must be an object")
        dependency_graph_metadata = {}

    for index, symbol in enumerate(symbol_inventory):
        if not isinstance(symbol, dict):
            errors.append(f"symbol_inventory[{index}] must be an object")
            continue
        if str(symbol.get("source_path") or "").strip() == "":
            errors.append(f"symbol_inventory[{index}].source_path must be non-empty")
        if str(symbol.get("symbol_name") or "").strip() == "":
            errors.append(f"symbol_inventory[{index}].symbol_name must be non-empty")
        if str(symbol.get("symbol_kind") or "").strip().lower() not in {"function", "struct"}:
            errors.append(f"symbol_inventory[{index}].symbol_kind must be function|struct")

    for index, symbol in enumerate(function_inventory):
        if not isinstance(symbol, dict):
            errors.append(f"function_inventory[{index}] must be an object")
            continue
        if str(symbol.get("source_path") or "").strip() == "":
            errors.append(f"function_inventory[{index}].source_path must be non-empty")
        if str(symbol.get("symbol_name") or "").strip() == "":
            errors.append(f"function_inventory[{index}].symbol_name must be non-empty")

    for index, symbol in enumerate(struct_inventory):
        if not isinstance(symbol, dict):
            errors.append(f"struct_inventory[{index}] must be an object")
            continue
        if str(symbol.get("source_path") or "").strip() == "":
            errors.append(f"struct_inventory[{index}].source_path must be non-empty")
        if str(symbol.get("symbol_name") or "").strip() == "":
            errors.append(f"struct_inventory[{index}].symbol_name must be non-empty")

    for index, rel in enumerate(include_relationships):
        if not isinstance(rel, dict):
            errors.append(f"include_relationships[{index}] must be an object")
            continue
        if str(rel.get("source_path") or "").strip() == "":
            errors.append(f"include_relationships[{index}].source_path must be non-empty")
        if str(rel.get("included_header") or "").strip() == "":
            errors.append(f"include_relationships[{index}].included_header must be non-empty")
        if str(rel.get("include_style") or "").strip().lower() not in {"quote", "angle"}:
            errors.append(f"include_relationships[{index}].include_style must be quote|angle")

    for index, rel in enumerate(source_header_relationships):
        if not isinstance(rel, dict):
            errors.append(f"source_header_relationships[{index}] must be an object")
            continue
        if str(rel.get("source_path") or "").strip() == "":
            errors.append(f"source_header_relationships[{index}].source_path must be non-empty")
        if str(rel.get("header_path") or "").strip() == "":
            errors.append(f"source_header_relationships[{index}].header_path must be non-empty")
        if str(rel.get("include_style") or "").strip().lower() not in {"quote", "angle"}:
            errors.append(f"source_header_relationships[{index}].include_style must be quote|angle")

    node_count = dependency_graph_metadata.get("node_count")
    edge_count = dependency_graph_metadata.get("edge_count")
    include_edge_count = dependency_graph_metadata.get("include_edge_count")
    source_header_edge_count = dependency_graph_metadata.get("source_header_edge_count")
    symbol_count = dependency_graph_metadata.get("symbol_count")
    function_count = dependency_graph_metadata.get("function_count")
    struct_count = dependency_graph_metadata.get("struct_count")
    if not isinstance(node_count, int) or node_count != len(nodes):
        errors.append("dependency_graph_metadata.node_count must equal len(driver_structure_map.nodes)")
    if not isinstance(edge_count, int) or edge_count != len(edges):
        errors.append("dependency_graph_metadata.edge_count must equal len(driver_structure_map.edges)")
    if not isinstance(include_edge_count, int) or include_edge_count != len(include_relationships):
        errors.append("dependency_graph_metadata.include_edge_count must equal len(include_relationships)")
    if not isinstance(source_header_edge_count, int) or source_header_edge_count != len(source_header_relationships):
        errors.append(
            "dependency_graph_metadata.source_header_edge_count must equal len(source_header_relationships)"
        )
    if not isinstance(symbol_count, int) or symbol_count != len(symbol_inventory):
        errors.append("dependency_graph_metadata.symbol_count must equal len(symbol_inventory)")
    if not isinstance(function_count, int) or function_count != len(function_inventory):
        errors.append("dependency_graph_metadata.function_count must equal len(function_inventory)")
    if not isinstance(struct_count, int) or struct_count != len(struct_inventory):
        errors.append("dependency_graph_metadata.struct_count must equal len(struct_inventory)")

    graph_fingerprint = str(dependency_graph_metadata.get("graph_fingerprint") or "").strip()
    if not graph_fingerprint:
        errors.append("dependency_graph_metadata.graph_fingerprint must be non-empty")
    indexed_input_fingerprint = str(dependency_graph_metadata.get("indexed_input_fingerprint") or "").strip()
    if not indexed_input_fingerprint:
        errors.append("dependency_graph_metadata.indexed_input_fingerprint must be non-empty")

    indexed_hash = str(payload.get("indexed_artifact_sha256") or "").strip()
    if not indexed_hash:
        errors.append("indexed_artifact_sha256 must be non-empty")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        required = {
            "symbol_inventory",
            "function_inventory",
            "struct_inventory",
            "include_relationships",
            "source_header_relationships",
            "dependency_graph_metadata",
        }
        if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
            errors.append("static evidence set must contain all required static analysis evidence types")
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
    cfg = _discovery_config_from_context(context)
    inventory = _build_discovery_inventory(context)
    assets = _safe_dict(context.get("control_plane_assets"))
    source_locator = _normalize_string_list(list(assets.values()))

    return {
        "artifact_name": "TRACK_B_STAGE_DISCOVERED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "DISCOVERED",
        "platform": platform,
        "scope_declaration": {
            "source_roots": cfg["source_roots"],
            "include_patterns": cfg["include_patterns"],
            "exclude_patterns": cfg["exclude_patterns"],
        },
        "discovery_inventory": inventory,
        "evidence": {
            "source_locator": source_locator,
            "required_evidence_types_satisfied": [
                "source_locator",
                "scope_declaration",
                "discovery_inventory",
            ],
        },
        "fail_closed_reasons": [],
    }


def _build_indexed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    discovered = _safe_dict(stage_payloads.get("DISCOVERED"))
    inventory = _safe_dict(discovered.get("discovery_inventory"))
    families = _safe_dict(inventory.get("file_families"))
    repository_root = str(inventory.get("repository_root") or "").strip()
    if not repository_root:
        raise RuntimeError("discovered discovery_inventory.repository_root missing")
    repo_root = Path(repository_root).resolve()

    normalized_families: dict[str, list[str]] = {}
    for key in CLASSIFICATION_KEYS:
        normalized_families[key] = _normalize_string_list(families.get(key))

    source_records = _build_indexed_source_records(
        repository_root=repo_root,
        driver_files=normalized_families["driver_files"],
    )

    counts = {key: len(values) for key, values in normalized_families.items()}
    fingerprints = {key: _file_fingerprint(values) for key, values in normalized_families.items()}
    analysis_input_counts = {
        "source_records": len(source_records),
        "include_directives": sum(len(item["include_directives"]) for item in source_records),
        "function_symbols": sum(len(item["functions"]) for item in source_records),
        "struct_symbols": sum(len(item["structs"]) for item in source_records),
        "unique_function_symbols": len(
            {symbol for item in source_records for symbol in item.get("functions", [])}
        ),
        "unique_struct_symbols": len({symbol for item in source_records for symbol in item.get("structs", [])}),
    }
    analysis_input_fingerprints = {"source_records": _canonical_value_sha256(source_records)}

    satisfied = []
    if normalized_families["driver_files"]:
        satisfied.append("driver_file_index")
    if normalized_families["dts_files"]:
        satisfied.append("dts_index")
    if normalized_families["yaml_files"]:
        satisfied.append("yaml_index")
    if normalized_families["config_files"]:
        satisfied.append("config_index")
    if normalized_families["makefile_files"]:
        satisfied.append("makefile_index")
    if source_records:
        satisfied.append("static_input_index")

    return {
        "artifact_name": "TRACK_B_STAGE_INDEXED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "INDEXED",
        "repository_root": repository_root,
        "file_families": normalized_families,
        "counts": counts,
        "fingerprints": fingerprints,
        "analysis_inputs": {
            "source_records": source_records,
            "counts": analysis_input_counts,
            "fingerprints": analysis_input_fingerprints,
        },
        "discovered_artifact_sha256": canonical_json_sha256(discovered),
        "evidence": {
            "required_evidence_types_satisfied": sorted(satisfied),
        },
        "fail_closed_reasons": [],
    }


_INCLUDE_RE = re.compile(r'^\s*#include\s*([<"])\s*([^">]+)\s*[">]\s*$')
_FUNC_RE = re.compile(
    r"^\s*(?:static\s+)?[A-Za-z_][\w\s\*]*?\s+([A-Za-z_]\w*)\s*\([^;{}]*\)\s*\{"
)
_STRUCT_RE = re.compile(r"\bstruct\s+([A-Za-z_]\w*)\b")


def _read_lines_fail_closed(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        raise RuntimeError(f"failed to read indexed source file: {path}") from exc


def _normalized_rel_path(path_text: str) -> str:
    return str(Path(path_text).as_posix()).replace("\\", "/")


def _extract_indexed_source_record(*, source_path: str, file_path: Path) -> dict[str, Any]:
    lines = _read_lines_fail_closed(file_path)
    include_directives: list[dict[str, str]] = []
    function_symbols: set[str] = set()
    struct_symbols: set[str] = set()

    for line in lines:
        include_match = _INCLUDE_RE.match(line)
        if include_match:
            style = "quote" if include_match.group(1) == '"' else "angle"
            header = _normalized_rel_path(include_match.group(2).strip())
            if header:
                include_directives.append(
                    {
                        "included_header": header,
                        "include_style": style,
                    }
                )

        func_match = _FUNC_RE.match(line)
        if func_match:
            symbol_name = str(func_match.group(1) or "").strip()
            if symbol_name:
                function_symbols.add(symbol_name)

        for struct_match in _STRUCT_RE.findall(line):
            symbol_name = str(struct_match or "").strip()
            if symbol_name:
                struct_symbols.add(symbol_name)

    include_directives = sorted(
        include_directives,
        key=lambda item: (str(item.get("included_header")), str(item.get("include_style"))),
    )
    source_kind = "header" if source_path.endswith(".h") else "source"
    return {
        "source_path": source_path,
        "source_kind": source_kind,
        "file_sha256": _sha256_file(file_path),
        "line_count": len(lines),
        "include_directives": include_directives,
        "functions": sorted(function_symbols),
        "structs": sorted(struct_symbols),
    }


def _build_indexed_source_records(*, repository_root: Path, driver_files: list[str]) -> list[dict[str, Any]]:
    source_records: list[dict[str, Any]] = []
    for rel in driver_files:
        rel_path = _normalized_rel_path(rel)
        file_path = (repository_root / rel_path).resolve()
        try:
            file_path.relative_to(repository_root)
        except ValueError as exc:
            raise RuntimeError(f"indexed driver file escapes repository_root: {rel_path}") from exc
        if not file_path.exists() or not file_path.is_file():
            raise RuntimeError(f"indexed driver file missing on filesystem: {rel_path}")
        source_records.append(
            _extract_indexed_source_record(
                source_path=rel_path,
                file_path=file_path,
            )
        )
    return sorted(source_records, key=lambda item: str(item.get("source_path")))


def _sorted_unique_dicts(
    items: list[dict[str, Any]],
    *,
    key_fn,
) -> list[dict[str, Any]]:
    by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in items:
        key = key_fn(item)
        by_key[key] = item
    return [by_key[key] for key in sorted(by_key.keys())]


def _resolve_header_path_from_index(
    *,
    source_path: str,
    included_header: str,
    header_file_set: set[str],
    header_basename_index: dict[str, list[str]],
) -> str:
    normalized_header = _normalized_rel_path(included_header).lstrip("./")
    if not normalized_header:
        return ""

    candidates: set[str] = set()
    if normalized_header in header_file_set:
        candidates.add(normalized_header)

    source_parent = str(Path(source_path).parent.as_posix())
    local_candidate = normalized_header
    if source_parent and source_parent != ".":
        local_candidate = _normalized_rel_path(str(Path(source_parent) / normalized_header))
    if local_candidate in header_file_set:
        candidates.add(local_candidate)

    base_name = str(Path(normalized_header).name)
    if base_name in header_basename_index:
        for candidate in header_basename_index[base_name]:
            candidates.add(candidate)

    if not candidates:
        return ""
    return sorted(candidates)[0]


def _build_static_analyzed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    indexed = _safe_dict(stage_payloads.get("INDEXED"))
    families = _safe_dict(indexed.get("file_families"))
    analysis_inputs = _safe_dict(indexed.get("analysis_inputs"))
    source_records = analysis_inputs.get("source_records", [])
    if not isinstance(source_records, list) or not source_records:
        raise RuntimeError("indexed analysis_inputs.source_records missing")

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    symbol_inventory: list[dict[str, str]] = []
    function_inventory: list[dict[str, str]] = []
    struct_inventory: list[dict[str, str]] = []
    include_relationships: list[dict[str, str]] = []
    source_header_relationships: list[dict[str, str]] = []
    relationships: list[dict[str, str]] = []

    driver_files = _normalize_string_list(families.get("driver_files"))
    header_files = sorted([path for path in driver_files if path.endswith(".h")])
    header_file_set = set(header_files)
    header_basename_index: dict[str, list[str]] = {}
    for header_path in header_files:
        base_name = str(Path(header_path).name)
        header_basename_index.setdefault(base_name, []).append(header_path)
    for base_name in list(header_basename_index.keys()):
        header_basename_index[base_name] = sorted(set(header_basename_index[base_name]))

    for raw_record in sorted(source_records, key=lambda item: str(_safe_dict(item).get("source_path"))):
        record = _safe_dict(raw_record)
        source_path = str(record.get("source_path") or "").strip()
        if not source_path:
            raise RuntimeError("indexed source record missing source_path")
        source_kind = str(record.get("source_kind") or "").strip().lower()
        if source_kind not in {"source", "header"}:
            raise RuntimeError(f"indexed source record has invalid source_kind: {source_kind!r}")
        include_directives = record.get("include_directives", [])
        if not isinstance(include_directives, list):
            raise RuntimeError("indexed source record include_directives must be a list")

        file_node_id = f"file:{source_path}"
        nodes[file_node_id] = {
            "node_id": file_node_id,
            "node_type": "driver_file" if source_kind == "source" else "header_file",
            "path": source_path,
        }

        for include in include_directives:
            if not isinstance(include, dict):
                raise RuntimeError("indexed include directive must be an object")
            included_header = str(include.get("included_header") or "").strip()
            include_style = str(include.get("include_style") or "").strip().lower()
            if not included_header:
                raise RuntimeError("indexed include directive missing included_header")
            if include_style not in {"quote", "angle"}:
                raise RuntimeError("indexed include directive has invalid include_style")

            include_relationships.append(
                {
                    "source_path": source_path,
                    "included_header": included_header,
                    "include_style": include_style,
                }
            )
            include_node_id = f"include:{included_header}"
            nodes.setdefault(
                include_node_id,
                {
                    "node_id": include_node_id,
                    "node_type": "include_header",
                    "header": included_header,
                },
            )
            edges.append(
                {
                    "source_node_id": file_node_id,
                    "target_node_id": include_node_id,
                    "relation": "includes",
                    "include_style": include_style,
                }
            )

            resolved_header = _resolve_header_path_from_index(
                source_path=source_path,
                included_header=included_header,
                header_file_set=header_file_set,
                header_basename_index=header_basename_index,
            )
            if resolved_header:
                source_header_relationships.append(
                    {
                        "source_path": source_path,
                        "header_path": resolved_header,
                        "include_style": include_style,
                    }
                )
                header_node_id = f"file:{resolved_header}"
                nodes.setdefault(
                    header_node_id,
                    {
                        "node_id": header_node_id,
                        "node_type": "header_file",
                        "path": resolved_header,
                    },
                )
                edges.append(
                    {
                        "source_node_id": file_node_id,
                        "target_node_id": header_node_id,
                        "relation": "source_header_link",
                        "include_style": include_style,
                    }
                )

        for symbol in _normalize_string_list(record.get("functions")):
            function_inventory.append({"source_path": source_path, "symbol_name": symbol})
            symbol_inventory.append(
                {
                    "source_path": source_path,
                    "symbol_name": symbol,
                    "symbol_kind": "function",
                }
            )
            relationships.append(
                {
                    "file": source_path,
                    "symbol": symbol,
                    "relation": "defines",
                    "symbol_kind": "function",
                }
            )

        for symbol in _normalize_string_list(record.get("structs")):
            struct_inventory.append({"source_path": source_path, "symbol_name": symbol})
            symbol_inventory.append(
                {
                    "source_path": source_path,
                    "symbol_name": symbol,
                    "symbol_kind": "struct",
                }
            )
            relationships.append(
                {
                    "file": source_path,
                    "symbol": symbol,
                    "relation": "defines",
                    "symbol_kind": "struct",
                }
            )

    structure_map = {
        "nodes": _sorted_unique_dicts(
            list(nodes.values()),
            key_fn=lambda item: (str(item.get("node_type")), str(item.get("node_id"))),
        ),
        "edges": _sorted_unique_dicts(
            edges,
            key_fn=lambda item: (
                str(item.get("source_node_id")),
                str(item.get("target_node_id")),
                str(item.get("relation")),
                str(item.get("include_style")),
            ),
        ),
    }
    symbol_inventory = _sorted_unique_dicts(
        symbol_inventory,
        key_fn=lambda item: (str(item.get("source_path")), str(item.get("symbol_name")), str(item.get("symbol_kind"))),
    )
    function_inventory = _sorted_unique_dicts(
        function_inventory,
        key_fn=lambda item: (str(item.get("source_path")), str(item.get("symbol_name"))),
    )
    struct_inventory = _sorted_unique_dicts(
        struct_inventory,
        key_fn=lambda item: (str(item.get("source_path")), str(item.get("symbol_name"))),
    )
    include_relationships = _sorted_unique_dicts(
        include_relationships,
        key_fn=lambda item: (
            str(item.get("source_path")),
            str(item.get("included_header")),
            str(item.get("include_style")),
        ),
    )
    source_header_relationships = _sorted_unique_dicts(
        source_header_relationships,
        key_fn=lambda item: (
            str(item.get("source_path")),
            str(item.get("header_path")),
            str(item.get("include_style")),
        ),
    )
    relationships = _sorted_unique_dicts(
        relationships,
        key_fn=lambda item: (
            str(item.get("file")),
            str(item.get("symbol")),
            str(item.get("relation")),
            str(item.get("symbol_kind")),
        ),
    )
    dependency_graph_metadata = {
        "node_count": len(structure_map["nodes"]),
        "edge_count": len(structure_map["edges"]),
        "include_edge_count": len(include_relationships),
        "source_header_edge_count": len(source_header_relationships),
        "symbol_count": len(symbol_inventory),
        "function_count": len(function_inventory),
        "struct_count": len(struct_inventory),
        "indexed_input_fingerprint": str(
            _safe_dict(analysis_inputs.get("fingerprints")).get("source_records")
            or _canonical_value_sha256(source_records)
        ).strip(),
        "graph_fingerprint": _canonical_value_sha256(
            {
                "nodes": structure_map["nodes"],
                "edges": structure_map["edges"],
            }
        ),
    }

    return {
        "artifact_name": "TRACK_B_STAGE_STATIC_ANALYZED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "STATIC_ANALYZED",
        "driver_structure_map": structure_map,
        "symbol_relationship_map": relationships,
        "symbol_inventory": symbol_inventory,
        "function_inventory": function_inventory,
        "struct_inventory": struct_inventory,
        "include_relationships": include_relationships,
        "source_header_relationships": source_header_relationships,
        "dependency_graph_metadata": dependency_graph_metadata,
        "indexed_artifact_sha256": canonical_json_sha256(indexed),
        "evidence": {
            "required_evidence_types_satisfied": [
                "symbol_inventory",
                "function_inventory",
                "struct_inventory",
                "include_relationships",
                "source_header_relationships",
                "dependency_graph_metadata",
            ],
        },
        "fail_closed_reasons": [],
    }


class TrackBStageExecutor:
    """M4 deterministic Track B stage execution: DISCOVERED -> INDEXED -> STATIC_ANALYZED."""

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
                required_evidence_types=("source_locator", "scope_declaration", "discovery_inventory"),
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
                    "config_index",
                    "makefile_index",
                    "static_input_index",
                ),
                build=_build_indexed,
                validate=_validate_indexed_schema,
            ),
            StageDefinition(
                stage_id="STATIC_ANALYZED",
                artifact_name="TRACK_B_STAGE_STATIC_ANALYZED",
                artifact_filename="track_b_static_analyzed.json",
                required_evidence_types=(
                    "symbol_inventory",
                    "function_inventory",
                    "struct_inventory",
                    "include_relationships",
                    "source_header_relationships",
                    "dependency_graph_metadata",
                ),
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
        except Exception as exc:
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
