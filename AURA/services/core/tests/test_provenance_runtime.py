"""Engineering source intake + provenance runtime regression tests."""

from __future__ import annotations

import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import aiosqlite
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.routers import provenance as provenance_router
from core.routers.auth import get_current_user


def _migration_sql() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    migration = repo_root / "knowledge" / "schema" / "019_source_provenance_runtime.sql"
    return migration.read_text(encoding="utf-8")


def _create_schema(db_path: Path) -> None:
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
                        'approval.submitted',
                        'approval.granted',
                        'approval.rejected',
                        'approval.escalated',
                        'config.changed'
                    )
                ),
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                before_state TEXT,
                after_state TEXT
            )
            """
        )
        conn.executescript(_migration_sql())
        conn.commit()
    finally:
        conn.close()


def _build_client(db_path: Path, *, role: str = "reviewer", email: str = "reviewer@aura.local") -> TestClient:
    app = FastAPI()
    app.include_router(provenance_router.router, prefix="/provenance")
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user-1",
        "email": email,
        "role": role,
    }

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    original_get_db = provenance_router.get_db
    provenance_router.get_db = _test_get_db
    client = TestClient(app)
    client._provenance_original_get_db = original_get_db  # type: ignore[attr-defined]
    return client


def _close_client(client: TestClient) -> None:
    original_get_db = getattr(client, "_provenance_original_get_db", None)
    if original_get_db is not None:
        provenance_router.get_db = original_get_db
    client.close()


def _base_payload() -> dict[str, Any]:
    return {
        "downstream_repo_url": "https://example.com/downstream/linux-msm.git",
        "downstream_ref_kind": "branch",
        "downstream_ref": "android-msm-audio",
        "bsp_lineage": "LA.UM.9.15.r1",
        "commit_anchors": ["3fa4b8d", "1aa5bc9", "3fa4b8d"],
        "subsystem_name": "audio-qualcomm",
        "subsystem_owner": "aura-audio",
        "upstream_repo_url": "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
        "target_kernel": "linux",
        "target_kernel_version": "6.12",
        "maintainer_refs": ["tiwai@suse.de", "broonie@kernel.org"],
        "patchset_lineage": ["3fa4b8d", "1aa5bc9"],
    }


def _events_for_intake(db_path: Path, intake_id: str) -> list[tuple[str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT event_type, event_payload FROM source_intake_events WHERE intake_id = ? ORDER BY id",
            (intake_id,),
        ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]
    finally:
        conn.close()


def _lineage_rows(db_path: Path, intake_id: str) -> list[tuple[str, str | None, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT lineage_stage, parent_lineage_hash, lineage_payload
            FROM source_lineage_entries
            WHERE intake_id = ?
            ORDER BY created_at, rowid
            """,
            (intake_id,),
        ).fetchall()
        return [(str(row[0]), row[1], str(row[2])) for row in rows]
    finally:
        conn.close()


