"""Core agents spawn endpoint input validation tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers.agents import router as agents_router
from core.routers.auth import get_current_user


class _FakeCircuitBreakers:
    async def allow_request(self, agent_type: str) -> tuple[bool, str]:
        return True, "closed"

    async def record_success(self, agent_type: str) -> None:
        return None

    async def record_failure(self, agent_type: str, reason: str = "failure") -> None:
        return None


class _FakeRuntime:
    def __init__(self):
        self.calls: list[dict] = []

    async def spawn(
        self,
        *,
        agent_type: str,
        requested_by: str,
        task_id: str | None = None,
        input_data: dict | None = None,
    ) -> dict:
        self.calls.append(
            {
                "agent_type": agent_type,
                "requested_by": requested_by,
                "task_id": task_id,
                "input_data": input_data,
            }
        )
        return {
            "agent_type": agent_type,
            "agent_id": f"{agent_type}-test1234",
            "task_id": task_id or "task-test1234",
            "pid": 1234,
            "status": "running",
        }


class _FakeQueue:
    async def get_task(self, task_id: str):
        return None

    async def register_external_spawn(self, **kwargs):
        return None


def _build_client() -> tuple[TestClient, _FakeRuntime]:
    app = FastAPI()
    app.include_router(agents_router, prefix="/agents")
    app.state.circuit_breakers = _FakeCircuitBreakers()
    runtime = _FakeRuntime()
    app.state.agent_runtime = runtime
    app.state.task_queue = _FakeQueue()
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    return TestClient(app), runtime


def test_spawn_rejects_non_object_json_body():
    client, _ = _build_client()
    response = client.post("/agents/learning/spawn", json=[])
    assert response.status_code == 422


def test_spawn_rejects_malformed_json():
    client, _ = _build_client()
    response = client.post(
        "/agents/learning/spawn",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_spawn_valid_body_still_succeeds():
    client, runtime = _build_client()
    response = client.post(
        "/agents/learning/spawn",
        json={
            "task_id": "task-abc",
            "description": "spawn-test",
            "input_data": {"scope": "validation"},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_id"] == "learning-test1234"
    assert payload["task_id"] == "task-abc"
    assert payload["status"] == "running"
    assert runtime.calls[0]["input_data"] == {"scope": "validation"}
