"""Governance models — RBAC, approvals, audit."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Role(StrEnum):
    """5 RBAC roles with escalating privileges."""

    VIEWER = "viewer"  # Read-only dashboard access
    REVIEWER = "reviewer"  # Can review patches, add comments
    APPROVER = "approver"  # Can approve/reject patches
    ARCHITECT = "architect"  # Can configure rules, plugins, agents
    ADMIN = "admin"  # Full system access


class Permission(StrEnum):
    """12 fine-grained permissions."""

    DASHBOARD_READ = "dashboard.read"
    AGENT_READ = "agent.read"
    AGENT_SPAWN = "agent.spawn"
    PATCH_READ = "patch.read"
    PATCH_REVIEW = "patch.review"
    PATCH_APPROVE = "patch.approve"
    RULE_READ = "rule.read"
    RULE_WRITE = "rule.write"
    SIMULATION_RUN = "simulation.run"
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"
    USER_MANAGE = "user.manage"


# Role → Permission mapping
ROLE_PERMISSIONS: dict[Role, list[Permission]] = {
    Role.VIEWER: [Permission.DASHBOARD_READ, Permission.AGENT_READ, Permission.PATCH_READ],
    Role.REVIEWER: [
        Permission.DASHBOARD_READ,
        Permission.AGENT_READ,
        Permission.PATCH_READ,
        Permission.PATCH_REVIEW,
        Permission.RULE_READ,
        Permission.SIMULATION_RUN,
    ],
    Role.APPROVER: [
        Permission.DASHBOARD_READ,
        Permission.AGENT_READ,
        Permission.PATCH_READ,
        Permission.PATCH_REVIEW,
        Permission.PATCH_APPROVE,
        Permission.RULE_READ,
        Permission.SIMULATION_RUN,
    ],
    Role.ARCHITECT: [
        Permission.DASHBOARD_READ,
        Permission.AGENT_READ,
        Permission.AGENT_SPAWN,
        Permission.PATCH_READ,
        Permission.PATCH_REVIEW,
        Permission.PATCH_APPROVE,
        Permission.RULE_READ,
        Permission.RULE_WRITE,
        Permission.SIMULATION_RUN,
        Permission.CONFIG_READ,
        Permission.CONFIG_WRITE,
    ],
    Role.ADMIN: list(Permission),  # All permissions
}


class User(BaseModel):
    """User account for the AURA platform."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    email: str = ""
    password_hash: str = ""
    role: Role = Role.VIEWER
    display_name: str = ""
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: datetime | None = None

    def has_permission(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS.get(self.role, [])

    def has_any_permission(self, permissions: list[Permission]) -> bool:
        return any(self.has_permission(p) for p in permissions)


class ApprovalAction(StrEnum):
    """Actions available on an approval request."""

    GRANT = "grant"
    REJECT = "reject"
    ESCALATE = "escalate"
    COMMENT = "comment"


class ApprovalDimension(StrEnum):
    """3-dimensional approval matrix dimensions."""

    LIFECYCLE = "lifecycle"
    SUBSYSTEM = "subsystem"
    QUALITY = "quality"


class Approval(BaseModel):
    """Approval record in the 3-dimensional approval matrix."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    patch_id: str
    dimension: ApprovalDimension
    stage: str = ""  # e.g. "migration", "validation"
    status: str = "pending"  # pending, in_progress, passed, failed, skipped
    assigned_to: str = ""  # user_id
    confidence_threshold: float = 0.7
    actual_confidence: float | None = None
    reviewed_by: str = ""  # user_id
    reviewed_at: datetime | None = None
    comments: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