def _audit_rows(db_path: Path, intake_id: str) -> list[tuple[str, str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT event_type, target_type, target_id, after_state
            FROM audit_ledger
            WHERE target_type = 'source_intake' AND target_id = ?
            ORDER BY id
            """,
            (intake_id,),
        ).fetchall()
        return [(str(row[0]), str(row[1]), str(row[2]), str(row[3] or "")) for row in rows]
    finally:
        conn.close()


def test_register_deterministic_hash_and_duplicate_rejected() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        client = _build_client(db_path)
        try:
            payload = _base_payload()
            first = client.post("/provenance/sources/register", json=payload)
            assert first.status_code == 200
            first_body = first.json()
            assert first_body["status"] == "registered"
            assert len(first_body["canonical_hash"]) == 64

            same_semantics_different_order = dict(payload)
            same_semantics_different_order["commit_anchors"] = ["1aa5bc9", "3fa4b8d"]
            same_semantics_different_order["patchset_lineage"] = ["1aa5bc9", "3fa4b8d"]
            duplicate = client.post("/provenance/sources/register", json=same_semantics_different_order)
            assert duplicate.status_code == 409
            assert duplicate.json()["detail"] == "duplicate_source_intake"
        finally:
            _close_client(client)


def test_trust_classification_matrix() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        client = _build_client(db_path)
        try:
            trusted_payload = _base_payload()
            trusted_reg = client.post("/provenance/sources/register", json=trusted_payload)
            trusted_id = trusted_reg.json()["intake_id"]
            trusted_val = client.post(f"/provenance/sources/{trusted_id}/validate")
            assert trusted_val.status_code == 200
            assert trusted_val.json()["trust_classification"] == "trusted"

            bounded_payload = _base_payload()
            bounded_payload["downstream_ref"] = "android-msm-audio-v2"
            bounded_payload["commit_anchors"] = []
            bounded_val_reg = client.post("/provenance/sources/register", json=bounded_payload)
            bounded_id = bounded_val_reg.json()["intake_id"]
            bounded_val = client.post(f"/provenance/sources/{bounded_id}/validate")
            assert bounded_val.status_code == 200
            assert bounded_val.json()["trust_classification"] == "bounded-trust"

            untrusted_payload = _base_payload()
            untrusted_payload["downstream_ref"] = "android-msm-audio-v3"
            untrusted_payload["downstream_repo_url"] = "not-a-git-url"
            untrusted_reg = client.post("/provenance/sources/register", json=untrusted_payload)
            untrusted_id = untrusted_reg.json()["intake_id"]
            untrusted_val = client.post(f"/provenance/sources/{untrusted_id}/validate")
            assert untrusted_val.status_code == 200
            assert untrusted_val.json()["trust_classification"] == "untrusted/manual-review-required"
            assert "invalid_url:downstream_repo_url" in untrusted_val.json()["issues"]
        finally:
            _close_client(client)


def test_untrusted_source_requires_approver_and_records_request_event() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        reviewer = _build_client(db_path, role="reviewer", email="reviewer@aura.local")
        approver = _build_client(db_path, role="approver", email="approver@aura.local")
        try:
            payload = _base_payload()
            payload["downstream_repo_url"] = "bad-url"
            registration = reviewer.post("/provenance/sources/register", json=payload)
            intake_id = registration.json()["intake_id"]

            validated = reviewer.post(f"/provenance/sources/{intake_id}/validate")
            assert validated.status_code == 200
            assert validated.json()["trust_classification"] == "untrusted/manual-review-required"

            reviewer_approve = reviewer.post(
                f"/provenance/sources/{intake_id}/approve",
                json={"decision": "approve", "comment": "reviewer attempt"},
            )
            assert reviewer_approve.status_code == 403

            approver_approve = approver.post(
                f"/provenance/sources/{intake_id}/approve",
                json={"decision": "approve", "comment": "approved by approver"},
            )
            assert approver_approve.status_code == 200
            assert approver_approve.json()["decision"] == "approve"

            event_types = [event_type for event_type, _ in _events_for_intake(db_path, intake_id)]
            assert "approval_requested" in event_types
            assert event_types[-1] == "approved"
        finally:
            _close_client(reviewer)
            _close_client(approver)


def test_override_writes_audit_and_snapshot_requires_approval() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        reviewer = _build_client(db_path, role="reviewer", email="reviewer@aura.local")
        admin = _build_client(db_path, role="admin", email="admin@aura.local")
        try:
            payload = _base_payload()
            payload["downstream_ref"] = "android-msm-audio-bounded"
            payload["commit_anchors"] = []
            registered = reviewer.post("/provenance/sources/register", json=payload)
            intake_id = registered.json()["intake_id"]
            validated = reviewer.post(f"/provenance/sources/{intake_id}/validate")
            assert validated.status_code == 200
            assert validated.json()["trust_classification"] == "bounded-trust"

            snapshot_before_approval = reviewer.post(
                f"/provenance/sources/{intake_id}/snapshot",
                json={"reason": "should fail pre-approval"},
            )
            assert snapshot_before_approval.status_code == 409
            assert snapshot_before_approval.json()["detail"] == "source_intake_not_approved"

            override = admin.post(
                f"/provenance/sources/{intake_id}/override-trust",
                json={"trust_classification": "trusted", "reason": "manual source audit complete"},
            )
            assert override.status_code == 200
            assert override.json()["overridden"] is True

            audit_rows = _audit_rows(db_path, intake_id)
            assert len(audit_rows) == 1
            event_type, target_type, target_id, after_state_json = audit_rows[0]
            assert (event_type, target_type, target_id) == ("config.changed", "source_intake", intake_id)
            assert json.loads(after_state_json)["trust_classification"] == "trusted"
        finally:
            _close_client(reviewer)
            _close_client(admin)


def test_reconstruction_hash_stable_and_lineage_retry_rebase_explicit() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        client = _build_client(db_path)
        try:
            registered = client.post("/provenance/sources/register", json=_base_payload())
            intake_id = registered.json()["intake_id"]

            validated = client.post(f"/provenance/sources/{intake_id}/validate")
            assert validated.status_code == 200
            approved = client.post(
                f"/provenance/sources/{intake_id}/approve",
                json={"decision": "approve", "comment": "approved for intake"},
            )
            assert approved.status_code == 200

            snapshot = client.post(
                f"/provenance/sources/{intake_id}/snapshot",
                json={"reason": "freeze deterministic intake state"},
            )
            assert snapshot.status_code == 200

            retry_1 = client.post(
                f"/provenance/sources/{intake_id}/lineage/retry",
                json={"reason": "validator timeout"},
            )
            assert retry_1.status_code == 200
            retry_2 = client.post(
                f"/provenance/sources/{intake_id}/lineage/retry",
                json={"reason": "nondeterministic sparse output"},
            )
            assert retry_2.status_code == 200
            rebase = client.post(
                f"/provenance/sources/{intake_id}/lineage/rebase",
                json={
                    "from_commit": "3fa4b8d",
                    "to_commit": "7dc45ac",
                    "reason": "rebase onto v6.12-rc1",
                },
            )
            assert rebase.status_code == 200

            bad_rebase = client.post(
                f"/provenance/sources/{intake_id}/lineage/rebase",
                json={"from_commit": "nope", "to_commit": "still-nope", "reason": "invalid"},
            )
            assert bad_rebase.status_code == 400

            reconstruction_1 = client.get(f"/provenance/sources/{intake_id}/reconstruct")
            reconstruction_2 = client.get(f"/provenance/sources/{intake_id}/reconstruct")
            assert reconstruction_1.status_code == 200
            assert reconstruction_2.status_code == 200
            assert reconstruction_1.json()["reconstruction_hash"] == reconstruction_2.json()["reconstruction_hash"]

            lineage = _lineage_rows(db_path, intake_id)
            assert [stage for stage, _, _ in lineage] == ["retry", "retry", "rebase"]
            payload_retry_1 = json.loads(lineage[0][2])
            payload_retry_2 = json.loads(lineage[1][2])
            payload_rebase = json.loads(lineage[2][2])
            assert payload_retry_1["retry_sequence"] == 1
            assert payload_retry_2["retry_sequence"] == 2
            assert payload_rebase["explicit_rebase"] is True
            assert lineage[0][1] is None
            assert isinstance(lineage[1][1], str) and len(str(lineage[1][1])) == 64
            assert isinstance(lineage[2][1], str) and len(str(lineage[2][1])) == 64

            event_types = [event_type for event_type, _ in _events_for_intake(db_path, intake_id)]
            assert "snapshot_created" in event_types
            assert "retry_recorded" in event_types
            assert "rebase_recorded" in event_types
        finally:
            _close_client(client)


def test_provenance_tables_are_immutable_or_append_only() -> None:
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "provenance.db"
        _create_schema(db_path)
        client = _build_client(db_path)
        try:
            registered = client.post("/provenance/sources/register", json=_base_payload())
            intake_id = registered.json()["intake_id"]
        finally:
            _close_client(client)

        conn = sqlite3.connect(db_path)
        try:
            try:
                conn.execute(
                    "UPDATE source_intakes SET subsystem_owner = 'mutated' WHERE id = ?",
                    (intake_id,),
                )
                conn.commit()
                raise AssertionError("expected source_intakes update to fail")
            except sqlite3.DatabaseError as exc:
                conn.rollback()
                assert "immutable" in str(exc)

            try:
                conn.execute("DELETE FROM source_intakes WHERE id = ?", (intake_id,))
                conn.commit()
                raise AssertionError("expected source_intakes delete to fail")
            except sqlite3.DatabaseError as exc:
                conn.rollback()
                assert "immutable" in str(exc)
        finally:
            conn.close()
