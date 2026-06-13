"""Track-B (M8) artifact contracts, indexing, lineage, and learning views.

Read-only module. It discovers frozen M8 artifacts from runtime output roots and
validated report directories, validates required schema fields from
m8_schema_freeze.json, and returns deterministic contract views.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field

from aura_sdk.logging.logger import get_logger
from core.contracts.transport_artifact_contracts import ContractIssue, ContractValidation, resolve_repo_root

logger = get_logger("core.track_b_artifact_contracts")

TrackBArtifactFile = Literal[
    "track_b_equivalence_map.json",
    "track_b_dependency_matrix.json",
    "track_b_conflict_ledger.json",
    "track_b_equivalence_decision.json",
    "track_b_upstreaming_report.json",
    "track_b_upstreaming_readiness.json",
]

TRACK_B_ARTIFACT_FILES: tuple[TrackBArtifactFile, ...] = (
    "track_b_equivalence_map.json",
    "track_b_dependency_matrix.json",
    "track_b_conflict_ledger.json",
    "track_b_equivalence_decision.json",
    "track_b_upstreaming_report.json",
    "track_b_upstreaming_readiness.json",
)

TRACK_B_ARTIFACT_NAME_BY_FILE: dict[TrackBArtifactFile, str] = {
    "track_b_equivalence_map.json": "TRACK_B_EQUIVALENCE_MAP",
    "track_b_dependency_matrix.json": "TRACK_B_DEPENDENCY_MATRIX",
    "track_b_conflict_ledger.json": "TRACK_B_CONFLICT_LEDGER",
    "track_b_equivalence_decision.json": "TRACK_B_EQUIVALENCE_DECISION",
    "track_b_upstreaming_report.json": "TRACK_B_UPSTREAMING_REPORT",
    "track_b_upstreaming_readiness.json": "TRACK_B_UPSTREAMING_READINESS",
}

DEFAULT_REQUIRED_FIELDS: dict[TrackBArtifactFile, tuple[str, ...]] = {
    "track_b_equivalence_map.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "upstreaming_request",
        "corpora",
        "downstream_anchor",
        "candidate_mappings",
        "ranking_policy",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
    "track_b_dependency_matrix.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "dependency_records",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
    "track_b_conflict_ledger.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "conflicts",
        "unresolved_conflict_count",
        "resolved_conflict_count",
        "resolution_policy",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
    "track_b_equivalence_decision.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "decision_state",
        "selected_candidate",
        "mandatory_checks",
        "complexity",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
    "track_b_upstreaming_report.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "downstream_component",
        "decision_state",
        "upstream_equivalents",
        "required_patches",
        "risk_assessment",
        "dependency_summary",
        "architectural_differences",
        "caller_callee_chain",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
    "track_b_upstreaming_readiness.json": (
        "artifact_name",
        "schema_version",
        "classification",
        "stage_id",
        "decision_state",
        "readiness_status",
        "mandatory_checks",
        "lineage",
        "evidence",
        "fail_closed_reasons",
    ),
}

RELEASE_TAG_HINT = "m8-release-v1"


class TrackBArtifactMetadata(BaseModel):
    artifact_id: str
    artifact_name: str
    artifact_file: TrackBArtifactFile
    artifact_path: str
    source_root: str
    run_id: str
    artifact_sha256: str
    exists: bool
    size_bytes: int
    modified_at: str

    schema_version: str = ""
    classification: str = ""
    stage_id: str = ""
    decision_state: str = ""
    readiness_status: str = ""
    task_id: str = ""
    platform: str = ""
    component: str = ""
    created_at: str = ""


class TrackBArtifactRecord(BaseModel):
    metadata: TrackBArtifactMetadata
    validation: ContractValidation
    payload: dict[str, Any] | None = None


class TrackBArtifactPagination(BaseModel):
    page: int
    limit: int
    total: int


class TrackBArtifactIndexResponse(BaseModel):
    artifacts: list[TrackBArtifactRecord]
    pagination: TrackBArtifactPagination
    generated_at: str
    validation: ContractValidation


class TrackBArtifactReadResponse(BaseModel):
    artifact: TrackBArtifactRecord
    generated_at: str


class TrackBLineageNode(BaseModel):
    node_id: str
    node_type: str
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class TrackBLineageEdge(BaseModel):
    from_id: str
    to_id: str
    relation: str


class TrackBLineageResponse(BaseModel):
    component_query: str
    nodes: list[TrackBLineageNode]
    edges: list[TrackBLineageEdge]
    generated_at: str
    validation: ContractValidation


class TrackBAuditRecord(BaseModel):
    audit_id: str
    artifact_name: str
    schema_version: str
    classification: str
    path: str
    sha256: str
    generated_at: str


class TrackBReleaseRecord(BaseModel):
    release_tag: str
    commit_sha: str
    schema_status: str
    schema_version: str
    schema_path: str
    audit_status: str
    audit_path: str


class TrackBLearningRecord(BaseModel):
    entry_id: str
    entry_type: str
    title: str
    path: str
    source_sha256: str
    schema_version: str
    classification: str
    version: str
    release_backlinks: list[str] = Field(default_factory=list)
    lineage_backlinks: list[str] = Field(default_factory=list)
    generated_at: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _safe_read_json(path: Path) -> tuple[dict[str, Any] | None, list[ContractIssue]]:
    issues: list[ContractIssue] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(
            ContractIssue(
                code="artifact_json_decode_failed",
                message=f"{path.name}: JSON decode failure: {exc}",
                severity="error",
            )
        )
        return None, issues
    if not isinstance(payload, dict):
        issues.append(
            ContractIssue(
                code="artifact_payload_not_object",
                message=f"{path.name}: payload must be a JSON object",
                severity="error",
            )
        )
        return None, issues
    return payload, issues


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _source_roots(repo_root: Path) -> list[Path]:
    roots: list[Path] = []

    env_roots = _normalize_text(os.environ.get("AURA_TRACK_B_ARTIFACT_ROOTS", ""))
    if env_roots:
        for raw in env_roots.split(","):
            text = raw.strip()
            if text:
                roots.append(Path(text).resolve())

    output_root = _normalize_text(os.environ.get("AURA_TRACK_B_OUTPUT_ROOT", "/data/outputs/learning"))
    if output_root:
        roots.append(Path(output_root).resolve())

    roots.append((repo_root / "track_b_validation").resolve())
    roots.append((repo_root / "docs" / "operations" / "transport" / "tracks" / "upstream-learning").resolve())

    dedup: dict[str, Path] = {}
    for root in roots:
        key = str(root)
        if key not in dedup and root.exists() and root.is_dir():
            dedup[key] = root
    return sorted(dedup.values(), key=lambda item: str(item))


def _m8_schema_freeze_path(repo_root: Path) -> Path:
    return (
        repo_root
        / "docs"
        / "operations"
        / "transport"
        / "tracks"
        / "upstream-learning"
        / "m8_schema_freeze.json"
    ).resolve()


def _load_required_fields(repo_root: Path) -> tuple[dict[TrackBArtifactFile, tuple[str, ...]], list[ContractIssue], str]:
    issues: list[ContractIssue] = []
    required = dict(DEFAULT_REQUIRED_FIELDS)
    schema_version = ""
    freeze_path = _m8_schema_freeze_path(repo_root)
    if not freeze_path.exists():
        issues.append(
            ContractIssue(
                code="m8_schema_freeze_missing",
                message=f"Frozen schema record missing: {freeze_path}",
                severity="error",
            )
        )
        return required, issues, schema_version

    payload, parse_issues = _safe_read_json(freeze_path)
    issues.extend(parse_issues)
    if payload is None:
        return required, issues, schema_version

    schema_version = _normalize_text(payload.get("schema_version"))
    frozen = payload.get("frozen_artifacts")
    if not isinstance(frozen, list):
        issues.append(
            ContractIssue(
                code="m8_schema_freeze_invalid",
                message="m8_schema_freeze.frozen_artifacts must be a list",
                severity="error",
            )
        )
        return required, issues, schema_version

    for entry in frozen:
        if not isinstance(entry, dict):
            continue
        file_name = _normalize_text(entry.get("artifact_file"))
        if file_name not in TRACK_B_ARTIFACT_FILES:
            continue
        fields = entry.get("required_fields")
        if not isinstance(fields, list):
            continue
        normalized = tuple(sorted({_normalize_text(item) for item in fields if _normalize_text(item)}))
        if normalized:
            required[file_name] = normalized
    return required, issues, schema_version


def _metadata_from_payload(path: Path, source_root: Path, payload: dict[str, Any], artifact_file: TrackBArtifactFile) -> TrackBArtifactMetadata:
    stat = path.stat()
    artifact_sha = _sha256_file(path)
    artifact_id = _sha256_text(f"{path.resolve()}|{artifact_sha}")

    run_id = _normalize_text(path.parent.relative_to(source_root) if path.parent != source_root else path.parent.name)
    if not run_id:
        run_id = path.parent.name

    session = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    task_id = _normalize_text(payload.get("task_id") or session.get("task_id"))
    platform = _normalize_text(payload.get("platform") or session.get("platform"))

    component = ""
    downstream_component = payload.get("downstream_component")
    if isinstance(downstream_component, dict):
        component = _normalize_text(downstream_component.get("component_name") or downstream_component.get("source_path"))
    if not component:
        downstream_anchor = payload.get("downstream_anchor")
        if isinstance(downstream_anchor, dict):
            component = _normalize_text(downstream_anchor.get("component_name") or downstream_anchor.get("source_path"))
    if not component:
        upstreaming_request = payload.get("upstreaming_request")
        if isinstance(upstreaming_request, dict):
            down = upstreaming_request.get("downstream_component")
            if isinstance(down, dict):
                component = _normalize_text(down.get("component_name") or down.get("source_path"))

    return TrackBArtifactMetadata(
        artifact_id=artifact_id,
        artifact_name=_normalize_text(payload.get("artifact_name") or TRACK_B_ARTIFACT_NAME_BY_FILE[artifact_file]),
        artifact_file=artifact_file,
        artifact_path=str(path),
        source_root=str(source_root),
        run_id=run_id,
        artifact_sha256=artifact_sha,
        exists=True,
        size_bytes=int(stat.st_size),
        modified_at=_iso_from_ts(stat.st_mtime),
        schema_version=_normalize_text(payload.get("schema_version")),
        classification=_normalize_text(payload.get("classification")),
        stage_id=_normalize_text(payload.get("stage_id")),
        decision_state=_normalize_text(payload.get("decision_state")),
        readiness_status=_normalize_text(payload.get("readiness_status")),
        task_id=task_id,
        platform=platform,
        component=component,
        created_at=_normalize_text(payload.get("created_at") or payload.get("generated_at")),
    )


def _validate_payload(
    *,
    artifact_file: TrackBArtifactFile,
    payload: dict[str, Any],
    required_fields: dict[TrackBArtifactFile, tuple[str, ...]],
) -> ContractValidation:
    issues: list[ContractIssue] = []

    for field in required_fields.get(artifact_file, ()):
        if field not in payload:
            issues.append(
                ContractIssue(
                    code="missing_required_field",
                    message=f"{artifact_file}: missing required field '{field}'",
                    severity="error",
                )
            )

    expected_name = TRACK_B_ARTIFACT_NAME_BY_FILE[artifact_file]
    artifact_name = _normalize_text(payload.get("artifact_name"))
    if artifact_name and artifact_name != expected_name:
        issues.append(
            ContractIssue(
                code="artifact_name_mismatch",
                message=f"{artifact_file}: artifact_name={artifact_name!r} expected={expected_name!r}",
                severity="error",
            )
        )

    schema_version = _normalize_text(payload.get("schema_version"))
    if not schema_version:
        issues.append(
            ContractIssue(
                code="schema_version_missing",
                message=f"{artifact_file}: schema_version missing",
                severity="error",
            )
        )

    classification = _normalize_text(payload.get("classification")).upper()
    if not classification:
        issues.append(
            ContractIssue(
                code="classification_missing",
                message=f"{artifact_file}: classification missing",
                severity="error",
            )
        )

    return ContractValidation(valid=not any(issue.severity == "error" for issue in issues), issues=issues)


def _collect_artifact_candidates(source_root: Path) -> list[Path]:
    files: list[Path] = []
    for artifact_file in TRACK_B_ARTIFACT_FILES:
        for path in source_root.rglob(artifact_file):
            if path.is_file():
                files.append(path.resolve())
    unique: dict[str, Path] = {}
    for path in files:
        unique[str(path)] = path
    return sorted(unique.values(), key=lambda item: str(item))


def collect_track_b_artifacts(
    *,
    repo_root: Path | None = None,
    strict: bool = True,
) -> tuple[list[TrackBArtifactRecord], ContractValidation]:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    required_fields, freeze_issues, _schema_version = _load_required_fields(root)
    source_roots = _source_roots(root)

    records: list[TrackBArtifactRecord] = []
    issues: list[ContractIssue] = list(freeze_issues)

    if not source_roots:
        issues.append(
            ContractIssue(
                code="track_b_source_roots_missing",
                message="No Track-B artifact roots were discovered",
                severity="error",
            )
        )

    for source_root in source_roots:
        for path in _collect_artifact_candidates(source_root):
            artifact_file = path.name
            if artifact_file not in TRACK_B_ARTIFACT_FILES:
                continue

            payload, parse_issues = _safe_read_json(path)
            if payload is None:
                metadata = TrackBArtifactMetadata(
                    artifact_id=_sha256_text(str(path)),
                    artifact_name=TRACK_B_ARTIFACT_NAME_BY_FILE[artifact_file],
                    artifact_file=artifact_file,
                    artifact_path=str(path),
                    source_root=str(source_root),
                    run_id=path.parent.name,
                    artifact_sha256="",
                    exists=True,
                    size_bytes=int(path.stat().st_size),
                    modified_at=_iso_from_ts(path.stat().st_mtime),
                )
                validation = ContractValidation(valid=False, issues=parse_issues)
                issues.extend(parse_issues)
                records.append(TrackBArtifactRecord(metadata=metadata, validation=validation, payload=None))
                continue

            metadata = _metadata_from_payload(path, source_root, payload, artifact_file)
            validation = _validate_payload(
                artifact_file=artifact_file,
                payload=payload,
                required_fields=required_fields,
            )
            issues.extend(validation.issues)
            records.append(TrackBArtifactRecord(metadata=metadata, validation=validation, payload=payload))

    records.sort(
        key=lambda record: (
            str(record.metadata.artifact_name),
            str(record.metadata.run_id),
            str(record.metadata.modified_at),
            str(record.metadata.artifact_id),
        )
    )

    valid = not any(issue.severity == "error" for issue in issues)
    if strict and not valid:
        logger.warning(
            "track_b_artifact_collection_fail_closed",
            error_count=len([issue for issue in issues if issue.severity == "error"]),
        )
    return records, ContractValidation(valid=valid, issues=issues)


T = TypeVar("T")


def _paginate(items: list[T], *, page: int, limit: int) -> tuple[list[T], TrackBArtifactPagination]:
    total = len(items)
    safe_page = max(1, page)
    safe_limit = max(1, min(limit, 500))
    start = (safe_page - 1) * safe_limit
    end = start + safe_limit
    return items[start:end], TrackBArtifactPagination(page=safe_page, limit=safe_limit, total=total)


def filter_track_b_artifacts(
    artifacts: list[TrackBArtifactRecord],
    *,
    artifact_name: str = "",
    classification: str = "",
    stage_id: str = "",
    decision_state: str = "",
    readiness_status: str = "",
    task_id: str = "",
    component: str = "",
) -> list[TrackBArtifactRecord]:
    name_filter = _normalize_text(artifact_name).lower()
    class_filter = _normalize_text(classification).upper()
    stage_filter = _normalize_text(stage_id).upper()
    decision_filter = _normalize_text(decision_state).upper()
    readiness_filter = _normalize_text(readiness_status).upper()
    task_filter = _normalize_text(task_id)
    component_filter = _normalize_text(component).lower()

    filtered: list[TrackBArtifactRecord] = []
    for item in artifacts:
        metadata = item.metadata
        if name_filter and name_filter not in metadata.artifact_name.lower() and name_filter not in metadata.artifact_file.lower():
            continue
        if class_filter and metadata.classification.upper() != class_filter:
            continue
        if stage_filter and metadata.stage_id.upper() != stage_filter:
            continue
        if decision_filter and metadata.decision_state.upper() != decision_filter:
            continue
        if readiness_filter and metadata.readiness_status.upper() != readiness_filter:
            continue
        if task_filter and metadata.task_id != task_filter:
            continue
        if component_filter and component_filter not in metadata.component.lower():
            continue
        filtered.append(item)
    return filtered


def _run_key(record: TrackBArtifactRecord) -> str:
    return f"{record.metadata.source_root}::{record.metadata.run_id}"


def _record_map_by_file(records: list[TrackBArtifactRecord]) -> dict[str, dict[TrackBArtifactFile, TrackBArtifactRecord]]:
    grouped: dict[str, dict[TrackBArtifactFile, TrackBArtifactRecord]] = {}
    for record in records:
        bucket = grouped.setdefault(_run_key(record), {})
        bucket[record.metadata.artifact_file] = record
    return grouped


def collect_track_b_audits(*, repo_root: Path | None = None) -> list[TrackBAuditRecord]:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    candidates: list[Path] = []

    for pattern in (
        "**/m8_fresh_audit_report.json",
        "**/*audit*report*.json",
        "**/*audit*summary*.json",
    ):
        candidates.extend((root / "docs" / "operations" / "transport").glob(pattern))
        candidates.extend((root / "track_b_validation").glob(pattern))

    unique: dict[str, Path] = {}
    for path in candidates:
        if path.is_file():
            unique[str(path.resolve())] = path.resolve()

    records: list[TrackBAuditRecord] = []
    for path in sorted(unique.values(), key=lambda item: str(item)):
        payload, _issues = _safe_read_json(path)
        schema_version = _normalize_text(payload.get("schema_version")) if payload else ""
        classification = _normalize_text(payload.get("classification")) if payload else ""
        artifact_name = _normalize_text(payload.get("artifact_name")) if payload else ""
        generated_at = _normalize_text(payload.get("generated_at") if payload else "")
        if not generated_at:
            generated_at = _iso_from_ts(path.stat().st_mtime)
        source_sha = _sha256_file(path)
        audit_id = _sha256_text(f"{path.resolve()}|{source_sha}")
        records.append(
            TrackBAuditRecord(
                audit_id=audit_id,
                artifact_name=artifact_name or path.name,
                schema_version=schema_version,
                classification=classification,
                path=str(path),
                sha256=source_sha,
                generated_at=generated_at,
            )
        )

    records.sort(key=lambda item: (item.generated_at, item.path, item.audit_id), reverse=True)
    return records


def collect_track_b_releases(*, repo_root: Path | None = None) -> list[TrackBReleaseRecord]:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    freeze_path = _m8_schema_freeze_path(root)
    audit_path = (
        root
        / "docs"
        / "operations"
        / "transport"
        / "tracks"
        / "upstream-learning"
        / "m8_fresh_audit_report.json"
    )

    schema_status = "MISSING"
    schema_version = ""
    if freeze_path.exists():
        payload, _issues = _safe_read_json(freeze_path)
        if payload is not None:
            schema_status = _normalize_text(payload.get("status") or "PRESENT")
            schema_version = _normalize_text(payload.get("schema_version"))

    audit_status = "MISSING"
    if audit_path.exists():
        payload, _issues = _safe_read_json(audit_path)
        if payload is not None:
            audit_status = _normalize_text(payload.get("classification") or "PRESENT")
        else:
            audit_status = "INVALID"

    tags: list[str] = []
    try:
        run = subprocess.run(
            ["git", "-C", str(root), "tag", "--list", "*release*"],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode == 0:
            tags = sorted({line.strip() for line in (run.stdout or "").splitlines() if line.strip()})
    except Exception:
        tags = []

    if RELEASE_TAG_HINT not in tags:
        tags.append(RELEASE_TAG_HINT)
    tags = sorted(set(tags))

    releases: list[TrackBReleaseRecord] = []
    for tag in tags:
        commit_sha = ""
        try:
            run = subprocess.run(
                ["git", "-C", str(root), "rev-list", "-n", "1", tag],
                capture_output=True,
                text=True,
                check=False,
            )
            if run.returncode == 0:
                commit_sha = _normalize_text(run.stdout)
        except Exception:
            commit_sha = ""
        releases.append(
            TrackBReleaseRecord(
                release_tag=tag,
                commit_sha=commit_sha,
                schema_status=schema_status,
                schema_version=schema_version,
                schema_path=str(freeze_path),
                audit_status=audit_status,
                audit_path=str(audit_path),
            )
        )

    releases.sort(key=lambda item: item.release_tag, reverse=True)
    return releases


def _evidence_nodes(payload: dict[str, Any], *, run_key: str) -> list[TrackBLineageNode]:
    nodes: list[TrackBLineageNode] = []
    candidate_mappings = payload.get("candidate_mappings")
    if not isinstance(candidate_mappings, list):
        return nodes

    seen: set[str] = set()
    for mapping in candidate_mappings:
        if not isinstance(mapping, dict):
            continue
        evidence = mapping.get("evidence")
        if not isinstance(evidence, list):
            continue
        for item in evidence:
            if not isinstance(item, dict):
                continue
            evidence_sig = _stable_json(item)
            evidence_id = f"evidence:{_sha256_text(run_key + '|' + evidence_sig)}"
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            nodes.append(
                TrackBLineageNode(
                    node_id=evidence_id,
                    node_type="evidence",
                    label=_normalize_text(item.get("path") or item.get("line_range") or "evidence"),
                    attributes={
                        "corpus_role": _normalize_text(item.get("corpus_role")),
                        "corpus_id": _normalize_text(item.get("corpus_id")),
                        "path": _normalize_text(item.get("path")),
                        "line_range": _normalize_text(item.get("line_range")),
                    },
                )
            )
    return nodes


def build_track_b_lineage(
    records: list[TrackBArtifactRecord],
    *,
    component_query: str = "",
    reverse_node_id: str = "",
) -> TrackBLineageResponse:
    grouped = _record_map_by_file(records)
    audits = collect_track_b_audits()
    releases = collect_track_b_releases()

    nodes: dict[str, TrackBLineageNode] = {}
    edges: dict[str, TrackBLineageEdge] = {}

    component_filter = _normalize_text(component_query).lower()

    for run_key in sorted(grouped.keys()):
        bucket = grouped[run_key]
        eq = bucket.get("track_b_equivalence_map.json")
        dep = bucket.get("track_b_dependency_matrix.json")
        conflict = bucket.get("track_b_conflict_ledger.json")
        decision = bucket.get("track_b_equivalence_decision.json")
        report = bucket.get("track_b_upstreaming_report.json")
        readiness = bucket.get("track_b_upstreaming_readiness.json")

        component_label = ""
        if report and report.payload:
            downstream_component = report.payload.get("downstream_component")
            if isinstance(downstream_component, dict):
                component_label = _normalize_text(
                    downstream_component.get("component_name")
                    or downstream_component.get("source_path")
                )
        if not component_label and eq and eq.payload:
            anchor = eq.payload.get("downstream_anchor")
            if isinstance(anchor, dict):
                component_label = _normalize_text(anchor.get("component_name") or anchor.get("source_path"))

        if component_filter and component_filter not in component_label.lower():
            continue

        component_id = f"component:{_sha256_text(run_key + '|' + component_label)}"
        nodes[component_id] = TrackBLineageNode(
            node_id=component_id,
            node_type="component",
            label=component_label or "component",
            attributes={"run_id": run_key},
        )

        evidence_nodes = []
        if eq and eq.payload:
            evidence_nodes = _evidence_nodes(eq.payload, run_key=run_key)
        for evidence_node in evidence_nodes:
            nodes[evidence_node.node_id] = evidence_node
            edge_key = f"{component_id}|{evidence_node.node_id}|component_to_evidence"
            edges[edge_key] = TrackBLineageEdge(
                from_id=component_id,
                to_id=evidence_node.node_id,
                relation="component_to_evidence",
            )

        dependency_nodes: list[str] = []
        if dep and dep.payload and isinstance(dep.payload.get("dependency_records"), list):
            for record in dep.payload["dependency_records"]:
                if not isinstance(record, dict):
                    continue
                dep_id = _normalize_text(record.get("candidate_id"))
                if not dep_id:
                    dep_id = _sha256_text(run_key + "|dependency|" + _stable_json(record))
                dep_node_id = f"dependency:{dep_id}"
                dependency_nodes.append(dep_node_id)
                nodes[dep_node_id] = TrackBLineageNode(
                    node_id=dep_node_id,
                    node_type="dependency",
                    label=_normalize_text(record.get("upstream_path") or record.get("downstream_path") or dep_id),
                    attributes={
                        "missing_dependency_count": int(record.get("missing_dependency_count") or 0),
                        "mandatory_checks": record.get("mandatory_checks", {}),
                    },
                )
                from_id = evidence_nodes[0].node_id if evidence_nodes else component_id
                edge_key = f"{from_id}|{dep_node_id}|evidence_to_dependency"
                edges[edge_key] = TrackBLineageEdge(
                    from_id=from_id,
                    to_id=dep_node_id,
                    relation="evidence_to_dependency",
                )

        conflict_nodes: list[str] = []
        if conflict and conflict.payload and isinstance(conflict.payload.get("conflicts"), list):
            for item in conflict.payload["conflicts"]:
                if not isinstance(item, dict):
                    continue
                conflict_id = _normalize_text(item.get("conflict_id"))
                if not conflict_id:
                    conflict_id = _sha256_text(run_key + "|conflict|" + _stable_json(item))
                conflict_node_id = f"conflict:{conflict_id}"
                conflict_nodes.append(conflict_node_id)
                nodes[conflict_node_id] = TrackBLineageNode(
                    node_id=conflict_node_id,
                    node_type="conflict",
                    label=_normalize_text(item.get("conflict_type") or "conflict"),
                    attributes={
                        "severity": _normalize_text(item.get("severity")),
                        "status": _normalize_text(item.get("status")),
                    },
                )
                sources = dependency_nodes or [component_id]
                for source in sources[:1]:
                    edge_key = f"{source}|{conflict_node_id}|dependency_to_conflict"
                    edges[edge_key] = TrackBLineageEdge(
                        from_id=source,
                        to_id=conflict_node_id,
                        relation="dependency_to_conflict",
                    )

        decision_node_id = ""
        if decision and decision.payload:
            decision_state = _normalize_text(decision.payload.get("decision_state") or "decision")
            decision_node_id = f"decision:{decision.metadata.artifact_id}"
            nodes[decision_node_id] = TrackBLineageNode(
                node_id=decision_node_id,
                node_type="decision",
                label=decision_state,
                attributes={"classification": decision.metadata.classification},
            )
            sources = conflict_nodes or dependency_nodes or [component_id]
            edge_key = f"{sources[0]}|{decision_node_id}|conflict_to_decision"
            edges[edge_key] = TrackBLineageEdge(
                from_id=sources[0],
                to_id=decision_node_id,
                relation="conflict_to_decision",
            )

        readiness_node_id = ""
        if readiness and readiness.payload:
            readiness_node_id = f"readiness:{readiness.metadata.artifact_id}"
            nodes[readiness_node_id] = TrackBLineageNode(
                node_id=readiness_node_id,
                node_type="readiness",
                label=_normalize_text(readiness.payload.get("readiness_status") or "readiness"),
                attributes={
                    "classification": readiness.metadata.classification,
                    "decision_state": readiness.metadata.decision_state,
                },
            )
            parent = decision_node_id or component_id
            edge_key = f"{parent}|{readiness_node_id}|decision_to_readiness"
            edges[edge_key] = TrackBLineageEdge(
                from_id=parent,
                to_id=readiness_node_id,
                relation="decision_to_readiness",
            )

            if audits:
                audit = audits[0]
                audit_node_id = f"audit:{audit.audit_id}"
                nodes[audit_node_id] = TrackBLineageNode(
                    node_id=audit_node_id,
                    node_type="audit",
                    label=audit.artifact_name,
                    attributes={
                        "classification": audit.classification,
                        "path": audit.path,
                    },
                )
                edge_key = f"{readiness_node_id}|{audit_node_id}|readiness_to_audit"
                edges[edge_key] = TrackBLineageEdge(
                    from_id=readiness_node_id,
                    to_id=audit_node_id,
                    relation="readiness_to_audit",
                )

                if releases:
                    release = releases[0]
                    release_node_id = f"release:{release.release_tag}"
                    nodes[release_node_id] = TrackBLineageNode(
                        node_id=release_node_id,
                        node_type="release",
                        label=release.release_tag,
                        attributes={
                            "commit_sha": release.commit_sha,
                            "schema_status": release.schema_status,
                            "audit_status": release.audit_status,
                        },
                    )
                    edge_key = f"{audit_node_id}|{release_node_id}|audit_to_release"
                    edges[edge_key] = TrackBLineageEdge(
                        from_id=audit_node_id,
                        to_id=release_node_id,
                        relation="audit_to_release",
                    )

    node_values = list(nodes.values())
    edge_values = list(edges.values())

    if reverse_node_id:
        selected_nodes: set[str] = set()
        selected_edges: list[TrackBLineageEdge] = []
        for edge in edge_values:
            if edge.from_id == reverse_node_id or edge.to_id == reverse_node_id:
                selected_edges.append(edge)
                selected_nodes.add(edge.from_id)
                selected_nodes.add(edge.to_id)
        if reverse_node_id in nodes:
            selected_nodes.add(reverse_node_id)
        node_values = [nodes[node_id] for node_id in sorted(selected_nodes)]
        edge_values = sorted(selected_edges, key=lambda item: (item.from_id, item.to_id, item.relation))
    else:
        node_values = sorted(node_values, key=lambda item: (item.node_type, item.label, item.node_id))
        edge_values = sorted(edge_values, key=lambda item: (item.from_id, item.to_id, item.relation))

    validation = ContractValidation(valid=True, issues=[])
    if not node_values:
        validation = ContractValidation(
            valid=False,
            issues=[
                ContractIssue(
                    code="lineage_not_found",
                    message="No lineage graph could be built for current filter",
                    severity="error",
                )
            ],
        )

    return TrackBLineageResponse(
        component_query=_normalize_text(component_query),
        nodes=node_values,
        edges=edge_values,
        generated_at=_now_iso(),
        validation=validation,
    )


def summarize_dependency_coverage(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    deps = [record for record in records if record.metadata.artifact_file == "track_b_dependency_matrix.json" and record.payload]

    totals = {
        "dt": {"resolved": 0, "total": 0},
        "kconfig": {"resolved": 0, "total": 0},
        "codec": {"resolved": 0, "total": 0},
        "soundwire": {"resolved": 0, "total": 0},
        "dsp_service": {"resolved": 0, "total": 0},
    }

    for dep in deps:
        dep_records = dep.payload.get("dependency_records") if isinstance(dep.payload, dict) else []
        if not isinstance(dep_records, list):
            continue
        for item in dep_records:
            if not isinstance(item, dict):
                continue
            checks = item.get("mandatory_checks") if isinstance(item.get("mandatory_checks"), dict) else {}

            totals["dt"]["total"] += 1
            if bool(checks.get("dts_resolved")):
                totals["dt"]["resolved"] += 1

            totals["kconfig"]["total"] += 1
            if bool(checks.get("kconfig_resolved")):
                totals["kconfig"]["resolved"] += 1

            up_path = _normalize_text(item.get("upstream_path")).lower()
            down_path = _normalize_text(item.get("downstream_path")).lower()
            merged = f"{up_path}|{down_path}"

            for key, needle in (("codec", "codec"), ("soundwire", "soundwire"), ("soundwire", "sdw"), ("dsp_service", "dsp"), ("dsp_service", "q6"), ("dsp_service", "apm")):
                if needle in merged:
                    totals[key]["total"] += 1
                    if int(item.get("missing_dependency_count") or 0) == 0:
                        totals[key]["resolved"] += 1
                    break

    coverage = {}
    for key, value in totals.items():
        total = int(value["total"])
        resolved = int(value["resolved"])
        percent = round((resolved / total) * 100.0, 2) if total else 0.0
        coverage[key] = {"resolved": resolved, "total": total, "coverage_percent": percent}

    return {
        "classification": "PASS",
        "generated_at": _now_iso(),
        "coverage": coverage,
    }


def summarize_conflicts(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    conflicts = [record for record in records if record.metadata.artifact_file == "track_b_conflict_ledger.json" and record.payload]
    open_count = 0
    resolved_count = 0
    categories: dict[str, int] = {}

    for item in conflicts:
        payload = item.payload or {}
        entries = payload.get("conflicts") if isinstance(payload.get("conflicts"), list) else []
        for conflict in entries:
            if not isinstance(conflict, dict):
                continue
            category = _normalize_text(conflict.get("conflict_type") or "unknown").upper()
            categories[category] = categories.get(category, 0) + 1
            status = _normalize_text(conflict.get("status")).upper()
            if status == "RESOLVED":
                resolved_count += 1
            else:
                open_count += 1

    ordered_categories = [
        {"category": key, "count": categories[key]} for key in sorted(categories.keys())
    ]

    return {
        "classification": "PASS",
        "generated_at": _now_iso(),
        "open_conflicts": open_count,
        "resolved_conflicts": resolved_count,
        "categories": ordered_categories,
    }


def summarize_equivalence(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    states = {
        "UNIQUE_EQUIVALENT": 0,
        "MULTI_EQUIVALENT": 0,
        "NO_EQUIVALENT": 0,
        "CONFLICTING_EVIDENCE": 0,
    }
    decisions = [
        record
        for record in records
        if record.metadata.artifact_file == "track_b_equivalence_decision.json" and record.payload
    ]
    for item in decisions:
        state = _normalize_text(item.metadata.decision_state).upper()
        if state in states:
            states[state] += 1

    return {
        "classification": "PASS",
        "generated_at": _now_iso(),
        "states": states,
        "total": sum(states.values()),
    }


def summarize_readiness(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    readiness_records = [
        record
        for record in records
        if record.metadata.artifact_file == "track_b_upstreaming_readiness.json" and record.payload
    ]
    total = len(readiness_records)
    fail_closed = len([record for record in readiness_records if record.metadata.classification.upper() == "FAIL_CLOSED"])
    blockers = 0
    mandatory_total = 0
    mandatory_passed = 0

    for item in readiness_records:
        payload = item.payload or {}
        reasons = payload.get("fail_closed_reasons")
        if isinstance(reasons, list):
            blockers += len([reason for reason in reasons if _normalize_text(reason)])
        mandatory_checks = payload.get("mandatory_checks")
        if isinstance(mandatory_checks, dict):
            mandatory_total += len(mandatory_checks)
            mandatory_passed += len([value for value in mandatory_checks.values() if bool(value)])

    completion = 100.0 if total else 0.0
    production_readiness = round(max(0.0, 100.0 - (fail_closed * 10.0 + blockers * 1.0)), 2)
    evidence_completeness = round((mandatory_passed / mandatory_total) * 100.0, 2) if mandatory_total else 0.0

    fresh_audit = (
        resolve_repo_root()
        / "docs"
        / "operations"
        / "transport"
        / "tracks"
        / "upstream-learning"
        / "m8_fresh_audit_report.json"
    )
    audit_status = "UNKNOWN"
    release_status = "UNKNOWN"
    completion_metric = completion
    readiness_metric = production_readiness
    blocker_metric = blockers

    if fresh_audit.exists():
        payload, _issues = _safe_read_json(fresh_audit)
        if payload is not None:
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            completion_metric = float(metrics.get("m8_completion_percentage") or completion_metric)
            readiness_metric = float(metrics.get("production_readiness_percentage") or readiness_metric)
            blocker_metric = int(metrics.get("blocker_count") or blocker_metric)
            audit_status = "PASS" if payload.get("targets", {}).get("blockers_eq_0") else "WARN"
            release_status = "RELEASED"

    return {
        "classification": "PASS",
        "generated_at": _now_iso(),
        "completion_percent": round(completion_metric, 2),
        "production_readiness_percent": round(readiness_metric, 2),
        "blocker_count": int(blocker_metric),
        "fail_closed_count": int(fail_closed),
        "artifact_count": int(total),
        "evidence_completeness_percent": float(evidence_completeness),
        "audit_status": audit_status,
        "release_status": release_status,
    }


def readiness_history(records: list[TrackBArtifactRecord]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in records:
        if item.metadata.artifact_file != "track_b_upstreaming_readiness.json" or not item.payload:
            continue
        payload = item.payload
        mandatory_checks = payload.get("mandatory_checks") if isinstance(payload.get("mandatory_checks"), dict) else {}
        passed_checks = len([value for value in mandatory_checks.values() if bool(value)])
        total_checks = len(mandatory_checks)
        score = round((passed_checks / total_checks) * 100.0, 2) if total_checks else 0.0
        rows.append(
            {
                "artifact_id": item.metadata.artifact_id,
                "task_id": item.metadata.task_id,
                "component": item.metadata.component,
                "decision_state": item.metadata.decision_state,
                "readiness_status": item.metadata.readiness_status,
                "classification": item.metadata.classification,
                "score_percent": score,
                "modified_at": item.metadata.modified_at,
            }
        )
    rows.sort(key=lambda row: (row["modified_at"], row["artifact_id"]))
    return rows


def collect_learning_records(records: list[TrackBArtifactRecord], *, repo_root: Path | None = None) -> list[TrackBLearningRecord]:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    releases = collect_track_b_releases(repo_root=root)
    release_backlinks = [release.release_tag for release in releases]

    entries: dict[tuple[str, str], TrackBLearningRecord] = {}

    def upsert(entry: TrackBLearningRecord) -> None:
        entries[(entry.entry_type, entry.source_sha256)] = entry

    for item in records:
        metadata = item.metadata
        if not metadata.artifact_sha256:
            continue
        entry_type = "readiness_report" if metadata.artifact_file == "track_b_upstreaming_readiness.json" else "artifact_report"
        title = f"{metadata.artifact_name} ({metadata.component or metadata.run_id})"
        lineage_backlinks = []
        payload = item.payload or {}
        lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
        for value in lineage.values():
            text = _normalize_text(value)
            if text:
                lineage_backlinks.append(text)
        upsert(
            TrackBLearningRecord(
                entry_id=_sha256_text(metadata.artifact_id + "|learning"),
                entry_type=entry_type,
                title=title,
                path=metadata.artifact_path,
                source_sha256=metadata.artifact_sha256,
                schema_version=metadata.schema_version,
                classification=metadata.classification,
                version=metadata.schema_version or "1.0",
                release_backlinks=release_backlinks,
                lineage_backlinks=sorted(set(lineage_backlinks)),
                generated_at=metadata.modified_at,
            )
        )

    report_candidates: list[tuple[str, Path]] = []
    for pattern, entry_type in (
        ("**/*audit*report*.json", "audit_report"),
        ("**/*validation*.json", "validation_report"),
        ("**/*closure*.md", "closure_report"),
        ("**/*defect*.json", "defect_report"),
        ("**/*schema*freeze*.json", "schema_freeze"),
        ("**/*release*.json", "release_summary"),
    ):
        report_candidates.extend(
            [
                (entry_type, path)
                for path in (root / "docs" / "operations" / "transport").glob(pattern)
                if path.is_file()
            ]
        )
        report_candidates.extend(
            [
                (entry_type, path)
                for path in (root / "track_b_validation").glob(pattern)
                if path.is_file()
            ]
        )

    unique_candidates: dict[str, tuple[str, Path]] = {}
    for entry_type, path in report_candidates:
        unique_candidates[str(path.resolve())] = (entry_type, path.resolve())

    for entry_type, path in sorted(unique_candidates.values(), key=lambda item: str(item[1])):
        source_sha = _sha256_file(path)
        payload, _issues = _safe_read_json(path) if path.suffix.lower() == ".json" else (None, [])
        schema_version = _normalize_text(payload.get("schema_version")) if payload else ""
        classification = _normalize_text(payload.get("classification")) if payload else ""
        generated_at = _normalize_text(payload.get("generated_at")) if payload else ""
        if not generated_at:
            generated_at = _iso_from_ts(path.stat().st_mtime)
        upsert(
            TrackBLearningRecord(
                entry_id=_sha256_text(f"{path.resolve()}|{source_sha}|learning"),
                entry_type=entry_type,
                title=path.name,
                path=str(path),
                source_sha256=source_sha,
                schema_version=schema_version,
                classification=classification,
                version=schema_version or "1.0",
                release_backlinks=release_backlinks,
                lineage_backlinks=[],
                generated_at=generated_at,
            )
        )

    values = list(entries.values())
    values.sort(key=lambda item: (item.entry_type, item.title, item.path, item.entry_id))
    return values


def collect_learning_patterns(records: list[TrackBArtifactRecord]) -> dict[str, Any]:
    conflicts_summary = summarize_conflicts(records)
    dependency_summary = summarize_dependency_coverage(records)
    readiness_summary = summarize_readiness(records)

    examples = []
    for item in records:
        if item.metadata.artifact_file != "track_b_upstreaming_report.json" or not item.payload:
            continue
        component = item.payload.get("downstream_component") if isinstance(item.payload.get("downstream_component"), dict) else {}
        examples.append(
            {
                "component": _normalize_text(component.get("component_name") or component.get("source_path")),
                "decision_state": _normalize_text(item.payload.get("decision_state")),
                "risk_assessment": item.payload.get("risk_assessment", {}),
            }
        )
    examples.sort(key=lambda item: (item["component"], item["decision_state"]))

    return {
        "classification": "PASS",
        "generated_at": _now_iso(),
        "defect_patterns": conflicts_summary,
        "dependency_patterns": dependency_summary,
        "readiness_examples": readiness_summary,
        "upstreaming_examples": examples[:50],
    }


def search_track_b(
    *,
    records: list[TrackBArtifactRecord],
    learning_records: list[TrackBLearningRecord],
    audits: list[TrackBAuditRecord],
    releases: list[TrackBReleaseRecord],
    query: str,
    kind: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    needle = _normalize_text(query).lower()
    kind_filter = _normalize_text(kind).lower()
    safe_limit = max(1, min(limit, 500))

    documents: list[dict[str, Any]] = []

    for record in records:
        payload_text = ""
        if record.payload:
            payload_text = _stable_json(record.payload)
        documents.append(
            {
                "kind": "artifact",
                "id": record.metadata.artifact_id,
                "title": record.metadata.artifact_name,
                "summary": " ".join(
                    [
                        record.metadata.component,
                        record.metadata.decision_state,
                        record.metadata.readiness_status,
                        record.metadata.stage_id,
                        record.metadata.artifact_file,
                        payload_text,
                    ]
                ).strip(),
                "path": record.metadata.artifact_path,
            }
        )

    for audit in audits:
        documents.append(
            {
                "kind": "audit",
                "id": audit.audit_id,
                "title": audit.artifact_name,
                "summary": f"{audit.classification} {audit.schema_version} {audit.path}",
                "path": audit.path,
            }
        )

    for release in releases:
        documents.append(
            {
                "kind": "release",
                "id": release.release_tag,
                "title": release.release_tag,
                "summary": f"{release.commit_sha} {release.schema_status} {release.audit_status}",
                "path": release.schema_path,
            }
        )

    for entry in learning_records:
        documents.append(
            {
                "kind": "lesson",
                "id": entry.entry_id,
                "title": entry.title,
                "summary": f"{entry.entry_type} {entry.classification} {entry.path}",
                "path": entry.path,
            }
        )

    filtered: list[dict[str, Any]] = []
    for doc in documents:
        doc_kind = _normalize_text(doc.get("kind")).lower()
        if kind_filter and doc_kind != kind_filter:
            continue
        if needle:
            haystack = (
                _normalize_text(doc.get("title"))
                + " "
                + _normalize_text(doc.get("summary"))
                + " "
                + _normalize_text(doc.get("id"))
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(doc)

    filtered.sort(key=lambda item: (_normalize_text(item.get("kind")), _normalize_text(item.get("title")), _normalize_text(item.get("id"))))
    return filtered[:safe_limit]


def track_b_overview(*, repo_root: Path | None = None, strict: bool = True) -> dict[str, Any]:
    records, validation = collect_track_b_artifacts(repo_root=repo_root, strict=strict)
    audits = collect_track_b_audits(repo_root=repo_root)
    releases = collect_track_b_releases(repo_root=repo_root)
    learning = collect_learning_records(records, repo_root=repo_root)

    return {
        "records": records,
        "validation": validation,
        "audits": audits,
        "releases": releases,
        "learning": learning,
    }


def artifact_by_id(records: list[TrackBArtifactRecord], artifact_id: str) -> TrackBArtifactRecord | None:
    for item in records:
        if item.metadata.artifact_id == artifact_id:
            return item
    return None


def artifact_index_response(
    *,
    records: list[TrackBArtifactRecord],
    validation: ContractValidation,
    page: int,
    limit: int,
) -> TrackBArtifactIndexResponse:
    window, pagination = _paginate(records, page=page, limit=limit)
    return TrackBArtifactIndexResponse(
        artifacts=window,
        pagination=pagination,
        generated_at=_now_iso(),
        validation=validation,
    )
