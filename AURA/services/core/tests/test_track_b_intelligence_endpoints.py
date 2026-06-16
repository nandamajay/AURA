"""Endpoint tests for Track-B M10 intelligence APIs."""

from __future__ import annotations

import enum
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

# Test runtime in this environment uses Python 3.10; provide StrEnum shim for aura_sdk imports.
if not hasattr(enum, "StrEnum"):
    class _StrEnum(str, enum.Enum):
        pass

    enum.StrEnum = _StrEnum  # type: ignore[attr-defined]

from core.routers import track_b_intelligence as track_b_intel_router
from core.routers.auth import get_current_user

from track_b_test_fixtures import write_track_b_fixture


@pytest.fixture
def track_b_intel_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    monkeypatch.setenv("AURA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("AURA_TRACK_B_OUTPUT_ROOT", str(repo_root / "missing-output"))
    monkeypatch.setenv("AURA_TRACK_B_ARTIFACT_ROOTS", str(repo_root / "track_b_validation"))

    app = FastAPI()
    app.include_router(track_b_intel_router.router, prefix="/track-b-intel")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-track-b",
        "email": "track-b@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_track_b_intel_endpoints(track_b_intel_client: TestClient) -> None:
    endpoints = [
        "/track-b-intel/overview",
        "/track-b-intel/trends",
        "/track-b-intel/patterns",
        "/track-b-intel/recommendations",
        "/track-b-intel/learning",
        "/track-b-intel/executive",
        "/track-b-intel/forecast",
    ]
    for endpoint in endpoints:
        response = track_b_intel_client.get(endpoint)
        assert response.status_code == 200
        payload = response.json()
        assert "payload" in payload

