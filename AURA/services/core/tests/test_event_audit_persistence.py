"""Event audit persistence regression tests."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import aiosqlite
import pytest

from aura_sdk.models.event import EventEnvelope, EventSource, EventType
from core import events as core_events


def _create_audit_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE audit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL DEFAULT 0,
                user_id TEXT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (
                    event_type IN (
                        'task.created',
                        'task.queued',
                        'task.cancelled',
                        'agent.timeout',
                        'agent.killed',
                        'service.started',
                        'service.stopped'
                    )
                ),
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                before_state TEXT,
                after_state TEXT,
                evidence_hash TEXT,
                chain_hash TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_rows(db_path: Path) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, target_type, target_id, session_id FROM audit_ledger ORDER BY id"
        ).fetchall()
        return rows
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_persist_event_to_audit_records_row() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "events.db"
        _create_audit_schema(db_path)

        @asynccontextmanager
        async def _test_get_db():
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                yield db

        original_get_db = core_events.get_db
        core_events.get_db = _test_get_db
        try:
            event = EventEnvelope(
                event_type=EventType.TASK_CREATED,
                source=EventSource(subsystem="S1", service="core", task_id="task-1"),
                payload={"task_id": "task-1", "requested_by": "user@aura.local"},
                trace_id="task-1",
            )
            persisted = await core_events._persist_event_to_audit(event)
            assert persisted is True

            rows = _fetch_rows(db_path)
            assert rows == [("task.created", "task", "task-1", "user@aura.local")]
        finally:
            core_events.get_db = original_get_db


@pytest.mark.asyncio
async def test_persist_and_forward_skips_ws_when_persist_fails(monkeypatch) -> None:
    event = EventEnvelope(
        event_type=EventType.AGENT_TIMEOUT,
        source=EventSource(subsystem="S1", service="core", task_id="task-x", agent_id="agent-x"),
        payload={"reason": "watchdog_timeout"},
        trace_id="task-x",
    )

    called = {"forward": 0}

    async def _persist_fail(_event: EventEnvelope) -> bool:
        return False

    async def _forward(_event: EventEnvelope, _ws_url: str) -> bool:
        called["forward"] += 1
        return True

    monkeypatch.setattr(core_events, "_persist_event_to_audit", _persist_fail)
    monkeypatch.setattr(core_events, "_forward_to_ws", _forward)

    ok = await core_events._persist_and_forward(event, "http://ws-server:8000")
    assert ok is False
    assert called["forward"] == 0


@pytest.mark.asyncio
async def test_persist_and_forward_forwards_after_persist(monkeypatch) -> None:
    event = EventEnvelope(
        event_type=EventType.SERVICE_STARTED,
        source=EventSource(subsystem="S1", service="core"),
        payload={"service": "aura-core"},
        trace_id="boot-1",
    )

    called = {"persist": 0, "forward": 0}

    async def _persist_ok(_event: EventEnvelope) -> bool:
        called["persist"] += 1
        return True

    async def _forward_ok(_event: EventEnvelope, _ws_url: str) -> bool:
        called["forward"] += 1
        return True

    monkeypatch.setattr(core_events, "_persist_event_to_audit", _persist_ok)
    monkeypatch.setattr(core_events, "_forward_to_ws", _forward_ok)

    ok = await core_events._persist_and_forward(event, "http://ws-server:8000")
    assert ok is True
    assert called == {"persist": 1, "forward": 1}


@pytest.mark.asyncio
async def test_persist_event_to_audit_retries_locked_then_succeeds(monkeypatch) -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "events.db"
        _create_audit_schema(db_path)

        attempts = {"count": 0}

        @asynccontextmanager
        async def _flaky_get_db():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("database is locked")
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                yield db

        monkeypatch.setattr(core_events, "get_db", _flaky_get_db)
        monkeypatch.setattr(core_events, "_WAL_CHECKPOINT_EVERY", 0)
        monkeypatch.setattr(core_events, "_persist_success_count", 0)

        event = EventEnvelope(
            event_type=EventType.TASK_CREATED,
            source=EventSource(subsystem="S1", service="core", task_id="task-retry"),
            payload={"task_id": "task-retry", "requested_by": "user@aura.local"},
            trace_id="task-retry",
        )
        persisted = await core_events._persist_event_to_audit(event)
        assert persisted is True
        assert attempts["count"] == 3

        rows = _fetch_rows(db_path)
        assert rows == [("task.created", "task", "task-retry", "user@aura.local")]


@pytest.mark.asyncio
async def test_persist_event_to_audit_uses_deterministic_retry_backoff(monkeypatch) -> None:
    attempts = {"count": 0}
    sleeps: list[float] = []

    @asynccontextmanager
    async def _always_locked_db():
        attempts["count"] += 1
        raise RuntimeError("database is locked")
        yield  # pragma: no cover

    async def _fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(core_events, "get_db", _always_locked_db)
    monkeypatch.setattr(core_events.asyncio, "sleep", _fake_sleep)
    monkeypatch.setattr(core_events, "_WAL_CHECKPOINT_EVERY", 0)
    monkeypatch.setattr(core_events, "_persist_success_count", 0)

    event = EventEnvelope(
        event_type=EventType.TASK_CREATED,
        source=EventSource(subsystem="S1", service="core", task_id="task-backoff"),
        payload={"task_id": "task-backoff"},
        trace_id="task-backoff",
    )
    persisted = await core_events._persist_event_to_audit(event)
    assert persisted is False
    assert attempts["count"] == core_events._PERSIST_RETRY_ATTEMPTS
    assert sleeps == list(core_events._PERSIST_RETRY_BACKOFF_SECONDS)


@pytest.mark.asyncio
async def test_persist_event_to_audit_triggers_wal_checkpoint_at_threshold(monkeypatch) -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "events.db"
        _create_audit_schema(db_path)

        @asynccontextmanager
        async def _test_get_db():
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                yield db

        checkpoint_calls = {"count": 0}

        async def _fake_checkpoint() -> None:
            checkpoint_calls["count"] += 1

        monkeypatch.setattr(core_events, "get_db", _test_get_db)
        monkeypatch.setattr(core_events, "_run_audit_wal_checkpoint", _fake_checkpoint)
        monkeypatch.setattr(core_events, "_WAL_CHECKPOINT_EVERY", 1)
        monkeypatch.setattr(core_events, "_persist_success_count", 0)

        event = EventEnvelope(
            event_type=EventType.TASK_CREATED,
            source=EventSource(subsystem="S1", service="core", task_id="task-checkpoint"),
            payload={"task_id": "task-checkpoint", "requested_by": "user@aura.local"},
            trace_id="task-checkpoint",
        )
        persisted = await core_events._persist_event_to_audit(event)
        assert persisted is True
        assert checkpoint_calls["count"] == 1

        rows = _fetch_rows(db_path)
        assert rows == [("task.created", "task", "task-checkpoint", "user@aura.local")]
