"""Health check models for service observability."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """Service health states."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ComponentHealth(BaseModel):
    """Health of a single dependency component."""

    name: str = ""
    status: HealthStatus = HealthStatus.HEALTHY
    latency_ms: int = 0
    message: str = ""


class HealthResponse(BaseModel):
    """Standard health check response."""

    service: str = "aura"
    status: HealthStatus = HealthStatus.HEALTHY
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    uptime_seconds: float = 0.0
    components: list[ComponentHealth] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY and all(
            c.status != HealthStatus.UNHEALTHY for c in self.components
        )

    @property
    def is_ready(self) -> bool:
        return self.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)
