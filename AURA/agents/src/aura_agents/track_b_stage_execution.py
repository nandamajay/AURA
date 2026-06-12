"""Track B-specific stage execution built on reusable stage engine primitives."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from aura_agents.confidence_engine import ConfidenceComputationError, compute_weighted_confidence
from aura_agents.stage_engine import (
    DeterministicStageEngine,
    StageDefinition,
    StageExecutionError,
    canonical_json_sha256,
    write_json_deterministic,
)


TRACK_B_STAGE_ORDER = (
    "DISCOVERED",
    "INDEXED",
    "STATIC_ANALYZED",
    "EQUIVALENCE_MAPPED",
    "DEPENDENCIES_BOUND",
    "CONFLICTS_EVALUATED",
    "DECISION_FINALIZED",
    "REPORT_GENERATED",
    "READINESS_GATED",
)
CORPUS_ROLES = ("downstream", "upstream")
UPSTREAMING_COMPONENT_TYPES = (
    "function",
    "driver",
    "dt_node",
    "mixer_control",
    "dai_link",
    "soundwire_endpoint",
    "apr_service",
    "dsp_graph_component",
)
RUNTIME_SENSITIVE_COMPONENT_TYPES = (
    "mixer_control",
    "dai_link",
    "soundwire_endpoint",
    "apr_service",
    "dsp_graph_component",
)
RUNTIME_EVIDENCE_REF_RE = re.compile(r"^(runtime|m7):[a-z0-9_.-]+:[a-z0-9_.:/-]+$", re.IGNORECASE)
EQUIVALENCE_DECISION_STATES = (
    "UNIQUE_EQUIVALENT",
    "MULTI_EQUIVALENT",
    "NO_EQUIVALENT",
    "CONFLICTING_EVIDENCE",
)
CONFLICT_TYPES = (
    "NO_CANDIDATE_MAPPING",
    "MULTI_EQUIVALENT_TOP_SCORE",
    "DEPENDENCY_MISMATCH",
    "STATIC_ONLY_EDGE",
    "RUNTIME_ONLY_EDGE",
    "ORDERING_MISMATCH",
    "SIGNATURE_MISMATCH",
    "DT_BINDING_MISMATCH",
)
CONFLICT_PRECEDENCE = (
    "NO_CANDIDATE_MAPPING",
    "MULTI_EQUIVALENT_TOP_SCORE",
    "SIGNATURE_MISMATCH",
    "DT_BINDING_MISMATCH",
    "DEPENDENCY_MISMATCH",
    "STATIC_ONLY_EDGE",
    "RUNTIME_ONLY_EDGE",
    "ORDERING_MISMATCH",
)
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
RELATIONSHIP_INDEX_KEYS = (
    "downstream_upstream_relationship_index",
    "dts_relationship_index",
    "yaml_relationship_index",
    "kconfig_relationship_index",
    "makefile_relationship_index",
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
TRACK_B_CONFIDENCE_SIGNALS = {
    "DISCOVERED": (
        "corpus_roles_integrity",
        "repository_provenance_integrity",
        "discovery_inventory_integrity",
    ),
    "INDEXED": (
        "dual_corpus_index_integrity",
        "relationship_index_integrity",
        "static_input_integrity",
        "lineage_integrity",
    ),
    "STATIC_ANALYZED": (
        "comparison_signals_integrity",
        "deterministic_delta_integrity",
        "lineage_integrity",
    ),
    "EQUIVALENCE_MAPPED": (
        "candidate_mapping_integrity",
        "mapping_provenance_integrity",
        "mapping_lineage_integrity",
    ),
    "DEPENDENCIES_BOUND": (
        "dependency_matrix_integrity",
        "dependency_provenance_integrity",
        "dependency_lineage_integrity",
    ),
    "CONFLICTS_EVALUATED": (
        "conflict_ledger_integrity",
        "conflict_resolution_integrity",
        "conflict_lineage_integrity",
    ),
    "DECISION_FINALIZED": (
        "decision_state_integrity",
        "decision_policy_integrity",
        "decision_lineage_integrity",
    ),
    "REPORT_GENERATED": (
        "report_completeness_integrity",
        "report_provenance_integrity",
        "report_lineage_integrity",
    ),
    "READINESS_GATED": (
        "readiness_checks_integrity",
        "readiness_policy_integrity",
        "readiness_lineage_integrity",
    ),
}
DEFAULT_TRACK_B_CONFIDENCE_WEIGHTS = {
    stage: {signal: 1.0 for signal in signals}
    for stage, signals in TRACK_B_CONFIDENCE_SIGNALS.items()
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


def _safe_run(command: list[str], *, cwd: Path) -> str:
    try:
        run = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    if run.returncode != 0:
        return ""
    return str(run.stdout or "").strip()


def _nearest_git_root(path: Path, *, ceiling: Path) -> Path | None:
    current = path.resolve()
    boundary = ceiling.resolve()
    while True:
        git_marker = current / ".git"
        if git_marker.exists():
            return current
        if current == boundary:
            return None
        if boundary not in current.parents:
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _path_parts(path: str) -> list[str]:
    return [part for part in str(Path(path).as_posix()).split("/") if part]


def _corpus_id_from_source_root(source_root: str) -> str:
    parts = _path_parts(source_root)
    if "track_b_corpora" in parts:
        idx = parts.index("track_b_corpora")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[0] if parts else ""


def _corpus_role_from_source_root(source_root: str, corpus_id: str) -> str:
    normalized = str(Path(source_root).as_posix())
    if "/linux-next/" in f"/{normalized}/" or corpus_id == "linux-next":
        return "upstream"
    if corpus_id:
        return "downstream"
    return "unknown"


def _build_source_locators(*, repository_root: Path, source_roots: list[str]) -> list[dict[str, str]]:
    source_locators: list[dict[str, str]] = []
    for source_root in sorted(set(source_roots)):
        base = (repository_root / source_root).resolve()
        if not base.exists() or not base.is_dir():
            continue
        try:
            rel_root = str(base.relative_to(repository_root)).replace("\\", "/")
        except ValueError:
            continue

        corpus_id = _corpus_id_from_source_root(rel_root)
        corpus_role = _corpus_role_from_source_root(rel_root, corpus_id)
        git_root = _nearest_git_root(base, ceiling=repository_root)
        repo_root_rel = ""
        repo_url = ""
        repo_branch = ""
        repo_head_sha = ""
        snapshot_ts = ""
        if git_root is not None:
            try:
                repo_root_rel = str(git_root.relative_to(repository_root)).replace("\\", "/")
            except ValueError:
                repo_root_rel = ""
            repo_url = _safe_run(["git", "config", "--get", "remote.origin.url"], cwd=git_root)
            repo_branch = _safe_run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
            repo_head_sha = _safe_run(["git", "rev-parse", "HEAD"], cwd=git_root)
            snapshot_ts = _safe_run(["git", "log", "-1", "--format=%cI"], cwd=git_root)

        source_locators.append(
            {
                "source_root": rel_root,
                "corpus_id": corpus_id,
                "corpus_role": corpus_role,
                "repo_root_path": repo_root_rel,
                "repo_url": repo_url,
                "repo_branch": repo_branch,
                "repo_head_sha": repo_head_sha,
                "snapshot_ts": snapshot_ts,
            }
        )

    return sorted(
        source_locators,
        key=lambda item: (
            str(item.get("corpus_role")),
            str(item.get("corpus_id")),
            str(item.get("repo_root_path")),
            str(item.get("source_root")),
        ),
    )


def _find_source_locator_for_path(*, source_path: str, source_locators: list[dict[str, str]]) -> dict[str, str]:
    normalized = str(Path(source_path).as_posix())
    best: dict[str, str] = {}
    best_len = -1
    for locator in source_locators:
        root = str(locator.get("source_root") or "").strip()
        if not root:
            continue
        if normalized == root or normalized.startswith(root + "/"):
            if len(root) > best_len:
                best = locator
                best_len = len(root)
    return best


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


def _is_sha256(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if len(text) != 64:
        return False
    for char in text:
        if char not in "0123456789abcdef":
            return False
    return True


def _is_commit_sha(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if len(text) < 7 or len(text) > 64:
        return False
    for char in text:
        if char not in "0123456789abcdef":
            return False
    return True


def _require_non_empty_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RuntimeError(f"{field} must be non-empty")
    return text


def _normalize_commit_sha(value: Any, *, field: str) -> str:
    text = _require_non_empty_text(value, field=field).lower()
    if not _is_commit_sha(text):
        raise RuntimeError(f"{field} must be a git-style hexadecimal commit SHA (7-64 chars)")
    return text


def _normalize_revision(value: Any, *, field: str) -> dict[str, str]:
    revision = _safe_dict(value)
    remote = _require_non_empty_text(revision.get("remote"), field=f"{field}.remote")
    branch = _require_non_empty_text(revision.get("branch"), field=f"{field}.branch")
    commit_sha = _normalize_commit_sha(revision.get("commit_sha"), field=f"{field}.commit_sha")
    return {
        "remote": remote,
        "branch": branch,
        "commit_sha": commit_sha,
    }


def _normalize_line_number(value: Any, *, field: str) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise RuntimeError(f"{field} must be an integer")
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        if not text.isdigit():
            raise RuntimeError(f"{field} must be an integer")
        number = int(text)
    elif isinstance(value, int):
        number = int(value)
    else:
        raise RuntimeError(f"{field} must be an integer")
    if number < 0:
        raise RuntimeError(f"{field} must be >= 0")
    return number


def _normalize_runtime_evidence_refs(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{field} must be a list")
    refs = _normalize_string_list(value)
    for index, entry in enumerate(refs):
        if not RUNTIME_EVIDENCE_REF_RE.match(entry):
            raise RuntimeError(
                f"{field}[{index}] must match '<runtime|m7>:<type>:<id>' deterministic format"
            )
    return refs


def _runtime_evidence_required(component_type: str) -> bool:
    return str(component_type or "").strip().lower() in RUNTIME_SENSITIVE_COMPONENT_TYPES


def _normalize_upstreaming_request(context: dict[str, Any]) -> dict[str, Any]:
    raw_request = context.get("upstreaming_request")
    if raw_request is None:
        return {}
    request = _safe_dict(raw_request)
    if not request:
        raise RuntimeError("upstreaming_request must be an object")

    request_id = _require_non_empty_text(request.get("request_id"), field="upstreaming_request.request_id")
    downstream_component = _safe_dict(request.get("downstream_component"))
    if not downstream_component:
        raise RuntimeError("upstreaming_request.downstream_component must be an object")

    component_type = _require_non_empty_text(
        downstream_component.get("component_type"),
        field="upstreaming_request.downstream_component.component_type",
    ).lower()
    if component_type not in UPSTREAMING_COMPONENT_TYPES:
        raise RuntimeError(
            "upstreaming_request.downstream_component.component_type must be one of "
            + str(UPSTREAMING_COMPONENT_TYPES)
        )
    component_name = _require_non_empty_text(
        downstream_component.get("component_name"),
        field="upstreaming_request.downstream_component.component_name",
    )
    source_path = str(downstream_component.get("source_path") or "").strip()
    if not source_path:
        raise RuntimeError("upstreaming_request.downstream_component.source_path must be non-empty")
    line_start = _normalize_line_number(
        downstream_component.get("line_start"),
        field="upstreaming_request.downstream_component.line_start",
    )
    line_end = _normalize_line_number(
        downstream_component.get("line_end"),
        field="upstreaming_request.downstream_component.line_end",
    )
    if line_end and line_start and line_end < line_start:
        raise RuntimeError("upstreaming_request.downstream_component.line_end must be >= line_start")

    runtime_evidence_refs = _normalize_runtime_evidence_refs(
        request.get("runtime_evidence_refs"),
        field="upstreaming_request.runtime_evidence_refs",
    )
    runtime_evidence_required = _runtime_evidence_required(component_type)
    if runtime_evidence_required and not runtime_evidence_refs:
        raise RuntimeError(
            "upstreaming_request.runtime_evidence_refs must be non-empty for runtime-sensitive "
            f"component_type={component_type}"
        )
    return {
        "request_id": request_id,
        "downstream_component": {
            "component_type": component_type,
            "component_name": component_name,
            "source_path": source_path,
            "line_start": line_start,
            "line_end": line_end,
        },
        "runtime_evidence_required": runtime_evidence_required,
        "runtime_evidence_refs": runtime_evidence_refs,
    }


def _line_range_text(*, line_start: int, line_end: int) -> str:
    start = int(line_start) if int(line_start) > 0 else 0
    end = int(line_end) if int(line_end) > 0 else start
    if end < start:
        end = start
    return f"{start}-{end}"


def _corpora_revision_map(corpora: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    for corpus in corpora:
        item = _safe_dict(corpus)
        role = str(item.get("corpus_role") or "").strip().lower()
        if role not in CORPUS_ROLES:
            continue
        revision = _safe_dict(item.get("revision"))
        mapping[role] = {
            "corpus_id": str(item.get("corpus_id") or "").strip(),
            "remote": str(revision.get("remote") or "").strip(),
            "branch": str(revision.get("branch") or "").strip(),
            "commit_sha": str(revision.get("commit_sha") or "").strip().lower(),
        }
    return mapping


def _build_provenance_entry(
    *,
    corpus_role: str,
    corpora_map: dict[str, dict[str, str]],
    path: str,
    line_start: int,
    line_end: int,
    evidence_type: str,
    source_artifact_sha256: str,
    source_artifact_name: str,
    extraction_rule_id: str,
    snippet_basis: str,
) -> dict[str, Any]:
    role = str(corpus_role or "").strip().lower()
    corpus = _safe_dict(corpora_map.get(role))
    start = int(line_start) if int(line_start) > 0 else 0
    end = int(line_end) if int(line_end) > 0 else start
    if end < start:
        end = start
    snippet_sha256 = hashlib.sha256(snippet_basis.encode("utf-8")).hexdigest()
    payload = {
        "evidence_type": str(evidence_type or "").strip(),
        "corpus_role": role,
        "corpus_id": str(corpus.get("corpus_id") or "").strip(),
        "remote": str(corpus.get("remote") or "").strip(),
        "branch": str(corpus.get("branch") or "").strip(),
        "commit_sha": str(corpus.get("commit_sha") or "").strip().lower(),
        "path": str(path or "").strip(),
        "line_start": start,
        "line_end": end,
        "snippet_sha256": snippet_sha256,
        "source_artifact_name": str(source_artifact_name or "").strip(),
        "source_artifact_sha256": str(source_artifact_sha256 or "").strip().lower(),
        "extraction_rule_id": str(extraction_rule_id or "").strip(),
    }
    payload["evidence_id"] = _canonical_value_sha256(payload)
    return payload


def _validate_line_range(value: str) -> bool:
    text = str(value or "").strip()
    if not text or "-" not in text:
        return False
    left, right = text.split("-", 1)
    if not left.isdigit() or not right.isdigit():
        return False
    return int(left) <= int(right)


def _validate_provenance_entry(entry: dict[str, Any], *, field_prefix: str) -> list[str]:
    errors: list[str] = []
    evidence_id = str(entry.get("evidence_id") or "").strip().lower()
    if not _is_sha256(evidence_id):
        errors.append(f"{field_prefix}.evidence_id must be sha256")
    if not str(entry.get("evidence_type") or "").strip():
        errors.append(f"{field_prefix}.evidence_type must be non-empty")
    corpus_role = str(entry.get("corpus_role") or "").strip().lower()
    if corpus_role not in CORPUS_ROLES:
        errors.append(f"{field_prefix}.corpus_role must be one of {CORPUS_ROLES}")
    for key in ("corpus_id", "remote", "branch", "path", "source_artifact_name", "extraction_rule_id"):
        if not str(entry.get(key) or "").strip():
            errors.append(f"{field_prefix}.{key} must be non-empty")
    commit_sha = str(entry.get("commit_sha") or "").strip().lower()
    if not _is_commit_sha(commit_sha):
        errors.append(f"{field_prefix}.commit_sha must be hexadecimal commit SHA")
    line_start = entry.get("line_start")
    line_end = entry.get("line_end")
    if not isinstance(line_start, int) or line_start < 0:
        errors.append(f"{field_prefix}.line_start must be integer >= 0")
    if not isinstance(line_end, int) or line_end < 0:
        errors.append(f"{field_prefix}.line_end must be integer >= 0")
    if isinstance(line_start, int) and isinstance(line_end, int) and line_end < line_start:
        errors.append(f"{field_prefix}.line_end must be >= line_start")
    snippet_sha256 = str(entry.get("snippet_sha256") or "").strip().lower()
    if not _is_sha256(snippet_sha256):
        errors.append(f"{field_prefix}.snippet_sha256 must be sha256")
    source_hash = str(entry.get("source_artifact_sha256") or "").strip().lower()
    if not _is_sha256(source_hash):
        errors.append(f"{field_prefix}.source_artifact_sha256 must be sha256")
    return errors


def _required_for_m8(target_stage: str) -> bool:
    stage_id = str(target_stage or "").strip().upper()
    if stage_id not in TRACK_B_STAGE_ORDER:
        return False
    return TRACK_B_STAGE_ORDER.index(stage_id) > TRACK_B_STAGE_ORDER.index("STATIC_ANALYZED")


def _normalize_corpus_config(corpus: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    cfg = _safe_dict(corpus.get("discovery_config"))

    source_roots = _normalize_string_list(
        corpus.get("source_roots")
        if "source_roots" in corpus
        else cfg.get(
            "source_roots",
            context.get("source_roots", DEFAULT_DISCOVERY_CONFIG["source_roots"]),
        )
    )
    include_patterns = _normalize_string_list(
        corpus.get("include_patterns")
        if "include_patterns" in corpus
        else cfg.get(
            "include_patterns",
            context.get("include_patterns", DEFAULT_DISCOVERY_CONFIG["include_patterns"]),
        )
    )
    exclude_patterns = _normalize_string_list(
        corpus.get("exclude_patterns")
        if "exclude_patterns" in corpus
        else cfg.get(
            "exclude_patterns",
            context.get("exclude_patterns", DEFAULT_DISCOVERY_CONFIG["exclude_patterns"]),
        )
    )
    classification_rules = _normalize_classification_rules(
        corpus.get("classification_rules")
        if "classification_rules" in corpus
        else cfg.get(
            "classification_rules",
            context.get("classification_rules", DEFAULT_DISCOVERY_CONFIG["classification_rules"]),
        )
    )
    if not source_roots:
        raise RuntimeError("corpus source_roots must be non-empty")
    if not include_patterns:
        raise RuntimeError("corpus include_patterns must be non-empty")
    return {
        "source_roots": source_roots,
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "classification_rules": classification_rules,
    }


def _normalized_corpora_from_context(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_corpora = context.get("corpora")
    if not isinstance(raw_corpora, list):
        raise RuntimeError("corpora must be a list with downstream and upstream declarations")
    if len(raw_corpora) != 2:
        raise RuntimeError("corpora must contain exactly two entries")

    normalized: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for index, raw_corpus in enumerate(raw_corpora):
        if not isinstance(raw_corpus, dict):
            raise RuntimeError(f"corpora[{index}] must be an object")
        corpus_id = _require_non_empty_text(raw_corpus.get("corpus_id"), field=f"corpora[{index}].corpus_id")
        if corpus_id in seen_ids:
            raise RuntimeError(f"duplicate corpus_id detected: {corpus_id!r}")
        seen_ids.add(corpus_id)

        role = _require_non_empty_text(raw_corpus.get("corpus_role"), field=f"corpora[{index}].corpus_role").lower()
        if role not in CORPUS_ROLES:
            raise RuntimeError(f"corpora[{index}].corpus_role must be one of {CORPUS_ROLES}")
        if role in normalized:
            raise RuntimeError(f"duplicate corpus_role detected: {role!r}")

        repo_root = _require_non_empty_text(
            raw_corpus.get("repository_root"),
            field=f"corpora[{index}].repository_root",
        )
        repo_path = Path(repo_root).resolve()
        if not repo_path.exists() or not repo_path.is_dir():
            raise RuntimeError(f"corpora[{index}].repository_root does not exist: {repo_root}")

        revision = _normalize_revision(raw_corpus.get("revision"), field=f"corpora[{index}].revision")
        corpus_cfg = _normalize_corpus_config(raw_corpus, context)

        normalized[role] = {
            "corpus_id": corpus_id,
            "corpus_role": role,
            "repository_root": str(repo_path),
            "revision": revision,
            **corpus_cfg,
        }

    if set(normalized.keys()) != set(CORPUS_ROLES):
        raise RuntimeError("corpora roles must be exactly {downstream, upstream}")
    return normalized


def _normalized_corpora_list(corpora_by_role: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(corpora_by_role[role]) for role in CORPUS_ROLES]


def _build_discovery_inventory_for_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    repo_root = Path(str(corpus["repository_root"])).resolve()
    source_roots = _normalize_string_list(corpus.get("source_roots"))
    include_patterns = _normalize_string_list(corpus.get("include_patterns"))
    exclude_patterns = _normalize_string_list(corpus.get("exclude_patterns"))
    classification_rules = _normalize_classification_rules(corpus.get("classification_rules"))

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


def _dedupe_sort(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = str(value).strip()
        if text:
            seen[text] = None
    return sorted(seen.keys())


def _build_dts_relationship_index(*, repository_root: Path, files: list[str]) -> dict[str, Any]:
    include_re = re.compile(r'^\s*#include\s*[<"]([^">]+)[">]')
    phandle_re = re.compile(r"&([A-Za-z0-9_]+)")
    records: list[dict[str, Any]] = []

    for rel in _normalize_string_list(files):
        path = (repository_root / rel).resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"dts file missing on filesystem: {rel}")
        lines = _read_lines_fail_closed(path)
        includes: list[str] = []
        phandle_refs: list[str] = []
        for line in lines:
            inc = include_re.search(line)
            if inc:
                includes.append(str(inc.group(1)).strip())
            phandle_refs.extend([str(item).strip() for item in phandle_re.findall(line)])
        records.append(
            {
                "source_path": rel,
                "includes": _dedupe_sort(includes),
                "phandle_refs": _dedupe_sort(phandle_refs),
            }
        )

    records = sorted(records, key=lambda item: str(item.get("source_path")))
    include_total = sum(len(item["includes"]) for item in records)
    phandle_total = sum(len(item["phandle_refs"]) for item in records)
    return {
        "records": records,
        "counts": {
            "files": len(records),
            "include_refs": include_total,
            "phandle_refs": phandle_total,
        },
        "fingerprints": {
            "records": _canonical_value_sha256(records),
        },
    }


def _build_yaml_relationship_index(*, repository_root: Path, files: list[str]) -> dict[str, Any]:
    ref_re = re.compile(r"\$ref:\s*([^\s#]+)")
    compatible_re = re.compile(r"compatible\s*:\s*(.+)$")
    records: list[dict[str, Any]] = []

    for rel in _normalize_string_list(files):
        path = (repository_root / rel).resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"yaml file missing on filesystem: {rel}")
        lines = _read_lines_fail_closed(path)
        refs: list[str] = []
        compatibles: list[str] = []
        for line in lines:
            ref_match = ref_re.search(line)
            if ref_match:
                refs.append(str(ref_match.group(1)).strip())
            comp_match = compatible_re.search(line)
            if comp_match:
                compatibles.append(str(comp_match.group(1)).strip().strip("[]"))
            stripped = line.strip()
            if stripped.startswith("- ") and "," in stripped:
                compatibles.append(stripped.lstrip("- ").strip())
        records.append(
            {
                "source_path": rel,
                "schema_refs": _dedupe_sort(refs),
                "compatible_entries": _dedupe_sort(compatibles),
            }
        )

    records = sorted(records, key=lambda item: str(item.get("source_path")))
    return {
        "records": records,
        "counts": {
            "files": len(records),
            "schema_refs": sum(len(item["schema_refs"]) for item in records),
            "compatible_entries": sum(len(item["compatible_entries"]) for item in records),
        },
        "fingerprints": {
            "records": _canonical_value_sha256(records),
        },
    }


def _build_kconfig_relationship_index(*, repository_root: Path, files: list[str]) -> dict[str, Any]:
    config_re = re.compile(r"^\s*config\s+([A-Za-z0-9_]+)")
    select_re = re.compile(r"^\s*select\s+([A-Za-z0-9_]+)")
    depends_re = re.compile(r"^\s*depends on\s+(.+)$")
    imply_re = re.compile(r"^\s*imply\s+([A-Za-z0-9_]+)")
    records: list[dict[str, Any]] = []

    for rel in _normalize_string_list(files):
        path = (repository_root / rel).resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"kconfig file missing on filesystem: {rel}")
        lines = _read_lines_fail_closed(path)
        config_symbols: list[str] = []
        selects: list[str] = []
        depends_on: list[str] = []
        implies: list[str] = []
        for line in lines:
            m = config_re.search(line)
            if m:
                config_symbols.append(str(m.group(1)).strip())
            m = select_re.search(line)
            if m:
                selects.append(str(m.group(1)).strip())
            m = depends_re.search(line)
            if m:
                depends_on.append(str(m.group(1)).strip())
            m = imply_re.search(line)
            if m:
                implies.append(str(m.group(1)).strip())
        records.append(
            {
                "source_path": rel,
                "config_symbols": _dedupe_sort(config_symbols),
                "selects": _dedupe_sort(selects),
                "depends_on": _dedupe_sort(depends_on),
                "implies": _dedupe_sort(implies),
            }
        )

    records = sorted(records, key=lambda item: str(item.get("source_path")))
    return {
        "records": records,
        "counts": {
            "files": len(records),
            "config_symbols": sum(len(item["config_symbols"]) for item in records),
            "selects": sum(len(item["selects"]) for item in records),
            "depends_on": sum(len(item["depends_on"]) for item in records),
            "implies": sum(len(item["implies"]) for item in records),
        },
        "fingerprints": {
            "records": _canonical_value_sha256(records),
        },
    }


def _build_makefile_relationship_index(*, repository_root: Path, files: list[str]) -> dict[str, Any]:
    assign_re = re.compile(r"^\s*([A-Za-z0-9_.$()/-]+)\s*\+?=\s*(.+)$")
    config_re = re.compile(r"CONFIG_[A-Za-z0-9_]+")
    records: list[dict[str, Any]] = []

    for rel in _normalize_string_list(files):
        path = (repository_root / rel).resolve()
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"makefile missing on filesystem: {rel}")
        lines = _read_lines_fail_closed(path)
        assignments: list[dict[str, Any]] = []
        object_targets: list[str] = []
        config_refs: list[str] = []
        for line in lines:
            config_refs.extend(config_re.findall(line))
            m = assign_re.search(line)
            if not m:
                continue
            lhs = str(m.group(1)).strip()
            rhs_tokens = [token.strip() for token in str(m.group(2)).split() if token.strip()]
            for token in rhs_tokens:
                if token.endswith(".o"):
                    object_targets.append(token)
            assignments.append(
                {
                    "lhs": lhs,
                    "rhs_tokens": rhs_tokens,
                }
            )
        assignments = _sorted_unique_dicts(
            assignments,
            key_fn=lambda item: (str(item.get("lhs")), tuple(item.get("rhs_tokens", []))),
        )
        records.append(
            {
                "source_path": rel,
                "assignments": assignments,
                "object_targets": _dedupe_sort(object_targets),
                "config_refs": _dedupe_sort(config_refs),
            }
        )

    records = sorted(records, key=lambda item: str(item.get("source_path")))
    return {
        "records": records,
        "counts": {
            "files": len(records),
            "assignments": sum(len(item["assignments"]) for item in records),
            "object_targets": sum(len(item["object_targets"]) for item in records),
            "config_refs": sum(len(item["config_refs"]) for item in records),
        },
        "fingerprints": {
            "records": _canonical_value_sha256(records),
        },
    }


def _build_downstream_upstream_relationship_index(
    *,
    downstream: dict[str, Any],
    upstream: dict[str, Any],
) -> dict[str, Any]:
    down_families = _safe_dict(downstream.get("file_families"))
    up_families = _safe_dict(upstream.get("file_families"))
    records: list[dict[str, Any]] = []
    for key in CLASSIFICATION_KEYS:
        down_files = _normalize_string_list(down_families.get(key))
        up_files = _normalize_string_list(up_families.get(key))
        down_set = set(down_files)
        up_set = set(up_files)
        shared = sorted(down_set.intersection(up_set))
        downstream_only = sorted(down_set.difference(up_set))
        upstream_only = sorted(up_set.difference(down_set))
        records.append(
            {
                "relationship_type": key,
                "shared_paths": shared,
                "downstream_only_paths": downstream_only,
                "upstream_only_paths": upstream_only,
            }
        )
    records = sorted(records, key=lambda item: str(item.get("relationship_type")))
    return {
        "records": records,
        "counts": {
            "relationship_types": len(records),
            "shared_paths": sum(len(item["shared_paths"]) for item in records),
            "downstream_only_paths": sum(len(item["downstream_only_paths"]) for item in records),
            "upstream_only_paths": sum(len(item["upstream_only_paths"]) for item in records),
        },
        "fingerprints": {
            "records": _canonical_value_sha256(records),
        },
    }


def _comparison_delta(*, downstream_values: list[str], upstream_values: list[str]) -> dict[str, Any]:
    down = sorted(set(downstream_values))
    up = sorted(set(upstream_values))
    down_set = set(down)
    up_set = set(up)
    shared = sorted(down_set.intersection(up_set))
    downstream_only = sorted(down_set.difference(up_set))
    upstream_only = sorted(up_set.difference(down_set))
    delta = {
        "downstream_count": len(down),
        "upstream_count": len(up),
        "shared_count": len(shared),
        "downstream_only": downstream_only,
        "upstream_only": upstream_only,
        "shared": shared,
    }
    delta["fingerprint"] = _canonical_value_sha256(delta)
    return delta


def _signal_satisfied(delta: dict[str, Any]) -> bool:
    fingerprint = str(delta.get("fingerprint") or "").strip()
    return bool(fingerprint)


def _confidence_weights_from_context(context: dict[str, Any]) -> dict[str, dict[str, float]]:
    raw = context.get("track_b_confidence_weights")
    base = {
        stage: dict(DEFAULT_TRACK_B_CONFIDENCE_WEIGHTS.get(stage, {}))
        for stage in TRACK_B_CONFIDENCE_SIGNALS.keys()
    }
    if raw is None:
        return base
    if not isinstance(raw, dict):
        raise RuntimeError("track_b_confidence_weights must be an object when provided")

    for raw_stage, raw_weights in raw.items():
        stage_id = str(raw_stage or "").strip().upper()
        if stage_id not in TRACK_B_CONFIDENCE_SIGNALS:
            raise RuntimeError(f"track_b_confidence_weights has unknown stage: {raw_stage!r}")
        if not isinstance(raw_weights, dict):
            raise RuntimeError(f"track_b_confidence_weights[{stage_id}] must be an object")
        allowed_signals = set(TRACK_B_CONFIDENCE_SIGNALS[stage_id])
        for raw_signal, raw_weight in raw_weights.items():
            signal_id = str(raw_signal or "").strip()
            if not signal_id:
                raise RuntimeError(f"track_b_confidence_weights[{stage_id}] contains empty signal id")
            if signal_id not in allowed_signals:
                raise RuntimeError(
                    f"track_b_confidence_weights[{stage_id}] has unknown signal id: {signal_id!r}"
                )
            if not isinstance(raw_weight, (int, float)):
                raise RuntimeError(
                    f"track_b_confidence_weights[{stage_id}][{signal_id}] must be numeric"
                )
            weight = float(raw_weight)
            if not weight > 0.0:
                raise RuntimeError(
                    f"track_b_confidence_weights[{stage_id}][{signal_id}] must be > 0"
                )
            base[stage_id][signal_id] = weight
    return base


def _discovered_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    corpora = payload.get("corpora", [])
    corpus_roles_integrity = 0.0
    repository_provenance_integrity = 0.0
    if isinstance(corpora, list) and len(corpora) == 2:
        roles = {str(_safe_dict(item).get("corpus_role") or "").strip().lower() for item in corpora}
        if roles == set(CORPUS_ROLES):
            corpus_roles_integrity = 1.0
        provenance_ok = True
        for item in corpora:
            corpus = _safe_dict(item)
            revision = _safe_dict(corpus.get("revision"))
            if not (
                str(revision.get("remote") or "").strip()
                and str(revision.get("branch") or "").strip()
                and _is_commit_sha(str(revision.get("commit_sha") or "").strip().lower())
            ):
                provenance_ok = False
                break
        repository_provenance_integrity = 1.0 if provenance_ok else 0.0

    inventories = _safe_dict(payload.get("discovery_inventory"))
    inventory_ok = True
    for role in CORPUS_ROLES:
        inventory = _safe_dict(inventories.get(role))
        all_files = inventory.get("all_files")
        if not isinstance(all_files, list) or not all_files:
            inventory_ok = False
            break
        counts = _safe_dict(inventory.get("counts"))
        fingerprints = _safe_dict(inventory.get("fingerprints"))
        all_files_ok = isinstance(counts.get("all_files"), int) and counts.get("all_files") == len(all_files)
        if not all_files_ok or not str(fingerprints.get("all_files") or "").strip():
            inventory_ok = False
            break
        families = _safe_dict(inventory.get("file_families"))
        for key in CLASSIFICATION_KEYS:
            family_list = families.get(key, [])
            if not isinstance(family_list, list):
                inventory_ok = False
                break
            if counts.get(key) != len(family_list):
                inventory_ok = False
                break
            if not str(fingerprints.get(key) or "").strip():
                inventory_ok = False
                break
        if not inventory_ok:
            break
    discovery_inventory_integrity = 1.0 if inventory_ok else 0.0

    return {
        "corpus_roles_integrity": corpus_roles_integrity,
        "repository_provenance_integrity": repository_provenance_integrity,
        "discovery_inventory_integrity": discovery_inventory_integrity,
    }


def _indexed_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    corpus_indexes = _safe_dict(payload.get("corpus_indexes"))
    dual_corpus_ok = True
    source_records_aggregate: list[dict[str, Any]] = []
    for role in CORPUS_ROLES:
        corpus = _safe_dict(corpus_indexes.get(role))
        families = _safe_dict(corpus.get("file_families"))
        for key in CLASSIFICATION_KEYS:
            if not isinstance(families.get(key), list) or not families.get(key):
                dual_corpus_ok = False
                break
        analysis_inputs = _safe_dict(corpus.get("analysis_inputs"))
        source_records = analysis_inputs.get("source_records")
        counts = _safe_dict(analysis_inputs.get("counts"))
        fingerprints = _safe_dict(analysis_inputs.get("fingerprints"))
        if not isinstance(source_records, list) or not source_records:
            dual_corpus_ok = False
            break
        if counts.get("source_records") != len(source_records):
            dual_corpus_ok = False
            break
        observed = str(fingerprints.get("source_records") or "").strip()
        if not observed or observed != _canonical_value_sha256(source_records):
            dual_corpus_ok = False
            break
        source_records_aggregate.extend(source_records)
        if not dual_corpus_ok:
            break

    relationship_indexes = _safe_dict(payload.get("relationship_indexes"))
    relationship_index_integrity = 1.0
    for key in RELATIONSHIP_INDEX_KEYS:
        index = _safe_dict(relationship_indexes.get(key))
        records = index.get("records")
        counts = _safe_dict(index.get("counts"))
        fingerprints = _safe_dict(index.get("fingerprints"))
        if not isinstance(records, list):
            relationship_index_integrity = 0.0
            break
        if not isinstance(counts, dict):
            relationship_index_integrity = 0.0
            break
        observed = str(fingerprints.get("records") or "").strip()
        if not observed or observed != _canonical_value_sha256(records):
            relationship_index_integrity = 0.0
            break

    static_input_integrity = 1.0 if bool(source_records_aggregate) else 0.0
    lineage_integrity = 1.0 if _is_sha256(payload.get("discovered_artifact_sha256")) else 0.0
    return {
        "dual_corpus_index_integrity": 1.0 if dual_corpus_ok else 0.0,
        "relationship_index_integrity": relationship_index_integrity,
        "static_input_integrity": static_input_integrity,
        "lineage_integrity": lineage_integrity,
    }


def _static_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    comparison_signals = _safe_dict(payload.get("comparison_signals"))
    required = (
        "symbols",
        "includes",
        "headers",
        "structs",
        "dependency_relationships",
        "dts_relationships",
        "yaml_relationships",
        "kconfig_relationships",
        "makefile_relationships",
    )
    comparison_signals_integrity = 1.0
    deterministic_delta_integrity = 1.0
    for key in required:
        signal = _safe_dict(comparison_signals.get(key))
        if not signal:
            comparison_signals_integrity = 0.0
            deterministic_delta_integrity = 0.0
            break
        for field in ("downstream_only", "upstream_only", "shared"):
            if not isinstance(signal.get(field), list):
                comparison_signals_integrity = 0.0
                deterministic_delta_integrity = 0.0
                break
        if not isinstance(signal.get("downstream_count"), int):
            comparison_signals_integrity = 0.0
            deterministic_delta_integrity = 0.0
            break
        if not isinstance(signal.get("upstream_count"), int):
            comparison_signals_integrity = 0.0
            deterministic_delta_integrity = 0.0
            break
        observed = str(signal.get("fingerprint") or "").strip()
        if not observed:
            deterministic_delta_integrity = 0.0
            break
    lineage_integrity = 1.0 if _is_sha256(payload.get("indexed_artifact_sha256")) else 0.0
    return {
        "comparison_signals_integrity": comparison_signals_integrity,
        "deterministic_delta_integrity": deterministic_delta_integrity,
        "lineage_integrity": lineage_integrity,
    }


def _equivalence_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    candidates = payload.get("candidate_mappings", [])
    candidate_mapping_integrity = 1.0 if isinstance(candidates, list) else 0.0
    mapping_provenance_integrity = 1.0
    if not isinstance(candidates, list):
        mapping_provenance_integrity = 0.0
    else:
        for candidate in candidates:
            item = _safe_dict(candidate)
            evidence = item.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                mapping_provenance_integrity = 0.0
                break
            for raw_entry in evidence:
                if _validate_provenance_entry(_safe_dict(raw_entry), field_prefix="equivalence.evidence"):
                    mapping_provenance_integrity = 0.0
                    break
            if not mapping_provenance_integrity:
                break
    lineage = _safe_dict(payload.get("lineage"))
    mapping_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in ("indexed_artifact_sha256", "static_artifact_sha256")
    ) else 0.0
    return {
        "candidate_mapping_integrity": candidate_mapping_integrity,
        "mapping_provenance_integrity": mapping_provenance_integrity,
        "mapping_lineage_integrity": mapping_lineage_integrity,
    }


def _dependency_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    records = payload.get("dependency_records", [])
    dependency_matrix_integrity = 1.0 if isinstance(records, list) else 0.0
    dependency_provenance_integrity = 1.0
    if not isinstance(records, list):
        dependency_provenance_integrity = 0.0
    else:
        for record in records:
            item = _safe_dict(record)
            provenance = item.get("provenance", [])
            if not isinstance(provenance, list) or not provenance:
                dependency_provenance_integrity = 0.0
                break
            for entry in provenance:
                if _validate_provenance_entry(_safe_dict(entry), field_prefix="dependency.provenance"):
                    dependency_provenance_integrity = 0.0
                    break
            if not dependency_provenance_integrity:
                break
    lineage = _safe_dict(payload.get("lineage"))
    dependency_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in ("equivalence_artifact_sha256", "indexed_artifact_sha256")
    ) else 0.0
    return {
        "dependency_matrix_integrity": dependency_matrix_integrity,
        "dependency_provenance_integrity": dependency_provenance_integrity,
        "dependency_lineage_integrity": dependency_lineage_integrity,
    }


def _conflict_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    conflicts = payload.get("conflicts", [])
    conflict_ledger_integrity = 1.0 if isinstance(conflicts, list) else 0.0
    conflict_resolution_integrity = 1.0
    conflict_provenance_integrity = 1.0
    if isinstance(conflicts, list):
        for conflict in conflicts:
            item = _safe_dict(conflict)
            status = str(item.get("status") or "").strip().upper()
            if status not in {"UNRESOLVED", "RESOLVED"}:
                conflict_resolution_integrity = 0.0
            provenance = item.get("provenance", [])
            if not isinstance(provenance, list) or not provenance:
                conflict_provenance_integrity = 0.0
                break
            for raw_entry in provenance:
                if _validate_provenance_entry(_safe_dict(raw_entry), field_prefix="conflict.provenance"):
                    conflict_provenance_integrity = 0.0
                    break
            if not conflict_provenance_integrity:
                break
    else:
        conflict_resolution_integrity = 0.0
        conflict_provenance_integrity = 0.0
    lineage = _safe_dict(payload.get("lineage"))
    conflict_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in ("dependency_artifact_sha256", "equivalence_artifact_sha256")
    ) else 0.0
    return {
        "conflict_ledger_integrity": conflict_ledger_integrity,
        "conflict_resolution_integrity": conflict_resolution_integrity,
        "conflict_lineage_integrity": conflict_lineage_integrity,
    }


def _decision_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    decision_state = str(payload.get("decision_state") or "").strip().upper()
    decision_state_integrity = 1.0 if decision_state in EQUIVALENCE_DECISION_STATES else 0.0
    complexity = _safe_dict(payload.get("complexity"))
    decision_policy_integrity = 1.0 if (
        str(complexity.get("label") or "").strip().upper() in {"LOW", "MEDIUM", "HIGH"}
        and isinstance(complexity.get("risk_points"), int)
        and str(complexity.get("formula") or "").strip()
    ) else 0.0
    lineage = _safe_dict(payload.get("lineage"))
    decision_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in ("equivalence_artifact_sha256", "dependency_artifact_sha256", "conflict_artifact_sha256")
    ) else 0.0
    return {
        "decision_state_integrity": decision_state_integrity,
        "decision_policy_integrity": decision_policy_integrity,
        "decision_lineage_integrity": decision_lineage_integrity,
    }


def _report_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    report_completeness_integrity = 1.0 if (
        bool(_safe_dict(payload.get("downstream_component")).get("component_name"))
        and isinstance(payload.get("upstream_equivalents"), list)
        and isinstance(payload.get("required_patches"), list)
    ) else 0.0
    dependency_summary = payload.get("dependency_summary", {})
    report_provenance_integrity = 1.0
    if isinstance(dependency_summary, dict) and dependency_summary:
        provenance = _safe_dict(dependency_summary).get("provenance", [])
        if not isinstance(provenance, list) or not provenance:
            report_provenance_integrity = 0.0
        else:
            for raw_entry in provenance:
                if _validate_provenance_entry(_safe_dict(raw_entry), field_prefix="report.dependency_summary"):
                    report_provenance_integrity = 0.0
                    break
    lineage = _safe_dict(payload.get("lineage"))
    report_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in (
            "decision_artifact_sha256",
            "dependency_artifact_sha256",
            "conflict_artifact_sha256",
            "equivalence_artifact_sha256",
        )
    ) else 0.0
    return {
        "report_completeness_integrity": report_completeness_integrity,
        "report_provenance_integrity": report_provenance_integrity,
        "report_lineage_integrity": report_lineage_integrity,
    }


def _readiness_signal_scores(payload: dict[str, Any]) -> dict[str, float]:
    checks = _safe_dict(payload.get("mandatory_checks"))
    readiness_checks_integrity = 1.0
    for key in (
        "decision_unique_equivalent",
        "dependencies_resolved",
        "conflicts_resolved",
        "provenance_complete",
        "runtime_evidence_complete",
        "report_complete",
    ):
        if not isinstance(checks.get(key), bool):
            readiness_checks_integrity = 0.0
            break
    readiness_policy_integrity = 1.0 if (
        str(payload.get("readiness_status") or "").strip().upper() in {"READY", "NOT_READY"}
        and str(payload.get("decision_state") or "").strip().upper() in EQUIVALENCE_DECISION_STATES
    ) else 0.0
    lineage = _safe_dict(payload.get("lineage"))
    readiness_lineage_integrity = 1.0 if all(
        _is_sha256(str(lineage.get(key) or "").strip().lower())
        for key in ("report_artifact_sha256", "decision_artifact_sha256", "conflict_artifact_sha256")
    ) else 0.0
    return {
        "readiness_checks_integrity": readiness_checks_integrity,
        "readiness_policy_integrity": readiness_policy_integrity,
        "readiness_lineage_integrity": readiness_lineage_integrity,
    }


def _stage_signal_scores(stage_id: str, payload: dict[str, Any]) -> dict[str, float]:
    if stage_id == "DISCOVERED":
        return _discovered_signal_scores(payload)
    if stage_id == "INDEXED":
        return _indexed_signal_scores(payload)
    if stage_id == "STATIC_ANALYZED":
        return _static_signal_scores(payload)
    if stage_id == "EQUIVALENCE_MAPPED":
        return _equivalence_signal_scores(payload)
    if stage_id == "DEPENDENCIES_BOUND":
        return _dependency_signal_scores(payload)
    if stage_id == "CONFLICTS_EVALUATED":
        return _conflict_signal_scores(payload)
    if stage_id == "DECISION_FINALIZED":
        return _decision_signal_scores(payload)
    if stage_id == "REPORT_GENERATED":
        return _report_signal_scores(payload)
    if stage_id == "READINESS_GATED":
        return _readiness_signal_scores(payload)
    raise RuntimeError(f"unsupported confidence stage_id: {stage_id!r}")


def _compute_stage_confidence(
    *,
    stage_payloads: dict[str, dict[str, Any]],
    stage_weights: dict[str, dict[str, float]],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    confidence: dict[str, float] = {}
    confidence_details: dict[str, dict[str, Any]] = {}
    for stage_id in TRACK_B_STAGE_ORDER:
        payload = _safe_dict(stage_payloads.get(stage_id))
        if not payload:
            continue
        signals = _stage_signal_scores(stage_id, payload)
        result = compute_weighted_confidence(
            stage_id=stage_id,
            signal_scores=signals,
            signal_weights=stage_weights.get(stage_id, {}),
            required_signals=TRACK_B_CONFIDENCE_SIGNALS.get(stage_id, ()),
        )
        confidence[stage_id] = result["score"]
        confidence_details[stage_id] = result
    if not confidence:
        raise RuntimeError("stage confidence computation produced no stage scores")
    return confidence, confidence_details


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

    corpora = payload.get("corpora", [])
    if not isinstance(corpora, list):
        errors.append("corpora must be a list")
        corpora = []
    if len(corpora) != 2:
        errors.append("corpora must contain exactly two entries")
    seen_roles: set[str] = set()
    for index, corpus in enumerate(corpora):
        if not isinstance(corpus, dict):
            errors.append(f"corpora[{index}] must be an object")
            continue
        corpus_id = str(corpus.get("corpus_id") or "").strip()
        if not corpus_id:
            errors.append(f"corpora[{index}].corpus_id must be non-empty")
        role = str(corpus.get("corpus_role") or "").strip().lower()
        if role not in CORPUS_ROLES:
            errors.append(f"corpora[{index}].corpus_role must be one of {CORPUS_ROLES}")
        else:
            seen_roles.add(role)
        repo_root = str(corpus.get("repository_root") or "").strip()
        if not repo_root:
            errors.append(f"corpora[{index}].repository_root must be non-empty")
        for key in ("source_roots", "include_patterns", "exclude_patterns"):
            value = corpus.get(key, [])
            if not isinstance(value, list):
                errors.append(f"corpora[{index}].{key} must be a list")
        revision = corpus.get("revision")
        if not isinstance(revision, dict):
            errors.append(f"corpora[{index}].revision must be an object")
            revision = {}
        if not str(revision.get("remote") or "").strip():
            errors.append(f"corpora[{index}].revision.remote must be non-empty")
        if not str(revision.get("branch") or "").strip():
            errors.append(f"corpora[{index}].revision.branch must be non-empty")
        commit_sha = str(revision.get("commit_sha") or "").strip().lower()
        if not _is_commit_sha(commit_sha):
            errors.append(f"corpora[{index}].revision.commit_sha must be hexadecimal commit SHA")
    if seen_roles != set(CORPUS_ROLES):
        errors.append("corpora roles must be exactly {downstream, upstream}")

    inventory_by_role = payload.get("discovery_inventory")
    if not isinstance(inventory_by_role, dict):
        errors.append("discovery_inventory must be an object")
        inventory_by_role = {}

    for role in CORPUS_ROLES:
        inventory = inventory_by_role.get(role, {})
        if not isinstance(inventory, dict):
            errors.append(f"discovery_inventory.{role} must be an object")
            continue
        all_files = inventory.get("all_files", [])
        if not isinstance(all_files, list) or not all_files:
            errors.append(f"discovery_inventory.{role}.all_files must be a non-empty list")
            all_files = []
        counts = inventory.get("counts", {})
        fingerprints = inventory.get("fingerprints", {})
        families = inventory.get("file_families", {})
        if not isinstance(counts, dict):
            errors.append(f"discovery_inventory.{role}.counts must be an object")
            counts = {}
        if not isinstance(fingerprints, dict):
            errors.append(f"discovery_inventory.{role}.fingerprints must be an object")
            fingerprints = {}
        if not isinstance(families, dict):
            errors.append(f"discovery_inventory.{role}.file_families must be an object")
            families = {}
        for key in CLASSIFICATION_KEYS:
            files = families.get(key, [])
            if not isinstance(files, list):
                errors.append(f"discovery_inventory.{role}.file_families.{key} must be a list")
                continue
            count = counts.get(key)
            if not isinstance(count, int) or count != len(files):
                errors.append(
                    f"discovery_inventory.{role}.counts.{key} must equal len(file_families.{key})"
                )
            digest = str(fingerprints.get(key) or "").strip()
            if not digest:
                errors.append(f"discovery_inventory.{role}.fingerprints.{key} must be non-empty")
        all_count = counts.get("all_files")
        if not isinstance(all_count, int) or all_count != len(all_files):
            errors.append(f"discovery_inventory.{role}.counts.all_files must equal len(all_files)")
        all_digest = str(fingerprints.get("all_files") or "").strip()
        if not all_digest:
            errors.append(f"discovery_inventory.{role}.fingerprints.all_files must be non-empty")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
        evidence = {}
    source_locator = evidence.get("source_locator", [])
    if not isinstance(source_locator, list) or not source_locator:
        errors.append("evidence.source_locator must be a non-empty list")
    corpus_roles = evidence.get("corpus_roles", [])
    if not isinstance(corpus_roles, list) or sorted(corpus_roles) != sorted(list(CORPUS_ROLES)):
        errors.append("evidence.corpus_roles must contain downstream and upstream")
    provenance = evidence.get("repository_provenance", [])
    if not isinstance(provenance, list) or len(provenance) != 2:
        errors.append("evidence.repository_provenance must contain two entries")
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    if not isinstance(satisfied, list):
        errors.append("evidence.required_evidence_types_satisfied must be a list")
    else:
        required = {
            "source_locator",
            "corpus_declaration",
            "repository_provenance",
            "discovery_inventory",
        }
        if required != {str(item).strip() for item in satisfied}:
            errors.append("required discovered evidence types are not fully satisfied")
    return errors


def _validate_indexed_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_STAGE_INDEXED",
        expected_stage_id="INDEXED",
    )
    corpora = payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        errors.append("corpora must contain exactly two entries")

    corpus_indexes = payload.get("corpus_indexes")
    if not isinstance(corpus_indexes, dict):
        errors.append("corpus_indexes must be an object")
        corpus_indexes = {}
    for role in CORPUS_ROLES:
        corpus = corpus_indexes.get(role, {})
        if not isinstance(corpus, dict):
            errors.append(f"corpus_indexes.{role} must be an object")
            continue
        for key in ("corpus_id", "repository_root"):
            if not str(corpus.get(key) or "").strip():
                errors.append(f"corpus_indexes.{role}.{key} must be non-empty")
        families = corpus.get("file_families", {})
        counts = corpus.get("counts", {})
        fingerprints = corpus.get("fingerprints", {})
        analysis_inputs = corpus.get("analysis_inputs", {})
        if not isinstance(families, dict):
            errors.append(f"corpus_indexes.{role}.file_families must be an object")
            families = {}
        if not isinstance(counts, dict):
            errors.append(f"corpus_indexes.{role}.counts must be an object")
            counts = {}
        if not isinstance(fingerprints, dict):
            errors.append(f"corpus_indexes.{role}.fingerprints must be an object")
            fingerprints = {}
        for key in CLASSIFICATION_KEYS:
            files = families.get(key, [])
            if not isinstance(files, list):
                errors.append(f"corpus_indexes.{role}.file_families.{key} must be a list")
                continue
            if counts.get(key) != len(files):
                errors.append(f"corpus_indexes.{role}.counts.{key} must equal len(file_families.{key})")
            if not str(fingerprints.get(key) or "").strip():
                errors.append(f"corpus_indexes.{role}.fingerprints.{key} must be non-empty")
        source_records = _safe_dict(analysis_inputs).get("source_records", [])
        input_counts = _safe_dict(analysis_inputs).get("counts", {})
        input_fingerprints = _safe_dict(analysis_inputs).get("fingerprints", {})
        if not isinstance(source_records, list) or not source_records:
            errors.append(f"corpus_indexes.{role}.analysis_inputs.source_records must be a non-empty list")
        else:
            if _safe_dict(input_counts).get("source_records") != len(source_records):
                errors.append(
                    f"corpus_indexes.{role}.analysis_inputs.counts.source_records must equal len(source_records)"
                )
            observed_source_hash = str(_safe_dict(input_fingerprints).get("source_records") or "").strip()
            expected_source_hash = _canonical_value_sha256(source_records)
            if observed_source_hash != expected_source_hash:
                errors.append(f"corpus_indexes.{role}.analysis_inputs.fingerprints.source_records mismatch")

    relationship_indexes = payload.get("relationship_indexes")
    if not isinstance(relationship_indexes, dict):
        errors.append("relationship_indexes must be an object")
        relationship_indexes = {}
    for key in RELATIONSHIP_INDEX_KEYS:
        index = relationship_indexes.get(key, {})
        if not isinstance(index, dict):
            errors.append(f"relationship_indexes.{key} must be an object")
            continue
        records = index.get("records", [])
        counts = index.get("counts", {})
        fingerprints = index.get("fingerprints", {})
        if not isinstance(records, list):
            errors.append(f"relationship_indexes.{key}.records must be a list")
        if not isinstance(counts, dict):
            errors.append(f"relationship_indexes.{key}.counts must be an object")
        observed_hash = str(_safe_dict(fingerprints).get("records") or "").strip()
        if not observed_hash or observed_hash != _canonical_value_sha256(records if isinstance(records, list) else []):
            errors.append(f"relationship_indexes.{key}.fingerprints.records mismatch")

    discovered_hash = str(payload.get("discovered_artifact_sha256") or "").strip()
    if not _is_sha256(discovered_hash):
        errors.append("discovered_artifact_sha256 must be sha256")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        if not isinstance(satisfied, list):
            errors.append("evidence.required_evidence_types_satisfied must be a list")
        else:
            required = {
                "dual_corpus_index",
                "downstream_upstream_relationship_index",
                "dts_relationship_index",
                "yaml_relationship_index",
                "kconfig_relationship_index",
                "makefile_relationship_index",
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
    corpora = payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        errors.append("corpora must contain exactly two entries")

    comparison_signals = payload.get("comparison_signals")
    if not isinstance(comparison_signals, dict):
        errors.append("comparison_signals must be an object")
        comparison_signals = {}
    required_signals = {
        "symbols",
        "includes",
        "headers",
        "structs",
        "dependency_relationships",
        "dts_relationships",
        "yaml_relationships",
        "kconfig_relationships",
        "makefile_relationships",
    }
    for key in sorted(required_signals):
        signal = comparison_signals.get(key, {})
        if not isinstance(signal, dict):
            errors.append(f"comparison_signals.{key} must be an object")
            continue
        for field in ("downstream_only", "upstream_only", "shared"):
            if not isinstance(signal.get(field), list):
                errors.append(f"comparison_signals.{key}.{field} must be a list")
        for field in ("downstream_count", "upstream_count", "shared_count"):
            if not isinstance(signal.get(field), int):
                errors.append(f"comparison_signals.{key}.{field} must be an integer")
        fingerprint = str(signal.get("fingerprint") or "").strip()
        if not fingerprint:
            errors.append(f"comparison_signals.{key}.fingerprint must be non-empty")

    delta_fingerprints = payload.get("delta_fingerprints", {})
    if not isinstance(delta_fingerprints, dict):
        errors.append("delta_fingerprints must be an object")
        delta_fingerprints = {}
    for key in sorted(required_signals):
        if not str(delta_fingerprints.get(key) or "").strip():
            errors.append(f"delta_fingerprints.{key} must be non-empty")

    indexed_hash = str(payload.get("indexed_artifact_sha256") or "").strip()
    if not _is_sha256(indexed_hash):
        errors.append("indexed_artifact_sha256 must be sha256")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be an object")
    else:
        satisfied = evidence.get("required_evidence_types_satisfied", [])
        required = {
            "comparison_signals",
            "deterministic_deltas",
            "downstream_upstream_comparison",
            "indexed_lineage",
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
                elif value < 0.0 or value > 1.0:
                    errors.append(f"stage_confidence.{stage} must be within [0.0, 1.0]")

    details = payload.get("stage_confidence_details", {})
    if not isinstance(details, dict):
        errors.append("execution stage_confidence_details must be an object")
    else:
        for stage, detail in details.items():
            stage_id = str(stage or "").strip().upper()
            if stage_id not in TRACK_B_STAGE_ORDER:
                errors.append(f"stage_confidence_details contains unknown stage {stage!r}")
                continue
            if not isinstance(detail, dict):
                errors.append(f"stage_confidence_details.{stage_id} must be an object")
                continue
            if str(detail.get("stage_id") or "").strip().upper() != stage_id:
                errors.append(f"stage_confidence_details.{stage_id}.stage_id mismatch")
            score = detail.get("score")
            if not isinstance(score, (int, float)):
                errors.append(f"stage_confidence_details.{stage_id}.score must be numeric")
            elif score < 0.0 or score > 1.0:
                errors.append(f"stage_confidence_details.{stage_id}.score must be within [0.0, 1.0]")
            required_signals = detail.get("required_signals", [])
            if not isinstance(required_signals, list) or not required_signals:
                errors.append(f"stage_confidence_details.{stage_id}.required_signals must be a non-empty list")
            signals = detail.get("signals", [])
            if not isinstance(signals, list) or not signals:
                errors.append(f"stage_confidence_details.{stage_id}.signals must be a non-empty list")
            else:
                for index, signal in enumerate(signals):
                    if not isinstance(signal, dict):
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}] must be an object"
                        )
                        continue
                    signal_id = str(signal.get("signal_id") or "").strip()
                    if not signal_id:
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}].signal_id must be non-empty"
                        )
                    value = signal.get("score")
                    if not isinstance(value, (int, float)):
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}].score must be numeric"
                        )
                    elif value < 0.0 or value > 1.0:
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}].score must be within [0.0, 1.0]"
                        )
                    weight = signal.get("weight")
                    if not isinstance(weight, (int, float)):
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}].weight must be numeric"
                        )
                    elif weight <= 0.0:
                        errors.append(
                            f"stage_confidence_details.{stage_id}.signals[{index}].weight must be > 0"
                        )
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


def _validate_comparison_signal_payload(
    signal: dict[str, Any],
    *,
    field_prefix: str,
) -> list[str]:
    errors: list[str] = []
    for key in ("downstream_only", "upstream_only", "shared"):
        if not isinstance(signal.get(key), list):
            errors.append(f"{field_prefix}.{key} must be a list")
    for key in ("downstream_count", "upstream_count", "shared_count"):
        if not isinstance(signal.get(key), int):
            errors.append(f"{field_prefix}.{key} must be an integer")
    if not str(signal.get("fingerprint") or "").strip():
        errors.append(f"{field_prefix}.fingerprint must be non-empty")
    return errors


def _validate_comparison_matrix_schema(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("artifact_name") or "").strip() != "TRACK_B_COMPARISON_MATRIX":
        errors.append("comparison_matrix artifact_name mismatch")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        errors.append("comparison_matrix schema_version mismatch")
    if str(payload.get("classification") or "").strip().upper() != "PASS":
        errors.append("comparison_matrix classification must be PASS")
    if not str(payload.get("platform") or "").strip():
        errors.append("comparison_matrix platform must be non-empty")
    corpora = payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        errors.append("comparison_matrix corpora must contain exactly two entries")
    else:
        roles = {str(_safe_dict(item).get("corpus_role") or "").strip().lower() for item in corpora}
        if roles != set(CORPUS_ROLES):
            errors.append("comparison_matrix corpora roles must be exactly {downstream, upstream}")
        for index, corpus in enumerate(corpora):
            item = _safe_dict(corpus)
            if not str(item.get("corpus_id") or "").strip():
                errors.append(f"comparison_matrix corpora[{index}].corpus_id must be non-empty")
            revision = _safe_dict(item.get("revision"))
            if not str(revision.get("remote") or "").strip():
                errors.append(f"comparison_matrix corpora[{index}].revision.remote must be non-empty")
            if not str(revision.get("branch") or "").strip():
                errors.append(f"comparison_matrix corpora[{index}].revision.branch must be non-empty")
            if not _is_commit_sha(str(revision.get("commit_sha") or "").strip().lower()):
                errors.append(
                    f"comparison_matrix corpora[{index}].revision.commit_sha must be hexadecimal commit SHA"
                )

    signals = payload.get("comparison_signals", {})
    if not isinstance(signals, dict):
        errors.append("comparison_matrix comparison_signals must be an object")
        signals = {}
    required_signals = (
        "symbols",
        "includes",
        "headers",
        "structs",
        "dependency_relationships",
        "dts_relationships",
        "yaml_relationships",
        "kconfig_relationships",
        "makefile_relationships",
    )
    for key in required_signals:
        signal = _safe_dict(signals.get(key))
        if not signal:
            errors.append(f"comparison_matrix comparison_signals.{key} must be an object")
            continue
        errors.extend(_validate_comparison_signal_payload(signal, field_prefix=f"comparison_signals.{key}"))

    lineage = payload.get("lineage", {})
    if not isinstance(lineage, dict):
        errors.append("comparison_matrix lineage must be an object")
        lineage = {}
    for key in ("discovered_artifact_sha256", "indexed_artifact_sha256", "static_artifact_sha256"):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"comparison_matrix lineage.{key} must be sha256")
    reasons = payload.get("fail_closed_reasons", [])
    if not isinstance(reasons, list):
        errors.append("comparison_matrix fail_closed_reasons must be a list")
    return errors


def _validate_comparison_readiness_schema(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("artifact_name") or "").strip() != "TRACK_B_COMPARISON_READINESS":
        errors.append("comparison_readiness artifact_name mismatch")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        errors.append("comparison_readiness schema_version mismatch")
    if str(payload.get("classification") or "").strip().upper() not in {"PASS", "FAIL_CLOSED"}:
        errors.append("comparison_readiness classification must be PASS or FAIL_CLOSED")
    required_signals = payload.get("required_signals", [])
    satisfied_signals = payload.get("satisfied_signals", [])
    if not isinstance(required_signals, list) or not required_signals:
        errors.append("comparison_readiness required_signals must be a non-empty list")
    if not isinstance(satisfied_signals, list):
        errors.append("comparison_readiness satisfied_signals must be a list")
    missing_signals = payload.get("missing_signals", [])
    if not isinstance(missing_signals, list):
        errors.append("comparison_readiness missing_signals must be a list")
    confidence_summary = payload.get("confidence_summary", {})
    if not isinstance(confidence_summary, dict):
        errors.append("comparison_readiness confidence_summary must be an object")
    else:
        for key in ("stage_confidence", "stage_confidence_details"):
            if key not in confidence_summary:
                errors.append(f"comparison_readiness confidence_summary.{key} missing")
    reasons = payload.get("fail_closed_reasons", [])
    if not isinstance(reasons, list):
        errors.append("comparison_readiness fail_closed_reasons must be a list")
    return errors


def _build_comparison_matrix_payload(
    *,
    discovered_payload: dict[str, Any],
    indexed_payload: dict[str, Any],
    static_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact_name": "TRACK_B_COMPARISON_MATRIX",
        "schema_version": "1.0",
        "classification": "PASS",
        "platform": str(discovered_payload.get("platform") or "").strip().lower(),
        "corpora": discovered_payload.get("corpora", []),
        "comparison_signals": static_payload.get("comparison_signals", {}),
        "lineage": {
            "discovered_artifact_sha256": canonical_json_sha256(discovered_payload),
            "indexed_artifact_sha256": canonical_json_sha256(indexed_payload),
            "static_artifact_sha256": canonical_json_sha256(static_payload),
        },
        "fail_closed_reasons": [],
    }


def _build_comparison_readiness_payload(
    *,
    comparison_matrix_payload: dict[str, Any],
    stage_confidence: dict[str, float],
    stage_confidence_details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    comparison_signals = _safe_dict(comparison_matrix_payload.get("comparison_signals"))
    required_signals = sorted(comparison_signals.keys())
    satisfied_signals = sorted(
        [
            key
            for key in required_signals
            if _signal_satisfied(_safe_dict(comparison_signals.get(key)))
        ]
    )
    missing_signals = sorted(set(required_signals).difference(set(satisfied_signals)))
    classification = "PASS" if not missing_signals else "FAIL_CLOSED"
    return {
        "artifact_name": "TRACK_B_COMPARISON_READINESS",
        "schema_version": "1.0",
        "classification": classification,
        "required_signals": required_signals,
        "satisfied_signals": satisfied_signals,
        "missing_signals": missing_signals,
        "confidence_summary": {
            "stage_confidence": stage_confidence,
            "stage_confidence_details": stage_confidence_details,
        },
        "fail_closed_reasons": [] if not missing_signals else [f"missing comparison signals: {missing_signals}"],
    }


def _build_discovered(context: dict[str, Any], _stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    platform = str(context.get("platform") or "").strip().lower()
    corpora_by_role = _normalized_corpora_from_context(context)
    corpora = _normalized_corpora_list(corpora_by_role)
    inventory_by_role = {
        role: _build_discovery_inventory_for_corpus(corpora_by_role[role]) for role in CORPUS_ROLES
    }
    assets = _safe_dict(context.get("control_plane_assets"))
    source_locator = _normalize_string_list(list(assets.values()))

    repository_provenance = [
        {
            "corpus_id": corpus["corpus_id"],
            "corpus_role": corpus["corpus_role"],
            "remote": corpus["revision"]["remote"],
            "branch": corpus["revision"]["branch"],
            "commit_sha": corpus["revision"]["commit_sha"],
        }
        for corpus in corpora
    ]

    return {
        "artifact_name": "TRACK_B_STAGE_DISCOVERED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "DISCOVERED",
        "platform": platform,
        "corpora": corpora,
        "discovery_inventory": inventory_by_role,
        "evidence": {
            "source_locator": source_locator,
            "corpus_roles": list(CORPUS_ROLES),
            "repository_provenance": repository_provenance,
            "required_evidence_types_satisfied": [
                "source_locator",
                "corpus_declaration",
                "repository_provenance",
                "discovery_inventory",
            ],
        },
        "fail_closed_reasons": [],
    }


def _build_indexed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    discovered = _safe_dict(stage_payloads.get("DISCOVERED"))
    discovered_corpora = discovered.get("corpora", [])
    if not isinstance(discovered_corpora, list) or len(discovered_corpora) != 2:
        raise RuntimeError("discovered corpora must contain downstream and upstream")
    corpora_by_role = {
        str(_safe_dict(item).get("corpus_role") or "").strip().lower(): _safe_dict(item)
        for item in discovered_corpora
    }
    if set(corpora_by_role.keys()) != set(CORPUS_ROLES):
        raise RuntimeError("discovered corpora roles must be exactly {downstream, upstream}")

    inventory_by_role = _safe_dict(discovered.get("discovery_inventory"))
    corpus_indexes: dict[str, dict[str, Any]] = {}
    static_input_ready = True
    for role in CORPUS_ROLES:
        corpus = _safe_dict(corpora_by_role.get(role))
        inventory = _safe_dict(inventory_by_role.get(role))
        repo_root = Path(str(corpus.get("repository_root") or "")).resolve()
        families = _safe_dict(inventory.get("file_families"))
        normalized_families = {key: _normalize_string_list(families.get(key)) for key in CLASSIFICATION_KEYS}

        source_locators = [
            {
                "source_root": source_root,
                "corpus_id": str(corpus.get("corpus_id") or "").strip(),
                "corpus_role": role,
                "repo_root_path": str(repo_root),
                "repo_url": str(_safe_dict(corpus.get("revision")).get("remote") or "").strip(),
                "repo_branch": str(_safe_dict(corpus.get("revision")).get("branch") or "").strip(),
                "repo_head_sha": str(_safe_dict(corpus.get("revision")).get("commit_sha") or "").strip(),
                "snapshot_ts": "",
            }
            for source_root in _normalize_string_list(corpus.get("source_roots"))
        ]
        source_records = _build_indexed_source_records(
            repository_root=repo_root,
            driver_files=normalized_families["driver_files"],
            source_locators=source_locators,
            platform_tag=str(context.get("platform") or "").strip().lower(),
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
        if not source_records:
            static_input_ready = False

        corpus_indexes[role] = {
            "corpus_id": str(corpus.get("corpus_id") or "").strip(),
            "repository_root": str(repo_root),
            "file_families": normalized_families,
            "counts": counts,
            "fingerprints": fingerprints,
            "analysis_inputs": {
                "source_records": source_records,
                "counts": analysis_input_counts,
                "fingerprints": analysis_input_fingerprints,
            },
        }

    downstream = _safe_dict(corpus_indexes.get("downstream"))
    upstream = _safe_dict(corpus_indexes.get("upstream"))
    relationship_indexes = {
        "downstream_upstream_relationship_index": _build_downstream_upstream_relationship_index(
            downstream=downstream,
            upstream=upstream,
        ),
        "dts_relationship_index": {
            "records": [
                {
                    "corpus_role": role,
                    **_build_dts_relationship_index(
                        repository_root=Path(str(_safe_dict(corpus_indexes[role]).get("repository_root"))),
                        files=_normalize_string_list(
                            _safe_dict(corpus_indexes[role]).get("file_families", {}).get("dts_files")
                        ),
                    ),
                }
                for role in CORPUS_ROLES
            ]
        },
        "yaml_relationship_index": {
            "records": [
                {
                    "corpus_role": role,
                    **_build_yaml_relationship_index(
                        repository_root=Path(str(_safe_dict(corpus_indexes[role]).get("repository_root"))),
                        files=_normalize_string_list(
                            _safe_dict(corpus_indexes[role]).get("file_families", {}).get("yaml_files")
                        ),
                    ),
                }
                for role in CORPUS_ROLES
            ]
        },
        "kconfig_relationship_index": {
            "records": [
                {
                    "corpus_role": role,
                    **_build_kconfig_relationship_index(
                        repository_root=Path(str(_safe_dict(corpus_indexes[role]).get("repository_root"))),
                        files=_normalize_string_list(
                            _safe_dict(corpus_indexes[role]).get("file_families", {}).get("config_files")
                        ),
                    ),
                }
                for role in CORPUS_ROLES
            ]
        },
        "makefile_relationship_index": {
            "records": [
                {
                    "corpus_role": role,
                    **_build_makefile_relationship_index(
                        repository_root=Path(str(_safe_dict(corpus_indexes[role]).get("repository_root"))),
                        files=_normalize_string_list(
                            _safe_dict(corpus_indexes[role]).get("file_families", {}).get("makefile_files")
                        ),
                    ),
                }
                for role in CORPUS_ROLES
            ]
        },
    }
    for key in ("dts_relationship_index", "yaml_relationship_index", "kconfig_relationship_index", "makefile_relationship_index"):
        records = relationship_indexes[key]["records"]
        relationship_indexes[key] = {
            "records": records,
            "counts": {
                "corpora": len(records),
                "records": sum(len(_safe_dict(item).get("records", [])) for item in records),
            },
            "fingerprints": {
                "records": _canonical_value_sha256(records),
            },
        }
    relationship_indexes["downstream_upstream_relationship_index"] = {
        **relationship_indexes["downstream_upstream_relationship_index"],
        "fingerprints": {
            "records": _canonical_value_sha256(
                _safe_dict(relationship_indexes["downstream_upstream_relationship_index"]).get("records", [])
            ),
        },
    }

    satisfied = [
        "dual_corpus_index",
        "downstream_upstream_relationship_index",
        "dts_relationship_index",
        "yaml_relationship_index",
        "kconfig_relationship_index",
        "makefile_relationship_index",
    ]
    if static_input_ready:
        satisfied.append("static_input_index")

    return {
        "artifact_name": "TRACK_B_STAGE_INDEXED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "INDEXED",
        "corpora": _normalized_corpora_list(corpora_by_role),
        "corpus_indexes": corpus_indexes,
        "relationship_indexes": relationship_indexes,
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
    function_definitions: list[dict[str, Any]] = []
    struct_definitions: list[dict[str, Any]] = []

    for line_number, line in enumerate(lines, start=1):
        include_match = _INCLUDE_RE.match(line)
        if include_match:
            style = "quote" if include_match.group(1) == '"' else "angle"
            header = _normalized_rel_path(include_match.group(2).strip())
            if header:
                snippet_hash = hashlib.sha256(
                    f"{source_path}:{line_number}:{line.strip()}".encode("utf-8")
                ).hexdigest()
                include_directives.append(
                    {
                        "included_header": header,
                        "include_style": style,
                        "line_start": line_number,
                        "line_end": line_number,
                        "snippet_hash": snippet_hash,
                    }
                )

        func_match = _FUNC_RE.match(line)
        if func_match:
            symbol_name = str(func_match.group(1) or "").strip()
            if symbol_name:
                function_symbols.add(symbol_name)
                function_definitions.append(
                    {
                        "symbol": symbol_name,
                        "line_start": line_number,
                        "line_end": line_number,
                        "snippet_hash": hashlib.sha256(
                            f"{source_path}:{line_number}:{line.strip()}".encode("utf-8")
                        ).hexdigest(),
                    }
                )

        for struct_match in _STRUCT_RE.findall(line):
            symbol_name = str(struct_match or "").strip()
            if symbol_name:
                struct_symbols.add(symbol_name)
                struct_definitions.append(
                    {
                        "symbol": symbol_name,
                        "line_start": line_number,
                        "line_end": line_number,
                        "snippet_hash": hashlib.sha256(
                            f"{source_path}:{line_number}:{line.strip()}".encode("utf-8")
                        ).hexdigest(),
                    }
                )

    include_directives = sorted(
        include_directives,
        key=lambda item: (
            str(item.get("included_header")),
            str(item.get("include_style")),
            int(item.get("line_start") or 0),
        ),
    )
    function_definitions = _sorted_unique_dicts(
        function_definitions,
        key_fn=lambda item: (
            str(item.get("symbol")),
            int(item.get("line_start") or 0),
            int(item.get("line_end") or 0),
            str(item.get("snippet_hash")),
        ),
    )
    struct_definitions = _sorted_unique_dicts(
        struct_definitions,
        key_fn=lambda item: (
            str(item.get("symbol")),
            int(item.get("line_start") or 0),
            int(item.get("line_end") or 0),
            str(item.get("snippet_hash")),
        ),
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
        "function_definitions": function_definitions,
        "struct_definitions": struct_definitions,
    }


def _source_record_id(record: dict[str, Any]) -> str:
    basis = {
        "source_path": str(record.get("source_path") or "").strip(),
        "file_sha256": str(record.get("file_sha256") or "").strip(),
        "corpus_id": str(record.get("corpus_id") or "").strip(),
        "repo_relative_path": str(record.get("repo_relative_path") or "").strip(),
    }
    return _canonical_value_sha256(basis)


def _repo_relative_path_for_source(*, source_path: str, locator: dict[str, str]) -> str:
    source = _normalized_rel_path(source_path)
    repo_root_path = _normalized_rel_path(str(locator.get("repo_root_path") or "").strip()).strip(".")
    if not repo_root_path:
        return source
    if source == repo_root_path:
        return ""
    prefix = repo_root_path + "/"
    if source.startswith(prefix):
        return source[len(prefix) :]
    return source


def _build_indexed_source_records(
    *,
    repository_root: Path,
    driver_files: list[str],
    source_locators: list[dict[str, str]],
    platform_tag: str,
) -> list[dict[str, Any]]:
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
        record = _extract_indexed_source_record(
            source_path=rel_path,
            file_path=file_path,
        )
        locator = _find_source_locator_for_path(source_path=rel_path, source_locators=source_locators)
        record["corpus_id"] = str(locator.get("corpus_id") or "").strip()
        record["repo_relative_path"] = _repo_relative_path_for_source(source_path=rel_path, locator=locator)
        record["platform_tag"] = str(platform_tag or "").strip().lower()
        record["source_record_id"] = _source_record_id(record)
        source_records.append(record)
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


def _corpus_role_from_path(path: str) -> str:
    normalized = _normalized_rel_path(path)
    corpus_id = _corpus_id_from_source_root(normalized)
    return _corpus_role_from_source_root(normalized, corpus_id)


def _mapping_type_for_link(*, source_path: str, header_path: str) -> str:
    source_role = _corpus_role_from_path(source_path)
    header_role = _corpus_role_from_path(header_path)
    if source_role and header_role and source_role != header_role:
        return "migrated"
    return "same"


def _mapping_confidence_score(*, source_path: str, header_path: str) -> float:
    mapping_type = _mapping_type_for_link(source_path=source_path, header_path=header_path)
    if mapping_type == "migrated":
        return 0.95
    return 1.0


def _build_static_analyzed(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    indexed = _safe_dict(stage_payloads.get("INDEXED"))
    corpora = indexed.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        raise RuntimeError("indexed corpora must contain downstream and upstream")
    corpus_indexes = _safe_dict(indexed.get("corpus_indexes"))
    relationship_indexes = _safe_dict(indexed.get("relationship_indexes"))

    def _signal_values_for_role(role: str) -> dict[str, list[str]]:
        corpus = _safe_dict(corpus_indexes.get(role))
        analysis_inputs = _safe_dict(corpus.get("analysis_inputs"))
        source_records = analysis_inputs.get("source_records", [])
        if not isinstance(source_records, list) or not source_records:
            raise RuntimeError(f"indexed corpus_indexes.{role}.analysis_inputs.source_records missing")

        symbols: list[str] = []
        includes: list[str] = []
        headers: list[str] = []
        structs: list[str] = []
        dependencies: list[str] = []
        for raw in source_records:
            record = _safe_dict(raw)
            source_path = str(record.get("source_path") or "").strip()
            if not source_path:
                raise RuntimeError(f"indexed corpus {role} source record missing source_path")
            for symbol in _normalize_string_list(record.get("functions")):
                symbols.append(f"function:{source_path}:{symbol}")
                dependencies.append(f"defines:function:{source_path}:{symbol}")
            for symbol in _normalize_string_list(record.get("structs")):
                symbols.append(f"struct:{source_path}:{symbol}")
                structs.append(f"struct:{source_path}:{symbol}")
                dependencies.append(f"defines:struct:{source_path}:{symbol}")
            for include in record.get("include_directives", []):
                include_obj = _safe_dict(include)
                header = str(include_obj.get("included_header") or "").strip()
                include_style = str(include_obj.get("include_style") or "").strip().lower()
                if not header:
                    continue
                includes.append(f"{source_path}|{header}|{include_style}")
                headers.append(f"{source_path}|{header}|{include_style}")
                dependencies.append(f"include:{source_path}:{header}:{include_style}")

        def _records_from_relationship_index(index_name: str) -> list[str]:
            index = _safe_dict(relationship_indexes.get(index_name))
            role_records = [
                item
                for item in index.get("records", [])
                if isinstance(item, dict) and str(item.get("corpus_role") or "").strip().lower() == role
            ]
            if not role_records:
                return []
            role_record = _safe_dict(role_records[0])
            records = role_record.get("records", [])
            if not isinstance(records, list):
                return []
            return [_canonical_value_sha256(_safe_dict(item)) for item in records if isinstance(item, dict)]

        return {
            "symbols": _dedupe_sort(symbols),
            "includes": _dedupe_sort(includes),
            "headers": _dedupe_sort(headers),
            "structs": _dedupe_sort(structs),
            "dependency_relationships": _dedupe_sort(dependencies),
            "dts_relationships": _dedupe_sort(_records_from_relationship_index("dts_relationship_index")),
            "yaml_relationships": _dedupe_sort(_records_from_relationship_index("yaml_relationship_index")),
            "kconfig_relationships": _dedupe_sort(_records_from_relationship_index("kconfig_relationship_index")),
            "makefile_relationships": _dedupe_sort(_records_from_relationship_index("makefile_relationship_index")),
        }

    downstream_values = _signal_values_for_role("downstream")
    upstream_values = _signal_values_for_role("upstream")
    comparison_signals = {
        key: _comparison_delta(
            downstream_values=downstream_values.get(key, []),
            upstream_values=upstream_values.get(key, []),
        )
        for key in (
            "symbols",
            "includes",
            "headers",
            "structs",
            "dependency_relationships",
            "dts_relationships",
            "yaml_relationships",
            "kconfig_relationships",
            "makefile_relationships",
        )
    }
    delta_fingerprints = {key: str(value.get("fingerprint") or "").strip() for key, value in comparison_signals.items()}

    return {
        "artifact_name": "TRACK_B_STAGE_STATIC_ANALYZED",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "STATIC_ANALYZED",
        "corpora": corpora,
        "comparison_signals": comparison_signals,
        "delta_fingerprints": delta_fingerprints,
        "indexed_artifact_sha256": canonical_json_sha256(indexed),
        "evidence": {
            "required_evidence_types_satisfied": [
                "comparison_signals",
                "deterministic_deltas",
                "downstream_upstream_comparison",
                "indexed_lineage",
            ],
        },
        "fail_closed_reasons": [],
    }


def _role_source_records(indexed_payload: dict[str, Any], *, role: str) -> list[dict[str, Any]]:
    corpus_indexes = _safe_dict(indexed_payload.get("corpus_indexes"))
    corpus = _safe_dict(corpus_indexes.get(role))
    analysis_inputs = _safe_dict(corpus.get("analysis_inputs"))
    records = analysis_inputs.get("source_records", [])
    if not isinstance(records, list):
        return []
    normalized = [_safe_dict(item) for item in records if isinstance(item, dict)]
    return sorted(normalized, key=lambda item: str(item.get("source_path") or ""))


def _role_dts_records(indexed_payload: dict[str, Any], *, role: str) -> list[dict[str, Any]]:
    relationship_indexes = _safe_dict(indexed_payload.get("relationship_indexes"))
    dts_index = _safe_dict(relationship_indexes.get("dts_relationship_index"))
    records = dts_index.get("records", [])
    if not isinstance(records, list):
        return []
    role_records: list[dict[str, Any]] = []
    for item in records:
        entry = _safe_dict(item)
        item_role = str(entry.get("corpus_role") or "").strip().lower()
        if item_role != role:
            continue
        leaf_records = entry.get("records", [])
        if not isinstance(leaf_records, list):
            continue
        role_records.extend([_safe_dict(leaf) for leaf in leaf_records if isinstance(leaf, dict)])
    return sorted(role_records, key=lambda item: str(item.get("source_path") or ""))


def _record_symbol_line(record: dict[str, Any], *, symbol: str, definition_key: str) -> tuple[int, int, str]:
    definitions = record.get(definition_key, [])
    if not isinstance(definitions, list):
        return 0, 0, ""
    matches: list[dict[str, Any]] = []
    for raw in definitions:
        item = _safe_dict(raw)
        if str(item.get("symbol") or "").strip() == symbol:
            matches.append(item)
    if not matches:
        return 0, 0, ""
    matches = sorted(
        matches,
        key=lambda item: (
            int(item.get("line_start") or 0),
            int(item.get("line_end") or 0),
            str(item.get("snippet_hash") or ""),
        ),
    )
    first = matches[0]
    return (
        int(first.get("line_start") or 0),
        int(first.get("line_end") or 0),
        str(first.get("snippet_hash") or "").strip(),
    )


def _mapping_candidates_for_request(
    *,
    indexed_payload: dict[str, Any],
    upstreaming_request: dict[str, Any],
    corpora: list[dict[str, Any]],
    source_artifact_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    corpora_map = _corpora_revision_map(corpora)
    downstream_records = _role_source_records(indexed_payload, role="downstream")
    upstream_records = _role_source_records(indexed_payload, role="upstream")
    downstream_dts = _role_dts_records(indexed_payload, role="downstream")
    upstream_dts = _role_dts_records(indexed_payload, role="upstream")

    downstream_component = _safe_dict(upstreaming_request.get("downstream_component"))
    component_type = str(downstream_component.get("component_type") or "").strip().lower()
    component_name = str(downstream_component.get("component_name") or "").strip()
    requested_source_path = str(downstream_component.get("source_path") or "").strip()

    downstream_anchor: dict[str, Any] = {
        "component_type": component_type,
        "component_name": component_name,
        "source_path": requested_source_path,
        "line_start": int(downstream_component.get("line_start") or 0),
        "line_end": int(downstream_component.get("line_end") or 0),
    }

    downstream_matches: list[dict[str, Any]] = []
    upstream_matches: list[dict[str, Any]] = []

    if component_type == "function":
        for record in downstream_records:
            functions = _normalize_string_list(record.get("functions"))
            if component_name not in functions:
                continue
            if requested_source_path and str(record.get("source_path") or "").strip() != requested_source_path:
                continue
            line_start, line_end, snippet_hash = _record_symbol_line(
                record, symbol=component_name, definition_key="function_definitions"
            )
            downstream_matches.append(
                {
                    "source_path": str(record.get("source_path") or "").strip(),
                    "symbol": component_name,
                    "line_start": line_start,
                    "line_end": line_end,
                    "snippet_hash": snippet_hash,
                }
            )
        for record in upstream_records:
            functions = _normalize_string_list(record.get("functions"))
            if component_name not in functions:
                continue
            line_start, line_end, snippet_hash = _record_symbol_line(
                record, symbol=component_name, definition_key="function_definitions"
            )
            upstream_matches.append(
                {
                    "source_path": str(record.get("source_path") or "").strip(),
                    "symbol": component_name,
                    "line_start": line_start,
                    "line_end": line_end,
                    "snippet_hash": snippet_hash,
                }
            )
    elif component_type == "driver":
        requested_basename = str(Path(component_name).name)
        for record in downstream_records:
            source_path = str(record.get("source_path") or "").strip()
            if source_path == component_name or str(Path(source_path).name) == requested_basename:
                downstream_matches.append(
                    {
                        "source_path": source_path,
                        "symbol": source_path,
                        "line_start": 1,
                        "line_end": 1,
                        "snippet_hash": hashlib.sha256(source_path.encode("utf-8")).hexdigest(),
                    }
                )
        for record in upstream_records:
            source_path = str(record.get("source_path") or "").strip()
            if source_path == component_name or str(Path(source_path).name) == requested_basename:
                upstream_matches.append(
                    {
                        "source_path": source_path,
                        "symbol": source_path,
                        "line_start": 1,
                        "line_end": 1,
                        "snippet_hash": hashlib.sha256(source_path.encode("utf-8")).hexdigest(),
                    }
                )
    elif component_type == "dt_node":
        for record in downstream_dts:
            includes = _normalize_string_list(record.get("includes"))
            phandle_refs = _normalize_string_list(record.get("phandle_refs"))
            if component_name not in includes and component_name not in phandle_refs:
                continue
            source_path = str(record.get("source_path") or "").strip()
            downstream_matches.append(
                {
                    "source_path": source_path,
                    "symbol": component_name,
                    "line_start": 1,
                    "line_end": 1,
                    "snippet_hash": _canonical_value_sha256(record),
                }
            )
        for record in upstream_dts:
            includes = _normalize_string_list(record.get("includes"))
            phandle_refs = _normalize_string_list(record.get("phandle_refs"))
            if component_name not in includes and component_name not in phandle_refs:
                continue
            source_path = str(record.get("source_path") or "").strip()
            upstream_matches.append(
                {
                    "source_path": source_path,
                    "symbol": component_name,
                    "line_start": 1,
                    "line_end": 1,
                    "snippet_hash": _canonical_value_sha256(record),
                }
            )

    downstream_matches = _sorted_unique_dicts(
        downstream_matches,
        key_fn=lambda item: (
            str(item.get("source_path")),
            str(item.get("symbol")),
            int(item.get("line_start") or 0),
            int(item.get("line_end") or 0),
            str(item.get("snippet_hash")),
        ),
    )
    upstream_matches = _sorted_unique_dicts(
        upstream_matches,
        key_fn=lambda item: (
            str(item.get("source_path")),
            str(item.get("symbol")),
            int(item.get("line_start") or 0),
            int(item.get("line_end") or 0),
            str(item.get("snippet_hash")),
        ),
    )

    if downstream_matches:
        anchor = downstream_matches[0]
        downstream_anchor = {
            **downstream_anchor,
            "source_path": str(anchor.get("source_path") or "").strip(),
            "line_start": int(anchor.get("line_start") or 0),
            "line_end": int(anchor.get("line_end") or 0),
        }

    provenance_complete = (
        1.0
        if bool(corpora_map.get("upstream"))
        and _is_commit_sha(str(_safe_dict(corpora_map.get("upstream")).get("commit_sha") or ""))
        else 0.0
    )
    downstream_path = str(downstream_anchor.get("source_path") or "").strip()
    downstream_line_start = int(downstream_anchor.get("line_start") or 0)
    downstream_line_end = int(downstream_anchor.get("line_end") or 0)
    downstream_provenance = _build_provenance_entry(
        corpus_role="downstream",
        corpora_map=corpora_map,
        path=downstream_path,
        line_start=downstream_line_start,
        line_end=downstream_line_end,
        evidence_type="downstream_component_anchor",
        source_artifact_sha256=source_artifact_sha256,
        source_artifact_name="TRACK_B_STAGE_INDEXED",
        extraction_rule_id="m8_equivalence_downstream_anchor",
        snippet_basis=f"downstream:{component_type}:{component_name}:{downstream_path}",
    )
    downstream_anchor["provenance"] = downstream_provenance

    candidates: list[dict[str, Any]] = []
    for upstream_match in upstream_matches:
        upstream_path = str(upstream_match.get("source_path") or "").strip()
        upstream_symbol = str(upstream_match.get("symbol") or "").strip() or component_name
        upstream_line_start = int(upstream_match.get("line_start") or 0)
        upstream_line_end = int(upstream_match.get("line_end") or 0)
        symbol_exact = 1.0 if upstream_symbol == component_name else 0.0
        path_exact = 1.0 if upstream_path and downstream_path and upstream_path == downstream_path else 0.0
        score = round((0.6 * symbol_exact) + (0.3 * path_exact) + (0.1 * provenance_complete), 4)

        upstream_provenance = _build_provenance_entry(
            corpus_role="upstream",
            corpora_map=corpora_map,
            path=upstream_path,
            line_start=upstream_line_start,
            line_end=upstream_line_end,
            evidence_type="upstream_component_candidate",
            source_artifact_sha256=source_artifact_sha256,
            source_artifact_name="TRACK_B_STAGE_INDEXED",
            extraction_rule_id="m8_equivalence_upstream_candidate",
            snippet_basis=f"upstream:{component_type}:{component_name}:{upstream_path}",
        )
        candidate_identity = {
            "component_type": component_type,
            "component_name": component_name,
            "upstream_path": upstream_path,
            "line_start": upstream_line_start,
            "line_end": upstream_line_end,
            "score": score,
        }
        candidates.append(
            {
                "candidate_id": _canonical_value_sha256(candidate_identity),
                "mapping_state": "CANDIDATE",
                "score": score,
                "score_components": {
                    "symbol_exact": symbol_exact,
                    "path_exact": path_exact,
                    "provenance_complete": provenance_complete,
                    "formula": "(symbol_exact*0.6)+(path_exact*0.3)+(provenance_complete*0.1)",
                },
                "downstream_component": {
                    "component_type": component_type,
                    "component_name": component_name,
                    "source_path": downstream_path,
                    "line_start": downstream_line_start,
                    "line_end": downstream_line_end,
                },
                "upstream_component": {
                    "component_type": component_type,
                    "component_name": upstream_symbol,
                    "source_path": upstream_path,
                    "line_start": upstream_line_start,
                    "line_end": upstream_line_end,
                },
                "evidence": [
                    downstream_provenance,
                    upstream_provenance,
                ],
            }
        )

    candidates = sorted(
        candidates,
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(_safe_dict(item.get("upstream_component")).get("component_name") or ""),
            str(_safe_dict(item.get("upstream_component")).get("source_path") or ""),
            int(_safe_dict(item.get("upstream_component")).get("line_start") or 0),
        ),
    )
    return downstream_anchor, candidates


def _validate_equivalence_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_EQUIVALENCE_MAP",
        expected_stage_id="EQUIVALENCE_MAPPED",
    )
    request = _safe_dict(payload.get("upstreaming_request"))
    if not request:
        errors.append("upstreaming_request must be an object")
    else:
        if not str(request.get("request_id") or "").strip():
            errors.append("upstreaming_request.request_id must be non-empty")
        downstream_component = _safe_dict(request.get("downstream_component"))
        if not downstream_component:
            errors.append("upstreaming_request.downstream_component must be an object")
        else:
            component_type = str(downstream_component.get("component_type") or "").strip().lower()
            if component_type not in UPSTREAMING_COMPONENT_TYPES:
                errors.append("upstreaming_request.downstream_component.component_type is invalid")
            if not str(downstream_component.get("component_name") or "").strip():
                errors.append("upstreaming_request.downstream_component.component_name must be non-empty")
            if not str(downstream_component.get("source_path") or "").strip():
                errors.append("upstreaming_request.downstream_component.source_path must be non-empty")
        runtime_evidence_required = request.get("runtime_evidence_required")
        if not isinstance(runtime_evidence_required, bool):
            errors.append("upstreaming_request.runtime_evidence_required must be bool")
        runtime_evidence_refs = request.get("runtime_evidence_refs", [])
        if not isinstance(runtime_evidence_refs, list):
            errors.append("upstreaming_request.runtime_evidence_refs must be a list")
        else:
            for index, raw_ref in enumerate(runtime_evidence_refs):
                ref = str(raw_ref or "").strip()
                if not ref:
                    errors.append(f"upstreaming_request.runtime_evidence_refs[{index}] must be non-empty")
                    continue
                if not RUNTIME_EVIDENCE_REF_RE.match(ref):
                    errors.append(
                        f"upstreaming_request.runtime_evidence_refs[{index}] "
                        "must match '<runtime|m7>:<type>:<id>' deterministic format"
                    )
            if runtime_evidence_required is True and not runtime_evidence_refs:
                errors.append(
                    "upstreaming_request.runtime_evidence_refs must be non-empty when runtime_evidence_required=true"
                )

    corpora = payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        errors.append("corpora must contain exactly two entries")

    candidates = payload.get("candidate_mappings", [])
    if not isinstance(candidates, list):
        errors.append("candidate_mappings must be a list")
        candidates = []
    for index, raw_candidate in enumerate(candidates):
        candidate = _safe_dict(raw_candidate)
        if not str(candidate.get("candidate_id") or "").strip():
            errors.append(f"candidate_mappings[{index}].candidate_id must be non-empty")
        score = candidate.get("score")
        if not isinstance(score, (int, float)):
            errors.append(f"candidate_mappings[{index}].score must be numeric")
        elif float(score) < 0.0 or float(score) > 1.0:
            errors.append(f"candidate_mappings[{index}].score must be within [0.0, 1.0]")
        evidence = candidate.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"candidate_mappings[{index}].evidence must be a non-empty list")
        else:
            for evidence_index, raw_evidence in enumerate(evidence):
                errors.extend(
                    _validate_provenance_entry(
                        _safe_dict(raw_evidence),
                        field_prefix=f"candidate_mappings[{index}].evidence[{evidence_index}]",
                    )
                )

    ranking_policy = _safe_dict(payload.get("ranking_policy"))
    if not str(ranking_policy.get("formula") or "").strip():
        errors.append("ranking_policy.formula must be non-empty")
    tie_break_order = ranking_policy.get("tie_break_order", [])
    if not isinstance(tie_break_order, list) or not tie_break_order:
        errors.append("ranking_policy.tie_break_order must be a non-empty list")

    lineage = _safe_dict(payload.get("lineage"))
    for key in ("indexed_artifact_sha256", "static_artifact_sha256"):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")

    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "equivalence_candidates",
        "equivalence_provenance",
        "static_lineage",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("equivalence evidence set must contain all required evidence types")
    return errors


def _build_equivalence_mapped(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    static_payload = _safe_dict(stage_payloads.get("STATIC_ANALYZED"))
    indexed_payload = _safe_dict(stage_payloads.get("INDEXED"))
    if not static_payload:
        raise RuntimeError("STATIC_ANALYZED payload is required for EQUIVALENCE_MAPPED")
    if not indexed_payload:
        raise RuntimeError("INDEXED payload is required for EQUIVALENCE_MAPPED")

    upstreaming_request = _normalize_upstreaming_request(context)
    if not upstreaming_request:
        raise RuntimeError("upstreaming_request is required for EQUIVALENCE_MAPPED")

    corpora = indexed_payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        raise RuntimeError("indexed corpora must contain downstream and upstream entries")
    indexed_sha = canonical_json_sha256(indexed_payload)
    static_sha = canonical_json_sha256(static_payload)
    downstream_anchor, candidates = _mapping_candidates_for_request(
        indexed_payload=indexed_payload,
        upstreaming_request=upstreaming_request,
        corpora=corpora,
        source_artifact_sha256=indexed_sha,
    )

    return {
        "artifact_name": "TRACK_B_EQUIVALENCE_MAP",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "EQUIVALENCE_MAPPED",
        "upstreaming_request": upstreaming_request,
        "corpora": corpora,
        "downstream_anchor": downstream_anchor,
        "candidate_mappings": candidates,
        "ranking_policy": {
            "formula": "(symbol_exact*0.6)+(path_exact*0.3)+(provenance_complete*0.1)",
            "tie_break_order": [
                "score_desc",
                "symbol_asc",
                "path_asc",
                "line_asc",
            ],
        },
        "lineage": {
            "indexed_artifact_sha256": indexed_sha,
            "static_artifact_sha256": static_sha,
        },
        "evidence": {
            "required_evidence_types_satisfied": [
                "equivalence_candidates",
                "equivalence_provenance",
                "static_lineage",
            ]
        },
        "fail_closed_reasons": [],
    }


def _relationship_tokens(indexed_payload: dict[str, Any], *, role: str, index_name: str) -> list[str]:
    relationship_indexes = _safe_dict(indexed_payload.get("relationship_indexes"))
    index = _safe_dict(relationship_indexes.get(index_name))
    role_entries = index.get("records", [])
    if not isinstance(role_entries, list):
        return []
    rows: list[dict[str, Any]] = []
    for entry in role_entries:
        item = _safe_dict(entry)
        if str(item.get("corpus_role") or "").strip().lower() != role:
            continue
        records = item.get("records", [])
        if not isinstance(records, list):
            continue
        rows.extend([_safe_dict(record) for record in records if isinstance(record, dict)])
    flattened: list[str] = []
    for row in rows:
        for key in sorted(row.keys()):
            value = row.get(key)
            if isinstance(value, list):
                for leaf in value:
                    text = str(leaf).strip()
                    if text:
                        flattened.append(f"{key}:{text}")
            elif isinstance(value, str):
                text = value.strip()
                if text:
                    flattened.append(f"{key}:{text}")
    return _dedupe_sort(flattened)


def _source_record_by_path(source_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for record in source_records:
        source_path = str(record.get("source_path") or "").strip()
        if source_path:
            mapping[source_path] = record
    return mapping


def _validate_dependency_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_DEPENDENCY_MATRIX",
        expected_stage_id="DEPENDENCIES_BOUND",
    )
    records = payload.get("dependency_records", [])
    if not isinstance(records, list):
        errors.append("dependency_records must be a list")
        records = []
    for index, raw_record in enumerate(records):
        record = _safe_dict(raw_record)
        if not str(record.get("candidate_id") or "").strip():
            errors.append(f"dependency_records[{index}].candidate_id must be non-empty")
        mandatory_checks = _safe_dict(record.get("mandatory_checks"))
        if not mandatory_checks:
            errors.append(f"dependency_records[{index}].mandatory_checks must be an object")
        else:
            for key in (
                "headers_resolved",
                "kconfig_resolved",
                "makefile_resolved",
                "dts_resolved",
                "yaml_resolved",
            ):
                if not isinstance(mandatory_checks.get(key), bool):
                    errors.append(f"dependency_records[{index}].mandatory_checks.{key} must be bool")
        for key in (
            "missing_headers",
            "missing_kconfig",
            "missing_makefile_objects",
            "missing_dts",
            "missing_yaml",
        ):
            if not isinstance(record.get(key), list):
                errors.append(f"dependency_records[{index}].{key} must be a list")
        if not isinstance(record.get("missing_dependency_count"), int):
            errors.append(f"dependency_records[{index}].missing_dependency_count must be an integer")
        provenance = record.get("provenance", [])
        if not isinstance(provenance, list) or not provenance:
            errors.append(f"dependency_records[{index}].provenance must be a non-empty list")
        else:
            for provenance_index, raw_entry in enumerate(provenance):
                errors.extend(
                    _validate_provenance_entry(
                        _safe_dict(raw_entry),
                        field_prefix=(
                            f"dependency_records[{index}].provenance[{provenance_index}]"
                        ),
                    )
                )

    lineage = _safe_dict(payload.get("lineage"))
    for key in ("equivalence_artifact_sha256", "indexed_artifact_sha256"):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")

    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "dependency_binding",
        "dependency_provenance",
        "equivalence_lineage",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("dependency evidence set must contain all required evidence types")
    return errors


def _build_dependencies_bound(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    indexed_payload = _safe_dict(stage_payloads.get("INDEXED"))
    equivalence_payload = _safe_dict(stage_payloads.get("EQUIVALENCE_MAPPED"))
    if not indexed_payload:
        raise RuntimeError("INDEXED payload is required for DEPENDENCIES_BOUND")
    if not equivalence_payload:
        raise RuntimeError("EQUIVALENCE_MAPPED payload is required for DEPENDENCIES_BOUND")

    corpora = indexed_payload.get("corpora", [])
    if not isinstance(corpora, list) or len(corpora) != 2:
        raise RuntimeError("indexed corpora must contain downstream and upstream entries")
    corpora_map = _corpora_revision_map(corpora)

    downstream_records = _role_source_records(indexed_payload, role="downstream")
    upstream_records = _role_source_records(indexed_payload, role="upstream")
    downstream_by_path = _source_record_by_path(downstream_records)
    upstream_by_path = _source_record_by_path(upstream_records)
    downstream_kconfig = _relationship_tokens(indexed_payload, role="downstream", index_name="kconfig_relationship_index")
    upstream_kconfig = _relationship_tokens(indexed_payload, role="upstream", index_name="kconfig_relationship_index")
    downstream_makefile = _relationship_tokens(indexed_payload, role="downstream", index_name="makefile_relationship_index")
    upstream_makefile = _relationship_tokens(indexed_payload, role="upstream", index_name="makefile_relationship_index")
    downstream_dts = _relationship_tokens(indexed_payload, role="downstream", index_name="dts_relationship_index")
    upstream_dts = _relationship_tokens(indexed_payload, role="upstream", index_name="dts_relationship_index")
    downstream_yaml = _relationship_tokens(indexed_payload, role="downstream", index_name="yaml_relationship_index")
    upstream_yaml = _relationship_tokens(indexed_payload, role="upstream", index_name="yaml_relationship_index")

    candidates = equivalence_payload.get("candidate_mappings", [])
    if not isinstance(candidates, list):
        raise RuntimeError("equivalence candidate_mappings must be a list")

    indexed_sha = canonical_json_sha256(indexed_payload)
    dependency_records: list[dict[str, Any]] = []
    for raw_candidate in candidates:
        candidate = _safe_dict(raw_candidate)
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        downstream_component = _safe_dict(candidate.get("downstream_component"))
        upstream_component = _safe_dict(candidate.get("upstream_component"))
        downstream_path = str(downstream_component.get("source_path") or "").strip()
        upstream_path = str(upstream_component.get("source_path") or "").strip()

        downstream_record = _safe_dict(downstream_by_path.get(downstream_path))
        upstream_record = _safe_dict(upstream_by_path.get(upstream_path))
        downstream_headers = _dedupe_sort(
            [
                str(_safe_dict(item).get("included_header") or "").strip()
                for item in downstream_record.get("include_directives", [])
                if isinstance(item, dict)
            ]
        )
        upstream_headers = _dedupe_sort(
            [
                str(_safe_dict(item).get("included_header") or "").strip()
                for item in upstream_record.get("include_directives", [])
                if isinstance(item, dict)
            ]
        )
        missing_headers = sorted(set(downstream_headers).difference(set(upstream_headers)))
        missing_kconfig = sorted(set(downstream_kconfig).difference(set(upstream_kconfig)))
        missing_makefile = sorted(set(downstream_makefile).difference(set(upstream_makefile)))
        missing_dts = sorted(set(downstream_dts).difference(set(upstream_dts)))
        missing_yaml = sorted(set(downstream_yaml).difference(set(upstream_yaml)))

        mandatory_checks = {
            "headers_resolved": not missing_headers,
            "kconfig_resolved": not missing_kconfig,
            "makefile_resolved": not missing_makefile,
            "dts_resolved": not missing_dts,
            "yaml_resolved": not missing_yaml,
        }
        missing_dependency_count = (
            len(missing_headers)
            + len(missing_kconfig)
            + len(missing_makefile)
            + len(missing_dts)
            + len(missing_yaml)
        )
        provenance = [
            _build_provenance_entry(
                corpus_role="downstream",
                corpora_map=corpora_map,
                path=downstream_path,
                line_start=int(downstream_component.get("line_start") or 0),
                line_end=int(downstream_component.get("line_end") or 0),
                evidence_type="dependency_downstream_component",
                source_artifact_sha256=indexed_sha,
                source_artifact_name="TRACK_B_STAGE_INDEXED",
                extraction_rule_id="m8_dependency_downstream_alignment",
                snippet_basis=f"dep:downstream:{candidate_id}:{downstream_path}",
            ),
            _build_provenance_entry(
                corpus_role="upstream",
                corpora_map=corpora_map,
                path=upstream_path,
                line_start=int(upstream_component.get("line_start") or 0),
                line_end=int(upstream_component.get("line_end") or 0),
                evidence_type="dependency_upstream_component",
                source_artifact_sha256=indexed_sha,
                source_artifact_name="TRACK_B_STAGE_INDEXED",
                extraction_rule_id="m8_dependency_upstream_alignment",
                snippet_basis=f"dep:upstream:{candidate_id}:{upstream_path}",
            ),
        ]
        dependency_records.append(
            {
                "candidate_id": candidate_id,
                "downstream_path": downstream_path,
                "upstream_path": upstream_path,
                "missing_headers": missing_headers,
                "missing_kconfig": missing_kconfig,
                "missing_makefile_objects": missing_makefile,
                "missing_dts": missing_dts,
                "missing_yaml": missing_yaml,
                "missing_dependency_count": missing_dependency_count,
                "mandatory_checks": mandatory_checks,
                "provenance": provenance,
            }
        )

    dependency_records = sorted(
        dependency_records,
        key=lambda item: (
            str(item.get("candidate_id") or ""),
            str(item.get("upstream_path") or ""),
        ),
    )
    return {
        "artifact_name": "TRACK_B_DEPENDENCY_MATRIX",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "DEPENDENCIES_BOUND",
        "dependency_records": dependency_records,
        "lineage": {
            "equivalence_artifact_sha256": canonical_json_sha256(equivalence_payload),
            "indexed_artifact_sha256": indexed_sha,
        },
        "evidence": {
            "required_evidence_types_satisfied": [
                "dependency_binding",
                "dependency_provenance",
                "equivalence_lineage",
            ]
        },
        "fail_closed_reasons": [],
    }


def _validate_conflict_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_CONFLICT_LEDGER",
        expected_stage_id="CONFLICTS_EVALUATED",
    )
    conflicts = payload.get("conflicts", [])
    if not isinstance(conflicts, list):
        errors.append("conflicts must be a list")
        conflicts = []
    for index, raw_conflict in enumerate(conflicts):
        conflict = _safe_dict(raw_conflict)
        for key in ("conflict_id", "conflict_type", "severity", "status", "summary"):
            if not str(conflict.get(key) or "").strip():
                errors.append(f"conflicts[{index}].{key} must be non-empty")
        conflict_type = str(conflict.get("conflict_type") or "").strip().upper()
        if conflict_type not in CONFLICT_TYPES:
            errors.append(f"conflicts[{index}].conflict_type must be one of {CONFLICT_TYPES}")
        provenance = conflict.get("provenance", [])
        if not isinstance(provenance, list) or not provenance:
            errors.append(f"conflicts[{index}].provenance must be a non-empty list")
        else:
            for provenance_index, raw_entry in enumerate(provenance):
                errors.extend(
                    _validate_provenance_entry(
                        _safe_dict(raw_entry),
                        field_prefix=f"conflicts[{index}].provenance[{provenance_index}]",
                    )
                )
    for key in ("unresolved_conflict_count", "resolved_conflict_count"):
        if not isinstance(payload.get(key), int):
            errors.append(f"{key} must be an integer")
    resolution_policy = _safe_dict(payload.get("resolution_policy"))
    supported_conflict_types = resolution_policy.get("supported_conflict_types", [])
    if not isinstance(supported_conflict_types, list) or supported_conflict_types != list(CONFLICT_TYPES):
        errors.append("resolution_policy.supported_conflict_types must exactly match conflict taxonomy")
    conflict_precedence = resolution_policy.get("conflict_precedence", [])
    if not isinstance(conflict_precedence, list) or conflict_precedence != list(CONFLICT_PRECEDENCE):
        errors.append("resolution_policy.conflict_precedence must exactly match deterministic precedence")
    for key in ("unresolved_conflicts_fail_closed",):
        if not isinstance(resolution_policy.get(key), bool):
            errors.append(f"resolution_policy.{key} must be bool")
    lineage = _safe_dict(payload.get("lineage"))
    for key in ("dependency_artifact_sha256", "equivalence_artifact_sha256"):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")
    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "conflict_detection",
        "conflict_provenance",
        "dependency_lineage",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("conflict evidence set must contain all required evidence types")
    return errors


def _build_conflicts_evaluated(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    static_payload = _safe_dict(stage_payloads.get("STATIC_ANALYZED"))
    dependency_payload = _safe_dict(stage_payloads.get("DEPENDENCIES_BOUND"))
    equivalence_payload = _safe_dict(stage_payloads.get("EQUIVALENCE_MAPPED"))
    if not dependency_payload:
        raise RuntimeError("DEPENDENCIES_BOUND payload is required for CONFLICTS_EVALUATED")
    if not equivalence_payload:
        raise RuntimeError("EQUIVALENCE_MAPPED payload is required for CONFLICTS_EVALUATED")

    candidates = equivalence_payload.get("candidate_mappings", [])
    if not isinstance(candidates, list):
        raise RuntimeError("equivalence candidate_mappings must be a list")
    dependency_records = dependency_payload.get("dependency_records", [])
    if not isinstance(dependency_records, list):
        raise RuntimeError("dependency_records must be a list")

    try:
        upstreaming_request = _normalize_upstreaming_request(context)
    except RuntimeError:
        upstreaming_request = {}
    request_component = _safe_dict(upstreaming_request.get("downstream_component"))
    request_component_name = str(request_component.get("component_name") or "").strip()
    runtime_evidence_refs = _normalize_string_list(upstreaming_request.get("runtime_evidence_refs"))
    runtime_evidence_types = sorted(
        {
            str(parts[1]).strip().lower()
            for parts in [entry.split(":", 2) for entry in runtime_evidence_refs]
            if len(parts) == 3
        }
    )

    def _new_conflict(
        *,
        conflict_type: str,
        severity: str,
        summary: str,
        candidate_ids: list[str],
        provenance: list[dict[str, Any]],
    ) -> dict[str, Any]:
        conflict_identity = {
            "conflict_type": conflict_type,
            "summary": summary,
            "candidate_ids": sorted([str(item).strip() for item in candidate_ids if str(item).strip()]),
            "provenance_ids": sorted(
                [
                    str(_safe_dict(item).get("evidence_id") or "").strip()
                    for item in provenance
                    if isinstance(item, dict)
                ]
            ),
        }
        return {
            "conflict_id": _canonical_value_sha256(conflict_identity),
            "conflict_type": conflict_type,
            "severity": severity,
            "status": "UNRESOLVED",
            "summary": summary,
            "candidate_ids": sorted([str(item).strip() for item in candidate_ids if str(item).strip()]),
            "provenance": [_safe_dict(item) for item in provenance if isinstance(item, dict)],
        }

    conflict_rows: list[dict[str, Any]] = []
    downstream_anchor = _safe_dict(equivalence_payload.get("downstream_anchor"))
    downstream_anchor_provenance = _safe_dict(downstream_anchor.get("provenance"))
    if not candidates:
        conflict_rows.append(
            _new_conflict(
                conflict_type="NO_CANDIDATE_MAPPING",
                severity="HIGH",
                summary="No upstream equivalent candidates were identified for the downstream component.",
                candidate_ids=[],
                provenance=[downstream_anchor_provenance],
            )
        )

    sorted_candidates = sorted(
        [_safe_dict(item) for item in candidates if isinstance(item, dict)],
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(_safe_dict(item.get("upstream_component")).get("component_name") or ""),
            str(_safe_dict(item.get("upstream_component")).get("source_path") or ""),
            int(_safe_dict(item.get("upstream_component")).get("line_start") or 0),
        ),
    )
    if sorted_candidates:
        if len(sorted_candidates) > 1:
            candidate_ids = [str(item.get("candidate_id") or "").strip() for item in sorted_candidates]
            provenance: list[dict[str, Any]] = []
            for item in sorted_candidates:
                evidence = item.get("evidence", [])
                if isinstance(evidence, list) and evidence:
                    provenance.append(_safe_dict(evidence[-1]))
            conflict_rows.append(
                _new_conflict(
                    conflict_type="MULTI_EQUIVALENT_TOP_SCORE",
                    severity="HIGH",
                    summary="Multiple upstream candidates were identified; explicit disambiguation required.",
                    candidate_ids=candidate_ids,
                    provenance=provenance,
                )
            )

        for item in sorted_candidates:
            upstream_component = _safe_dict(item.get("upstream_component"))
            upstream_name = str(upstream_component.get("component_name") or "").strip()
            if request_component_name and upstream_name and upstream_name != request_component_name:
                evidence = item.get("evidence", [])
                conflict_rows.append(
                    _new_conflict(
                        conflict_type="SIGNATURE_MISMATCH",
                        severity="MEDIUM",
                        summary="Downstream component signature differs from upstream candidate signature.",
                        candidate_ids=[str(item.get("candidate_id") or "").strip()],
                        provenance=[_safe_dict(entry) for entry in evidence if isinstance(entry, dict)],
                    )
                )

    for record in dependency_records:
        item = _safe_dict(record)
        missing_count = int(item.get("missing_dependency_count") or 0)
        if missing_count <= 0:
            continue
        candidate_id = str(item.get("candidate_id") or "").strip()
        provenance = [_safe_dict(entry) for entry in item.get("provenance", []) if isinstance(entry, dict)]
        conflict_rows.append(
            _new_conflict(
                conflict_type="DEPENDENCY_MISMATCH",
                severity="MEDIUM",
                summary=f"Candidate {candidate_id} has unresolved dependency gaps.",
                candidate_ids=[candidate_id] if candidate_id else [],
                provenance=provenance,
            )
        )
        has_dt_gap = bool(item.get("missing_dts")) or bool(item.get("missing_yaml"))
        if has_dt_gap:
            conflict_rows.append(
                _new_conflict(
                    conflict_type="DT_BINDING_MISMATCH",
                    severity="HIGH",
                    summary=f"Candidate {candidate_id} has unresolved DTS/YAML binding mismatches.",
                    candidate_ids=[candidate_id] if candidate_id else [],
                    provenance=provenance,
                )
            )

    comparison_signals = _safe_dict(static_payload.get("comparison_signals"))
    has_downstream_only_static = any(
        bool(_safe_dict(signal).get("downstream_only"))
        for signal in comparison_signals.values()
        if isinstance(signal, dict)
    )
    if has_downstream_only_static and not sorted_candidates:
        conflict_rows.append(
            _new_conflict(
                conflict_type="STATIC_ONLY_EDGE",
                severity="MEDIUM",
                summary="Static analysis exposes downstream-only edges without upstream equivalents.",
                candidate_ids=[],
                provenance=[downstream_anchor_provenance],
            )
        )

    if "runtime_only_edge" in runtime_evidence_types:
        conflict_rows.append(
            _new_conflict(
                conflict_type="RUNTIME_ONLY_EDGE",
                severity="MEDIUM",
                summary="Runtime evidence reports an edge absent in static correlation artifacts.",
                candidate_ids=[],
                provenance=[downstream_anchor_provenance],
            )
        )
    if "ordering_mismatch" in runtime_evidence_types:
        conflict_rows.append(
            _new_conflict(
                conflict_type="ORDERING_MISMATCH",
                severity="MEDIUM",
                summary="Runtime evidence reports ordering mismatch against static expectations.",
                candidate_ids=[],
                provenance=[downstream_anchor_provenance],
            )
        )

    conflict_rows = sorted(
        [_safe_dict(item) for item in conflict_rows if isinstance(item, dict)],
        key=lambda item: (
            str(item.get("conflict_type") or ""),
            str(item.get("conflict_id") or ""),
        ),
    )
    unresolved_count = len([item for item in conflict_rows if str(item.get("status") or "").upper() == "UNRESOLVED"])
    resolved_count = len(conflict_rows) - unresolved_count

    return {
        "artifact_name": "TRACK_B_CONFLICT_LEDGER",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "CONFLICTS_EVALUATED",
        "conflicts": conflict_rows,
        "unresolved_conflict_count": unresolved_count,
        "resolved_conflict_count": resolved_count,
        "resolution_policy": {
            "unresolved_conflicts_fail_closed": True,
            "multi_equivalent_policy": "Require explicit disambiguation evidence before readiness PASS.",
            "supported_conflict_types": list(CONFLICT_TYPES),
            "conflict_precedence": list(CONFLICT_PRECEDENCE),
        },
        "lineage": {
            "dependency_artifact_sha256": canonical_json_sha256(dependency_payload),
            "equivalence_artifact_sha256": canonical_json_sha256(equivalence_payload),
        },
        "evidence": {
            "required_evidence_types_satisfied": [
                "conflict_detection",
                "conflict_provenance",
                "dependency_lineage",
            ]
        },
        "fail_closed_reasons": [],
    }


def _validate_decision_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_EQUIVALENCE_DECISION",
        expected_stage_id="DECISION_FINALIZED",
    )
    decision_state = str(payload.get("decision_state") or "").strip().upper()
    if decision_state not in EQUIVALENCE_DECISION_STATES:
        errors.append("decision_state must be a supported equivalence decision state")
    selected_candidate = _safe_dict(payload.get("selected_candidate"))
    if decision_state == "UNIQUE_EQUIVALENT" and not selected_candidate:
        errors.append("selected_candidate is required for UNIQUE_EQUIVALENT")

    mandatory_checks = _safe_dict(payload.get("mandatory_checks"))
    if not mandatory_checks:
        errors.append("mandatory_checks must be an object")
    else:
        for key in (
            "unique_equivalent",
            "dependencies_resolved",
            "conflicts_resolved",
            "provenance_complete",
            "runtime_evidence_complete",
            "lineage_complete",
        ):
            if not isinstance(mandatory_checks.get(key), bool):
                errors.append(f"mandatory_checks.{key} must be bool")
    complexity = _safe_dict(payload.get("complexity"))
    if not complexity:
        errors.append("complexity must be an object")
    else:
        label = str(complexity.get("label") or "").strip().upper()
        if label not in {"LOW", "MEDIUM", "HIGH"}:
            errors.append("complexity.label must be LOW/MEDIUM/HIGH")
        if not isinstance(complexity.get("risk_points"), int):
            errors.append("complexity.risk_points must be an integer")
        if not str(complexity.get("formula") or "").strip():
            errors.append("complexity.formula must be non-empty")

    lineage = _safe_dict(payload.get("lineage"))
    for key in (
        "equivalence_artifact_sha256",
        "dependency_artifact_sha256",
        "conflict_artifact_sha256",
    ):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")
    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "decision_state",
        "conflict_lineage",
        "dependency_lineage",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("decision evidence set must contain all required evidence types")
    return errors


def _build_decision_finalized(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    upstreaming_request = _safe_dict(context.get("upstreaming_request"))
    equivalence_payload = _safe_dict(stage_payloads.get("EQUIVALENCE_MAPPED"))
    dependency_payload = _safe_dict(stage_payloads.get("DEPENDENCIES_BOUND"))
    conflict_payload = _safe_dict(stage_payloads.get("CONFLICTS_EVALUATED"))
    if not equivalence_payload:
        raise RuntimeError("EQUIVALENCE_MAPPED payload is required for DECISION_FINALIZED")
    if not dependency_payload:
        raise RuntimeError("DEPENDENCIES_BOUND payload is required for DECISION_FINALIZED")
    if not conflict_payload:
        raise RuntimeError("CONFLICTS_EVALUATED payload is required for DECISION_FINALIZED")

    candidates = equivalence_payload.get("candidate_mappings", [])
    if not isinstance(candidates, list):
        raise RuntimeError("equivalence candidate_mappings must be a list")
    normalized_candidates = sorted(
        [_safe_dict(item) for item in candidates if isinstance(item, dict)],
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(_safe_dict(item.get("upstream_component")).get("component_name") or ""),
            str(_safe_dict(item.get("upstream_component")).get("source_path") or ""),
            int(_safe_dict(item.get("upstream_component")).get("line_start") or 0),
        ),
    )
    dependency_records = dependency_payload.get("dependency_records", [])
    if not isinstance(dependency_records, list):
        raise RuntimeError("dependency_records must be a list")
    dep_by_candidate = {
        str(_safe_dict(item).get("candidate_id") or "").strip(): _safe_dict(item)
        for item in dependency_records
        if isinstance(item, dict)
    }

    conflicts = conflict_payload.get("conflicts", [])
    if not isinstance(conflicts, list):
        raise RuntimeError("conflicts must be a list")
    unresolved_conflicts = [
        _safe_dict(item)
        for item in conflicts
        if isinstance(item, dict) and str(item.get("status") or "").strip().upper() == "UNRESOLVED"
    ]
    unresolved_types = {str(item.get("conflict_type") or "").strip().upper() for item in unresolved_conflicts}

    decision_state = "UNIQUE_EQUIVALENT"
    selected_candidate: dict[str, Any] = {}
    if "NO_CANDIDATE_MAPPING" in unresolved_types or not normalized_candidates:
        decision_state = "NO_EQUIVALENT"
    else:
        top_score = float(normalized_candidates[0].get("score") or 0.0)
        top_candidates = [
            item for item in normalized_candidates if float(item.get("score") or 0.0) == top_score
        ]
        if "MULTI_EQUIVALENT_TOP_SCORE" in unresolved_types or len(normalized_candidates) > 1:
            decision_state = "MULTI_EQUIVALENT"
        elif unresolved_conflicts:
            decision_state = "CONFLICTING_EVIDENCE"
        else:
            decision_state = "UNIQUE_EQUIVALENT"
            selected_candidate = _safe_dict(top_candidates[0])

    selected_candidate_id = str(selected_candidate.get("candidate_id") or "").strip()
    selected_dependency = _safe_dict(dep_by_candidate.get(selected_candidate_id))
    dependencies_resolved = bool(selected_dependency) and all(
        bool(_safe_dict(selected_dependency.get("mandatory_checks")).get(key))
        for key in (
            "headers_resolved",
            "kconfig_resolved",
            "makefile_resolved",
            "dts_resolved",
            "yaml_resolved",
        )
    )
    provenance_complete = True
    for candidate in normalized_candidates:
        evidence = candidate.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            provenance_complete = False
            break
        for raw_entry in evidence:
            if _validate_provenance_entry(_safe_dict(raw_entry), field_prefix="decision.provenance"):
                provenance_complete = False
                break
        if not provenance_complete:
            break

    missing_dependency_total = sum(
        int(_safe_dict(item).get("missing_dependency_count") or 0) for item in dependency_records
    )
    unresolved_count = len(unresolved_conflicts)
    candidate_count = len(normalized_candidates)
    risk_points = (missing_dependency_total * 2) + (unresolved_count * 3) + max(candidate_count - 1, 0)
    if decision_state != "UNIQUE_EQUIVALENT":
        risk_points += 4
    complexity_label = "LOW" if risk_points <= 2 else "MEDIUM" if risk_points <= 8 else "HIGH"

    lineage = {
        "equivalence_artifact_sha256": canonical_json_sha256(equivalence_payload),
        "dependency_artifact_sha256": canonical_json_sha256(dependency_payload),
        "conflict_artifact_sha256": canonical_json_sha256(conflict_payload),
    }
    lineage_complete = all(_is_sha256(value) for value in lineage.values())
    request_component = _safe_dict(upstreaming_request.get("downstream_component"))
    request_component_type = str(request_component.get("component_type") or "").strip().lower()
    runtime_evidence_required = _runtime_evidence_required(request_component_type)
    runtime_evidence_refs = _normalize_string_list(upstreaming_request.get("runtime_evidence_refs"))
    runtime_evidence_complete = (not runtime_evidence_required) or bool(runtime_evidence_refs)
    mandatory_checks = {
        "unique_equivalent": decision_state == "UNIQUE_EQUIVALENT",
        "dependencies_resolved": dependencies_resolved,
        "conflicts_resolved": unresolved_count == 0,
        "provenance_complete": provenance_complete,
        "runtime_evidence_complete": runtime_evidence_complete,
        "lineage_complete": lineage_complete,
    }

    return {
        "artifact_name": "TRACK_B_EQUIVALENCE_DECISION",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "DECISION_FINALIZED",
        "decision_state": decision_state,
        "selected_candidate": selected_candidate,
        "mandatory_checks": mandatory_checks,
        "complexity": {
            "label": complexity_label,
            "risk_points": int(risk_points),
            "formula": "(missing_dependency_total*2)+(unresolved_conflicts*3)+max(candidate_count-1,0)+decision_penalty",
        },
        "lineage": lineage,
        "evidence": {
            "required_evidence_types_satisfied": [
                "decision_state",
                "conflict_lineage",
                "dependency_lineage",
            ]
        },
        "fail_closed_reasons": [],
    }


def _validate_report_schema(payload: dict[str, Any]) -> list[str]:
    errors = _validate_common_header(
        payload,
        expected_artifact_name="TRACK_B_UPSTREAMING_REPORT",
        expected_stage_id="REPORT_GENERATED",
    )
    downstream_component = _safe_dict(payload.get("downstream_component"))
    if not downstream_component:
        errors.append("downstream_component must be an object")
    else:
        for key in ("component_type", "component_name"):
            if not str(downstream_component.get(key) or "").strip():
                errors.append(f"downstream_component.{key} must be non-empty")

    for key in ("decision_state",):
        if not str(payload.get(key) or "").strip():
            errors.append(f"{key} must be non-empty")
    if not isinstance(payload.get("upstream_equivalents"), list):
        errors.append("upstream_equivalents must be a list")
    if not isinstance(payload.get("required_patches"), list):
        errors.append("required_patches must be a list")
    if not isinstance(payload.get("caller_callee_chain"), list):
        errors.append("caller_callee_chain must be a list")

    lineage = _safe_dict(payload.get("lineage"))
    for key in (
        "decision_artifact_sha256",
        "dependency_artifact_sha256",
        "conflict_artifact_sha256",
        "equivalence_artifact_sha256",
    ):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")
    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "report_generation",
        "decision_lineage",
        "dependency_matrix",
        "conflict_ledger",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("report evidence set must contain all required evidence types")
    return errors


def _build_report_generated(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    decision_payload = _safe_dict(stage_payloads.get("DECISION_FINALIZED"))
    dependency_payload = _safe_dict(stage_payloads.get("DEPENDENCIES_BOUND"))
    conflict_payload = _safe_dict(stage_payloads.get("CONFLICTS_EVALUATED"))
    equivalence_payload = _safe_dict(stage_payloads.get("EQUIVALENCE_MAPPED"))
    static_payload = _safe_dict(stage_payloads.get("STATIC_ANALYZED"))
    if not decision_payload:
        raise RuntimeError("DECISION_FINALIZED payload is required for REPORT_GENERATED")
    if not dependency_payload:
        raise RuntimeError("DEPENDENCIES_BOUND payload is required for REPORT_GENERATED")
    if not conflict_payload:
        raise RuntimeError("CONFLICTS_EVALUATED payload is required for REPORT_GENERATED")
    if not equivalence_payload:
        raise RuntimeError("EQUIVALENCE_MAPPED payload is required for REPORT_GENERATED")

    decision_state = str(decision_payload.get("decision_state") or "").strip().upper()
    selected_candidate = _safe_dict(decision_payload.get("selected_candidate"))
    dependency_records = dependency_payload.get("dependency_records", [])
    if not isinstance(dependency_records, list):
        dependency_records = []
    dep_by_candidate = {
        str(_safe_dict(item).get("candidate_id") or "").strip(): _safe_dict(item)
        for item in dependency_records
        if isinstance(item, dict)
    }
    selected_candidate_id = str(selected_candidate.get("candidate_id") or "").strip()
    selected_dependency = _safe_dict(dep_by_candidate.get(selected_candidate_id))
    upstream_equivalents = [
        {
            "candidate_id": str(_safe_dict(item).get("candidate_id") or "").strip(),
            "score": float(_safe_dict(item).get("score") or 0.0),
            "upstream_component": _safe_dict(_safe_dict(item).get("upstream_component")),
        }
        for item in equivalence_payload.get("candidate_mappings", [])
        if isinstance(item, dict)
    ]
    upstream_equivalents = sorted(
        upstream_equivalents,
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(_safe_dict(item.get("upstream_component")).get("component_name") or ""),
            str(_safe_dict(item.get("upstream_component")).get("source_path") or ""),
            int(_safe_dict(item.get("upstream_component")).get("line_start") or 0),
        ),
    )
    required_patches: list[str] = []
    if decision_state != "UNIQUE_EQUIVALENT":
        required_patches.append("resolve_equivalence_decision_state")
    if selected_dependency:
        if _safe_dict(selected_dependency).get("missing_headers"):
            required_patches.append("synchronize_header_dependencies")
        if _safe_dict(selected_dependency).get("missing_kconfig"):
            required_patches.append("add_kconfig_dependencies")
        if _safe_dict(selected_dependency).get("missing_makefile_objects"):
            required_patches.append("synchronize_makefile_object_integration")
        if _safe_dict(selected_dependency).get("missing_dts"):
            required_patches.append("align_dts_dependencies")
        if _safe_dict(selected_dependency).get("missing_yaml"):
            required_patches.append("align_yaml_binding_dependencies")
    required_patches = sorted(set(required_patches))

    comparison_signals = _safe_dict(static_payload.get("comparison_signals"))
    architectural_differences = {
        key: {
            "downstream_only_count": int(_safe_dict(value).get("downstream_count") or 0),
            "upstream_only_count": int(_safe_dict(value).get("upstream_count") or 0),
            "shared_count": int(_safe_dict(value).get("shared_count") or 0),
        }
        for key, value in comparison_signals.items()
        if isinstance(value, dict)
    }
    caller_callee_chain: list[dict[str, Any]] = []
    if selected_candidate:
        upstream_component = _safe_dict(selected_candidate.get("upstream_component"))
        component_name = str(upstream_component.get("component_name") or "").strip()
        source_path = str(upstream_component.get("source_path") or "").strip()
        line_start = int(upstream_component.get("line_start") or 0)
        line_end = int(upstream_component.get("line_end") or 0)
        if component_name and source_path:
            caller_callee_chain.append(
                {
                    "caller": "DIRECT_ENTRY",
                    "callee": component_name,
                    "source_path": source_path,
                    "line_range": _line_range_text(line_start=line_start, line_end=line_end),
                }
            )

    return {
        "artifact_name": "TRACK_B_UPSTREAMING_REPORT",
        "schema_version": "1.0",
        "classification": "PASS",
        "stage_id": "REPORT_GENERATED",
        "downstream_component": _safe_dict(_safe_dict(equivalence_payload.get("upstreaming_request")).get("downstream_component")),
        "decision_state": decision_state,
        "upstream_equivalents": upstream_equivalents,
        "required_patches": required_patches,
        "risk_assessment": {
            "complexity_label": str(_safe_dict(decision_payload.get("complexity")).get("label") or "").strip().upper(),
            "risk_points": int(_safe_dict(decision_payload.get("complexity")).get("risk_points") or 0),
            "unresolved_conflict_count": int(conflict_payload.get("unresolved_conflict_count") or 0),
        },
        "dependency_summary": selected_dependency,
        "architectural_differences": architectural_differences,
        "caller_callee_chain": caller_callee_chain,
        "lineage": {
            "decision_artifact_sha256": canonical_json_sha256(decision_payload),
            "dependency_artifact_sha256": canonical_json_sha256(dependency_payload),
            "conflict_artifact_sha256": canonical_json_sha256(conflict_payload),
            "equivalence_artifact_sha256": canonical_json_sha256(equivalence_payload),
        },
        "evidence": {
            "required_evidence_types_satisfied": [
                "report_generation",
                "decision_lineage",
                "dependency_matrix",
                "conflict_ledger",
            ]
        },
        "fail_closed_reasons": [],
    }


def _validate_readiness_schema(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if str(payload.get("artifact_name") or "").strip() != "TRACK_B_UPSTREAMING_READINESS":
        errors.append("artifact_name expected 'TRACK_B_UPSTREAMING_READINESS'")
    if str(payload.get("schema_version") or "").strip() != "1.0":
        errors.append("schema_version expected '1.0'")
    stage_id = str(payload.get("stage_id") or "").strip().upper()
    if stage_id != "READINESS_GATED":
        errors.append("stage_id expected 'READINESS_GATED'")
    classification = str(payload.get("classification") or "").strip().upper()
    if classification not in {"PASS", "FAIL_CLOSED"}:
        errors.append("classification must be PASS or FAIL_CLOSED")

    decision_state = str(payload.get("decision_state") or "").strip().upper()
    if decision_state not in EQUIVALENCE_DECISION_STATES:
        errors.append("decision_state must be a supported equivalence decision state")
    readiness_status = str(payload.get("readiness_status") or "").strip().upper()
    if readiness_status not in {"READY", "NOT_READY"}:
        errors.append("readiness_status must be READY or NOT_READY")

    checks = payload.get("mandatory_checks", {})
    if not isinstance(checks, dict):
        errors.append("mandatory_checks must be an object")
        checks = {}
    for key in (
        "decision_unique_equivalent",
        "dependencies_resolved",
        "conflicts_resolved",
        "provenance_complete",
        "runtime_evidence_complete",
        "report_complete",
    ):
        if not isinstance(checks.get(key), bool):
            errors.append(f"mandatory_checks.{key} must be bool")
    reasons = payload.get("fail_closed_reasons", [])
    if not isinstance(reasons, list):
        errors.append("fail_closed_reasons must be a list")
    elif classification == "FAIL_CLOSED" and not reasons:
        errors.append("fail_closed_reasons must be non-empty when classification=FAIL_CLOSED")

    lineage = _safe_dict(payload.get("lineage"))
    for key in ("report_artifact_sha256", "decision_artifact_sha256", "conflict_artifact_sha256"):
        if not _is_sha256(str(lineage.get(key) or "").strip().lower()):
            errors.append(f"lineage.{key} must be sha256")
    evidence = _safe_dict(payload.get("evidence"))
    satisfied = evidence.get("required_evidence_types_satisfied", [])
    required = {
        "readiness_gate",
        "decision_lineage",
        "report_lineage",
    }
    if not isinstance(satisfied, list) or required != {str(item).strip() for item in satisfied}:
        errors.append("readiness evidence set must contain all required evidence types")
    return errors


def _build_readiness_gated(context: dict[str, Any], stage_payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    _ = context
    report_payload = _safe_dict(stage_payloads.get("REPORT_GENERATED"))
    decision_payload = _safe_dict(stage_payloads.get("DECISION_FINALIZED"))
    conflict_payload = _safe_dict(stage_payloads.get("CONFLICTS_EVALUATED"))
    if not report_payload:
        raise RuntimeError("REPORT_GENERATED payload is required for READINESS_GATED")
    if not decision_payload:
        raise RuntimeError("DECISION_FINALIZED payload is required for READINESS_GATED")
    if not conflict_payload:
        raise RuntimeError("CONFLICTS_EVALUATED payload is required for READINESS_GATED")

    decision_state = str(decision_payload.get("decision_state") or "").strip().upper()
    decision_checks = _safe_dict(decision_payload.get("mandatory_checks"))
    report_complete = bool(_safe_dict(report_payload.get("downstream_component")).get("component_name")) and bool(
        report_payload.get("upstream_equivalents", [])
    )
    mandatory_checks = {
        "decision_unique_equivalent": decision_state == "UNIQUE_EQUIVALENT",
        "dependencies_resolved": bool(decision_checks.get("dependencies_resolved")),
        "conflicts_resolved": bool(decision_checks.get("conflicts_resolved")),
        "provenance_complete": bool(decision_checks.get("provenance_complete")),
        "runtime_evidence_complete": bool(decision_checks.get("runtime_evidence_complete")),
        "report_complete": report_complete,
    }
    readiness_pass = all(mandatory_checks.values())
    classification = "PASS" if readiness_pass else "FAIL_CLOSED"
    reasons: list[str] = []
    if decision_state != "UNIQUE_EQUIVALENT":
        reasons.append(f"decision_state={decision_state}")
    for key, passed in mandatory_checks.items():
        if not passed:
            reasons.append(f"mandatory_check_failed:{key}")
    unresolved_count = int(conflict_payload.get("unresolved_conflict_count") or 0)
    if unresolved_count > 0:
        reasons.append(f"unresolved_conflicts={unresolved_count}")

    return {
        "artifact_name": "TRACK_B_UPSTREAMING_READINESS",
        "schema_version": "1.0",
        "classification": classification,
        "stage_id": "READINESS_GATED",
        "decision_state": decision_state,
        "readiness_status": "READY" if readiness_pass else "NOT_READY",
        "mandatory_checks": mandatory_checks,
        "lineage": {
            "report_artifact_sha256": canonical_json_sha256(report_payload),
            "decision_artifact_sha256": canonical_json_sha256(decision_payload),
            "conflict_artifact_sha256": canonical_json_sha256(conflict_payload),
        },
        "evidence": {
            "required_evidence_types_satisfied": [
                "readiness_gate",
                "decision_lineage",
                "report_lineage",
            ]
        },
        "fail_closed_reasons": [] if readiness_pass else sorted(set(reasons)),
    }


class TrackBStageExecutor:
    """Deterministic Track B stage execution with explicit fail-closed stage transitions."""

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
        if _required_for_m8(target_stage):
            try:
                normalized_request = _normalize_upstreaming_request(context)
            except RuntimeError as exc:
                self._write_fail_closed_execution(context=context, reasons=[str(exc)])
                raise RuntimeError(f"track_b_stage_execution fail-closed: {exc}") from exc
            if not normalized_request:
                reason = "upstreaming_request is required when target_stage is beyond STATIC_ANALYZED"
                self._write_fail_closed_execution(context=context, reasons=[reason])
                raise RuntimeError(f"track_b_stage_execution fail-closed: {reason}")
            context = dict(context)
            context["upstreaming_request"] = normalized_request

        stage_definitions = [
            StageDefinition(
                stage_id="DISCOVERED",
                artifact_name="TRACK_B_STAGE_DISCOVERED",
                artifact_filename="track_b_discovered.json",
                required_evidence_types=(
                    "source_locator",
                    "corpus_declaration",
                    "repository_provenance",
                    "discovery_inventory",
                ),
                build=_build_discovered,
                validate=_validate_discovered_schema,
            ),
            StageDefinition(
                stage_id="INDEXED",
                artifact_name="TRACK_B_STAGE_INDEXED",
                artifact_filename="track_b_indexed.json",
                required_evidence_types=(
                    "dual_corpus_index",
                    "downstream_upstream_relationship_index",
                    "dts_relationship_index",
                    "yaml_relationship_index",
                    "kconfig_relationship_index",
                    "makefile_relationship_index",
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
                    "comparison_signals",
                    "deterministic_deltas",
                    "downstream_upstream_comparison",
                    "indexed_lineage",
                ),
                build=_build_static_analyzed,
                validate=_validate_static_schema,
            ),
            StageDefinition(
                stage_id="EQUIVALENCE_MAPPED",
                artifact_name="TRACK_B_EQUIVALENCE_MAP",
                artifact_filename="track_b_equivalence_map.json",
                required_evidence_types=(
                    "equivalence_candidates",
                    "equivalence_provenance",
                    "static_lineage",
                ),
                build=_build_equivalence_mapped,
                validate=_validate_equivalence_schema,
            ),
            StageDefinition(
                stage_id="DEPENDENCIES_BOUND",
                artifact_name="TRACK_B_DEPENDENCY_MATRIX",
                artifact_filename="track_b_dependency_matrix.json",
                required_evidence_types=(
                    "dependency_binding",
                    "dependency_provenance",
                    "equivalence_lineage",
                ),
                build=_build_dependencies_bound,
                validate=_validate_dependency_schema,
            ),
            StageDefinition(
                stage_id="CONFLICTS_EVALUATED",
                artifact_name="TRACK_B_CONFLICT_LEDGER",
                artifact_filename="track_b_conflict_ledger.json",
                required_evidence_types=(
                    "conflict_detection",
                    "conflict_provenance",
                    "dependency_lineage",
                ),
                build=_build_conflicts_evaluated,
                validate=_validate_conflict_schema,
            ),
            StageDefinition(
                stage_id="DECISION_FINALIZED",
                artifact_name="TRACK_B_EQUIVALENCE_DECISION",
                artifact_filename="track_b_equivalence_decision.json",
                required_evidence_types=(
                    "decision_state",
                    "conflict_lineage",
                    "dependency_lineage",
                ),
                build=_build_decision_finalized,
                validate=_validate_decision_schema,
            ),
            StageDefinition(
                stage_id="REPORT_GENERATED",
                artifact_name="TRACK_B_UPSTREAMING_REPORT",
                artifact_filename="track_b_upstreaming_report.json",
                required_evidence_types=(
                    "report_generation",
                    "decision_lineage",
                    "dependency_matrix",
                    "conflict_ledger",
                ),
                build=_build_report_generated,
                validate=_validate_report_schema,
            ),
            StageDefinition(
                stage_id="READINESS_GATED",
                artifact_name="TRACK_B_UPSTREAMING_READINESS",
                artifact_filename="track_b_upstreaming_readiness.json",
                required_evidence_types=(
                    "readiness_gate",
                    "decision_lineage",
                    "report_lineage",
                ),
                build=_build_readiness_gated,
                validate=_validate_readiness_schema,
            ),
        ]

        engine = DeterministicStageEngine(stage_definitions)

        comparison_matrix_path = self._output_dir / "track_b_comparison_matrix.json"
        comparison_readiness_path = self._output_dir / "track_b_comparison_readiness.json"
        comparison_matrix_sha = ""
        comparison_readiness_sha = ""
        comparison_matrix_payload: dict[str, Any] = {}
        comparison_readiness_payload: dict[str, Any] = {}
        discovered_payload: dict[str, Any] = {}

        try:
            execution = engine.execute(
                initial_stage=initial_stage,
                target_stage=target_stage,
                context=context,
                output_dir=self._output_dir,
            )
            stage_weights = _confidence_weights_from_context(context)
            stage_confidence, stage_confidence_details = _compute_stage_confidence(
                stage_payloads=execution.get("stage_payloads", {}),
                stage_weights=stage_weights,
            )

            stage_payloads = _safe_dict(execution.get("stage_payloads"))
            terminal_stage = str(execution.get("terminal_stage") or "").strip().upper()
            terminal_payload = _safe_dict(stage_payloads.get(terminal_stage))
            terminal_classification = str(terminal_payload.get("classification") or "").strip().upper()
            if terminal_classification == "FAIL_CLOSED":
                reasons = terminal_payload.get("fail_closed_reasons", [])
                reason_text = (
                    ", ".join([str(item).strip() for item in reasons if str(item).strip()]) or "unknown"
                )
                raise RuntimeError(f"terminal stage {terminal_stage} fail-closed: {reason_text}")
            discovered_payload = _safe_dict(stage_payloads.get("DISCOVERED"))
            indexed_payload = _safe_dict(stage_payloads.get("INDEXED"))
            static_payload = _safe_dict(stage_payloads.get("STATIC_ANALYZED"))
            has_full_comparison = bool(discovered_payload and indexed_payload and static_payload)
            if target_stage == "STATIC_ANALYZED" and not has_full_comparison:
                raise RuntimeError("stage payloads must contain DISCOVERED, INDEXED, and STATIC_ANALYZED")

            if has_full_comparison:
                comparison_matrix_payload = _build_comparison_matrix_payload(
                    discovered_payload=discovered_payload,
                    indexed_payload=indexed_payload,
                    static_payload=static_payload,
                )
                comparison_matrix_errors = _validate_comparison_matrix_schema(comparison_matrix_payload)
                if comparison_matrix_errors:
                    raise RuntimeError(
                        "comparison matrix schema invalid: " + "; ".join(comparison_matrix_errors)
                    )
                comparison_matrix_sha = write_json_deterministic(comparison_matrix_path, comparison_matrix_payload)

                comparison_readiness_payload = _build_comparison_readiness_payload(
                    comparison_matrix_payload=comparison_matrix_payload,
                    stage_confidence=stage_confidence,
                    stage_confidence_details=stage_confidence_details,
                )
                comparison_readiness_errors = _validate_comparison_readiness_schema(comparison_readiness_payload)
                if comparison_readiness_errors:
                    raise RuntimeError(
                        "comparison readiness schema invalid: " + "; ".join(comparison_readiness_errors)
                    )
                comparison_readiness_sha = write_json_deterministic(
                    comparison_readiness_path,
                    comparison_readiness_payload,
                )
                if str(comparison_readiness_payload.get("classification") or "").strip().upper() != "PASS":
                    reasons = comparison_readiness_payload.get("fail_closed_reasons", [])
                    reason_text = (
                        ", ".join([str(item).strip() for item in reasons if str(item).strip()]) or "unknown"
                    )
                    raise RuntimeError(f"comparison readiness fail-closed: {reason_text}")
        except StageExecutionError as exc:
            self._write_fail_closed_execution(context=context, reasons=[str(exc)])
            raise RuntimeError(f"track_b_stage_execution fail-closed: {exc}") from exc
        except ConfidenceComputationError as exc:
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
            "stage_confidence": stage_confidence,
            "stage_confidence_details": stage_confidence_details,
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
        if comparison_matrix_payload:
            manifest_artifacts.append(
                {
                    "name": comparison_matrix_payload["artifact_name"],
                    "path": comparison_matrix_path.name,
                    "sha256": comparison_matrix_sha,
                    "schema_valid": True,
                }
            )
        if comparison_readiness_payload:
            manifest_artifacts.append(
                {
                    "name": comparison_readiness_payload["artifact_name"],
                    "path": comparison_readiness_path.name,
                    "sha256": comparison_readiness_sha,
                    "schema_valid": True,
                }
            )
        manifest_artifacts = sorted(manifest_artifacts, key=lambda item: str(item["name"]))
        bundle_basis = {item["name"]: item["sha256"] for item in manifest_artifacts}
        deterministic_bundle_hash = hashlib.sha256(
            str(sorted(bundle_basis.items())).encode("utf-8")
        ).hexdigest()
        corpus_provenance = []
        corpora = discovered_payload.get("corpora", [])
        if isinstance(corpora, list):
            for item in corpora:
                corpus = _safe_dict(item)
                if not corpus:
                    continue
                revision = _safe_dict(corpus.get("revision"))
                corpus_provenance.append(
                    {
                        "corpus_id": str(corpus.get("corpus_id") or "").strip(),
                        "corpus_role": str(corpus.get("corpus_role") or "").strip(),
                        "repository_root": str(corpus.get("repository_root") or "").strip(),
                        "remote": str(revision.get("remote") or "").strip(),
                        "branch": str(revision.get("branch") or "").strip(),
                        "commit_sha": str(revision.get("commit_sha") or "").strip(),
                    }
                )
        corpus_provenance = _sorted_unique_dicts(
            corpus_provenance,
            key_fn=lambda item: (
                str(item.get("corpus_role")),
                str(item.get("corpus_id")),
                str(item.get("repository_root")),
                str(item.get("remote")),
                str(item.get("branch")),
                str(item.get("commit_sha")),
            ),
        )
        manifest_payload = {
            "artifact_name": "TRACK_B_STAGE_ARTIFACT_MANIFEST",
            "schema_version": "1.0",
            "classification": "PASS",
            "task_id": str(context.get("task_id") or "").strip(),
            "artifacts": manifest_artifacts,
            "corpus_provenance": corpus_provenance,
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
            "stage_confidence": stage_confidence,
            "stage_confidence_details": stage_confidence_details,
            "execution_artifact_path": str(execution_path),
            "execution_artifact_sha256": execution_sha,
            "artifact_manifest_path": str(manifest_path),
            "artifact_manifest_sha256": manifest_sha,
            "artifact_manifest": manifest_payload,
            "stage_artifacts": execution["stage_artifacts"],
            "comparison_matrix_artifact_path": str(comparison_matrix_path),
            "comparison_matrix_artifact_sha256": comparison_matrix_sha,
            "comparison_readiness_artifact_path": str(comparison_readiness_path),
            "comparison_readiness_artifact_sha256": comparison_readiness_sha,
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
            "stage_confidence_details": {},
            "fail_closed_reasons": [str(reason).strip() for reason in reasons if str(reason).strip()],
        }
        write_json_deterministic(self._output_dir / "track_b_stage_execution.json", payload)
