"""Snapshot-bound engineering workflow runtime regression tests."""

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
import pytest

from aura_sdk.models.task import Task, TaskStatus
from aura_sdk.replay import TaskRecorder
from core.config import Config
from core.routers import engineering as engineering_router
from core.routers import tasks as tasks_router
from core.routers.auth import get_current_user


class _QueueStub:
    def __init__(self) -> None:
        self.created: list[Task] = []

    async def create_task(self, task_in, *, requested_by: str) -> Task:
        task = Task(
            agent_type=task_in.agent_type,
            status=TaskStatus.QUEUED,
            priority=task_in.priority,
            input_data=task_in.input_data,
            description=task_in.description,
            requested_by=requested_by,
            max_retries=task_in.max_retries,
        )
        self.created.append(task)
        return task


def _migration_sql(filename: str) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    return (repo_root / "knowledge" / "schema" / filename).read_text(encoding="utf-8")


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
                        'task.created',
                        'task.queued',
                        'task.started',
                        'task.progress',
                        'task.completed',
                        'task.failed',
                        'task.cancelled',
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
        conn.executescript(_migration_sql("019_source_provenance_runtime.sql"))
        conn.executescript(_migration_sql("020_snapshot_bound_engineering_workflow.sql"))
        conn.commit()
    finally:
        conn.close()


