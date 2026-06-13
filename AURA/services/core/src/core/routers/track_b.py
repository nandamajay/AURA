"""Track-B artifact visibility endpoints (read-only, deterministic, fail-closed)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aura_sdk.logging.logger import get_logger
from core.contracts.track_b_artifact_contracts import (
    TrackBArtifactIndexResponse,
    TrackBArtifactPagination,
    TrackBArtifactReadResponse,
    TrackBAuditRecord,
    TrackBLineageResponse,
    TrackBLearningRecord,
    TrackBReleaseRecord,
    artifact_by_id,
    artifact_index_response,
    build_track_b_lineage,
    collect_learning_patterns,
    collect_learning_records,
    collect_track_b_audits,
    collect_track_b_releases,
    filter_track_b_artifacts,
    readiness_history,
    search_track_b,
    summarize_conflicts,
    summarize_dependency_coverage,
    summarize_equivalence,
    summarize_readiness,
    track_b_overview,
)
from core.contracts.transport_artifact_contracts import ContractValidation
from core.routers.auth import get_current_user

logger = get_logger("core.track_b")
router = APIRouter()

T = TypeVar("T")


class TrackBErrorDetail(BaseModel):
    code: str
    message: str
    classification: str = "FAIL_CLOSED"
    operation: str
    generated_at: str


class TrackBAuditIndexResponse(BaseModel):
    audits: list[TrackBAuditRecord]
    generated_at: str
    pagination: TrackBArtifactPagination


class TrackBAuditReadResponse(BaseModel):
    audit: TrackBAuditRecord
    generated_at: str


class TrackBReleaseIndexResponse(BaseModel):
    releases: list[TrackBReleaseRecord]
    generated_at: str
    pagination: TrackBArtifactPagination


class TrackBReleaseReadResponse(BaseModel):
    release: TrackBReleaseRecord
    generated_at: str


class TrackBLearningIndexResponse(BaseModel):
    learning_entries: list[TrackBLearningRecord]
    generated_at: str
    pagination: TrackBArtifactPagination


class TrackBLearningPatternsResponse(BaseModel):
    payload: dict[str, Any]
    generated_at: str


class TrackBDashboardSummaryResponse(BaseModel):
    payload: dict[str, Any]
    generated_at: str
    validation: ContractValidation


class TrackBReleaseSummaryResponse(BaseModel):
    payload: dict[str, Any]
    generated_at: str
    validation: ContractValidation


class TrackBSearchResponse(BaseModel):
    query: str
    kind: str
    total: int
    results: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paginate(items: list[T], *, page: int, limit: int) -> tuple[list[T], TrackBArtifactPagination]:
    total = len(items)
    safe_page = max(1, page)
    safe_limit = max(1, min(limit, 500))
    start = (safe_page - 1) * safe_limit
    end = start + safe_limit
    return items[start:end], TrackBArtifactPagination(page=safe_page, limit=safe_limit, total=total)


def _track_b_exception(operation: str, exc: Exception) -> HTTPException:
    logger.exception("track_b_endpoint_failure", operation=operation, error=str(exc))
    detail = TrackBErrorDetail(
        code="track_b_visibility_failure",
        message=str(exc),
        operation=operation,
        generated_at=_now_iso(),
    )
    return HTTPException(status_code=503, detail=detail.model_dump(mode="json"))


def _normalize_summary(payload: dict[str, Any], validation: ContractValidation) -> dict[str, Any]:
    summary = dict(payload)
    if not validation.valid:
        reasons = list(summary.get("fail_closed_reasons", []))
        reasons.extend(issue.code for issue in validation.errors)
        summary["classification"] = "FAIL_CLOSED"
        summary["fail_closed_reasons"] = sorted(set(str(reason) for reason in reasons if str(reason)))
    return summary


@router.get("/artifacts/index", response_model=TrackBArtifactIndexResponse)
async def track_b_artifacts_index(
    page: int = 1,
    limit: int = 20,
    include_invalid: bool = True,
    strict_validation: bool = True,
    artifact_name: str = "",
    classification: str = "",
    stage_id: str = "",
    decision_state: str = "",
    readiness_status: str = "",
    task_id: str = "",
    component: str = "",
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """List M8 Track-B artifacts with optional deterministic filters."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        records = filter_track_b_artifacts(
            overview["records"],
            artifact_name=artifact_name,
            classification=classification,
            stage_id=stage_id,
            decision_state=decision_state,
            readiness_status=readiness_status,
            task_id=task_id,
            component=component,
        )
        if not include_invalid:
            records = [record for record in records if record.validation.valid]
        return artifact_index_response(
            records=records,
            validation=overview["validation"],
            page=page,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_artifacts_index", exc) from exc


@router.get("/artifacts/{artifact_id}", response_model=TrackBArtifactReadResponse)
async def track_b_artifacts_read(
    artifact_id: str,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Read one M8 Track-B artifact by deterministic artifact_id."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        record = artifact_by_id(overview["records"], artifact_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=TrackBErrorDetail(
                    code="track_b_artifact_not_found",
                    message=f"artifact_id not found: {artifact_id}",
                    operation="track_b_artifacts_read",
                    generated_at=_now_iso(),
                ).model_dump(mode="json"),
            )
        return TrackBArtifactReadResponse(artifact=record, generated_at=_now_iso())
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_artifacts_read", exc) from exc


