"""Core charter endpoint input validation regression tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers.auth import get_current_user
from core.routers.charter import router as charter_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(charter_router, prefix="/charter")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_charter_intervene_rejects_non_object_json_body():
    client = _client()
    response = client.post("/charter/intervene", json=[])
    assert response.status_code == 422


def test_charter_intervene_rejects_malformed_json():
    client = _client()
    response = client.post(
        "/charter/intervene",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_charter_intervene_valid_payload_still_succeeds():
    client = _client()
    response = client.post(
        "/charter/intervene",
        json={"target": "task-123", "action": "pause"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "intervened"
    assert payload["target"] == "task-123"
    assert payload["action"] == "pause"


def test_charter_reject_approval_rejects_non_object_json_body():
    client = _client()
    response = client.post("/charter/approvals/nonexistent/reject", json=[])
    assert response.status_code == 422


def test_charter_enforce_missing_action_remains_400():
    client = _client()
    response = client.post("/charter/enforce", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "Field 'action' is required"
