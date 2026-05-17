"""Core task endpoint input/negative-path regression tests."""

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aura_sdk.models.agent import AgentType
from aura_sdk.models.task import Task, TaskStatus
from core.routers.auth import get_current_user
from core.routers.tasks import router as tasks_router


class _QueueStub:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}

    async def list_tasks(self, status=None, agent_type=None, page=1, limit=50):
        _ = (status, agent_type, page, limit)
        values = list(self.tasks.values())
        return values, len(values)

    async def get_task(self, task_id: str):
        return self.tasks.get(task_id)

    async def create_task(self, task_create, requested_by: str):
        task = Task(
            id="task-created",
            agent_type=task_create.agent_type,
            status=TaskStatus.QUEUED,
            priority=task_create.priority,
            input_data=task_create.input_data,
            description=task_create.description,
            requested_by=requested_by,
            max_retries=task_create.max_retries,
        )
        self.tasks[task.id] = task
        return task

    async def cancel_task(self, task_id: str, requested_by: str):
        _ = requested_by
        task = self.tasks.get(task_id)
        if task is None:
            return None
        task.status = TaskStatus.CANCELLED
        return task

    async def get_queue_stats(self):
        return {"total": len(self.tasks)}


def _client(queue: _QueueStub | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(tasks_router, prefix="/tasks")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    if queue is not None:
        app.state.task_queue = queue
    return TestClient(app)


def test_tasks_list_returns_503_when_queue_manager_is_unavailable():
    client = _client()
    response = client.get("/tasks/")
    assert response.status_code == 503
    assert response.json()["detail"] == "Task queue manager unavailable"


def test_tasks_create_rejects_non_object_json_body():
    client = _client(_QueueStub())
    response = client.post("/tasks/", json=[])
    assert response.status_code == 422


def test_tasks_create_rejects_malformed_json():
    client = _client(_QueueStub())
    response = client.post(
        "/tasks/",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_tasks_get_returns_404_for_missing_task():
    client = _client(_QueueStub())
    response = client.get("/tasks/missing-task-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found: missing-task-id"


def test_tasks_cancel_returns_404_for_missing_task():
    client = _client(_QueueStub())
    response = client.patch("/tasks/missing-task-id/cancel")
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found: missing-task-id"


def test_tasks_replay_returns_404_for_missing_task_log():
    client = _client(_QueueStub())
    with (
        patch("core.routers.tasks.TaskRecorder"),
        patch("core.routers.tasks.ReplayEngine") as replay_engine_cls,
    ):
        replay_engine = replay_engine_cls.return_value
        replay_engine.replay = AsyncMock(return_value={"success": False})
        replay_engine.verify_integrity.return_value = False
        response = client.get("/tasks/missing-task-id/replay")
        assert response.status_code == 404
        assert response.json()["detail"] == "Replay log not found for task_id=missing-task-id"


def test_tasks_list_returns_data_when_queue_is_available():
    queue = _QueueStub()
    queue.tasks["task-1"] = Task(id="task-1", agent_type=AgentType.LEARNING, status=TaskStatus.RUNNING)
    client = _client(queue)
    response = client.get("/tasks/?page=1&limit=10")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["tasks"][0]["id"] == "task-1"
