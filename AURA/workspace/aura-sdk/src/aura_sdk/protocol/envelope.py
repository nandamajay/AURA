"""Stdio envelope codec — JSON lines on stdin/stdout."""

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from aura_sdk.protocol.constants import ExitCode, MessageType


class AgentHeartbeat(BaseModel):
    """Periodic heartbeat from agent to orchestrator."""

    message_type: Literal["heartbeat"] = "heartbeat"
    agent_id: str = ""
    task_id: str = ""
    timestamp: float = 0.0  # Unix timestamp
    memory_mb: int = 0
    cpu_percent: float = 0.0


class AgentProgress(BaseModel):
    """Progress update from agent to orchestrator."""

    message_type: Literal["progress"] = "progress"
    task_id: str = ""
    progress_percent: int = 0  # 0-100
    status: str = ""  # Human-readable status
    message: str = ""


class AgentResult(BaseModel):
    """Final result from agent to orchestrator."""

    message_type: Literal["task.complete"] = "task.complete"
    task_id: str = ""
    exit_code: ExitCode = ExitCode.SUCCESS
    results: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    usage: dict[str, Any] = Field(default_factory=dict)  # tokens, duration_ms, memory_mb
    output_path: str = ""


class StdioEnvelope(BaseModel):
    """Wrapper for stdio messages with metadata."""

    version: str = "1.0"
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def encode(cls, obj: BaseModel) -> str:
        """Encode a pydantic model to a JSON line."""
        return json.dumps(obj.model_dump(mode="json"), default=str)

    @classmethod
    def decode(cls, line: str) -> dict[str, Any]:
        """Decode a JSON line to a dict."""
        return json.loads(line.strip())
