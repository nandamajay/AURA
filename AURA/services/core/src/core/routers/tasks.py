"""Task queue endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventType
from aura_sdk.replay import ReplayEngine, TaskRecorder
from aura_sdk.models.task import TaskCreate, TaskStatus
from core.config import Config
from core.events import publish_event
from core.routers.auth import get_current_user
from core.services.task_queue import TaskQueueManager

logger = get_logger("core.tasks")
router = APIRouter()


def _get_task_queue(request: Request) -> TaskQueueManager:
    queue: TaskQueueManager | None = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="Task queue manager unavailable")
    return queue


@router.get("/")
async def list_tasks(
    request: Request,
    status: str | None = None,
    agent_type: str | None = None,
    page: int = 1,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List tasks with optional filtering."""
    queue = _get_task_queue(request)
    tasks, total = await queue.list_tasks(
        status=status,
        agent_type=agent_type,
        page=page,
        limit=limit,
    )
    return {
        "tasks": [task.model_dump(mode="json") for task in tasks],
        "page": page,
        "limit": limit,
        "total": total,
    }


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get task details."""
    queue = _get_task_queue(request)
    task = await queue.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return task.model_dump(mode="json")


@router.post("/")
async def create_task(
    task: TaskCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Create a new task."""
    queue = _get_task_queue(request)
    created = await queue.create_task(task, requested_by=current_user.get("email", "unknown"))
    task_id = created.id
    logger.info(
        "task_created",
        task_id=task_id,
        agent_type=task.agent_type.value,
        priority=task.priority.value,
        user=current_user.get("email"),
    )
    await publish_event(
        request,
        EventType.TASK_CREATED,
        {
            "task_id": task_id,
            "agent_type": task.agent_type.value,
            "priority": task.priority.value,
            "requested_by": current_user.get("email"),
            "description": task.description,
        },
        task_id=task_id,
        agent_type=task.agent_type.value,
        trace_id=task_id,
    )
    await publish_event(
        request,
        EventType.TASK_QUEUED,
        {
            "task_id": task_id,
            "agent_type": task.agent_type.value,
            "priority": task.priority.value,
            "status": TaskStatus.QUEUED.value,
        },
        task_id=task_id,
        agent_type=task.agent_type.value,
        trace_id=task_id,
    )
    return {
        "task_id": task_id,
        "status": TaskStatus.QUEUED.value,
        "priority": task.priority.value,
        "message": "Task created and queued",
    }


@router.patch("/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Cancel a queued or running task."""
    queue = _get_task_queue(request)
    task = await queue.cancel_task(task_id, requested_by=current_user.get("email", "unknown"))
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    logger.info("task_cancelled", task_id=task_id, user=current_user.get("email"))
    await publish_event(
        request,
        EventType.TASK_CANCELLED,
        {
            "task_id": task_id,
            "cancelled_by": current_user.get("email"),
        },
        task_id=task_id,
        trace_id=task_id,
    )
    return {"task_id": task_id, "status": task.status.value}


@router.get("/{task_id}/replay")
async def replay_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Replay a recorded task for deterministic inspection."""
    recorder = TaskRecorder(Config.SQLITE_PATH)
    engine = ReplayEngine(recorder)
    replay_result = await engine.replay(task_id)

    if not replay_result.get("success", False):
        raise HTTPException(status_code=404, detail=f"Replay log not found for task_id={task_id}")

    # Backward-compatible normalization for placeholder replay timestamps.
    replay_payload = replay_result.get("replayed_at")
    if (isinstance(replay_payload, dict) and not replay_payload) or replay_payload in {"{}", ""}:
        replay_result["replayed_at"] = datetime.now(timezone.utc).isoformat()

    integrity_ok = engine.verify_integrity(task_id)
    logger.info(
        "task_replay_requested",
        task_id=task_id,
        requested_by=current_user.get("email"),
        integrity_ok=integrity_ok,
        fidelity=replay_result.get("fidelity"),
    )
    return {
        "task_id": task_id,
        "requested_by": current_user.get("email"),
        "integrity_ok": integrity_ok,
        "replay": replay_result,
    }


@router.get("/queue/stats")
async def queue_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get queue statistics."""
    queue = _get_task_queue(request)
    return await queue.get_queue_stats()
