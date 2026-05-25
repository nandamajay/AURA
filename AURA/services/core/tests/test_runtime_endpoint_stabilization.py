"""Runtime endpoint stabilization tests for fail-closed behavior."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.routers import runtime as runtime_router
from core.routers.auth import get_current_user


@pytest.fixture
def runtime_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Intentionally point to an empty repo root to validate fail-closed behavior.
    repo_root = tmp_path / "repo"
    transport_root = repo_root / "docs" / "operations" / "transport"
    transport_root.mkdir(parents=True, exist_ok=True)
    repo_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AURA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("AURA_TRANSPORT_ARTIFACT_ROOT", str(transport_root))

    app = FastAPI()
    app.include_router(runtime_router.router, prefix="/runtime")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-1",
        "email": "ops@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_runtime_endpoints_return_200_fail_closed(runtime_client: TestClient) -> None:
    endpoints = [
        "/runtime/artifacts/index",
        "/runtime/governance/summary",
        "/runtime/topology",
        "/runtime/equivalence",
        "/runtime/confidence",
    ]

    for endpoint in endpoints:
        response = runtime_client.get(endpoint)
        assert response.status_code == 200, endpoint


def test_runtime_artifacts_read_return_200_for_missing_artifact(runtime_client: TestClient) -> None:
    response = runtime_client.get(
        "/runtime/artifacts/read",
        params={"artifact_type": "runtime_equivalence_report"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["valid"] is False
    assert payload["metadata"]["exists"] is False
    assert any(issue["code"] == "artifact_not_found" for issue in payload["validation"]["issues"])
