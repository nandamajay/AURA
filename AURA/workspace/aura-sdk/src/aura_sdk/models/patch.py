"""Patch lifecycle models for driver upstreaming workflow."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class PatchStatus(StrEnum):
    """Patch lifecycle states."""

    DRAFT = "draft"
    MIGRATING = "migrating"
    VALIDATING = "validating"
    SIMULATING = "simulating"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    REJECTED = "rejected"
    UPSTREAMED = "upstreamed"


class Patch(BaseModel):
    """A patch being prepared for upstream submission."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    subsystem_id: str = ""
    version: int = 1
    status: PatchStatus = PatchStatus.DRAFT
    title: str = ""
    description: str = ""
    confidence_score: float = Field(ge=0.0, le=1.0, default=0.0)
    generated_by: str = ""  # agent type
    approved_by: str = ""  # user_id
    diff_path: str = ""
    cover_letter_path: str = ""
    changelog_path: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
