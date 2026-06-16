"""Track-B intelligence endpoints (M10, additive, deterministic, read-only)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aura_sdk.logging.logger import get_logger
from core.contracts.track_b_intelligence_contracts import (
    build_cross_release_trends,
    build_executive_dashboard,
    build_learning_intelligence,
    build_readiness_forecast,
    build_recommendations,
    mine_patterns,
    track_b_intelligence_overview,
)
from core.contracts.track_b_artifact_contracts import track_b_overview
from core.contracts.transport_artifact_contracts import ContractValidation
from core.routers.auth import get_current_user

logger = get_logger("core.track_b_intelligence")
router = APIRouter()


class TrackBIntelErrorDetail(BaseModel):
    code: str
    message: str
    classification: str = "FAIL_CLOSED"
    operation: str
    generated_at: str


class TrackBIntelResponse(BaseModel):
    payload: dict[str, Any]
    generated_at: str
    validation: ContractValidation


def _intel_exception(operation: str, exc: Exception) -> HTTPException:
    logger.exception("track_b_intelligence_failure", operation=operation, error=str(exc))
    detail = TrackBIntelErrorDetail(
        code="track_b_intelligence_failure",
        message=str(exc),
        operation=operation,
        generated_at="",
    )
    return HTTPException(status_code=503, detail=detail.model_dump(mode="json"))


@router.get("/overview", response_model=TrackBIntelResponse)
async def track_b_intel_overview(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        payload = track_b_intelligence_overview(strict=strict_validation)
        validation = payload.get("validation") if isinstance(payload, dict) else None
        if not isinstance(validation, ContractValidation):
            validation = ContractValidation(valid=True, issues=[])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=validation)
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_overview", exc) from exc


@router.get("/trends", response_model=TrackBIntelResponse)
async def track_b_intel_trends(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = build_cross_release_trends(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_trends", exc) from exc


@router.get("/patterns", response_model=TrackBIntelResponse)
async def track_b_intel_patterns(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = mine_patterns(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_patterns", exc) from exc


@router.get("/recommendations", response_model=TrackBIntelResponse)
async def track_b_intel_recommendations(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = build_recommendations(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_recommendations", exc) from exc


@router.get("/learning", response_model=TrackBIntelResponse)
async def track_b_intel_learning(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = build_learning_intelligence(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_learning", exc) from exc


@router.get("/executive", response_model=TrackBIntelResponse)
async def track_b_intel_executive(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = build_executive_dashboard(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_executive", exc) from exc


@router.get("/forecast", response_model=TrackBIntelResponse)
async def track_b_intel_forecast(
    strict_validation: bool = True,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    _ = current_user
    try:
        overview = track_b_overview(strict=strict_validation)
        payload = build_readiness_forecast(overview["records"])
        return TrackBIntelResponse(payload=payload, generated_at=str(payload.get("generated_at") or ""), validation=overview["validation"])
    except HTTPException:
        raise
    except Exception as exc:
        raise _intel_exception("track_b_intel_forecast", exc) from exc
