"""LLM gateway models — request/response/cost tracking."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class CompletionRequest(BaseModel):
    """Request to the LLM gateway."""

    agent_type: str = ""
    task_id: str = ""
    model: str = "gpt-4o-2024-08-06"
    messages: list[dict[str, str]] = Field(default_factory=list)
    temperature: float = 0.1
    max_tokens: int = 4000
    seed: int = 42
    top_p: float | None = None


class TokenUsage(BaseModel):
    """Token consumption details."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class CompletionResponse(BaseModel):
    """Response from the LLM gateway."""

    content: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cached: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-2024-08-06"
    latency_ms: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
