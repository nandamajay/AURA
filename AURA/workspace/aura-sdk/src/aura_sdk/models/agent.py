"""Agent models — spawned process lifecycle and results."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentType(StrEnum):
    """14 agent types defined in the AURA architecture."""

    LEARNING = "learning"
    DEPENDENCY = "dependency"
    DTS_BINDINGS = "dts_bindings"
    UPSTREAM_PHILOSOPHY = "upstream_philosophy"
    REFACTOR = "refactor"
    VALIDATION = "validation"
    REGRESSION = "regression"
    KNOWLEDGE_BASE = "knowledge_base"
    DASHBOARD = "dashboard"
    SIMULATION = "simulation"
    MAINTAINER_INTEL = "maintainer_intel"
    PATCH_BUILDER = "patch_builder"
    TEST_RUNNER = "test_runner"
    REVIEW_COORDINATOR = "review_coordinator"


class AgentStatus(StrEnum):
    """Agent process lifecycle states."""

    PENDING = "pending"
    SPAWNING = "spawning"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


class AgentSpawnRequest(BaseModel):
    """Request to spawn an agent process."""

    task_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_type: AgentType
    rules_path: str = ""
    input_data: dict[str, Any] = Field(default_factory=dict)
    seed: int = 42
    model_version: str = "gpt-4o-2024-08-06"
    timeout_seconds: int = 300
    priority: int = 1  # 0=critical, 1=normal, 2=background


class AgentProgress(BaseModel):
    """Progress update emitted by agent via stdout."""

    task_id: str
    progress_percent: int = Field(ge=0, le=100)
    status: str = ""  # Human-readable status
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentResult(BaseModel):
    """Final result emitted by agent on completion."""

    task_id: str
    agent_type: AgentType
    status: AgentStatus
    exit_code: int = 0
    results: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    usage: dict[str, Any] = Field(default_factory=dict)  # tokens, duration_ms, memory_mb
    output_path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
