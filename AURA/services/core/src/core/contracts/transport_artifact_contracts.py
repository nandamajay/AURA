"""Contract-first runtime transport artifact models and validation helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aura_sdk.logging.logger import get_logger

RuntimeArtifactType = Literal[
    "runtime_equivalence_report",
    "hardware_truth_graph",
    "replay_consistency_report",
    "runtime_governance_decision",
    "transformation_confidence_report",
]

KNOWN_RUNTIME_ARTIFACTS: tuple[RuntimeArtifactType, ...] = (
    "runtime_equivalence_report",
    "hardware_truth_graph",
    "replay_consistency_report",
    "runtime_governance_decision",
    "transformation_confidence_report",
)

_RUNTIME_ARTIFACT_FILES: dict[RuntimeArtifactType, str] = {
    "runtime_equivalence_report": "runtime_equivalence_report.json",
    "hardware_truth_graph": "hardware_truth_graph.json",
    "replay_consistency_report": "replay_consistency_report.json",
    "runtime_governance_decision": "runtime_governance_decision.json",
    "transformation_confidence_report": "transformation_confidence_report.json",
}

_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")
logger = get_logger("core.transport_artifact_contracts")


class ContractIssue(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ContractValidation(BaseModel):
    valid: bool
    issues: list[ContractIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[ContractIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[ContractIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]


class RuntimeExecutionFingerprint(BaseModel):
    model_config = ConfigDict(extra="allow")

    python_version: str
    dependency_hashes: dict[str, str] = Field(default_factory=dict)
    git_sha: str
    parser_version: str
    execution_container_hash: str
    timestamp: str


class RuntimeArtifactMetadata(BaseModel):
    artifact_type: RuntimeArtifactType
    artifact_file: str
    artifact_path: str
    exists: bool
    size_bytes: int = 0
    modified_at: str = ""

    report_name: str = ""
    schema_version: str = ""
    target_id: str = ""
    classification: str = ""

    lineage_id: str = ""
    session_id: str = ""
    created_at: str = ""

    advisory_only_behavior: bool = True
    runtime_truth_precedence: bool = True
    deterministic_fingerprint: str = ""
    replay_fingerprint: str = ""
    runtime_execution_python_version: str = ""
    runtime_execution_container_hash: str = ""
    runtime_execution_parser_version: str = ""
    evidence_references: list[str] = Field(default_factory=list)


class BaseTransportArtifact(BaseModel):
    """Common contract fields for all runtime transport artifacts."""

    model_config = ConfigDict(extra="allow")

    report_name: str
    schema_version: str
    target_id: str
    advisory_only_behavior: bool
    runtime_truth_precedence: bool
    classification: str
    deterministic_fingerprint: str
    runtime_execution_fingerprint: RuntimeExecutionFingerprint
    evidence_references: list[str] = Field(default_factory=list)
    lineage_id: str = ""
    session_id: str = ""
    created_at: str = ""


class RuntimeEquivalenceDimension(BaseModel):
    model_config = ConfigDict(extra="allow")

    dimension: str
    classification: str
    critical: bool = False
    difference_count: int = 0
    drift_ratio: float = 0.0
    baseline_count: int = 0
    transformed_count: int = 0
    weight: float = 0.0
    added_items: list[str] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list)


class RuntimeEquivalenceSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    confidence_score: float = 0.0
    critical_divergence_count: int = 0
    total_differences: int = 0


class RuntimeEquivalenceReport(BaseTransportArtifact):
    dimensions: list[RuntimeEquivalenceDimension] = Field(default_factory=list)
    summary: RuntimeEquivalenceSummary


class HardwareTruthEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp_ms: float | None = None
    message: str = ""


class HardwareTruthSummary(BaseModel):
    model_config = ConfigDict(extra="allow")


class HardwareTruthGraphReport(BaseTransportArtifact):
    nodes: dict[str, list[HardwareTruthEvent]] = Field(default_factory=dict)
    summary: HardwareTruthSummary = Field(default_factory=HardwareTruthSummary)
    fail_closed_reasons: list[str] = Field(default_factory=list)


class ReplayConsistencyModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    deterministic_event_ordering: bool = False
    lineage_fingerprint: str = ""
    previous_lineage_fingerprint: str = ""
    replay_drift: bool = False


class ReplayConsistencyReport(BaseTransportArtifact):
    consistency: ReplayConsistencyModel
    reasons: list[str] = Field(default_factory=list)


class RuntimePromotionGate(BaseModel):
    model_config = ConfigDict(extra="allow")

    confidence_score: float = 0.0
    confidence_threshold: float = 0.0
    critical_divergence_count: int = 0
    deterministic_replay_ready: bool = False
    runtime_sensitive_impact_count: int = 0


class RuntimeInputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    runtime_confidence_fingerprint: str = ""
    runtime_divergence_fingerprint: str = ""
    runtime_equivalence_fingerprint: str = ""
    runtime_replay_fingerprint: str = ""


class RuntimeGovernanceDecisionReport(BaseTransportArtifact):
    promotion_eligible: bool = False
    runtime_promotion_gate: RuntimePromotionGate
    runtime_inputs: RuntimeInputs = Field(default_factory=RuntimeInputs)
    fail_closed_reasons: list[str] = Field(default_factory=list)


class ConfidenceDrivers(BaseModel):
    model_config = ConfigDict(extra="allow")

    approved_transformations: int = 0
    blocked_transformations: int = 0
    compile_classification: str = ""
    missing_include_count: int = 0
    runtime_sensitive_region_count: int = 0
    symbol_lineage_consistent: bool = False


class ConfidenceSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    confidence_delta_from_threshold: float = 0.0
    confidence_threshold: float = 0.0


class TransformationConfidenceReport(BaseTransportArtifact):
    runtime_confidence: float = 0.0
    drivers: ConfidenceDrivers = Field(default_factory=ConfidenceDrivers)
    summary: ConfidenceSummary = Field(default_factory=ConfidenceSummary)


RuntimeArtifactContract = (
    RuntimeEquivalenceReport
    | HardwareTruthGraphReport
    | ReplayConsistencyReport
    | RuntimeGovernanceDecisionReport
    | TransformationConfidenceReport
)

_MODEL_BY_ARTIFACT: dict[RuntimeArtifactType, type[RuntimeArtifactContract]] = {
    "runtime_equivalence_report": RuntimeEquivalenceReport,
    "hardware_truth_graph": HardwareTruthGraphReport,
    "replay_consistency_report": ReplayConsistencyReport,
    "runtime_governance_decision": RuntimeGovernanceDecisionReport,
    "transformation_confidence_report": TransformationConfidenceReport,
}


class RuntimeArtifactIndexItem(BaseModel):
    metadata: RuntimeArtifactMetadata
    validation: ContractValidation


class RuntimeArtifactReadResponse(BaseModel):
    metadata: RuntimeArtifactMetadata
    validation: ContractValidation
    contract: RuntimeArtifactContract | None = None


class RuntimeArtifactPagination(BaseModel):
    page: int
    limit: int
    total: int


class RuntimeArtifactIndexResponse(BaseModel):
    artifacts: list[RuntimeArtifactIndexItem]
    pagination: RuntimeArtifactPagination
    generated_at: str


class RuntimeEnvironmentStatus(BaseModel):
    repo_root: str
    transport_root: str
    transport_root_exists: bool
    evidence_root: str
    evidence_root_exists: bool
    replay_store_path: str
    replay_store_exists: bool
    artifact_presence: dict[str, bool]
    classification: Literal["PASS", "FAIL_CLOSED"]
    fail_closed_reasons: list[str] = Field(default_factory=list)
    generated_at: str


@dataclass(slots=True)
class ParsedRuntimeArtifact:
    metadata: RuntimeArtifactMetadata
    validation: ContractValidation
    contract: RuntimeArtifactContract | None


def _to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _safe_iso(raw: str) -> bool:
    if not raw:
        return False
    try:
        datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return True
    except Exception:
        return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _search_replay_fingerprint(value: Any) -> str:
    if isinstance(value, dict):
        for key in (
            "runtime_replay_fingerprint",
            "replay_fingerprint",
            "lineage_fingerprint",
        ):
            raw = value.get(key)
            if isinstance(raw, str) and raw:
                return raw
        for nested in value.values():
            result = _search_replay_fingerprint(nested)
            if result:
                return result
    elif isinstance(value, list):
        for nested in value:
            result = _search_replay_fingerprint(nested)
            if result:
                return result
    return ""


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    env_root = os.environ.get("AURA_REPO_ROOT", "").strip()
    env_transport = os.environ.get("AURA_TRANSPORT_ARTIFACT_ROOT", "").strip()

    if env_root:
        candidates.append(Path(env_root).resolve())
    if env_transport:
        candidates.append(Path(env_transport).resolve())

    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    candidates.extend(cwd.parents)

    here = Path(__file__).resolve()
    candidates.append(here.parent)
    candidates.extend(here.parents)
    return candidates


def _normalize_root(candidate: Path) -> Path:
    transport_path = (candidate / "docs" / "operations" / "transport").resolve()
    if transport_path.exists():
        return candidate.resolve()

    if (
        candidate.name == "transport"
        and candidate.parent.name == "operations"
        and candidate.parent.parent.name == "docs"
    ):
        return candidate.parent.parent.parent.resolve()
    return candidate.resolve()


def resolve_repo_root() -> Path:
    env_root = os.environ.get("AURA_REPO_ROOT", "").strip()
    if env_root:
        root = Path(env_root).resolve()
        if root.exists():
            return root

    env_transport = os.environ.get("AURA_TRANSPORT_ARTIFACT_ROOT", "").strip()
    if env_transport:
        candidate = _normalize_root(Path(env_transport).resolve())
        if candidate.exists():
            return candidate

    normalized: list[Path] = []
    seen: set[str] = set()
    for candidate in _candidate_roots():
        root = _normalize_root(candidate)
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(root)

    for root in normalized:
        if (root / "docs" / "operations" / "transport").exists():
            return root

    for root in normalized:
        if (root / "evidence").exists():
            return root

    return Path.cwd().resolve()


def transport_artifact_root(repo_root: Path | None = None) -> Path:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    return (root / "docs" / "operations" / "transport").resolve()


def transport_artifact_paths(repo_root: Path | None = None) -> dict[RuntimeArtifactType, Path]:
    base = transport_artifact_root(repo_root)
    return {
        artifact_type: (base / filename).resolve()
        for artifact_type, filename in _RUNTIME_ARTIFACT_FILES.items()
    }


def _base_metadata_for_missing(artifact_type: RuntimeArtifactType, path: Path) -> RuntimeArtifactMetadata:
    return RuntimeArtifactMetadata(
        artifact_type=artifact_type,
        artifact_file=path.name,
        artifact_path=str(path),
        exists=False,
    )


def _contract_specific_checks(
    artifact_type: RuntimeArtifactType,
    payload: RuntimeArtifactContract,
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []

    if not payload.lineage_id:
        issues.append(
            ContractIssue(
                code="missing_lineage_id",
                message="lineage_id missing; replay lineage traceability is reduced.",
                severity="warning",
            )
        )

    if not payload.session_id:
        issues.append(
            ContractIssue(
                code="missing_session_id",
                message="session_id missing; session-scoped replay correlation is reduced.",
                severity="warning",
            )
        )

    if payload.created_at and not _safe_iso(payload.created_at):
        issues.append(
            ContractIssue(
                code="invalid_created_at",
                message="created_at must be an ISO-8601 timestamp.",
                severity="error",
            )
        )

    if payload.deterministic_fingerprint and not _HEX_64_RE.fullmatch(payload.deterministic_fingerprint.lower()):
        issues.append(
            ContractIssue(
                code="invalid_deterministic_fingerprint",
                message="deterministic_fingerprint must be a 64-char lowercase hex string.",
                severity="error",
            )
        )

    execution_fp = payload.runtime_execution_fingerprint
    if not execution_fp.python_version.startswith("3.12."):
        issues.append(
            ContractIssue(
                code="runtime_execution_python_version_mismatch",
                message="runtime_execution_fingerprint.python_version must be Python 3.12.x.",
                severity="error",
            )
        )
    if not execution_fp.execution_container_hash:
        issues.append(
            ContractIssue(
                code="runtime_execution_container_hash_missing",
                message="runtime_execution_fingerprint.execution_container_hash is required.",
                severity="error",
            )
        )
    if not execution_fp.dependency_hashes:
        issues.append(
            ContractIssue(
                code="runtime_execution_dependency_hashes_missing",
                message="runtime_execution_fingerprint.dependency_hashes is required.",
                severity="warning",
            )
        )
    if not _safe_iso(execution_fp.timestamp):
        issues.append(
            ContractIssue(
                code="runtime_execution_timestamp_invalid",
                message="runtime_execution_fingerprint.timestamp must be ISO-8601.",
                severity="error",
            )
        )

    if artifact_type == "hardware_truth_graph" and isinstance(payload, HardwareTruthGraphReport):
        if not payload.nodes:
            issues.append(
                ContractIssue(
                    code="empty_topology_nodes",
                    message="hardware_truth_graph.nodes is empty.",
                    severity="error",
                )
            )
        for section, events in payload.nodes.items():
            last_ts: float | None = None
            for index, event in enumerate(events):
                if event.timestamp_ms is None:
                    continue
                if last_ts is not None and event.timestamp_ms < last_ts:
                    issues.append(
                        ContractIssue(
                            code="non_monotonic_topology_timestamps",
                            message=(
                                "Non-monotonic timestamp in topology section "
                                f"{section} at index={index}."
                            ),
                            severity="error",
                        )
                    )
                    break
                last_ts = event.timestamp_ms

    if artifact_type == "runtime_governance_decision" and isinstance(payload, RuntimeGovernanceDecisionReport):
        if payload.classification == "FAIL_CLOSED" and payload.promotion_eligible:
            issues.append(
                ContractIssue(
                    code="classification_gate_mismatch",
                    message="FAIL_CLOSED governance cannot be promotion_eligible=true.",
                    severity="error",
                )
            )

    if artifact_type == "replay_consistency_report" and isinstance(payload, ReplayConsistencyReport):
        if payload.consistency.replay_drift and payload.classification == "PASS":
            issues.append(
                ContractIssue(
                    code="replay_drift_classification_mismatch",
                    message="replay_drift=true with PASS classification should be reviewed.",
                    severity="warning",
                )
            )

    if artifact_type == "transformation_confidence_report" and isinstance(payload, TransformationConfidenceReport):
        threshold = payload.summary.confidence_threshold
        if threshold and payload.runtime_confidence < threshold and payload.classification != "FAIL_CLOSED":
            issues.append(
                ContractIssue(
                    code="confidence_below_threshold_without_fail_closed",
                    message="Runtime confidence below threshold without FAIL_CLOSED classification.",
                    severity="error",
                )
            )

    return issues


def parse_runtime_artifact(
    artifact_type: RuntimeArtifactType,
    path: Path,
    *,
    strict: bool = True,
) -> ParsedRuntimeArtifact:
    if not path.exists():
        metadata = _base_metadata_for_missing(artifact_type, path)
        validation = ContractValidation(
            valid=False,
            issues=[
                ContractIssue(
                    code="artifact_not_found",
                    message=f"Artifact missing: {path}",
                    severity="error",
                )
            ],
        )
        return ParsedRuntimeArtifact(metadata=metadata, validation=validation, contract=None)

    stat = path.stat()
    metadata = RuntimeArtifactMetadata(
        artifact_type=artifact_type,
        artifact_file=path.name,
        artifact_path=str(path),
        exists=True,
        size_bytes=int(stat.st_size),
        modified_at=_to_iso(stat.st_mtime),
    )

    issues: list[ContractIssue] = []
    payload_data: Any = None

    try:
        payload_data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(
            ContractIssue(
                code="artifact_json_decode_failed",
                message=f"JSON decode failure: {exc}",
                severity="error",
            )
        )

    contract: RuntimeArtifactContract | None = None
    if payload_data is not None:
        model_cls = _MODEL_BY_ARTIFACT[artifact_type]
        try:
            contract = model_cls.model_validate(payload_data)
        except ValidationError as exc:
            for entry in exc.errors():
                location = ".".join(str(part) for part in entry.get("loc", [])) or "root"
                issues.append(
                    ContractIssue(
                        code="contract_validation_error",
                        message=f"{location}: {entry.get('msg', 'invalid')}",
                        severity="error",
                    )
                )

    if contract is not None:
        metadata.report_name = contract.report_name
        metadata.schema_version = contract.schema_version
        metadata.target_id = contract.target_id
        metadata.classification = contract.classification
        metadata.lineage_id = contract.lineage_id
        metadata.session_id = contract.session_id
        metadata.created_at = contract.created_at
        metadata.advisory_only_behavior = contract.advisory_only_behavior
        metadata.runtime_truth_precedence = contract.runtime_truth_precedence
        metadata.deterministic_fingerprint = contract.deterministic_fingerprint
        metadata.runtime_execution_python_version = contract.runtime_execution_fingerprint.python_version
        metadata.runtime_execution_container_hash = (
            contract.runtime_execution_fingerprint.execution_container_hash
        )
        metadata.runtime_execution_parser_version = contract.runtime_execution_fingerprint.parser_version
        metadata.evidence_references = list(contract.evidence_references)
        metadata.replay_fingerprint = _search_replay_fingerprint(contract.model_dump(mode="python"))

        issues.extend(_contract_specific_checks(artifact_type, contract))

    if strict and contract is None and payload_data is not None and not issues:
        issues.append(
            ContractIssue(
                code="contract_validation_unknown_failure",
                message="Contract parsing failed for unknown reason.",
                severity="error",
            )
        )

    if strict and not metadata.schema_version:
        issues.append(
            ContractIssue(
                code="missing_schema_version",
                message="schema_version missing from artifact payload.",
                severity="error",
            )
        )

    if not metadata.deterministic_fingerprint:
        metadata.deterministic_fingerprint = _sha256_file(path)
        issues.append(
            ContractIssue(
                code="derived_deterministic_fingerprint",
                message="deterministic_fingerprint missing; derived from file SHA-256.",
                severity="warning",
            )
        )

    if not metadata.created_at:
        metadata.created_at = metadata.modified_at
        issues.append(
            ContractIssue(
                code="derived_created_at",
                message="created_at missing; derived from filesystem mtime.",
                severity="warning",
            )
        )

    if not metadata.replay_fingerprint:
        metadata.replay_fingerprint = metadata.deterministic_fingerprint
        issues.append(
            ContractIssue(
                code="derived_replay_fingerprint",
                message="No replay fingerprint found; using deterministic fingerprint as fallback.",
                severity="warning",
            )
        )

    validation = ContractValidation(valid=not any(i.severity == "error" for i in issues), issues=issues)
    return ParsedRuntimeArtifact(metadata=metadata, validation=validation, contract=contract)


def collect_runtime_artifacts(
    *,
    repo_root: Path | None = None,
    strict: bool = True,
) -> list[ParsedRuntimeArtifact]:
    items: list[ParsedRuntimeArtifact] = []
    for artifact_type, artifact_path in transport_artifact_paths(repo_root).items():
        items.append(parse_runtime_artifact(artifact_type, artifact_path, strict=strict))
    return items


def read_runtime_artifact(
    artifact_type: RuntimeArtifactType,
    *,
    repo_root: Path | None = None,
    strict: bool = True,
) -> ParsedRuntimeArtifact:
    path = transport_artifact_paths(repo_root)[artifact_type]
    return parse_runtime_artifact(artifact_type, path, strict=strict)


def runtime_lineage_consistency(
    parsed_items: list[ParsedRuntimeArtifact],
) -> ContractValidation:
    """Cross-artifact lineage/replay integrity checks for governance gating."""

    issues: list[ContractIssue] = []
    valid_items = [item for item in parsed_items if item.validation.valid and item.contract is not None]

    if not valid_items:
        return ContractValidation(
            valid=False,
            issues=[
                ContractIssue(
                    code="no_valid_runtime_artifacts",
                    message="No valid runtime artifacts were available for lineage consistency checks.",
                    severity="error",
                )
            ],
        )

    target_ids = {item.metadata.target_id for item in valid_items if item.metadata.target_id}
    if len(target_ids) > 1:
        issues.append(
            ContractIssue(
                code="target_id_mismatch",
                message=f"Cross-artifact target_id mismatch: {sorted(target_ids)}",
                severity="error",
            )
        )

    session_ids = {item.metadata.session_id for item in valid_items if item.metadata.session_id}
    if len(session_ids) > 1:
        issues.append(
            ContractIssue(
                code="session_id_mismatch",
                message=f"Cross-artifact session_id mismatch: {sorted(session_ids)}",
                severity="warning",
            )
        )

    lineage_ids = {item.metadata.lineage_id for item in valid_items if item.metadata.lineage_id}
    if len(lineage_ids) > 1:
        issues.append(
            ContractIssue(
                code="lineage_id_mismatch",
                message=f"Cross-artifact lineage_id mismatch: {sorted(lineage_ids)}",
                severity="warning",
            )
        )

    replay_fingerprints = {
        item.metadata.replay_fingerprint
        for item in valid_items
        if item.metadata.replay_fingerprint
    }
    if len(replay_fingerprints) > 1:
        issues.append(
            ContractIssue(
                code="replay_fingerprint_drift",
                message="Replay fingerprint differs across runtime artifacts.",
                severity="warning",
            )
        )

    execution_container_hashes = {
        item.metadata.runtime_execution_container_hash
        for item in valid_items
        if item.metadata.runtime_execution_container_hash
    }
    if len(execution_container_hashes) > 1:
        issues.append(
            ContractIssue(
                code="runtime_execution_container_hash_mismatch",
                message="Runtime artifacts were produced by different execution containers.",
                severity="error",
            )
        )

    execution_python_versions = {
        item.metadata.runtime_execution_python_version
        for item in valid_items
        if item.metadata.runtime_execution_python_version
    }
    if len(execution_python_versions) > 1:
        issues.append(
            ContractIssue(
                code="runtime_execution_python_version_mismatch",
                message="Runtime artifacts were produced by different Python versions.",
                severity="error",
            )
        )

    return ContractValidation(valid=not any(issue.severity == "error" for issue in issues), issues=issues)


def runtime_environment_diagnostics(
    *,
    repo_root: Path | None = None,
    sqlite_path: str = "",
) -> RuntimeEnvironmentStatus:
    root = repo_root.resolve() if repo_root else resolve_repo_root()
    transport_root = transport_artifact_root(root)
    evidence_root = (root / "evidence").resolve()
    replay_store = Path(sqlite_path).resolve() if sqlite_path else Path("").resolve()

    artifact_paths = transport_artifact_paths(root)
    artifact_presence = {
        artifact_type: path.exists()
        for artifact_type, path in artifact_paths.items()
    }

    fail_closed_reasons: list[str] = []
    if not transport_root.exists():
        fail_closed_reasons.append("transport_artifact_root_missing")
    missing_artifacts = [name for name, exists in artifact_presence.items() if not exists]
    if missing_artifacts:
        fail_closed_reasons.append(
            f"runtime_artifacts_missing:{','.join(sorted(missing_artifacts))}"
        )
    if not evidence_root.exists():
        fail_closed_reasons.append("runtime_evidence_root_missing")
    if sqlite_path and not replay_store.exists():
        fail_closed_reasons.append("replay_store_unavailable")

    classification: Literal["PASS", "FAIL_CLOSED"] = (
        "PASS" if not fail_closed_reasons else "FAIL_CLOSED"
    )
    return RuntimeEnvironmentStatus(
        repo_root=str(root),
        transport_root=str(transport_root),
        transport_root_exists=transport_root.exists(),
        evidence_root=str(evidence_root),
        evidence_root_exists=evidence_root.exists(),
        replay_store_path=str(replay_store) if sqlite_path else "",
        replay_store_exists=replay_store.exists() if sqlite_path else False,
        artifact_presence=artifact_presence,
        classification=classification,
        fail_closed_reasons=fail_closed_reasons,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
