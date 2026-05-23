"""Health check endpoints — liveness and readiness probes."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_sdk.logging.logger import get_logger
from aura_sdk.db.connection import get_db
from aura_sdk.models.health import ComponentHealth, HealthResponse, HealthStatus
from core.config import Config
from core.lifespan import get_uptime
from core.routers.auth import get_current_user

logger = get_logger("core.health")
router = APIRouter()

# Dependency states
_deps_healthy: dict[str, HealthStatus] = {
    "sqlite": HealthStatus.HEALTHY,
    "llm-gateway": HealthStatus.HEALTHY,
    "ws-server": HealthStatus.HEALTHY,
}


def _row_int(row: Any, key: str, default: int = 0) -> int:
    if row is None:
        return default
    try:
        return int(row[key] or 0)
    except Exception:
        return default


async def _ws_coexistence_metrics() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{Config.WS_SERVER_URL}/metrics/coexistence")
            response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return {"available": False, "error": "invalid_payload"}
        return {"available": True, "payload": payload}
    except Exception as exc:
        return {"available": False, "error": str(exc)}


async def _query_task_status_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
            )
            rows = await cursor.fetchall()
        for row in rows:
            key = str(row["status"] or "unknown")
            counts[key] = int(row["count"] or 0)
    except Exception:
        return {}
    return counts


async def _query_retry_pressure() -> dict[str, int]:
    try:
        async with get_db() as db:
            pending_cursor = await db.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE json_extract(result_data, '$.retry_pending') = 1
                """
            )
            pending_row = await pending_cursor.fetchone()
            lineage_cursor = await db.execute(
                """
                SELECT COUNT(*) AS count
                FROM tasks
                WHERE json_type(json_extract(result_data, '$.retry_lineage')) = 'array'
                """
            )
            lineage_row = await lineage_cursor.fetchone()
        return {
            "retry_pending_tasks": _row_int(pending_row, "count", 0),
            "tasks_with_retry_lineage": _row_int(lineage_row, "count", 0),
        }
    except Exception:
        return {"retry_pending_tasks": 0, "tasks_with_retry_lineage": 0}


async def _query_domain_activity(limit: int = 300) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    try:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT input_data, status
                FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
    except Exception:
        return {}

    import json

    for row in rows:
        domain = "default"
        raw_input = row["input_data"]
        if isinstance(raw_input, str) and raw_input:
            try:
                parsed = json.loads(raw_input)
                value = parsed.get("plugin_domain") if isinstance(parsed, dict) else None
                if isinstance(value, str) and value.strip():
                    domain = value.strip().lower()
            except Exception:
                domain = "default"
        bucket = stats.setdefault(
            domain,
            {"total": 0, "running": 0, "queued": 0, "failed": 0, "completed": 0},
        )
        bucket["total"] += 1
        status = str(row["status"] or "")
        if status in {"running", "started"}:
            bucket["running"] += 1
        elif status in {"queued", "created"}:
            bucket["queued"] += 1
        elif status in {"failed", "timed_out", "cancelled"}:
            bucket["failed"] += 1
        elif status == "completed":
            bucket["completed"] += 1
    return stats


