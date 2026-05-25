"""Governance stabilization regression tests for race/conflict semantics."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers import governance as governance_router
from core.routers.auth import get_current_user


def _create_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE approvals (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by TEXT,
                reviewed_at INTEGER,
                comments TEXT,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL DEFAULT 0,
                user_id TEXT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (
                    event_type IN (
                        'approval.submitted',
                        'approval.granted',
                        'approval.rejected',
                        'approval.escalated'
                    )
                ),
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                before_state TEXT,
                after_state TEXT,
                chain_hash TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_approval(db_path: Path, approval_id: str, status: str = "pending") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO approvals (id, status, reviewed_by, reviewed_at, comments, updated_at)
            VALUES (?, ?, '', 0, '', 0)
            """,
            (approval_id, status),
        )
        conn.commit()
    finally:
        conn.close()


def _get_approval_status(db_path: Path, approval_id: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        return str(row[0]) if row else ""
    finally:
        conn.close()


def _get_audit_events(db_path: Path, approval_id: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type FROM audit_ledger WHERE target_type = 'approval' AND target_id = ? ORDER BY id",
            (approval_id,),
        ).fetchall()
        return [str(row[0]) for row in rows]
    finally:
        conn.close()


def _build_client(db_path: Path) -> TestClient:
    app = FastAPI()
    app.include_router(governance_router.router, prefix="/governance")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user-1",
        "email": "user-1@aura.local",
        "role": "admin",
    }

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = OFF")
            yield db

    original_get_db = governance_router.get_db
    governance_router.get_db = _test_get_db

    client = TestClient(app)

    # Keep original getter attached for manual reset.
    client._governance_original_get_db = original_get_db  # type: ignore[attr-defined]
    return client


def _close_client(client: TestClient) -> None:
    original_get_db = getattr(client, "_governance_original_get_db", None)
    if original_get_db is not None:
        governance_router.get_db = original_get_db
    client.close()


def test_governance_conflict_is_deterministic_first_writer_wins() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "governance.db"
        _create_schema(db_path)
        approval_id = "approval-race-1"
        _seed_approval(db_path, approval_id, status="pending")

        client = _build_client(db_path)
        try:
            def _grant():
                return client.post(
                    f"/governance/approvals/{approval_id}",
                    json={"action": "grant", "comment": "first"},
                )

            def _reject():
                return client.post(
                    f"/governance/approvals/{approval_id}",
                    json={"action": "reject", "comment": "second"},
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                first, second = list(pool.map(lambda fn: fn(), (_grant, _reject)))

            statuses = sorted([first.status_code, second.status_code])
            assert statuses == [200, 409]

            success = first if first.status_code == 200 else second
            payload = success.json()
            final_status = _get_approval_status(db_path, approval_id)
            assert payload["status"] == final_status
            assert final_status in {"passed", "failed"}

            events = _get_audit_events(db_path, approval_id)
            assert len(events) == 1
            assert events[0] in {"approval.granted", "approval.rejected"}
        finally:
            _close_client(client)


def test_governance_escalate_uses_schema_compliant_transition() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "governance.db"
        _create_schema(db_path)
        approval_id = "approval-escalate-1"
        _seed_approval(db_path, approval_id, status="pending")

        client = _build_client(db_path)
        try:
            response = client.post(
                f"/governance/approvals/{approval_id}",
                json={"action": "escalate", "comment": "needs escalated review"},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "in_progress"
            assert payload["outcome"] == "applied"

            events = _get_audit_events(db_path, approval_id)
            assert events == ["approval.escalated"]
        finally:
            _close_client(client)


def test_governance_evidence_summary_remains_fail_closed_with_partial_schema() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "governance.db"
        _create_schema(db_path)
        _seed_approval(db_path, "approval-summary-1", status="pending")

        client = _build_client(db_path)
        try:
            response = client.get("/governance/summary/evidence", params={"limit": 20})
            assert response.status_code == 200
            payload = response.json()
            assert payload["classification"] == "FAIL_CLOSED"
            assert isinstance(payload["fail_closed_reasons"], list)
            assert payload["approvals"]["counts_by_status"]["pending"] >= 1
            assert payload["audit_history"]["total_entries"] >= 0
        finally:
            _close_client(client)
