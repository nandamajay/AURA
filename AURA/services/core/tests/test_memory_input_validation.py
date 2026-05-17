"""Core memory router input validation regression tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.routers.auth import get_current_user
from core.routers import memory as memory_router


class _FakeMemoryStore:
    def __init__(self):
        self.created_decisions = []

    async def create_decision(self, record):
        self.created_decisions.append(record)
        return record.decision_id


@pytest.fixture
def client() -> tuple[TestClient, _FakeMemoryStore]:
    app = FastAPI()
    app.include_router(memory_router.router, prefix="/memory")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }

    fake_store = _FakeMemoryStore()
    original_store = memory_router.store
    memory_router.store = fake_store
    try:
        yield TestClient(app), fake_store
    finally:
        memory_router.store = original_store


def test_memory_decisions_rejects_non_object_json_body(client):
    test_client, _ = client
    response = test_client.post("/memory/decisions", json=[])
    assert response.status_code == 422


def test_memory_decisions_rejects_malformed_json(client):
    test_client, _ = client
    response = test_client.post(
        "/memory/decisions",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_memory_decisions_valid_payload_still_records(client):
    test_client, fake_store = client
    response = test_client.post(
        "/memory/decisions",
        json={"title": "Decision A", "subsystem": "S1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "recorded"
    assert fake_store.created_decisions[0].title == "Decision A"
    assert fake_store.created_decisions[0].decided_by == "test-user"


def test_memory_validation_run_rejects_non_object_json_body(client):
    test_client, _ = client
    response = test_client.post("/memory/validation/run", json=[])
    assert response.status_code == 422


def test_memory_nondeterminism_check_accepts_valid_payload(client):
    test_client, _ = client
    response = test_client.post(
        "/memory/validation/nondeterminism-check",
        json={"source_code": "import random\nx = random.random()\n"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["risk_count"], int)
