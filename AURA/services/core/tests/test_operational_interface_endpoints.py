"""Operational interface endpoint regression tests."""

from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core.routers import health as health_router
from core.routers import knowledge as knowledge_router
from core.routers.auth import get_current_user


class _QueueStub:
    async def get_queue_stats(self):
        return {
            "P0_critical": 0,
            "P1_normal": 2,
            "P2_background": 4,
            "running": 3,
            "completed_today": 10,
            "failed_today": 1,
            "fairness_overrides_total": 7,
            "starvation_events_total": 2,
            "domains_tracked": 2,
        }

    async def get_isolation_stats(self):
        return {
            "policy_version": "p2-isolation-v1",
            "dispatch_sequence": 12,
            "p2_wait_override_seconds": 3.0,
            "p2_fairness_window": 3,
            "per_domain": {
                "automation": {
                    "dispatches": 4,
                    "starvation_events": 2,
                    "fairness_overrides": 2,
                    "last_queue_wait_ms": 12_500,
                }
            },
            "queue_depth": {"P0_critical": 0, "P1_normal": 2, "P2_background": 4, "running": 3},
        }


class _RuntimeStub:
    def list_running(self):
        return [{"agent_id": "learning-a1", "task_id": "task-1", "status": "running"}]


class _WatchdogConfigStub:
    max_watches = 50


class _WatchdogStub:
    config = _WatchdogConfigStub()

    def list_states(self):
        return {"learning-a1": {"agent_id": "learning-a1", "status": "running"}}


class _BreakerStub:
    def list_states(self):
        return {"learning": {"state": "closed"}}


def _create_runtime_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                status TEXT,
                input_data TEXT,
                result_data TEXT,
                updated_at INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE task_logs (
                task_id TEXT PRIMARY KEY,
                recording_state TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE approvals (
                id TEXT PRIMARY KEY,
                status TEXT
            )
            """
        )
        db.execute(
            """
            CREATE TABLE audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                event_type TEXT,
                target_type TEXT,
                target_id TEXT,
                session_id TEXT
            )
            """
        )
        db.execute(
            "INSERT INTO tasks (id, status, input_data, result_data, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                "task-1",
                "running",
                '{"plugin_domain":"automation"}',
                '{"retry_pending":true,"retry_lineage":[{"retry_sequence":1}]}',
                1700000001,
            ),
        )
        db.execute(
            "INSERT INTO task_logs (task_id, recording_state) VALUES (?, ?)",
            ("task-1", "mutable"),
        )
        db.execute(
            "INSERT INTO task_logs (task_id, recording_state) VALUES (?, ?)",
            ("task-2", "finalized"),
        )
        db.execute(
            "INSERT INTO approvals (id, status) VALUES (?, ?)",
            ("approval-1", "pending"),
        )
        db.execute(
            "INSERT INTO audit_ledger (timestamp, event_type, target_type, target_id, session_id) VALUES (?, ?, ?, ?, ?)",
            (1_700_000_000, "task.created", "task", "task-1", "user@aura.local"),
        )
        db.commit()


@pytest.fixture
def operational_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "runtime_overview.db"
    _create_runtime_db(db_path)

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    async def _fake_ws_metrics():
        return {
            "available": True,
            "payload": {
                "sse_drop_total": 3,
                "buffer_evictions_total": 2,
            },
        }

    monkeypatch.setattr(health_router, "get_db", _test_get_db)
    monkeypatch.setattr(health_router, "_ws_coexistence_metrics", _fake_ws_metrics)

    app = FastAPI()
    app.include_router(health_router.router, prefix="/health")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-1",
        "email": "ops@aura.local",
        "role": "admin",
    }
    app.state.task_queue = _QueueStub()
    app.state.agent_runtime = _RuntimeStub()
    app.state.watchdog = _WatchdogStub()
    app.state.circuit_breakers = _BreakerStub()
    return TestClient(app)


def test_runtime_overview_contains_operational_surfaces(operational_client: TestClient):
    response = operational_client.get("/health/runtime-overview")
    assert response.status_code == 200
    payload = response.json()

    assert payload["queue"]["P2_background"] == 4
    assert payload["agents"]["running_count"] == 1
    assert payload["tasks"]["retry_pressure"]["retry_pending_tasks"] == 1
    assert payload["replay"]["mutable"] == 1
    assert payload["replay"]["finalized"] == 1
    assert payload["websocket"]["available"] is True
    assert payload["pressure_alerts"]
    assert payload["classification"]["operational"] == "bounded"


@pytest.fixture
def evidence_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    repo_root = tmp_path / "repo"
    evidence_dir = repo_root / "evidence" / "runtime-isolation"
    docs_dir = repo_root / "docs" / "architecture-consolidation"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "sample-report.md").write_text("# report\nok\n", encoding="utf-8")
    (docs_dir / "charter.md").write_text("determinism charter", encoding="utf-8")

    monkeypatch.setenv("AURA_REPO_ROOT", str(repo_root))

    app = FastAPI()
    app.include_router(knowledge_router.router, prefix="/knowledge")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "u-1",
        "email": "ops@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_evidence_index_lists_curated_sections(evidence_client: TestClient):
    response = evidence_client.get("/knowledge/evidence/index")
    assert response.status_code == 200
    payload = response.json()
    assert "runtime_evidence" in payload["sections"]
    files = payload["sections"]["runtime_evidence"]["files"]
    assert any(item["name"] == "sample-report.md" for item in files)


def test_evidence_read_blocks_path_escape(evidence_client: TestClient):
    response = evidence_client.get(
        "/knowledge/evidence/read",
        params={
            "section": "runtime_evidence",
            "relative_path": "../secret.env",
        },
    )
    assert response.status_code == 400


def test_evidence_read_returns_file_content(evidence_client: TestClient):
    response = evidence_client.get(
        "/knowledge/evidence/read",
        params={
            "section": "runtime_evidence",
            "relative_path": "runtime-isolation/sample-report.md",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["truncated"] is False
    assert "# report" in payload["content"]
