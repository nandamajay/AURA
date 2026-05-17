"""Task queue models — 3-tier priority system."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from aura_sdk.models.agent import AgentType


class TaskPriority(StrEnum):
    """3-tier priority queue system.

    P0: Critical — FIFO, interrupt background
    P1: Normal — Round-robin across agent types
    P2: Background — Best-effort, only when load < 50%
    """

    CRITICAL = "P0"
    NORMAL = "P1"
    BACKGROUND = "P2"


class TaskStatus(StrEnum):
    """Task lifecycle states."""

    CREATED = "created"
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TaskCreate(BaseModel):
    """Create a new task for the orchestrator."""

    agent_type: AgentType
    input_data: dict[str, Any] = Field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    description: str = ""
    requested_by: str = ""  # user_id or "system"
    parent_task_id: str = ""  # For sub-tasks
    max_retries: int = 3


class Task(BaseModel):
    """Full task record with runtime state."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent_type: AgentType
    status: TaskStatus = TaskStatus.CREATED
    priority: TaskPriority = TaskPriority.NORMAL
    input_data: dict[str, Any] = Field(default_factory=dict)
    result_data: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    requested_by: str = ""
    parent_task_id: str = ""
    current_attempt: int = 0
    max_retries: int = 3
    agent_pid: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_ms(self) -> int | None:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        if self.started_at:
            return int((datetime.now(timezone.utc) - self.started_at).total_seconds() * 1000)
        return None
