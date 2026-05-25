"""Runtime cognition artifact endpoints (contract-first, governed, read-only)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aura_sdk.logging.logger import get_logger
from core.contracts.transport_artifact_contracts import (
    ContractIssue,
    ContractValidation,
    HardwareTruthEvent,
    HardwareTruthGraphReport,
    KNOWN_RUNTIME_ARTIFACTS,
    RuntimeArtifactIndexItem,
    RuntimeArtifactIndexResponse,
    RuntimeArtifactMetadata,
    RuntimeArtifactPagination,
    RuntimeArtifactReadResponse,
    RuntimeArtifactType,
    RuntimeEquivalenceDimension,
    RuntimeEquivalenceSummary,
    RuntimeGovernanceDecisionReport,
    TransformationConfidenceReport,
    collect_runtime_artifacts,
    read_runtime_artifact,
    runtime_lineage_consistency,
)
from core.routers.auth import get_current_user

logger = get_logger("core.runtime")
router = APIRouter()


class RuntimeGovernanceSummaryResponse(BaseModel):
    available: bool
    generated_at: str
    classification: str
    promotion_eligible: bool
    confidence_score: float
    confidence_threshold: float
    critical_divergence_count: int
    runtime_sensitive_impact_count: int
    deterministic_replay_ready: bool
    fail_closed_reasons: list[str] = Field(default_factory=list)
    lineage_consistency: ContractValidation
    replay_consistency: dict[str, Any] = Field(default_factory=dict)
    metadata: RuntimeArtifactMetadata | None = None
    references: dict[str, str] = Field(default_factory=dict)


class RuntimeTopologyResponse(BaseModel):
    available: bool
    generated_at: str
    section: str
    sections: list[str] = Field(default_factory=list)
    events: list[HardwareTruthEvent] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    integrity: ContractValidation
    metadata: RuntimeArtifactMetadata | None = None
    pagination: RuntimeArtifactPagination


class RuntimeEquivalenceResponse(BaseModel):
    available: bool
    generated_at: str
    dimensions: list[RuntimeEquivalenceDimension] = Field(default_factory=list)
    summary: RuntimeEquivalenceSummary = Field(default_factory=RuntimeEquivalenceSummary)
    unsafe_regions: list[str] = Field(default_factory=list)
    validation: ContractValidation
    metadata: RuntimeArtifactMetadata | None = None
    pagination: RuntimeArtifactPagination


class RuntimeConfidenceResponse(BaseModel):
    available: bool
    generated_at: str
    classification: str
    runtime_confidence: float
    confidence_threshold: float
    confidence_delta_from_threshold: float
    governance_blocked: bool
    stale_state: bool
    stale_reason: str
    drivers: dict[str, Any] = Field(default_factory=dict)
    validation: ContractValidation
    metadata: RuntimeArtifactMetadata | None = None
    references: dict[str, str] = Field(default_factory=dict)


class RuntimeArtifactsReadQuery(BaseModel):
    artifact_type: RuntimeArtifactType


class RuntimeErrorDetail(BaseModel):
    code: str
    message: str
    classification: str = "FAIL_CLOSED"
    operation: str
    generated_at: str


T = TypeVar("T")


def _paginate(items: list[T], page: int, limit: int) -> tuple[list[T], RuntimeArtifactPagination]:
    total = len(items)
    safe_page = max(1, page)
    safe_limit = max(1, min(limit, 500))
    start = (safe_page - 1) * safe_limit
    end = start + safe_limit
    return items[start:end], RuntimeArtifactPagination(page=safe_page, limit=safe_limit, total=total)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _missing_validation(reason: str) -> ContractValidation:
    return ContractValidation(
        valid=False,
        issues=[ContractIssue(code="runtime_artifact_unavailable", message=reason, severity="error")],
    )


def _runtime_exception(operation: str, exc: Exception) -> HTTPException:
    logger.exception("runtime_endpoint_failure", operation=operation, error=str(exc))
    detail = RuntimeErrorDetail(
        code="runtime_artifact_access_failed",
        message=str(exc),
        operation=operation,
        generated_at=_now_iso(),
    )
    return HTTPException(status_code=503, detail=detail.model_dump(mode="json"))


@router.get("/artifacts/index", response_model=RuntimeArtifactIndexResponse)
async def runtime_artifacts_index(
    page: int = 1,
    limit: int = 20,
    include_invalid: bool = True,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """List governed runtime artifacts under docs/operations/transport."""
    _ = current_user

    try:
        items = collect_runtime_artifacts(strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_artifacts_index", exc) from exc
    if not include_invalid:
        items = [item for item in items if item.validation.valid]

    response_items = [
        RuntimeArtifactIndexItem(metadata=item.metadata, validation=item.validation)
        for item in items
    ]
    window, pagination = _paginate(response_items, page=page, limit=limit)
    logger.info(
        "runtime_artifacts_indexed",
        total=len(response_items),
        returned=len(window),
        include_invalid=include_invalid,
        strict_validation=strict_validation,
    )
    invalid_count = len([item for item in response_items if not item.validation.valid])
    if invalid_count:
        logger.warning("runtime_artifacts_contract_validation_failed", invalid_count=invalid_count)
    return RuntimeArtifactIndexResponse(
        artifacts=window,
        pagination=pagination,
        generated_at=_now_iso(),
    )


@router.get("/artifacts/read", response_model=RuntimeArtifactReadResponse)
async def runtime_artifacts_read(
    artifact_type: RuntimeArtifactType,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Read one runtime artifact using strict typed contracts."""
    _ = current_user

    try:
        artifact = read_runtime_artifact(artifact_type, strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_artifacts_read", exc) from exc
    logger.info(
        "runtime_artifact_read",
        artifact_type=artifact_type,
        valid=artifact.validation.valid,
        exists=artifact.metadata.exists,
    )
    if not artifact.validation.valid:
        logger.warning(
            "runtime_artifact_contract_mismatch",
            artifact_type=artifact_type,
            issues=[issue.code for issue in artifact.validation.issues],
        )
    return RuntimeArtifactReadResponse(
        metadata=artifact.metadata,
        validation=artifact.validation,
        contract=artifact.contract,
    )


@router.get("/governance/summary", response_model=RuntimeGovernanceSummaryResponse)
async def runtime_governance_summary(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Runtime-governance summary correlated with replay consistency and lineage."""
    _ = current_user

    try:
        parsed = collect_runtime_artifacts(strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_governance_summary", exc) from exc
    parsed_by_type = {item.metadata.artifact_type: item for item in parsed}

    governance_item = parsed_by_type.get("runtime_governance_decision")
    replay_item = parsed_by_type.get("replay_consistency_report")
    lineage_check = runtime_lineage_consistency(parsed)

    if governance_item is None or governance_item.contract is None:
        logger.warning("runtime_governance_summary_missing_artifact")
        return RuntimeGovernanceSummaryResponse(
            available=False,
            generated_at=_now_iso(),
            classification="FAIL_CLOSED",
            promotion_eligible=False,
            confidence_score=0.0,
            confidence_threshold=1.0,
            critical_divergence_count=0,
            runtime_sensitive_impact_count=0,
            deterministic_replay_ready=False,
            fail_closed_reasons=["runtime_governance_decision_missing"],
            lineage_consistency=lineage_check,
            replay_consistency={},
            metadata=governance_item.metadata if governance_item else None,
            references={},
        )

    governance = governance_item.contract
    assert isinstance(governance, RuntimeGovernanceDecisionReport)

    replay_payload: dict[str, Any] = {}
    if replay_item and replay_item.contract is not None:
        replay_payload = replay_item.contract.model_dump(mode="json")

    fail_closed_reasons = list(governance.fail_closed_reasons)
    fail_closed_reasons.extend(issue.code for issue in governance_item.validation.errors)
    if not lineage_check.valid:
        fail_closed_reasons.append("lineage_consistency_failed")

    promotion_eligible = (
        governance.promotion_eligible
        and governance_item.validation.valid
        and lineage_check.valid
    )

    if governance.classification == "FAIL_CLOSED":
        promotion_eligible = False
        logger.warning(
            "runtime_governance_fail_closed",
            fail_closed_reasons=fail_closed_reasons,
        )

    return RuntimeGovernanceSummaryResponse(
        available=True,
        generated_at=_now_iso(),
        classification=governance.classification,
        promotion_eligible=promotion_eligible,
        confidence_score=governance.runtime_promotion_gate.confidence_score,
        confidence_threshold=governance.runtime_promotion_gate.confidence_threshold,
        critical_divergence_count=governance.runtime_promotion_gate.critical_divergence_count,
        runtime_sensitive_impact_count=governance.runtime_promotion_gate.runtime_sensitive_impact_count,
        deterministic_replay_ready=governance.runtime_promotion_gate.deterministic_replay_ready,
        fail_closed_reasons=sorted(set(fail_closed_reasons)),
        lineage_consistency=lineage_check,
        replay_consistency=replay_payload,
        metadata=governance_item.metadata,
        references={
            "governance": governance_item.metadata.artifact_path,
            "replay": replay_item.metadata.artifact_path if replay_item else "",
        },
    )


@router.get("/topology", response_model=RuntimeTopologyResponse)
async def runtime_topology(
    section: str = "",
    page: int = 1,
    limit: int = 60,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Topology-facing normalized view over hardware_truth_graph."""
    _ = current_user

    try:
        item = read_runtime_artifact("hardware_truth_graph", strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_topology", exc) from exc
    if item.contract is None:
        logger.warning("runtime_topology_unavailable", issues=[issue.code for issue in item.validation.issues])
        return RuntimeTopologyResponse(
            available=False,
            generated_at=_now_iso(),
            section="",
            sections=[],
            events=[],
            summary={},
            integrity=item.validation,
            metadata=item.metadata,
            pagination=RuntimeArtifactPagination(page=1, limit=limit, total=0),
        )

    report = item.contract
    assert isinstance(report, HardwareTruthGraphReport)

    sections = sorted(report.nodes.keys())
    if not sections:
        logger.warning("runtime_topology_no_sections")
        return RuntimeTopologyResponse(
            available=False,
            generated_at=_now_iso(),
            section="",
            sections=[],
            events=[],
            summary=report.summary.model_dump(mode="json"),
            integrity=_missing_validation("hardware_truth_graph contains no topology sections"),
            metadata=item.metadata,
            pagination=RuntimeArtifactPagination(page=1, limit=limit, total=0),
        )

    active_section = section.strip() or sections[0]
    if active_section not in report.nodes:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown topology section: {active_section}",
        )

    section_events = report.nodes.get(active_section, [])
    window, pagination = _paginate(section_events, page=page, limit=limit)

    return RuntimeTopologyResponse(
        available=item.validation.valid,
        generated_at=_now_iso(),
        section=active_section,
        sections=sections,
        events=window,
        summary=report.summary.model_dump(mode="json"),
        integrity=item.validation,
        metadata=item.metadata,
        pagination=pagination,
    )


@router.get("/equivalence", response_model=RuntimeEquivalenceResponse)
async def runtime_equivalence(
    critical_only: bool = False,
    page: int = 1,
    limit: int = 50,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Typed runtime equivalence comparison with unsafe-region extraction."""
    _ = current_user

    try:
        item = read_runtime_artifact("runtime_equivalence_report", strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_equivalence", exc) from exc
    if item.contract is None:
        logger.warning("runtime_equivalence_unavailable", issues=[issue.code for issue in item.validation.issues])
        return RuntimeEquivalenceResponse(
            available=False,
            generated_at=_now_iso(),
            dimensions=[],
            summary=RuntimeEquivalenceSummary(),
            unsafe_regions=[],
            validation=item.validation,
            metadata=item.metadata,
            pagination=RuntimeArtifactPagination(page=1, limit=limit, total=0),
        )

    report = item.contract
    dimensions = report.dimensions
    if critical_only:
        dimensions = [dimension for dimension in dimensions if dimension.critical]

    window, pagination = _paginate(dimensions, page=page, limit=limit)
    unsafe_regions = [
        dimension.dimension
        for dimension in report.dimensions
        if dimension.critical and dimension.classification != "MATCHED"
    ]

    return RuntimeEquivalenceResponse(
        available=item.validation.valid,
        generated_at=_now_iso(),
        dimensions=window,
        summary=report.summary,
        unsafe_regions=unsafe_regions,
        validation=item.validation,
        metadata=item.metadata,
        pagination=pagination,
    )


@router.get("/confidence", response_model=RuntimeConfidenceResponse)
async def runtime_confidence(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Typed confidence model with governance-aware fail-closed indicators."""
    _ = current_user

    try:
        confidence_item = read_runtime_artifact("transformation_confidence_report", strict=strict_validation)
        governance_item = read_runtime_artifact("runtime_governance_decision", strict=strict_validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _runtime_exception("runtime_confidence", exc) from exc

    if confidence_item.contract is None:
        logger.warning(
            "runtime_confidence_unavailable",
            issues=[issue.code for issue in confidence_item.validation.issues],
        )
        return RuntimeConfidenceResponse(
            available=False,
            generated_at=_now_iso(),
            classification="FAIL_CLOSED",
            runtime_confidence=0.0,
            confidence_threshold=1.0,
            confidence_delta_from_threshold=-1.0,
            governance_blocked=True,
            stale_state=True,
            stale_reason="transformation_confidence_report_missing",
            drivers={},
            validation=confidence_item.validation,
            metadata=confidence_item.metadata,
            references={},
        )

    confidence = confidence_item.contract
    assert isinstance(confidence, TransformationConfidenceReport)

    governance_classification = governance_item.metadata.classification
    governance_blocked = governance_classification == "FAIL_CLOSED"

    stale_state = False
    stale_reason = ""
    if confidence_item.metadata.created_at:
        try:
            created = datetime.fromisoformat(
                confidence_item.metadata.created_at.replace("Z", "+00:00")
            )
            age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
            if age_hours > 24:
                stale_state = True
                stale_reason = f"confidence artifact older than 24h ({age_hours:.1f}h)"
        except Exception:
            stale_state = True
            stale_reason = "invalid confidence created_at timestamp"

    validation_issues = list(confidence_item.validation.issues)
    if governance_blocked:
        validation_issues.append(
            ContractIssue(
                code="governance_fail_closed",
                message="Runtime governance is FAIL_CLOSED; confidence cannot promote runtime transitions.",
                severity="error",
            )
        )

    merged_validation = ContractValidation(
        valid=not any(issue.severity == "error" for issue in validation_issues),
        issues=validation_issues,
    )
    if not merged_validation.valid:
        logger.warning(
            "runtime_confidence_contract_validation_failed",
            issues=[issue.code for issue in merged_validation.issues],
        )

    return RuntimeConfidenceResponse(
        available=confidence_item.validation.valid,
        generated_at=_now_iso(),
        classification=confidence.classification,
        runtime_confidence=confidence.runtime_confidence,
        confidence_threshold=confidence.summary.confidence_threshold,
        confidence_delta_from_threshold=confidence.summary.confidence_delta_from_threshold,
        governance_blocked=governance_blocked,
        stale_state=stale_state,
        stale_reason=stale_reason,
        drivers=confidence.drivers.model_dump(mode="json"),
        validation=merged_validation,
        metadata=confidence_item.metadata,
        references={
            "confidence": confidence_item.metadata.artifact_path,
            "governance": governance_item.metadata.artifact_path,
        },
    )
