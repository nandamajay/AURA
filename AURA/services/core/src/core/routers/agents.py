"""Agent management endpoints."""

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventType
from aura_sdk.models.agent import AgentType
from aura_sdk.models.task import TaskStatus
from aura_sdk.protocol.envelope import AgentHeartbeat
from core.events import publish_event
from core.routers.auth import get_current_user
from core.services.agent_runtime import AgentRuntimeManager
from core.services.circuit_breaker import CircuitBreakerManager
from core.services.task_queue import TaskQueueManager
from core.services.watchdog import WatchdogManager

logger = get_logger("core.agents")
router = APIRouter()


class AgentSpawnRequest(BaseModel):
    """Spawn request payload."""

    task_id: str = ""
    description: str = ""
    input_data: Any = Field(default_factory=dict)


def _ensure_valid_agent_type(agent_type: str) -> None:
    if agent_type not in [t.value for t in AgentType]:
        raise HTTPException(status_code=400, detail=f"Unknown agent type: {agent_type}")


def _get_circuit_breakers(request: Request) -> CircuitBreakerManager:
    circuit_breakers: CircuitBreakerManager | None = getattr(request.app.state, "circuit_breakers", None)
    if circuit_breakers is None:
        raise HTTPException(status_code=503, detail="Circuit breaker manager unavailable")
    return circuit_breakers


def _get_watchdog(request: Request) -> WatchdogManager:
    watchdog: WatchdogManager | None = getattr(request.app.state, "watchdog", None)
    if watchdog is None:
        raise HTTPException(status_code=503, detail="Watchdog manager unavailable")
    return watchdog


def _get_agent_runtime(request: Request) -> AgentRuntimeManager:
    runtime: AgentRuntimeManager | None = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Agent runtime manager unavailable")
    return runtime


def _get_task_queue(request: Request) -> TaskQueueManager:
    queue: TaskQueueManager | None = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="Task queue manager unavailable")
    return queue


@router.get("/")
async def list_agents(request: Request, current_user: dict = Depends(get_current_user)):
    """List all agent types and their counts."""
    agent_types = [t.value for t in AgentType]
    runtime = _get_agent_runtime(request)
    return {
        "agent_types": agent_types,
        "supported_types": sorted(runtime.supported_agent_types),
        "total_types": len(agent_types),
    }


