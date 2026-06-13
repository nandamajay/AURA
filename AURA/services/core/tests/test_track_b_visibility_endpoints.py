"""Endpoint tests for Track-B visibility, lineage, readiness, and learning APIs."""

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

from core.routers import track_b as track_b_router
from core.routers.auth import get_current_user

from track_b_test_fixtures import write_track_b_fixture


@pytest.fixture
def track_b_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root)
    monkeypatch.setenv("AURA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("AURA_TRACK_B_OUTPUT_ROOT", str(repo_root / "missing-output"))
    monkeypatch.setenv("AURA_TRACK_B_ARTIFACT_ROOTS", str(repo_root / "track_b_validation"))

    app = FastAPI()
    app.include_router(track_b_router.router, prefix="/track-b")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-track-b",
        "email": "track-b@aura.local",
        "role": "admin",
    }
    return TestClient(app)


@pytest.fixture
def track_b_client_without_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo_root = tmp_path / "repo"
    write_track_b_fixture(repo_root, include_schema_freeze=False)
    monkeypatch.setenv("AURA_REPO_ROOT", str(repo_root))
    monkeypatch.setenv("AURA_TRACK_B_OUTPUT_ROOT", str(repo_root / "missing-output"))
    monkeypatch.setenv("AURA_TRACK_B_ARTIFACT_ROOTS", str(repo_root / "track_b_validation"))

    app = FastAPI()
    app.include_router(track_b_router.router, prefix="/track-b")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-track-b",
        "email": "track-b@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_track_b_artifacts_index_and_read(track_b_client: TestClient) -> None:
    index = track_b_client.get("/track-b/artifacts/index", params={"limit": 100})
    assert index.status_code == 200
    index_payload = index.json()
    assert index_payload["validation"]["valid"] is True
    assert index_payload["pagination"]["total"] == 6

    artifact_id = index_payload["artifacts"][0]["metadata"]["artifact_id"]
    read = track_b_client.get(f"/track-b/artifacts/{artifact_id}")
    assert read.status_code == 200
    read_payload = read.json()
    assert read_payload["artifact"]["metadata"]["artifact_id"] == artifact_id


def test_track_b_lineage_forward_and_reverse(track_b_client: TestClient) -> None:
    forward = track_b_client.get("/track-b/lineage", params={"component_query": "q6apm_dai_prepare"})
    assert forward.status_code == 200
    forward_payload = forward.json()
    assert forward_payload["validation"]["valid"] is True
    assert len(forward_payload["nodes"]) > 0
    assert len(forward_payload["edges"]) > 0

    node_id = forward_payload["nodes"][0]["node_id"]
    reverse = track_b_client.get("/track-b/lineage", params={"reverse_node_id": node_id})
    assert reverse.status_code == 200
    reverse_payload = reverse.json()
    assert len(reverse_payload["nodes"]) > 0


def test_track_b_dashboard_widgets(track_b_client: TestClient) -> None:
    endpoints = [
        "/track-b/dashboard/release-summary",
        "/track-b/dashboard/readiness",
        "/track-b/dashboard/readiness-history",
        "/track-b/dashboard/dependency-coverage",
        "/track-b/dashboard/conflicts",
        "/track-b/dashboard/equivalence",
        "/track-b/dashboard/audit-history",
        "/track-b/dashboard/release-history",
    ]
    for endpoint in endpoints:
        response = track_b_client.get(endpoint)
        assert response.status_code == 200

    readiness = track_b_client.get("/track-b/dashboard/readiness")
    readiness_payload = readiness.json()["payload"]
    assert "evidence_completeness_percent" in readiness_payload
    assert "dependency_coverage_percent" in readiness_payload
    assert "open_conflict_count" in readiness_payload


def test_track_b_search_learning_audit_and_release_lookups(track_b_client: TestClient) -> None:
    audits = track_b_client.get("/track-b/audits/index")
    assert audits.status_code == 200
    audit_payload = audits.json()
    assert audit_payload["pagination"]["total"] >= 1
    audit_id = audit_payload["audits"][0]["audit_id"]

    audit_read = track_b_client.get(f"/track-b/audits/{audit_id}")
    assert audit_read.status_code == 200
    assert audit_read.json()["audit"]["audit_id"] == audit_id

    releases = track_b_client.get("/track-b/releases/index")
    assert releases.status_code == 200
    release_payload = releases.json()
    assert release_payload["pagination"]["total"] >= 1
    release_tag = release_payload["releases"][0]["release_tag"]

    release_read = track_b_client.get(f"/track-b/releases/{release_tag}")
    assert release_read.status_code == 200
    assert release_read.json()["release"]["release_tag"] == release_tag

    learning = track_b_client.get("/track-b/learning/index")
    assert learning.status_code == 200
    assert learning.json()["pagination"]["total"] >= 1

    patterns = track_b_client.get("/track-b/learning/patterns")
    assert patterns.status_code == 200

    search = track_b_client.get("/track-b/search", params={"q": "q6apm_dai_prepare", "kind": "artifact"})
    assert search.status_code == 200
    assert search.json()["total"] >= 1


def test_track_b_fail_closed_when_frozen_schema_missing(
    track_b_client_without_schema: TestClient,
) -> None:
    response = track_b_client_without_schema.get("/track-b/artifacts/index", params={"limit": 20})
    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["valid"] is False
    assert any(issue["code"] == "m8_schema_freeze_missing" for issue in payload["validation"]["issues"])
