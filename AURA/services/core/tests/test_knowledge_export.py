"""Knowledge export endpoint regression tests."""

import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from aura_sdk.db import connection as db_connection
from core.routers.auth import get_current_user
from core.routers.knowledge import router as knowledge_router


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    db_path = tmp_path / "knowledge_export_test.db"

    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE subsystems (id TEXT PRIMARY KEY, name TEXT NOT NULL)")
        db.execute(
            """CREATE TABLE migration_rules (
                id TEXT PRIMARY KEY,
                subsystem_id TEXT,
                category TEXT NOT NULL,
                downstream_pattern TEXT NOT NULL,
                upstream_equivalent TEXT,
                description TEXT,
                confidence REAL NOT NULL,
                evidence_count INTEGER NOT NULL,
                source_refs TEXT,
                created_at INTEGER NOT NULL,
                last_applied_at INTEGER,
                success_count INTEGER NOT NULL,
                failure_count INTEGER NOT NULL
            )"""
        )
        db.execute(
            "INSERT INTO subsystems (id, name) VALUES (?, ?)",
            ("subsys-a", "audio-qualcomm"),
        )
        db.execute(
            """INSERT INTO migration_rules (
                id, subsystem_id, category, downstream_pattern, upstream_equivalent,
                description, confidence, evidence_count, source_refs, created_at,
                last_applied_at, success_count, failure_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "rule-a",
                "subsys-a",
                "pattern",
                "downstream_clk_enable()",
                "upstream_clk_prepare_enable()",
                "Clock API migration",
                0.92,
                3,
                "[]",
                1700000000,
                None,
                5,
                0,
            ),
        )
        db.commit()

    db_connection._DB_PATH = str(db_path)

    app = FastAPI()
    app.include_router(knowledge_router, prefix="/knowledge")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "email": "test@aura.local",
        "role": "admin",
    }
    return TestClient(app)


def test_export_knowledge_json(client: TestClient):
    response = client.post("/knowledge/export", json={"format": "json"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "json"
    assert payload["count"] == 1
    assert payload["data"][0]["id"] == "rule-a"


def test_export_knowledge_csv(client: TestClient):
    response = client.post("/knowledge/export", json={"format": "csv"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "csv"
    assert payload["count"] == 1
    assert "id,subsystem_id,category,downstream_pattern" in payload["data"]
    assert "rule-a,subsys-a,pattern,downstream_clk_enable()" in payload["data"]


def test_export_knowledge_unsupported_format_returns_400(client: TestClient):
    response = client.post("/knowledge/export", json={"format": "xml"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported export format. Use 'json' or 'csv'."


def test_export_knowledge_unknown_subsystem_returns_404(client: TestClient):
    response = client.post(
        "/knowledge/export",
        json={"format": "json", "subsystem": "unknown-subsys"},
    )
    assert response.status_code == 404
