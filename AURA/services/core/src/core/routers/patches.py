"""Patch lifecycle endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.patch import Patch, PatchStatus
from core.routers.auth import get_current_user

logger = get_logger("core.patches")
router = APIRouter()


@router.get("/")
async def list_patches(
    status: str | None = None,
    subsystem: str | None = None,
    page: int = 1,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List patches with optional filtering."""
    return {
        "patches": [],
        "page": page,
        "limit": limit,
        "total": 0,
    }


@router.get("/{patch_id}")
async def get_patch(patch_id: str, current_user: dict = Depends(get_current_user)):
    """Get patch details."""
    return {"patch_id": patch_id, "status": "not_found"}


@router.get("/{patch_id}/diff")
async def get_patch_diff(patch_id: str, current_user: dict = Depends(get_current_user)):
    """Get patch diff content."""
    return {"patch_id": patch_id, "diff": ""}


@router.get("/{patch_id}/evidence")
async def get_patch_evidence(patch_id: str, current_user: dict = Depends(get_current_user)):
    """Get evidence links for a patch."""
    return {"patch_id": patch_id, "evidence": []}


@router.post("/{patch_id}/submit-approval")
async def submit_for_approval(
    patch_id: str, current_user: dict = Depends(get_current_user)
):
    """Submit a patch for approval review."""
    logger.info("patch_submitted_approval", patch_id=patch_id, user=current_user.get("email"))
    return {"patch_id": patch_id, "status": "submitted_for_review"}
