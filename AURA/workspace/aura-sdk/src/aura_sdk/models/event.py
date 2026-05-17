"""Canonical event schema — every event in AURA uses EventEnvelope."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """26 typed event types across all subsystems."""

    # Agent lifecycle
    AGENT_REGISTERED = "agent.registered"
    AGENT_SPAWNED = "agent.spawned"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_TIMEOUT = "agent.timeout"
    AGENT_KILLED = "agent.killed"

    # Task orchestration
    TASK_CREATED = "task.created"
    TASK_QUEUED = "task.queued"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_CANCELLED = "task.cancelled"

    # Simulation
    SIM_STARTED = "sim.started"
    SIM_PROGRESS = "sim.progress"
    SIM_COMPLETED = "sim.completed"
    SIM_FAILED = "sim.failed"

    # Governance
    APPROVAL_REQUIRED = "governance.approval_required"
    APPROVAL_GRANTED = "governance.approval_granted"
    APPROVAL_REJECTED = "governance.approval_rejected"
    ESCALATION_TRIGGERED = "governance.escalation_triggered"

    # LLM
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"
    LLM_CACHE_HIT = "llm.cache_hit"

    # System
    SERVICE_STARTED = "service.started"
    SERVICE_STOPPED = "service.stopped"
    CIRCUIT_BREAKER_STATE = "system.circuit_breaker_state"


class EventSource(BaseModel):
    """Identifies who/what produced an event."""

    subsystem: Literal["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"] = "S1"
    service: str = ""  # e.g. "core", "llm-gateway"
    agent_type: str = ""  # e.g. "learning", "refactor"
    agent_id: str = ""
    task_id: str = ""


class EventEnvelope(BaseModel):
    """Every event in the system uses this envelope.

    Immutable — create new instances for state changes.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: EventSource
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = ""
    version: str = "1.0"

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, raw: str) -> "EventEnvelope":
        return cls.model_validate_json(raw)