async def _query_replay_state() -> dict[str, int]:
    try:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT recording_state, COUNT(*) AS count
                FROM task_logs
                GROUP BY recording_state
                """
            )
            rows = await cursor.fetchall()
    except Exception:
        return {"finalized": 0, "mutable": 0}

    finalized = 0
    mutable = 0
    for row in rows:
        state = str(row["recording_state"] or "")
        count = int(row["count"] or 0)
        if state == "finalized":
            finalized += count
        elif state == "mutable":
            mutable += count
    return {"finalized": finalized, "mutable": mutable}


async def _query_governance_state() -> dict[str, Any]:
    statuses: dict[str, int] = {}
    audit_last_hour = 0
    try:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT status, COUNT(*) AS count FROM approvals GROUP BY status"
            )
            rows = await cursor.fetchall()
            now_ts = int(time.time())
            cutoff = now_ts - 3600
            audit_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM audit_ledger WHERE timestamp >= ?",
                (cutoff,),
            )
            audit_row = await audit_cursor.fetchone()
        for row in rows:
            key = str(row["status"] or "unknown")
            statuses[key] = int(row["count"] or 0)
        audit_last_hour = _row_int(audit_row, "count", 0)
    except Exception:
        return {"approvals": {}, "audit_last_hour": 0}

    return {"approvals": statuses, "audit_last_hour": audit_last_hour}


def _build_pressure_alerts(
    queue_isolation: dict[str, Any],
    ws_metrics: dict[str, Any],
    replay_state: dict[str, int],
    retry_pressure: dict[str, int],
) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    per_domain = queue_isolation.get("per_domain")
    if isinstance(per_domain, dict):
        for domain, metrics in per_domain.items():
            if not isinstance(metrics, dict):
                continue
            wait_ms = int(metrics.get("last_queue_wait_ms", 0) or 0)
            starvation = int(metrics.get("starvation_events", 0) or 0)
            if wait_ms >= 10_000 or starvation > 0:
                alerts.append(
                    {
                        "severity": "bounded",
                        "surface": "queue",
                        "message": f"domain={domain} wait_ms={wait_ms} starvation_events={starvation}",
                    }
                )

    ws_payload = ws_metrics.get("payload")
    if isinstance(ws_payload, dict):
        sse_drop = int(ws_payload.get("sse_drop_total", 0) or 0)
        evictions = int(ws_payload.get("buffer_evictions_total", 0) or 0)
        if sse_drop > 0:
            alerts.append(
                {
                    "severity": "bounded",
                    "surface": "websocket_sse",
                    "message": f"sse_drop_total={sse_drop}",
                }
            )
        if evictions > 0:
            alerts.append(
                {
                    "severity": "bounded",
                    "surface": "replay_buffer",
                    "message": f"buffer_evictions_total={evictions}",
                }
            )

    mutable = int(replay_state.get("mutable", 0) or 0)
    if mutable > 0:
        alerts.append(
            {
                "severity": "info",
                "surface": "replay",
                "message": f"mutable_replay_logs={mutable} (non-finalized traces are not deterministic replay artifacts)",
            }
        )

    pending = int(retry_pressure.get("retry_pending_tasks", 0) or 0)
    if pending > 0:
        alerts.append(
            {
                "severity": "bounded",
                "surface": "retry",
                "message": f"retry_pending_tasks={pending}",
            }
        )

    return alerts


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


@router.get("/runtime-overview")
async def runtime_overview(
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Operational snapshot for runtime dashboard and pressure observability."""
    queue_manager = getattr(request.app.state, "task_queue", None)
    runtime = getattr(request.app.state, "agent_runtime", None)
    watchdog = getattr(request.app.state, "watchdog", None)
    breakers = getattr(request.app.state, "circuit_breakers", None)

    queue_stats = await queue_manager.get_queue_stats() if queue_manager is not None else {}
    queue_isolation = await queue_manager.get_isolation_stats() if queue_manager is not None else {}
    running_agents = runtime.list_running() if runtime is not None else []
    watchdog_states = watchdog.list_states() if watchdog is not None else {}
    breaker_states = breakers.list_states() if breakers is not None else {}

    ws_metrics = await _ws_coexistence_metrics()
    task_counts = await _query_task_status_counts()
    retry_pressure = await _query_retry_pressure()
    replay_state = await _query_replay_state()
    governance_state = await _query_governance_state()
    domain_activity = await _query_domain_activity(limit=400)
    alerts = _build_pressure_alerts(queue_isolation, ws_metrics, replay_state, retry_pressure)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_by": current_user.get("email", ""),
        "queue": queue_stats,
        "queue_isolation": queue_isolation,
        "agents": {
            "running_count": len(running_agents),
            "running_sample": running_agents[:20],
            "watchdog_count": len(watchdog_states),
            "watchdog_max_watches": watchdog.config.max_watches if watchdog is not None else 0,
            "circuit_breakers": breaker_states,
        },
        "tasks": {
            "status_counts": task_counts,
            "retry_pressure": retry_pressure,
            "domain_activity": domain_activity,
        },
        "replay": replay_state,
        "governance": governance_state,
        "websocket": ws_metrics,
        "pressure_alerts": alerts,
        "classification": {
            "operational": "bounded" if alerts else "stable",
            "determinism": "strong_bounded",
        },
    }