def _seed_source_intake(db_path: Path) -> tuple[str, str]:
    intake_id = "intake-001"
    source_snapshot_id = "source-snapshot-001"
    canonical_payload = {
        "downstream_repo_url": "https://example.com/downstream/linux-msm.git",
        "downstream_ref_kind": "branch",
        "downstream_ref": "android-msm-audio",
        "bsp_lineage": "LA.UM.9.15.r1",
        "commit_anchors": ["3fa4b8d"],
        "subsystem_name": "audio-qualcomm",
        "subsystem_owner": "aura-audio",
        "upstream_repo_url": "https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
        "target_kernel": "linux",
        "target_kernel_version": "6.12",
        "maintainer_refs": ["tiwai@suse.de"],
        "patchset_lineage": ["3fa4b8d"],
    }
    canonical_json = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"))
    canonical_hash = "abc123abc123abc123abc123abc123abc123abc123abc123abc123abc123abcd"
    source_snapshot_json = json.dumps(
        {"intake": canonical_payload, "events": [{"event_type": "approved"}]},
        sort_keys=True,
        separators=(",", ":"),
    )
    source_snapshot_hash = "f" * 64

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO source_intakes (
                id, downstream_repo_url, downstream_ref_kind, downstream_ref, bsp_lineage,
                commit_anchors_json, subsystem_name, subsystem_owner, upstream_repo_url,
                target_kernel, target_kernel_version, maintainer_refs_json, patchset_lineage_json,
                registered_by, canonical_json, canonical_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intake_id,
                canonical_payload["downstream_repo_url"],
                canonical_payload["downstream_ref_kind"],
                canonical_payload["downstream_ref"],
                canonical_payload["bsp_lineage"],
                json.dumps(canonical_payload["commit_anchors"]),
                canonical_payload["subsystem_name"],
                canonical_payload["subsystem_owner"],
                canonical_payload["upstream_repo_url"],
                canonical_payload["target_kernel"],
                canonical_payload["target_kernel_version"],
                json.dumps(canonical_payload["maintainer_refs"]),
                json.dumps(canonical_payload["patchset_lineage"]),
                "seed@aura.local",
                canonical_json,
                canonical_hash,
            ),
        )
        for event_type in ("registered", "validated", "classified", "approved"):
            conn.execute(
                """
                INSERT INTO source_intake_events (intake_id, event_type, event_payload, actor, event_hash)
                VALUES (?, ?, '{}', 'seed@aura.local', ?)
                """,
                (intake_id, event_type, f"{event_type}-hash"),
            )
        conn.execute(
            """
            INSERT INTO source_replay_snapshots (
                id, intake_id, replay_identifier, snapshot_json, snapshot_hash, created_by
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                source_snapshot_id,
                intake_id,
                "source-intake:intake-001:events:4",
                source_snapshot_json,
                source_snapshot_hash,
                "seed@aura.local",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return intake_id, source_snapshot_id


def _build_client(db_path: Path) -> tuple[TestClient, dict[str, str], _QueueStub]:
    app = FastAPI()
    app.include_router(engineering_router.router, prefix="/engineering")
    app.include_router(tasks_router.router, prefix="/tasks")

    current_user = {
        "sub": "u-1",
        "email": "reviewer@aura.local",
        "role": "reviewer",
    }
    app.dependency_overrides[get_current_user] = lambda: current_user
    queue = _QueueStub()
    app.state.task_queue = queue

    @asynccontextmanager
    async def _test_get_db():
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            yield db

    original_engineering_get_db = engineering_router.get_db
    engineering_router.get_db = _test_get_db
    client = TestClient(app)
    client._engineering_original_get_db = original_engineering_get_db  # type: ignore[attr-defined]
    return client, current_user, queue


def _close_client(client: TestClient) -> None:
    original = getattr(client, "_engineering_original_get_db", None)
    if original is not None:
        engineering_router.get_db = original
    client.close()


def _freeze_snapshot(client: TestClient, intake_id: str, source_snapshot_id: str) -> str:
    response = client.post(
        "/engineering/snapshots/freeze",
        json={
            "intake_id": intake_id,
            "source_snapshot_id": source_snapshot_id,
            "downstream_repo_url": "https://example.com/downstream/linux-msm.git",
            "downstream_ref_kind": "branch",
            "downstream_ref": "android-msm-audio",
            "downstream_commit_sha": "3fa4b8d",
            "subsystem_classification": "audio-qualcomm",
            "upstream_target_kernel_version": "6.12",
            "upstream_target_branch": "torvalds/master",
            "maintainer_context": ["tiwai@suse.de"],
            "validation_profile_version": "validation-profile-v1",
            "ruleset_version": "ruleset-v1",
            "validation_tool_versions": {
                "checkpatch": "strict-v1",
                "sparse": "strict-v1",
                "clang_build": "clang-18",
            },
            "replay_runtime_version": "replay-v1",
            "governance_policy_version": "gov-v1",
        },
    )
    assert response.status_code == 200
    return response.json()["snapshot_id"]


def _create_workflow(client: TestClient, intake_id: str, snapshot_id: str) -> str:
    response = client.post(
        "/engineering/workflows",
        json={"intake_id": intake_id, "snapshot_id": snapshot_id},
    )
    assert response.status_code == 200
    return response.json()["workflow_id"]


def _task_recorder_seed(db_path: Path, task_id: str) -> None:
    recorder = TaskRecorder(str(db_path))
    recorder.start_task(
        task_id=task_id,
        agent_type="patch_builder",
        seed=42,
        model_version="gpt-4o-2024-08-06",
        rules_path="/rules",
        input_data={"workflow_id": "wf", "task_id": task_id},
    )
    recorder.record_prompt(task_id, "system", "analyze patch")
    recorder.record_response(task_id, "analysis")
    assert recorder.finalize(task_id, {"status": "ok"}) is True


def _set_role(current_user: dict[str, str], role: str, email: str) -> None:
    current_user["role"] = role
    current_user["email"] = email


def _workflow_state(db_path: Path, workflow_id: str) -> dict[str, Any]:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT state, replay_trust_valid, validation_status, governance_state FROM engineering_workflows WHERE id = ?",
            (workflow_id,),
        ).fetchone()
        return {
            "state": row[0],
            "replay_trust_valid": row[1],
            "validation_status": row[2],
            "governance_state": row[3],
        } if row else {}
    finally:
        conn.close()


def test_snapshot_bound_end_to_end_workflow_and_reconstruction():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        intake_id, source_snapshot_id = _seed_source_intake(db_path)
        client, current_user, _ = _build_client(db_path)
        Config.SQLITE_PATH = str(db_path)
        try:
            snapshot_id = _freeze_snapshot(client, intake_id, source_snapshot_id)
            workflow_id = _create_workflow(client, intake_id, snapshot_id)

            bind = client.post(
                f"/engineering/workflows/{workflow_id}/task",
                json={"agent_type": "patch_builder", "priority": "P1", "plugin_domain": "driver"},
            )
            assert bind.status_code == 200
            task_id = bind.json()["task_id"]
            _task_recorder_seed(db_path, task_id)

            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "patch_analysis", "reason": "analysis started"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "transformation_proposal", "reason": "proposal generated"},
            ).status_code == 200

            validation = client.post(
                f"/engineering/workflows/{workflow_id}/validation/run",
                json={"patch_paths": ["sound/soc/qcom/qdsp6.c"]},
            )
            assert validation.status_code == 200
            assert validation.json()["state"] == "governance_review"

            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/request",
                json={"operation": "transformation_proposal", "reason": "needs approval"},
            ).status_code == 200

            _set_role(current_user, "approver", "approver@aura.local")
            decision = client.post(
                f"/engineering/workflows/{workflow_id}/governance/decision",
                json={"operation": "transformation_proposal", "decision": "reject", "reason": "validation failed"},
            )
            assert decision.status_code == 200
            assert decision.json()["state"] == "rejected"

            _set_role(current_user, "reviewer", "reviewer@aura.local")
            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/request",
                json={"operation": "lineage_finalization", "reason": "finalize lineage"},
            ).status_code == 403

            _set_role(current_user, "approver", "approver@aura.local")
            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/request",
                json={"operation": "lineage_finalization", "reason": "finalize lineage"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/decision",
                json={"operation": "lineage_finalization", "decision": "approve", "reason": "approve finalization"},
            ).status_code == 200

            _set_role(current_user, "reviewer", "reviewer@aura.local")
            finalize = client.post(f"/engineering/workflows/{workflow_id}/lineage/finalize")
            assert finalize.status_code == 200
            assert finalize.json()["state"] == "lineage_finalized"

            reconstructed = client.get(f"/engineering/workflows/{workflow_id}/reconstruct")
            assert reconstructed.status_code == 200
            payload = reconstructed.json()
            assert payload["trust_valid"] is True
            assert payload["reconstruction"]["workflow"]["state"] == "lineage_finalized"
            assert payload["reconstruction"]["task_replay"]["integrity_ok"] is True
        finally:
            _close_client(client)


def test_snapshot_mutation_is_rejected_by_immutability_trigger():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        intake_id, source_snapshot_id = _seed_source_intake(db_path)
        client, _, _ = _build_client(db_path)
        try:
            snapshot_id = _freeze_snapshot(client, intake_id, source_snapshot_id)
        finally:
            _close_client(client)

        conn = sqlite3.connect(db_path)
        try:
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(
                    "UPDATE engineering_snapshots SET ruleset_version = 'mutated' WHERE id = ?",
                    (snapshot_id,),
                )
                conn.commit()
        finally:
            conn.close()


def test_detached_engineering_execution_is_rejected():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        _seed_source_intake(db_path)
        client, _, _ = _build_client(db_path)
        try:
            response = client.post(
                "/tasks/",
                json={
                    "agent_type": "patch_builder",
                    "priority": "P1",
                    "description": "detached engineering execution",
                    "input_data": {
                        "workflow_kind": "engineering",
                        "workflow_id": "wf-123",
                    },
                },
            )
            assert response.status_code == 400
            assert "detached_engineering_execution_forbidden" in response.json()["detail"]
        finally:
            _close_client(client)


def test_approval_bypass_is_blocked_for_lineage_finalization():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        intake_id, source_snapshot_id = _seed_source_intake(db_path)
        client, current_user, _ = _build_client(db_path)
        Config.SQLITE_PATH = str(db_path)
        try:
            snapshot_id = _freeze_snapshot(client, intake_id, source_snapshot_id)
            workflow_id = _create_workflow(client, intake_id, snapshot_id)
            bind = client.post(
                f"/engineering/workflows/{workflow_id}/task",
                json={"agent_type": "patch_builder", "priority": "P1", "plugin_domain": "driver"},
            )
            task_id = bind.json()["task_id"]
            _task_recorder_seed(db_path, task_id)

            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "patch_analysis", "reason": "analysis"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "transformation_proposal", "reason": "proposal"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/validation/run",
                json={"patch_paths": []},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/request",
                json={"operation": "transformation_proposal", "reason": "approval"},
            ).status_code == 200
            _set_role(current_user, "approver", "approver@aura.local")
            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/decision",
                json={"operation": "transformation_proposal", "decision": "reject", "reason": "reject"},
            ).status_code == 200

            _set_role(current_user, "reviewer", "reviewer@aura.local")
            blocked = client.post(f"/engineering/workflows/{workflow_id}/lineage/finalize")
            assert blocked.status_code == 409
            assert blocked.json()["detail"] == "lineage_finalization_approval_required"
        finally:
            _close_client(client)


def test_validation_drift_is_reported_and_persisted():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        intake_id, source_snapshot_id = _seed_source_intake(db_path)
        client, _, _ = _build_client(db_path)
        Config.SQLITE_PATH = str(db_path)
        try:
            snapshot_id = _freeze_snapshot(client, intake_id, source_snapshot_id)
            workflow_id = _create_workflow(client, intake_id, snapshot_id)
            assert client.post(
                f"/engineering/workflows/{workflow_id}/task",
                json={"agent_type": "patch_builder", "priority": "P1"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "patch_analysis", "reason": "analysis"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "transformation_proposal", "reason": "proposal"},
            ).status_code == 200

            validation = client.post(
                f"/engineering/workflows/{workflow_id}/validation/run",
                json={"patch_paths": ["vendor/qcom/audio.c"]},
            )
            assert validation.status_code == 200
            payload = validation.json()
            assert payload["validation_status"] == "failed"
            clang_result = [item for item in payload["results"] if item["tool_name"] == "clang_build"][0]
            assert any("version_drift" in finding for finding in clang_result["findings"])
            forbidden_result = [item for item in payload["results"] if item["tool_name"] == "forbidden_path"][0]
            assert forbidden_result["passed"] is False
        finally:
            _close_client(client)


def test_retry_lineage_is_monotonic_and_replay_failure_invalidates_trust():
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "engineering.db"
        _create_schema(db_path)
        intake_id, source_snapshot_id = _seed_source_intake(db_path)
        client, current_user, _ = _build_client(db_path)
        Config.SQLITE_PATH = str(db_path)
        try:
            snapshot_id = _freeze_snapshot(client, intake_id, source_snapshot_id)
            workflow_id = _create_workflow(client, intake_id, snapshot_id)
            assert client.post(
                f"/engineering/workflows/{workflow_id}/task",
                json={"agent_type": "patch_builder", "priority": "P1"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "patch_analysis", "reason": "analysis"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/transition",
                json={"to_state": "transformation_proposal", "reason": "proposal"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/validation/run",
                json={"patch_paths": []},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/lineage/retry",
                json={"reason": "retry one"},
            ).status_code == 200
            assert client.post(
                f"/engineering/workflows/{workflow_id}/lineage/retry",
                json={"reason": "retry two"},
            ).status_code == 200

            assert client.post(
                f"/engineering/workflows/{workflow_id}/governance/request",
                json={"operation": "transformation_proposal", "reason": "approve"},
            ).status_code == 200
            _set_role(current_user, "admin", "admin@aura.local")
            decision = client.post(
                f"/engineering/workflows/{workflow_id}/governance/decision",
                json={
                    "operation": "transformation_proposal",
                    "decision": "approve",
                    "reason": "manual override",
                },
            )
            assert decision.status_code == 200
            assert decision.json()["state"] == "rejected"
            assert decision.json()["decision"] == "approved_but_replay_failed"

            state = _workflow_state(db_path, workflow_id)
            assert state["replay_trust_valid"] == 0
            assert state["state"] == "rejected"

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    """
                    SELECT json_extract(lineage_payload, '$.retry_sequence') AS seq
                    FROM source_lineage_entries
                    WHERE intake_id = ? AND lineage_stage = 'retry'
                    ORDER BY created_at, rowid
                    """,
                    (intake_id,),
                ).fetchall()
                assert [int(row[0]) for row in rows] == [1, 2]
            finally:
                conn.close()
        finally:
            _close_client(client)
