"""Core auth endpoint input validation regression tests."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers.auth import router as auth_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(auth_router, prefix="/auth")
    return TestClient(app)


def test_login_rejects_non_object_json_body():
    client = _client()
    response = client.post("/auth/login", json=[])
    assert response.status_code == 422


def test_login_rejects_malformed_json():
    client = _client()
    response = client.post(
        "/auth/login",
        data="{",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_login_missing_password_remains_400():
    client = _client()
    response = client.post("/auth/login", json={"email": "admin@aura.local"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Email and password required"