@router.get("/lineage", response_model=TrackBLineageResponse)
async def track_b_lineage(
    component_query: str = "",
    reverse_node_id: str = "",
    include_invalid: bool = True,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Build deterministic Track-B lineage graph with forward/reverse navigation."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        records = overview["records"]
        if not include_invalid:
            records = [record for record in records if record.validation.valid]
        return build_track_b_lineage(
            records,
            component_query=component_query,
            reverse_node_id=reverse_node_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_lineage", exc) from exc


@router.get("/audits/index", response_model=TrackBAuditIndexResponse)
async def track_b_audits_index(
    page: int = 1,
    limit: int = 20,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """List Track-B audit and validation reports."""
    _ = current_user
    try:
        audits = collect_track_b_audits()
        window, pagination = _paginate(audits, page=page, limit=limit)
        return TrackBAuditIndexResponse(audits=window, generated_at=_now_iso(), pagination=pagination)
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_audits_index", exc) from exc


@router.get("/audits/{audit_id}", response_model=TrackBAuditReadResponse)
async def track_b_audits_read(
    audit_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Read one audit by id."""
    _ = current_user
    try:
        for audit in collect_track_b_audits():
            if audit.audit_id == audit_id:
                return TrackBAuditReadResponse(audit=audit, generated_at=_now_iso())
        raise HTTPException(
            status_code=404,
            detail=TrackBErrorDetail(
                code="track_b_audit_not_found",
                message=f"audit_id not found: {audit_id}",
                operation="track_b_audits_read",
                generated_at=_now_iso(),
            ).model_dump(mode="json"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_audits_read", exc) from exc


@router.get("/releases/index", response_model=TrackBReleaseIndexResponse)
async def track_b_releases_index(
    page: int = 1,
    limit: int = 20,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """List Track-B release records linked to frozen schema/audit state."""
    _ = current_user
    try:
        releases = collect_track_b_releases()
        window, pagination = _paginate(releases, page=page, limit=limit)
        return TrackBReleaseIndexResponse(releases=window, generated_at=_now_iso(), pagination=pagination)
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_releases_index", exc) from exc


@router.get("/releases/{release_tag}", response_model=TrackBReleaseReadResponse)
async def track_b_releases_read(
    release_tag: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Read one release record by release tag."""
    _ = current_user
    try:
        for release in collect_track_b_releases():
            if release.release_tag == release_tag:
                return TrackBReleaseReadResponse(release=release, generated_at=_now_iso())
        raise HTTPException(
            status_code=404,
            detail=TrackBErrorDetail(
                code="track_b_release_not_found",
                message=f"release_tag not found: {release_tag}",
                operation="track_b_releases_read",
                generated_at=_now_iso(),
            ).model_dump(mode="json"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_releases_read", exc) from exc


@router.get("/dashboard/release-summary", response_model=TrackBReleaseSummaryResponse)
async def track_b_dashboard_release_summary(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Release summary widget payload for M8 visibility center."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        releases = overview["releases"]
        audits = overview["audits"]
        head = releases[0] if releases else None
        payload: dict[str, Any] = {
            "classification": "PASS" if overview["validation"].valid else "FAIL_CLOSED",
            "release_tag": head.release_tag if head else "",
            "commit_sha": head.commit_sha if head else "",
            "schema_version": head.schema_version if head else "",
            "schema_status": head.schema_status if head else "MISSING",
            "audit_status": head.audit_status if head else "MISSING",
            "audit_count": len(audits),
            "release_count": len(releases),
            "artifact_count": len(overview["records"]),
            "fail_closed_reasons": [issue.code for issue in overview["validation"].errors],
        }
        return TrackBReleaseSummaryResponse(
            payload=payload,
            generated_at=_now_iso(),
            validation=overview["validation"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_release_summary", exc) from exc


@router.get("/dashboard/readiness", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_readiness(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Readiness widget payload for M8 visibility center."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = summarize_readiness(overview["records"])
        dependency = summarize_dependency_coverage(overview["records"])
        conflicts = summarize_conflicts(overview["records"])

        coverage = dependency.get("coverage", {}) if isinstance(dependency, dict) else {}
        resolved_total = 0
        observed_total = 0
        for item in coverage.values():
            if isinstance(item, dict):
                resolved_total += int(item.get("resolved") or 0)
                observed_total += int(item.get("total") or 0)
        payload["dependency_coverage_percent"] = round((resolved_total / observed_total) * 100.0, 2) if observed_total else 0.0
        payload["open_conflict_count"] = int(conflicts.get("open_conflicts") or 0)
        payload["resolved_conflict_count"] = int(conflicts.get("resolved_conflicts") or 0)
        payload["audit_health"] = payload.get("audit_status", "UNKNOWN")
        payload["release_health"] = payload.get("release_status", "UNKNOWN")
        payload = _normalize_summary(payload, overview["validation"])
        return TrackBDashboardSummaryResponse(payload=payload, generated_at=_now_iso(), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_readiness", exc) from exc


@router.get("/dashboard/readiness-history", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_readiness_history(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Readiness trend/history payload for M8 visibility center."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = {
            "classification": "PASS" if overview["validation"].valid else "FAIL_CLOSED",
            "history": readiness_history(overview["records"]),
            "fail_closed_reasons": [issue.code for issue in overview["validation"].errors],
        }
        return TrackBDashboardSummaryResponse(payload=payload, generated_at=_now_iso(), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_readiness_history", exc) from exc


@router.get("/dashboard/dependency-coverage", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_dependency_coverage(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Dependency coverage widget payload (DT/Kconfig/Codec/SoundWire/DSP Service)."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = _normalize_summary(summarize_dependency_coverage(overview["records"]), overview["validation"])
        return TrackBDashboardSummaryResponse(payload=payload, generated_at=_now_iso(), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_dependency_coverage", exc) from exc


@router.get("/dashboard/conflicts", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_conflicts(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Conflict summary widget payload."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = _normalize_summary(summarize_conflicts(overview["records"]), overview["validation"])
        return TrackBDashboardSummaryResponse(payload=payload, generated_at=_now_iso(), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_conflicts", exc) from exc


@router.get("/dashboard/equivalence", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_equivalence(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Equivalence-state summary widget payload."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = _normalize_summary(summarize_equivalence(overview["records"]), overview["validation"])
        return TrackBDashboardSummaryResponse(payload=payload, generated_at=_now_iso(), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_equivalence", exc) from exc


@router.get("/dashboard/audit-history", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_audit_history(
    limit: int = 50,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Audit history widget payload."""
    _ = current_user
    try:
        audits = collect_track_b_audits()
        safe_limit = max(1, min(limit, 500))
        payload = {
            "classification": "PASS",
            "generated_at": _now_iso(),
            "total": len(audits),
            "audits": [audit.model_dump(mode="json") for audit in audits[:safe_limit]],
        }
        return TrackBDashboardSummaryResponse(
            payload=payload,
            generated_at=_now_iso(),
            validation=ContractValidation(valid=True, issues=[]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_audit_history", exc) from exc


@router.get("/dashboard/release-history", response_model=TrackBDashboardSummaryResponse)
async def track_b_dashboard_release_history(
    limit: int = 50,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Release history widget payload."""
    _ = current_user
    try:
        releases = collect_track_b_releases()
        safe_limit = max(1, min(limit, 500))
        payload = {
            "classification": "PASS",
            "generated_at": _now_iso(),
            "total": len(releases),
            "releases": [release.model_dump(mode="json") for release in releases[:safe_limit]],
        }
        return TrackBDashboardSummaryResponse(
            payload=payload,
            generated_at=_now_iso(),
            validation=ContractValidation(valid=True, issues=[]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_dashboard_release_history", exc) from exc


@router.get("/learning/index", response_model=TrackBLearningIndexResponse)
async def track_b_learning_index(
    page: int = 1,
    limit: int = 50,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Learning-center ingestion index derived from artifacts/reports."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        entries = collect_learning_records(overview["records"])
        window, pagination = _paginate(entries, page=page, limit=limit)
        return TrackBLearningIndexResponse(
            learning_entries=window,
            generated_at=_now_iso(),
            pagination=pagination,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_learning_index", exc) from exc


@router.get("/learning/patterns", response_model=TrackBLearningPatternsResponse)
async def track_b_learning_patterns(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Learning pattern summary over defects/conflicts/dependencies/readiness."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = _normalize_summary(collect_learning_patterns(overview["records"]), overview["validation"])
        return TrackBLearningPatternsResponse(payload=payload, generated_at=_now_iso())
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_learning_patterns", exc) from exc


@router.get("/search", response_model=TrackBSearchResponse)
async def track_b_search(
    q: str = "",
    kind: str = "",
    limit: int = 100,
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Search artifacts/audits/releases/learning entries for Track-B discovery."""
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        results = search_track_b(
            records=overview["records"],
            learning_records=overview["learning"],
            audits=overview["audits"],
            releases=overview["releases"],
            query=q,
            kind=kind,
            limit=limit,
        )
        return TrackBSearchResponse(
            query=q,
            kind=kind,
            total=len(results),
            results=results,
            generated_at=_now_iso(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _track_b_exception("track_b_search", exc) from exc
