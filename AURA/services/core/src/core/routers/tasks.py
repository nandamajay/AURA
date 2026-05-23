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
    if isinstance(task.input_data, dict):
        workflow_kind = str(task.input_data.get("workflow_kind") or "").strip().lower()
        if workflow_kind == "engineering":
            required = ("intake_id", "snapshot_id", "provenance_lineage_hash", "workflow_id")
            missing = [key for key in required if not str(task.input_data.get(key) or "").strip()]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=f"detached_engineering_execution_forbidden:missing={','.join(missing)}",
                )

    queue = _get_task_queue(request)
    created = await queue.create_task(task, requested_by=current_user.get("email", "unknown"))
    task_id = created.id
    plugin_domain = "default"
    if isinstance(task.input_data, dict):
        domain_value = task.input_data.get("plugin_domain")
        if isinstance(domain_value, str) and domain_value.strip():
            plugin_domain = domain_value.strip().lower()
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
            "plugin_domain": plugin_domain,
            "runtime_cell_scope": f"domain:{plugin_domain}",
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
            "plugin_domain": plugin_domain,
            "runtime_cell_scope": f"domain:{plugin_domain}",
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


@router.get("/{task_id}/replay/state")
async def replay_state(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Inspect replay recording state without requiring finalized replay."""
    recorder = TaskRecorder(Config.SQLITE_PATH)
    log = recorder.get_log(task_id)
    if log is None:
        return {
            "task_id": task_id,
            "exists": False,
            "recording_state": "missing",
            "replayable": False,
            "integrity_ok": False,
        }

    recording_state = str(log.get("recording_state") or "mutable")
    replayable = recording_state == "finalized"
    integrity_ok = False
    if replayable:
        integrity_ok = ReplayEngine(recorder).verify_integrity(task_id)

    return {
        "task_id": task_id,
        "exists": True,
        "recording_state": recording_state,
        "replayable": replayable,
        "integrity_ok": integrity_ok,
        "revision": int(log.get("revision") or 0),
        "created_at": int(log.get("created_at") or 0),
        "finalized_at": int(log.get("finalized_at") or 0),
        "output_hash": str(log.get("output_hash") or ""),
        "snapshot_hash": str(log.get("snapshot_hash") or ""),
    }


@router.get("/queue/stats")
async def queue_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get queue statistics."""
    queue = _get_task_queue(request)
    return await queue.get_queue_stats()


@router.get("/queue/isolation")
async def queue_isolation_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Get queue fairness/isolation statistics."""
    queue = _get_task_queue(request)
    return await queue.get_isolation_stats()
