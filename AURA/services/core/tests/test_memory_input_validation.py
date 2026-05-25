"""Core memory router input validation regression tests."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
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


def _create_memory_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE engineering_decisions (
                decision_id TEXT PRIMARY KEY,
                title TEXT,
                subsystem TEXT,
                created_at INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE failure_investigations (
                failure_id TEXT PRIMARY KEY,
                title TEXT,
                subsystem TEXT,
                status TEXT,
                severity TEXT,
                created_at INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE replay_incidents (
                incident_id TEXT PRIMARY KEY,
                task_id TEXT,
                description TEXT,
                divergence_cause TEXT,
                status TEXT,
                severity TEXT,
                created_at INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE architecture_drift (
                drift_id TEXT PRIMARY KEY,
                title TEXT,
                subsystem TEXT,
                status TEXT,
                introduced_at INTEGER
            )
            """
        )
        db.execute(
            """
            CREATE TABLE technical_debt (
                debt_id TEXT PRIMARY KEY,
                title TEXT,
                subsystem TEXT,
                status TEXT,
                severity TEXT,
                created_at INTEGER
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
                target_id TEXT
            )
            """
        )
        db.execute(
            "INSERT INTO engineering_decisions (decision_id, title, subsystem, created_at) VALUES (?, ?, ?, ?)",
            ("dec-1", "decision", "sound/soc/qcom", 1_710_000_100),
        )
        db.execute(
            "INSERT INTO failure_investigations (failure_id, title, subsystem, status, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("fail-1", "failure", "sound/soc/qcom", "open", "high", 1_710_000_200),
        )
        db.execute(
            "INSERT INTO replay_incidents (incident_id, task_id, description, divergence_cause, status, severity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("rep-1", "task-1", "drift", "irq_order", "open", "high", 1_710_000_300),
        )
        db.execute(
            "INSERT INTO architecture_drift (drift_id, title, subsystem, status, introduced_at) VALUES (?, ?, ?, ?, ?)",
            ("drift-1", "drift", "sound/soc/qcom", "open", 1_710_000_400),
        )
        db.execute(
            "INSERT INTO technical_debt (debt_id, title, subsystem, status, severity, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("debt-1", "debt", "sound/soc/qcom", "open", "medium", 1_710_000_500),
        )
        db.execute(
            "INSERT INTO audit_ledger (timestamp, event_type, target_type, target_id) VALUES (?, ?, ?, ?)",
            (1_710_000_600, "approval.escalated", "task", "task-1"),
        )
        db.execute(
            "INSERT INTO audit_ledger (timestamp, event_type, target_type, target_id) VALUES (?, ?, ?, ?)",
            (1_710_000_610, "patch.rejected", "patch", "patch-1"),
        )
        db.commit()


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


@pytest.fixture
def aggregate_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "memory_router.db"
    _create_memory_schema(db_path)

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(memory_router, "get_db", _test_get_db)

    app = FastAPI()
    app.include_router(memory_router.router, prefix="/memory")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    return TestClient(app)


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


def test_learning_timeline_aggregates_real_ledgers(aggregate_client: TestClient):
    response = aggregate_client.get("/memory/learning/timeline", params={"limit": 50})
    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "PASS"
    assert payload["count"] > 0
    assert any(entry["kind"] == "decision" for entry in payload["entries"])
    assert any(entry["kind"] == "audit_event" for entry in payload["entries"])


def test_maintainer_intelligence_aggregates_rejections_and_escalations(aggregate_client: TestClient):
    response = aggregate_client.get("/memory/maintainer/intelligence", params={"limit": 50})
    assert response.status_code == 200
    payload = response.json()
    assert payload["classification"] == "PASS"
    assert payload["signals"]["governance_escalations"] >= 1
    assert payload["signals"]["rejected_patch_events"] >= 1
    assert isinstance(payload["debt_hotspots"], list)


def test_learning_timeline_fail_closed_when_required_ledgers_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    db_path = tmp_path / "memory_partial.db"
    with sqlite3.connect(db_path) as db:
        db.execute(
            """
            CREATE TABLE audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                event_type TEXT,
                target_type TEXT,
                target_id TEXT
            )
            """
        )
        db.commit()

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            yield db

    monkeypatch.setattr(memory_router, "get_db", _test_get_db)

    app = FastAPI()
    app.include_router(memory_router.router, prefix="/memory")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    client = TestClient(app)
    try:
        response = client.get("/memory/learning/timeline", params={"limit": 20})
        assert response.status_code == 200
        payload = response.json()
        assert payload["classification"] == "FAIL_CLOSED"
        assert payload["fail_closed_reasons"]
    finally:
        client.close()
