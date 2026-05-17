"""AURA SDK — Shared library for the Audio Upstream Refactor Agent platform."""

__version__ = "0.1.0"

from aura_sdk.models.event import EventEnvelope, EventType, EventSource
from aura_sdk.models.agent import AgentSpawnRequest, AgentStatus, AgentResult
from aura_sdk.models.task import TaskCreate, TaskStatus, TaskPriority
from aura_sdk.models.governance import User, Role, ApprovalAction
from aura_sdk.models.health import HealthResponse, HealthStatus
from aura_sdk.models.llm import CompletionRequest, CompletionResponse

__all__ = [
    "__version__",
    "EventEnvelope",
    "EventType",
    "EventSource",
    "AgentSpawnRequest",
    "AgentStatus",
    "AgentResult",
    "TaskCreate",
    "TaskStatus",
    "TaskPriority",
    "User",
    "Role",
    "ApprovalAction",
    "HealthResponse",
    "HealthStatus",
    "CompletionRequest",
    "CompletionResponse",
]