@router.get("/running")
async def list_running_agents(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List currently running agent instances."""
    runtime = _get_agent_runtime(request)
    agents = runtime.list_running()
    return {"agents": agents, "count": len(agents)}


@router.get("/watchdog")
async def list_watchdog_states(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List watchdog states for all registered agents."""
    watchdog = _get_watchdog(request)
    states = watchdog.list_states()
    return {
        "count": len(states),
        "max_watches": watchdog.config.max_watches,
        "states": states,
    }


@router.get("/watchdog/{agent_id}")
async def get_watchdog_state(
    agent_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get watchdog state for a specific agent id."""
    watchdog = _get_watchdog(request)
    try:
        return watchdog.get_state(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Agent not registered in watchdog: {agent_id}") from exc


@router.post("/{agent_id}/heartbeat")
async def agent_heartbeat(
    agent_id: str,
    heartbeat: AgentHeartbeat,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Update watchdog heartbeat for a running agent."""
    watchdog = _get_watchdog(request)
    if heartbeat.agent_id and heartbeat.agent_id != agent_id:
        raise HTTPException(status_code=400, detail="agent_id mismatch between path and payload")

    accepted = watchdog.on_heartbeat(agent_id, heartbeat)
    if not accepted:
        raise HTTPException(status_code=404, detail=f"Agent not registered in watchdog: {agent_id}")

    await publish_event(
        request,
        EventType.AGENT_HEARTBEAT,
        {
            "agent_id": agent_id,
            "task_id": heartbeat.task_id,
            "memory_mb": heartbeat.memory_mb,
            "cpu_percent": heartbeat.cpu_percent,
            "timestamp": heartbeat.timestamp,
            "updated_by": current_user.get("email"),
        },
        agent_id=agent_id,
        task_id=heartbeat.task_id,
        trace_id=heartbeat.task_id,
    )
    return {"agent_id": agent_id, "status": "heartbeat_recorded"}


@router.get("/circuit-breakers")
async def list_circuit_breakers(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """List all circuit breaker states."""
    circuit_breakers = _get_circuit_breakers(request)
    states = circuit_breakers.list_states()
    return {"count": len(states), "breakers": states}


@router.get("/{agent_type}/circuit-breaker")
async def get_circuit_breaker(
    agent_type: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get circuit breaker state for one agent type."""
    _ensure_valid_agent_type(agent_type)
    circuit_breakers = _get_circuit_breakers(request)
    return circuit_breakers.get_state(agent_type)


@router.post("/{agent_type}/circuit-breaker/reset")
async def reset_circuit_breaker(
    agent_type: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Reset an agent-type circuit breaker (admin only)."""
    _ensure_valid_agent_type(agent_type)
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    circuit_breakers = _get_circuit_breakers(request)
    await circuit_breakers.reset(
        agent_type,
        reason=f"manual_reset:{current_user.get('email', 'unknown')}",
    )
    return {
        "agent_type": agent_type,
        "status": "reset",
        "state": circuit_breakers.get_state(agent_type),
    }


@router.post("/{agent_type}/spawn")
async def spawn_agent(
    agent_type: str,
    request: Request,
    body: AgentSpawnRequest = Body(default_factory=AgentSpawnRequest),
    current_user: dict = Depends(get_current_user),
):
    """Spawn a new agent process."""
    _ensure_valid_agent_type(agent_type)
    circuit_breakers = _get_circuit_breakers(request)

    allowed, reason = await circuit_breakers.allow_request(agent_type)
    if not allowed:
        logger.warning(
            "agent_spawn_rejected_by_circuit_breaker",
            agent_type=agent_type,
            reason=reason,
            user=current_user.get("email"),
        )
        raise HTTPException(
            status_code=503,
            detail={"code": "circuit_open", "reason": reason, "agent_type": agent_type},
        )

    logger.info("agent_spawn_requested", agent_type=agent_type, user=current_user.get("email"))
    runtime = _get_agent_runtime(request)
    queue = _get_task_queue(request)
    requested_task_id = str(body.task_id).strip() or None
    description = str(body.description).strip()
    input_data = body.input_data if body.input_data is not None else {}
    if not isinstance(input_data, dict):
        raise HTTPException(status_code=400, detail="input_data must be an object")
    if requested_task_id:
        existing = await queue.get_task(requested_task_id)
        if existing is not None and existing.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMED_OUT,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"task_id_conflict_terminal_status:{existing.status.value}",
            )

    try:
        spawned = await runtime.spawn(
            agent_type=agent_type,
            requested_by=current_user.get("email", "unknown"),
            task_id=requested_task_id,
            input_data=input_data,
        )
        try:
            await queue.register_external_spawn(
                task_id=spawned["task_id"],
                agent_type=agent_type,
                requested_by=current_user.get("email", "unknown"),
                agent_id=spawned["agent_id"],
                agent_pid=spawned.get("pid"),
                input_data=input_data,
                description=description,
            )
        except ValueError:
            await runtime.terminate(
                spawned["agent_id"],
                reason="task_registration_failed",
                requested_by=current_user.get("email", "unknown"),
            )
            raise
        await circuit_breakers.record_success(agent_type)
    except ValueError as exc:
        reason = str(exc)
        logger.warning(
            "agent_spawn_rejected_invalid_request",
            agent_type=agent_type,
            error=reason,
            user=current_user.get("email"),
        )
        status_code = 409 if reason.startswith("task_id_conflict") else 400
        raise HTTPException(status_code=status_code, detail=reason) from exc
    except Exception as exc:
        await circuit_breakers.record_failure(agent_type, reason=exc.__class__.__name__.lower())
        logger.exception(
            "agent_spawn_failed",
            agent_type=agent_type,
            error=str(exc),
            user=current_user.get("email"),
        )
        raise HTTPException(status_code=500, detail="Failed to start agent process") from exc

    return {
        "agent_type": agent_type,
        "agent_id": spawned["agent_id"],
        "task_id": spawned["task_id"],
        "pid": spawned["pid"],
        "status": spawned["status"],
        "message": "Agent process started",
    }


@router.delete("/{agent_id}")
async def kill_agent(
    agent_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Kill a running agent."""
    logger.info("agent_kill_requested", agent_id=agent_id, user=current_user.get("email"))
    runtime = _get_agent_runtime(request)
    killed = await runtime.terminate(
        agent_id,
        reason="manual_kill",
        requested_by=current_user.get("email", "unknown"),
    )
    if not killed:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    return {"agent_id": agent_id, "status": "killed"}
