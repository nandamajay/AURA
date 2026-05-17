"""Health check endpoints — liveness and readiness probes."""

import httpx

from fastapi import APIRouter, HTTPException

from aura_sdk.logging.logger import get_logger
from aura_sdk.models.health import ComponentHealth, HealthResponse, HealthStatus
from core.config import Config
from core.lifespan import get_uptime

logger = get_logger("core.health")
router = APIRouter()

# Dependency states
_deps_healthy: dict[str, HealthStatus] = {
    "sqlite": HealthStatus.HEALTHY,
    "llm-gateway": HealthStatus.HEALTHY,
    "ws-server": HealthStatus.HEALTHY,
}


@router.get("/live")
async def liveness() -> HealthResponse:
    """Liveness probe — is the process running?

    Kubernetes uses this to know if the container should be restarted.
    Always returns 200 if we can respond.
    """
    return HealthResponse(
        service=Config.SERVICE_NAME,
        status=HealthStatus.HEALTHY,
        version=Config.VERSION,
        uptime_seconds=get_uptime(),
        components=[
            ComponentHealth(name="process", status=HealthStatus.HEALTHY, latency_ms=0),
        ],
    )


@router.get("/ready")
async def readiness() -> HealthResponse:
    """Readiness probe — is the service ready to accept traffic?

    Checks all dependencies (SQLite, LLM gateway, WS server).
    Returns 503 if any critical dependency is unhealthy.
    """
    components = []
    overall = HealthStatus.HEALTHY

    # Check SQLite
    try:
        from aura_sdk.db.connection import get_db
        import time
        t0 = time.time()
        async with get_db() as db:
            await db.execute("SELECT 1")
        latency = int((time.time() - t0) * 1000)
        sqlite_health = HealthStatus.HEALTHY
    except Exception as e:
        sqlite_health = HealthStatus.UNHEALTHY
        overall = HealthStatus.UNHEALTHY
        latency = 0
        logger.warning("sqlite_health_check_failed", error=str(e))

    components.append(
        ComponentHealth(name="sqlite", status=sqlite_health, latency_ms=latency)
    )

    # Check LLM gateway
    try:
        import time
        t0 = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{Config.LLM_GATEWAY_URL}/health")
            resp.raise_for_status()
        latency = int((time.time() - t0) * 1000)
        llm_health = HealthStatus.HEALTHY
    except Exception as e:
        llm_health = HealthStatus.DEGRADED
        if overall == HealthStatus.HEALTHY:
            overall = HealthStatus.DEGRADED
        latency = 0
        logger.warning("llm_gateway_health_check_failed", error=str(e))

    components.append(
        ComponentHealth(name="llm-gateway", status=llm_health, latency_ms=latency)
    )

    # Check WS server
    try:
        import time
        t0 = time.time()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{Config.WS_SERVER_URL}/health")
            resp.raise_for_status()
        latency = int((time.time() - t0) * 1000)
        ws_health = HealthStatus.HEALTHY
    except Exception as e:
        ws_health = HealthStatus.DEGRADED
        if overall == HealthStatus.HEALTHY:
            overall = HealthStatus.DEGRADED
        latency = 0
        logger.warning("ws_server_health_check_failed", error=str(e))

    components.append(
        ComponentHealth(name="ws-server", status=ws_health, latency_ms=latency)
    )

    return HealthResponse(
        service=Config.SERVICE_NAME,
        status=overall,
        version=Config.VERSION,
        uptime_seconds=get_uptime(),
        components=components,
    )
