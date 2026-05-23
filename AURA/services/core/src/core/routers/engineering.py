"""Snapshot-bound engineering workflow runtime endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.agent import AgentType
from aura_sdk.models.event import EventType
from aura_sdk.models.task import TaskCreate, TaskPriority
from aura_sdk.replay import ReplayEngine, TaskRecorder
from core.config import Config
from core.events import publish_event
from core.routers.auth import get_current_user
from core.services.task_queue import TaskQueueManager

logger = get_logger("core.engineering")
router = APIRouter()

_REVIEWER_ROLES = {"reviewer", "approver", "architect", "admin"}
_APPROVER_ROLES = {"approver", "architect", "admin"}
_ADMIN_ROLES = {"architect", "admin"}

_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
_REF_KIND_VALUES = {"branch", "tag", "commit"}
_WORKFLOW_STATES = {
    "source_intake",
    "snapshot_frozen",
    "task_created",
    "patch_analysis",
    "transformation_proposal",
    "validation_running",
    "governance_review",
    "replay_persisted",
    "approved",
    "rejected",
    "lineage_finalized",
}
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "source_intake": {"snapshot_frozen"},
    "snapshot_frozen": {"task_created"},
    "task_created": {"patch_analysis"},
    "patch_analysis": {"transformation_proposal"},
    "transformation_proposal": {"validation_running"},
    "validation_running": {"governance_review"},
    "governance_review": {"replay_persisted", "rejected"},
    "replay_persisted": {"approved", "rejected"},
    "approved": {"lineage_finalized"},
    "rejected": {"lineage_finalized"},
    "lineage_finalized": set(),
}

_GOVERNANCE_OPERATIONS = {"transformation_proposal", "lineage_finalization"}
_VALIDATION_TOOLS = ("checkpatch", "sparse", "clang_build", "forbidden_path", "lineage_integrity")
_FORBIDDEN_PATH_PREFIXES = ("drivers/staging/", "vendor/", "out/", "tmp/")


class SnapshotFreezeRequest(BaseModel):
    intake_id: str
    source_snapshot_id: str
    downstream_repo_url: str = ""
    downstream_ref_kind: str = "branch"
    downstream_ref: str = ""
    downstream_commit_sha: str = ""
    subsystem_classification: str = ""
    upstream_target_kernel_version: str = ""
    upstream_target_branch: str = ""
    maintainer_context: list[str] = Field(default_factory=list)
    validation_profile_version: str = ""
    ruleset_version: str = ""
    validation_tool_versions: dict[str, str] = Field(default_factory=dict)
    replay_runtime_version: str = ""
    governance_policy_version: str = ""


class WorkflowCreateRequest(BaseModel):
    intake_id: str
    snapshot_id: str
    provenance_lineage_hash: str = ""


class WorkflowTaskRequest(BaseModel):
    agent_type: AgentType = AgentType.PATCH_BUILDER
    priority: TaskPriority = TaskPriority.NORMAL
    description: str = "snapshot-bound engineering task"
    plugin_domain: str = "driver"
    input_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowTransitionRequest(BaseModel):
    to_state: str
    reason: str = ""


class ValidationRunRequest(BaseModel):
    target_path: str = ""
    patch_paths: list[str] = Field(default_factory=list)
    build_probe_file: str = ""


class GovernanceRequest(BaseModel):
    operation: str = "transformation_proposal"
    reason: str = ""


class GovernanceDecisionRequest(BaseModel):
    operation: str = "transformation_proposal"
    decision: str = "approve"  # approve|reject
    reason: str = ""


class EvidenceLinkRequest(BaseModel):
    evidence_type: str
    evidence_ref: str
    evidence_content: str = ""


class RetryRecordRequest(BaseModel):
    reason: str = ""


def _require_role(current_user: dict[str, Any], allowed_roles: set[str], action: str) -> None:
    role = str(current_user.get("role") or "viewer").strip().lower()
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"insufficient_role_for_{action}:{role}")


def _normalize(value: Any) -> str:
    return str(value or "").strip()


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_commit_hash(value: str) -> bool:
    return bool(_COMMIT_RE.fullmatch(_normalize(value).lower()))


def _unix_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _version_commands(tool_name: str) -> list[list[str]]:
    if tool_name == "checkpatch":
        base = os.environ.get("AURA_CHECKPATCH_CMD", "checkpatch.pl")
    elif tool_name == "sparse":
        base = os.environ.get("AURA_SPARSE_CMD", "sparse")
    else:
        base = os.environ.get("AURA_CLANG_CMD", "clang")
    tokens = shlex.split(base)
    if not tokens:
        return []
    return [tokens + ["--version"], tokens + ["-v"]]


def _first_line(raw: str) -> str:
    for line in raw.splitlines():
        val = line.strip()
        if val:
            return val
    return ""


def _run_subprocess_sync(argv: list[str], timeout_seconds: float = 6.0) -> tuple[bool, int, str, str]:
    if not argv:
        return False, 127, "", "missing command"
    binary = argv[0]
    if not Path(binary).is_absolute() and shutil.which(binary) is None:
        return False, 127, "", f"command_not_found:{binary}"
    try:
        proc = subprocess.run(
            argv,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        return True, int(proc.returncode), proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return True, 124, "", "timeout"
    except Exception as exc:
        return False, 127, "", str(exc)


async def _probe_tool_version(tool_name: str) -> tuple[bool, str, list[str]]:
    findings: list[str] = []
    commands = _version_commands(tool_name)
    if not commands:
        return False, "unconfigured", ["tool_command_unconfigured"]

    available = False
    version_text = ""
    for argv in commands:
        ok, code, out, err = await asyncio.to_thread(_run_subprocess_sync, argv, 6.0)
        if ok:
            available = True
        line = _first_line(out) or _first_line(err)
        if line:
            version_text = line
        if ok and code == 0:
            break
    if not available:
        findings.append(f"tool_unavailable:{tool_name}")
        return False, "unavailable", findings
    if not version_text:
        version_text = "unknown"
        findings.append(f"version_probe_nonzero_or_empty:{tool_name}")
    return True, version_text, findings


async def _lineage_integrity_findings(intake_id: str) -> tuple[bool, list[str]]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT lineage_stage, parent_lineage_hash, lineage_hash
            FROM source_lineage_entries
            WHERE intake_id = ?
            ORDER BY created_at, rowid
            """,
            (intake_id,),
        )
        rows = await cursor.fetchall()

    findings: list[str] = []
    if not rows:
        return True, ["lineage_chain_empty_for_intake"]

    previous_hash = ""
    for idx, row in enumerate(rows):
        parent_hash = _normalize(row["parent_lineage_hash"])
        lineage_hash = _normalize(row["lineage_hash"])
        if idx == 0:
            if parent_hash:
                findings.append("first_lineage_parent_should_be_empty")
        else:
            if parent_hash != previous_hash:
                findings.append(f"lineage_parent_mismatch_at_index:{idx}")
        previous_hash = lineage_hash
    return len(findings) == 0, findings


async def _audit_row(
    db: Any,
    *,
    current_user: dict[str, Any],
    event_type: str,
    target_type: str,
    target_id: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> None:
    await db.execute(
        """
        INSERT INTO audit_ledger
        (timestamp, user_id, session_id, event_type, target_type, target_id, before_state, after_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _unix_ts(),
            _normalize(current_user.get("sub")),
            _normalize(current_user.get("email")) or "unknown",
            event_type,
            target_type,
            target_id,
            _stable_json(before_state),
            _stable_json(after_state),
        ),
    )


async def _append_workflow_event(
    db: Any,
    *,
    workflow_id: str,
    event_type: str,
    from_state: str = "",
    to_state: str = "",
    payload: dict[str, Any],
    actor: str,
) -> int:
    payload_json = _stable_json(payload)
    event_hash = _sha256(
        f"{workflow_id}|{event_type}|{from_state}|{to_state}|{payload_json}|{actor}"
    )
    cursor = await db.execute(
        """
        INSERT INTO engineering_workflow_events
        (workflow_id, event_type, from_state, to_state, event_payload, actor, event_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workflow_id,
            event_type,
            from_state or None,
            to_state or None,
            payload_json,
            actor,
            event_hash,
        ),
    )
    return int(cursor.lastrowid)


async def _load_row(sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute(sql, params)
        row = await cursor.fetchone()
    if row is None:
        return {}
    return dict(row)


async def _load_intake(intake_id: str) -> dict[str, Any]:
    row = await _load_row("SELECT * FROM source_intakes WHERE id = ?", (intake_id,))
    if not row:
        raise HTTPException(status_code=404, detail=f"source_intake_not_found:{intake_id}")
    row["canonical_payload"] = json.loads(row.get("canonical_json") or "{}")
    return row


async def _latest_intake_approval_state(intake_id: str) -> str:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT event_type
            FROM source_intake_events
            WHERE intake_id = ?
            ORDER BY id
            """,
            (intake_id,),
        )
        rows = await cursor.fetchall()
    state = "pending"
    for row in rows:
        event_type = _normalize(row["event_type"])
        if event_type == "approved":
            state = "approved"
        elif event_type == "rejected":
            state = "rejected"
    return state


async def _load_source_snapshot(intake_id: str, source_snapshot_id: str) -> dict[str, Any]:
    row = await _load_row(
        """
        SELECT *
        FROM source_replay_snapshots
        WHERE id = ? AND intake_id = ?
        """,
        (source_snapshot_id, intake_id),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"source_snapshot_not_found:{source_snapshot_id}")
    return row


async def _load_engineering_snapshot(snapshot_id: str) -> dict[str, Any]:
    row = await _load_row(
        "SELECT * FROM engineering_snapshots WHERE id = ?",
        (snapshot_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"engineering_snapshot_not_found:{snapshot_id}")
    row["snapshot"] = json.loads(row.get("snapshot_json") or "{}")
    row["maintainer_context"] = json.loads(row.get("maintainer_context_json") or "[]")
    row["validation_tool_versions"] = json.loads(row.get("validation_tool_versions_json") or "{}")
    return row


async def _load_workflow(workflow_id: str) -> dict[str, Any]:
    row = await _load_row("SELECT * FROM engineering_workflows WHERE id = ?", (workflow_id,))
    if not row:
        raise HTTPException(status_code=404, detail=f"engineering_workflow_not_found:{workflow_id}")
    return row


async def _latest_lineage_hash(intake_id: str) -> str:
    row = await _load_row(
        """
        SELECT lineage_hash
        FROM source_lineage_entries
        WHERE intake_id = ?
        ORDER BY created_at DESC, rowid DESC
        LIMIT 1
        """,
        (intake_id,),
    )
    return _normalize(row.get("lineage_hash"))


def _get_task_queue(request: Request) -> TaskQueueManager:
    queue: TaskQueueManager | None = getattr(request.app.state, "task_queue", None)
    if queue is None:
        raise HTTPException(status_code=503, detail="task_queue_manager_unavailable")
    return queue


async def _transition_workflow(
    *,
    workflow_id: str,
    to_state: str,
    current_user: dict[str, Any],
    reason: str,
    event_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_state = _normalize(to_state)
    if target_state not in _WORKFLOW_STATES:
        raise HTTPException(status_code=400, detail=f"invalid_workflow_state:{target_state}")

    actor = _normalize(current_user.get("email")) or "unknown"
    payload = dict(event_payload or {})
    payload["reason"] = _normalize(reason)

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                "SELECT id, state FROM engineering_workflows WHERE id = ?",
                (workflow_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"engineering_workflow_not_found:{workflow_id}")
            current_state = _normalize(row["state"])
            if target_state == current_state:
                raise HTTPException(status_code=409, detail=f"workflow_already_in_state:{target_state}")
            allowed = _ALLOWED_TRANSITIONS.get(current_state, set())
            if target_state not in allowed:
                raise HTTPException(
                    status_code=409,
                    detail=f"invalid_workflow_transition:{current_state}->{target_state}",
                )

            await db.execute(
                "UPDATE engineering_workflows SET state = ?, updated_at = ? WHERE id = ? AND state = ?",
                (target_state, _unix_ts(), workflow_id, current_state),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="state_transition",
                from_state=current_state,
                to_state=target_state,
                payload=payload,
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="task.progress",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"state": current_state},
                after_state={"state": target_state, "reason": _normalize(reason)},
            )
            await db.commit()
            return {"workflow_id": workflow_id, "from_state": current_state, "to_state": target_state}
        except HTTPException:
            await db.rollback()
            raise
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_workflow_transition_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="workflow_transition_failed") from exc


@router.post("/snapshots/freeze")
async def freeze_engineering_snapshot(
    request: SnapshotFreezeRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "snapshot_freeze")
    intake = await _load_intake(_normalize(request.intake_id))
    _ = await _load_source_snapshot(_normalize(request.intake_id), _normalize(request.source_snapshot_id))

    intake_approval = await _latest_intake_approval_state(_normalize(request.intake_id))
    if intake_approval != "approved":
        raise HTTPException(status_code=409, detail="intake_not_approved_for_snapshot")

    ref_kind = _normalize(request.downstream_ref_kind).lower()
    if ref_kind not in _REF_KIND_VALUES:
        raise HTTPException(status_code=400, detail=f"invalid_downstream_ref_kind:{ref_kind}")
    commit_sha = _normalize(request.downstream_commit_sha).lower()
    if not _is_commit_hash(commit_sha):
        raise HTTPException(status_code=400, detail="invalid_downstream_commit_sha")

    maintainer_context = sorted(dict.fromkeys([_normalize(v) for v in request.maintainer_context if _normalize(v)]))
    validation_tool_versions = {
        _normalize(k): _normalize(v)
        for k, v in request.validation_tool_versions.items()
        if _normalize(k)
    }

    snapshot_payload = {
        "downstream": {
            "repo_url": _normalize(request.downstream_repo_url) or _normalize(intake["downstream_repo_url"]),
            "ref_kind": ref_kind,
            "ref": _normalize(request.downstream_ref) or _normalize(intake["downstream_ref"]),
            "commit_sha": commit_sha,
            "subsystem_classification": _normalize(request.subsystem_classification) or _normalize(intake["subsystem_name"]),
        },
        "upstream": {
            "target_kernel_version": _normalize(request.upstream_target_kernel_version),
            "target_branch_tree": _normalize(request.upstream_target_branch),
            "maintainer_context": maintainer_context,
            "validation_profile_version": _normalize(request.validation_profile_version),
        },
        "system": {
            "ruleset_version": _normalize(request.ruleset_version),
            "validation_tool_versions": validation_tool_versions,
            "replay_runtime_version": _normalize(request.replay_runtime_version),
            "governance_policy_version": _normalize(request.governance_policy_version),
        },
        "provenance": {
            "intake_id": _normalize(request.intake_id),
            "source_snapshot_id": _normalize(request.source_snapshot_id),
            "canonical_hash": _normalize(intake["canonical_hash"]),
        },
    }

    required_fields = [
        snapshot_payload["downstream"]["repo_url"],
        snapshot_payload["downstream"]["ref"],
        snapshot_payload["upstream"]["target_kernel_version"],
        snapshot_payload["upstream"]["target_branch_tree"],
        snapshot_payload["upstream"]["validation_profile_version"],
        snapshot_payload["system"]["ruleset_version"],
        snapshot_payload["system"]["replay_runtime_version"],
        snapshot_payload["system"]["governance_policy_version"],
    ]
    if any(not value for value in required_fields):
        raise HTTPException(status_code=400, detail="missing_required_snapshot_fields")

    snapshot_json = _stable_json(snapshot_payload)
    snapshot_hash = _sha256(snapshot_json)
    actor = _normalize(current_user.get("email")) or "unknown"

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                """
                INSERT INTO engineering_snapshots (
                    intake_id, source_snapshot_id, downstream_repo_url, downstream_ref_kind,
                    downstream_ref, downstream_commit_sha, subsystem_name,
                    upstream_target_kernel_version, upstream_target_branch, maintainer_context_json,
                    validation_profile_version, ruleset_version, validation_tool_versions_json,
                    replay_runtime_version, governance_policy_version, created_by,
                    snapshot_json, snapshot_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _normalize(request.intake_id),
                    _normalize(request.source_snapshot_id),
                    snapshot_payload["downstream"]["repo_url"],
                    ref_kind,
                    snapshot_payload["downstream"]["ref"],
                    commit_sha,
                    snapshot_payload["downstream"]["subsystem_classification"],
                    snapshot_payload["upstream"]["target_kernel_version"],
                    snapshot_payload["upstream"]["target_branch_tree"],
                    _stable_json(maintainer_context),
                    snapshot_payload["upstream"]["validation_profile_version"],
                    snapshot_payload["system"]["ruleset_version"],
                    _stable_json(validation_tool_versions),
                    snapshot_payload["system"]["replay_runtime_version"],
                    snapshot_payload["system"]["governance_policy_version"],
                    actor,
                    snapshot_json,
                    snapshot_hash,
                ),
            )
            row_cursor = await db.execute(
                "SELECT id FROM engineering_snapshots WHERE snapshot_hash = ?",
                (snapshot_hash,),
            )
            row = await row_cursor.fetchone()
            snapshot_id = _normalize(row["id"]) if row else ""

            await _audit_row(
                db,
                current_user=current_user,
                event_type="config.changed",
                target_type="engineering_snapshot",
                target_id=snapshot_id,
                before_state={},
                after_state={"snapshot_hash": snapshot_hash, "intake_id": _normalize(request.intake_id)},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            text = str(exc).lower()
            if "unique" in text and "snapshot_hash" in text:
                raise HTTPException(status_code=409, detail="duplicate_engineering_snapshot") from exc
            raise

    return {
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "intake_id": _normalize(request.intake_id),
        "status": "snapshot_frozen",
    }


@router.post("/workflows")
async def create_engineering_workflow(
    request: WorkflowCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_create")
    snapshot = await _load_engineering_snapshot(_normalize(request.snapshot_id))
    if _normalize(snapshot["intake_id"]) != _normalize(request.intake_id):
        raise HTTPException(status_code=409, detail="snapshot_intake_mismatch")

    actor = _normalize(current_user.get("email")) or "unknown"
    lineage_hash = _normalize(request.provenance_lineage_hash)
    if not lineage_hash:
        lineage_hash = await _latest_lineage_hash(_normalize(request.intake_id))
    if not lineage_hash:
        intake = await _load_intake(_normalize(request.intake_id))
        lineage_hash = _normalize(intake["canonical_hash"])
    if not lineage_hash:
        raise HTTPException(status_code=409, detail="missing_provenance_lineage_hash")

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                """
                INSERT INTO engineering_workflows (
                    intake_id, snapshot_id, provenance_lineage_hash, state, created_by
                ) VALUES (?, ?, ?, 'source_intake', ?)
                """,
                (
                    _normalize(request.intake_id),
                    _normalize(request.snapshot_id),
                    lineage_hash,
                    actor,
                ),
            )
            workflow_id = str(cursor.lastrowid)
            row_cursor = await db.execute(
                """
                SELECT id FROM engineering_workflows
                WHERE intake_id = ? AND snapshot_id = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (_normalize(request.intake_id), _normalize(request.snapshot_id)),
            )
            row = await row_cursor.fetchone()
            workflow_id = _normalize(row["id"]) if row else workflow_id

            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="state_transition",
                from_state="",
                to_state="source_intake",
                payload={"reason": "workflow_created_from_snapshot"},
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="task.created",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={},
                after_state={
                    "state": "source_intake",
                    "snapshot_id": _normalize(request.snapshot_id),
                    "lineage_hash": lineage_hash,
                },
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_workflow_create_failed", error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_workflow_create_failed") from exc

    transition = await _transition_workflow(
        workflow_id=workflow_id,
        to_state="snapshot_frozen",
        current_user=current_user,
        reason="snapshot_root_confirmed",
        event_payload={"snapshot_id": _normalize(request.snapshot_id)},
    )

    return {
        "workflow_id": workflow_id,
        "snapshot_id": _normalize(request.snapshot_id),
        "intake_id": _normalize(request.intake_id),
        "state": transition["to_state"],
        "provenance_lineage_hash": lineage_hash,
    }


@router.post("/workflows/{workflow_id}/task")
async def bind_snapshot_task(
    workflow_id: str,
    body: WorkflowTaskRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_task_bind")
    workflow = await _load_workflow(workflow_id)
    if _normalize(workflow["state"]) != "snapshot_frozen":
        raise HTTPException(status_code=409, detail="workflow_not_ready_for_task_binding")

    queue = _get_task_queue(request)
    plugin_domain = _normalize(body.plugin_domain).lower() or "driver"
    runtime_scope = f"domain:{plugin_domain}"
    input_data = dict(body.input_data or {})
    input_data["workflow_kind"] = "engineering"
    input_data["workflow_id"] = workflow_id
    input_data["intake_id"] = _normalize(workflow["intake_id"])
    input_data["snapshot_id"] = _normalize(workflow["snapshot_id"])
    input_data["provenance_lineage_hash"] = _normalize(workflow["provenance_lineage_hash"])
    input_data["plugin_domain"] = plugin_domain
    input_data["runtime_cell_scope"] = runtime_scope

    created = await queue.create_task(
        TaskCreate(
            agent_type=body.agent_type,
            priority=body.priority,
            input_data=input_data,
            description=_normalize(body.description),
        ),
        requested_by=_normalize(current_user.get("email")) or "unknown",
    )

    transition = await _transition_workflow(
        workflow_id=workflow_id,
        to_state="task_created",
        current_user=current_user,
        reason="snapshot_bound_task_created",
        event_payload={"task_id": created.id, "agent_type": body.agent_type.value},
    )

    actor = _normalize(current_user.get("email")) or "unknown"
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                "UPDATE engineering_workflows SET task_id = ?, updated_at = ? WHERE id = ?",
                (created.id, _unix_ts(), workflow_id),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="task_bound",
                from_state=transition["from_state"],
                to_state=transition["to_state"],
                payload={
                    "task_id": created.id,
                    "agent_type": body.agent_type.value,
                    "priority": body.priority.value,
                    "runtime_cell_scope": runtime_scope,
                },
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="task.created",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"task_id": _normalize(workflow.get("task_id"))},
                after_state={"task_id": created.id, "state": "task_created"},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_workflow_task_bind_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="workflow_task_bind_failed") from exc

    await publish_event(
        request,
        EventType.TASK_CREATED,
        {
            "task_id": created.id,
            "workflow_id": workflow_id,
            "agent_type": body.agent_type.value,
            "plugin_domain": plugin_domain,
            "runtime_cell_scope": runtime_scope,
            "requested_by": actor,
        },
        task_id=created.id,
        agent_type=body.agent_type.value,
        trace_id=workflow_id,
    )
    await publish_event(
        request,
        EventType.TASK_QUEUED,
        {
            "task_id": created.id,
            "workflow_id": workflow_id,
            "status": "queued",
            "plugin_domain": plugin_domain,
            "runtime_cell_scope": runtime_scope,
        },
        task_id=created.id,
        agent_type=body.agent_type.value,
        trace_id=workflow_id,
    )

    return {
        "workflow_id": workflow_id,
        "task_id": created.id,
        "state": "task_created",
        "snapshot_id": _normalize(workflow["snapshot_id"]),
    }


@router.post("/workflows/{workflow_id}/transition")
async def transition_workflow(
    workflow_id: str,
    body: WorkflowTransitionRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_transition")
    result = await _transition_workflow(
        workflow_id=workflow_id,
        to_state=body.to_state,
        current_user=current_user,
        reason=body.reason,
    )
    return {"workflow_id": workflow_id, "state": result["to_state"]}


@router.post("/workflows/{workflow_id}/validation/run")
async def run_workflow_validation(
    workflow_id: str,
    body: ValidationRunRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_validation_run")
    workflow = await _load_workflow(workflow_id)
    snapshot = await _load_engineering_snapshot(_normalize(workflow["snapshot_id"]))

    if _normalize(workflow["state"]) == "transformation_proposal":
        await _transition_workflow(
            workflow_id=workflow_id,
            to_state="validation_running",
            current_user=current_user,
            reason="validation_run_started",
        )
        workflow = await _load_workflow(workflow_id)

    if _normalize(workflow["state"]) != "validation_running":
        raise HTTPException(status_code=409, detail="workflow_not_in_validation_state")

    expected_versions: dict[str, str] = snapshot.get("validation_tool_versions") or {}
    patch_paths = [p.strip() for p in body.patch_paths if p.strip()]
    actor = _normalize(current_user.get("email")) or "unknown"

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COALESCE(MAX(run_sequence), 0) AS max_run FROM engineering_validation_runs WHERE workflow_id = ?",
            (workflow_id,),
        )
        row = await cursor.fetchone()
        run_sequence = int(row["max_run"] or 0) + 1

    results: list[dict[str, Any]] = []
    for tool_name in _VALIDATION_TOOLS:
        findings: list[str] = []
        passed = True
        confidence = 1.0
        version = ""

        if tool_name in {"checkpatch", "sparse", "clang_build"}:
            available, observed_version, probe_findings = await _probe_tool_version(tool_name)
            findings.extend(probe_findings)
            version = observed_version
            if not available:
                passed = False
            expected = _normalize(expected_versions.get(tool_name))
            if expected and expected not in observed_version:
                passed = False
                findings.append(f"version_drift:{tool_name}:expected={expected}:observed={observed_version}")
            if tool_name == "clang_build" and body.build_probe_file.strip():
                probe_file = Path(body.build_probe_file.strip())
                if probe_file.exists():
                    argv = shlex.split(os.environ.get("AURA_CLANG_CMD", "clang")) + [
                        "-fsyntax-only",
                        str(probe_file),
                    ]
                    ok, code, out, err = await asyncio.to_thread(_run_subprocess_sync, argv, 20.0)
                    _ = out
                    if not ok or code != 0:
                        passed = False
                        findings.append(f"clang_build_probe_failed:{_first_line(err) or 'nonzero_exit'}")
        elif tool_name == "forbidden_path":
            version = "builtin-v1"
            forbidden = [
                path for path in patch_paths
                if any(path.startswith(prefix) for prefix in _FORBIDDEN_PATH_PREFIXES)
            ]
            if forbidden:
                passed = False
                findings.extend([f"forbidden_path:{path}" for path in forbidden])
            else:
                findings.append("forbidden_path_check_passed")
        else:
            version = "builtin-v1"
            ok, lineage_findings = await _lineage_integrity_findings(_normalize(workflow["intake_id"]))
            if not ok:
                passed = False
            findings.extend(lineage_findings)

        if not passed:
            confidence = 0.4
        output_hash = _sha256(_stable_json({"tool": tool_name, "version": version, "passed": passed, "findings": findings}))
        results.append(
            {
                "tool_name": tool_name,
                "tool_version": version,
                "passed": passed,
                "findings": findings,
                "confidence": confidence,
                "output_hash": output_hash,
            }
        )

    all_passed = all(item["passed"] for item in results)
    validation_status = "passed" if all_passed else "failed"

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            for item in results:
                await db.execute(
                    """
                    INSERT INTO engineering_validation_runs (
                        workflow_id, snapshot_id, run_sequence, tool_name, tool_version,
                        passed, findings_json, confidence, output_hash, created_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workflow_id,
                        _normalize(workflow["snapshot_id"]),
                        run_sequence,
                        item["tool_name"],
                        item["tool_version"],
                        1 if item["passed"] else 0,
                        _stable_json(item["findings"]),
                        float(item["confidence"]),
                        item["output_hash"],
                        actor,
                    ),
                )
            await db.execute(
                "UPDATE engineering_workflows SET validation_status = ?, updated_at = ? WHERE id = ?",
                (validation_status, _unix_ts(), workflow_id),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="validation_recorded",
                from_state="validation_running",
                to_state="validation_running",
                payload={
                    "run_sequence": run_sequence,
                    "validation_status": validation_status,
                    "all_passed": all_passed,
                    "tools": [{k: v for k, v in item.items() if k != "output_hash"} for item in results],
                },
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="task.completed" if all_passed else "task.failed",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"validation_status": _normalize(workflow["validation_status"])},
                after_state={"validation_status": validation_status, "run_sequence": run_sequence},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_validation_run_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_validation_run_failed") from exc

    if _normalize((await _load_workflow(workflow_id))["state"]) == "validation_running":
        await _transition_workflow(
            workflow_id=workflow_id,
            to_state="governance_review",
            current_user=current_user,
            reason="validation_completed",
            event_payload={"validation_status": validation_status, "run_sequence": run_sequence},
        )

    return {
        "workflow_id": workflow_id,
        "run_sequence": run_sequence,
        "validation_status": validation_status,
        "results": results,
        "state": "governance_review",
    }


@router.post("/workflows/{workflow_id}/governance/request")
async def request_governance(
    workflow_id: str,
    body: GovernanceRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_governance_request")
    workflow = await _load_workflow(workflow_id)
    operation = _normalize(body.operation)
    if operation not in _GOVERNANCE_OPERATIONS:
        raise HTTPException(status_code=400, detail=f"invalid_governance_operation:{operation}")
    workflow_state = _normalize(workflow["state"])
    if operation == "transformation_proposal":
        if workflow_state != "governance_review":
            raise HTTPException(status_code=409, detail="workflow_not_in_governance_review")
    elif operation == "lineage_finalization":
        _require_role(current_user, _APPROVER_ROLES, "lineage_finalization_request")
        if workflow_state not in {"approved", "rejected"}:
            raise HTTPException(status_code=409, detail="workflow_not_ready_for_lineage_finalization")

    actor = _normalize(current_user.get("email")) or "unknown"
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                """
                INSERT INTO engineering_governance_actions
                (workflow_id, operation, status, reason, requested_by, decided_by)
                VALUES (?, ?, 'requested', ?, ?, '')
                """,
                (workflow_id, operation, _normalize(body.reason), actor),
            )
            action_id = int(cursor.lastrowid)
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="governance_requested",
                from_state="governance_review",
                to_state="governance_review",
                payload={"action_id": action_id, "operation": operation, "reason": _normalize(body.reason)},
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="approval.submitted",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"governance_state": _normalize(workflow["governance_state"])},
                after_state={"governance_state": "pending", "operation": operation},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_governance_request_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_governance_request_failed") from exc

    return {
        "workflow_id": workflow_id,
        "action_id": action_id,
        "operation": operation,
        "status": "requested",
    }


@router.post("/workflows/{workflow_id}/governance/decision")
async def decide_governance(
    workflow_id: str,
    body: GovernanceDecisionRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _APPROVER_ROLES, "workflow_governance_decision")
    operation = _normalize(body.operation)
    decision = _normalize(body.decision).lower()
    if operation not in _GOVERNANCE_OPERATIONS:
        raise HTTPException(status_code=400, detail=f"invalid_governance_operation:{operation}")
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail=f"invalid_governance_decision:{decision}")

    workflow = await _load_workflow(workflow_id)
    actor = _normalize(current_user.get("email")) or "unknown"
    decision_status = "approved" if decision == "approve" else "rejected"

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            cursor = await db.execute(
                """
                SELECT id, status, requested_by
                FROM engineering_governance_actions
                WHERE workflow_id = ? AND operation = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (workflow_id, operation),
            )
            latest = await cursor.fetchone()
            if latest is None or _normalize(latest["status"]) != "requested":
                raise HTTPException(status_code=409, detail="no_pending_governance_request")

            if (
                operation == "transformation_proposal"
                and decision == "approve"
                and _normalize(workflow["validation_status"]) == "failed"
            ):
                _require_role(current_user, _ADMIN_ROLES, "approve_failed_validation")
                if not _normalize(body.reason):
                    raise HTTPException(status_code=400, detail="approval_reason_required_for_failed_validation")

            await db.execute(
                """
                INSERT INTO engineering_governance_actions
                (workflow_id, operation, status, reason, requested_by, decided_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    workflow_id,
                    operation,
                    decision_status,
                    _normalize(body.reason),
                    _normalize(latest["requested_by"]),
                    actor,
                ),
            )
            await db.execute(
                "UPDATE engineering_workflows SET governance_state = ?, updated_at = ? WHERE id = ?",
                (decision_status, _unix_ts(), workflow_id),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="governance_decided",
                from_state=_normalize(workflow["state"]),
                to_state=_normalize(workflow["state"]),
                payload={"operation": operation, "decision": decision_status, "reason": _normalize(body.reason)},
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="approval.granted" if decision == "approve" else "approval.rejected",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"governance_state": _normalize(workflow["governance_state"])},
                after_state={"governance_state": decision_status, "operation": operation},
            )
            await db.commit()
        except HTTPException:
            await db.rollback()
            raise
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_governance_decision_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_governance_decision_failed") from exc

    await publish_event(
        request,
        EventType.APPROVAL_GRANTED if decision == "approve" else EventType.APPROVAL_REJECTED,
        {
            "workflow_id": workflow_id,
            "operation": operation,
            "decision": decision_status,
            "reason": _normalize(body.reason),
        },
        task_id=_normalize(workflow.get("task_id")),
        trace_id=workflow_id,
    )

    if operation == "transformation_proposal":
        if decision == "reject":
            transition = await _transition_workflow(
                workflow_id=workflow_id,
                to_state="rejected",
                current_user=current_user,
                reason="governance_rejected_transformation",
            )
            return {"workflow_id": workflow_id, "state": transition["to_state"], "decision": decision_status}

        first = await _transition_workflow(
            workflow_id=workflow_id,
            to_state="replay_persisted",
            current_user=current_user,
            reason="governance_approved_transformation",
        )

        task_id = _normalize((await _load_workflow(workflow_id)).get("task_id"))
        replay_ok = False
        replay_error = ""
        replay_payload: dict[str, Any] = {}
        integrity_ok = False
        if task_id:
            engine = ReplayEngine(TaskRecorder(Config.SQLITE_PATH))
            replay_payload = await engine.replay(task_id)
            integrity_ok = engine.verify_integrity(task_id)
            replay_ok = bool(replay_payload.get("success")) and integrity_ok
            if not replay_ok:
                replay_error = _normalize(replay_payload.get("error")) or "replay_integrity_failed"
        else:
            replay_error = "missing_task_id_for_replay"

        if not replay_ok:
            async with get_db() as db:
                await db.execute("BEGIN IMMEDIATE")
                try:
                    await db.execute(
                        "UPDATE engineering_workflows SET replay_trust_valid = 0, updated_at = ? WHERE id = ?",
                        (_unix_ts(), workflow_id),
                    )
                    await _append_workflow_event(
                        db,
                        workflow_id=workflow_id,
                        event_type="reconstruction_failed",
                        from_state=first["to_state"],
                        to_state=first["to_state"],
                        payload={"reason": replay_error, "task_id": task_id},
                        actor=actor,
                    )
                    await _audit_row(
                        db,
                        current_user=current_user,
                        event_type="task.failed",
                        target_type="engineering_workflow",
                        target_id=workflow_id,
                        before_state={"replay_trust_valid": 1},
                        after_state={"replay_trust_valid": 0, "reason": replay_error},
                    )
                    await db.commit()
                except Exception as exc:
                    await db.rollback()
                    logger.exception("engineering_replay_trust_mark_failed", workflow_id=workflow_id, error=str(exc))
                    raise HTTPException(status_code=500, detail="engineering_replay_trust_mark_failed") from exc

            second = await _transition_workflow(
                workflow_id=workflow_id,
                to_state="rejected",
                current_user=current_user,
                reason="replay_reconstruction_failure",
                event_payload={"replay_error": replay_error},
            )
            return {
                "workflow_id": workflow_id,
                "state": second["to_state"],
                "decision": "approved_but_replay_failed",
                "replay_error": replay_error,
                "replay": replay_payload,
            }

        second = await _transition_workflow(
            workflow_id=workflow_id,
            to_state="approved",
            current_user=current_user,
            reason="replay_verified_after_governance_approval",
        )
        return {
            "workflow_id": workflow_id,
            "state": second["to_state"],
            "decision": decision_status,
            "replay_integrity_ok": integrity_ok,
        }

    return {"workflow_id": workflow_id, "state": _normalize((await _load_workflow(workflow_id))["state"]), "decision": decision_status}


@router.post("/workflows/{workflow_id}/lineage/retry")
async def record_workflow_retry(
    workflow_id: str,
    body: RetryRecordRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_retry_record")
    workflow = await _load_workflow(workflow_id)
    actor = _normalize(current_user.get("email")) or "unknown"
    intake_id = _normalize(workflow["intake_id"])

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            seq_cursor = await db.execute(
                """
                SELECT COUNT(*) AS c
                FROM source_lineage_entries
                WHERE intake_id = ? AND lineage_stage = 'retry'
                """,
                (intake_id,),
            )
            seq_row = await seq_cursor.fetchone()
            retry_sequence = int(seq_row["c"] or 0) + 1

            parent_cursor = await db.execute(
                """
                SELECT lineage_hash
                FROM source_lineage_entries
                WHERE intake_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (intake_id,),
            )
            parent_row = await parent_cursor.fetchone()
            parent_hash = _normalize(parent_row["lineage_hash"]) if parent_row else ""
            payload = {
                "workflow_id": workflow_id,
                "snapshot_id": _normalize(workflow["snapshot_id"]),
                "retry_sequence": retry_sequence,
                "reason": _normalize(body.reason),
            }
            payload_json = _stable_json(payload)
            lineage_hash = _sha256(f"{parent_hash}|retry|{payload_json}|{actor}")

            await db.execute(
                """
                INSERT INTO source_lineage_entries (
                    intake_id, lineage_stage, parent_lineage_hash, lineage_payload, lineage_hash, created_by
                ) VALUES (?, 'retry', ?, ?, ?, ?)
                """,
                (intake_id, parent_hash or None, payload_json, lineage_hash, actor),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="retry_recorded",
                from_state=_normalize(workflow["state"]),
                to_state=_normalize(workflow["state"]),
                payload={"retry_sequence": retry_sequence, "lineage_hash": lineage_hash},
                actor=actor,
            )
            await _audit_row(
                db,
                current_user=current_user,
                event_type="task.progress",
                target_type="engineering_workflow",
                target_id=workflow_id,
                before_state={"retry_sequence": retry_sequence - 1},
                after_state={"retry_sequence": retry_sequence, "lineage_hash": lineage_hash},
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_retry_record_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_retry_record_failed") from exc

    return {
        "workflow_id": workflow_id,
        "retry_sequence": retry_sequence,
        "lineage_hash": lineage_hash,
    }


@router.post("/workflows/{workflow_id}/lineage/finalize")
async def finalize_workflow_lineage(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_lineage_finalize")
    workflow = await _load_workflow(workflow_id)
    state = _normalize(workflow["state"])
    if state not in {"approved", "rejected"}:
        raise HTTPException(status_code=409, detail="workflow_not_final_decision_state")

    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT status
            FROM engineering_governance_actions
            WHERE workflow_id = ? AND operation = 'lineage_finalization'
            ORDER BY id DESC
            LIMIT 1
            """,
            (workflow_id,),
        )
        row = await cursor.fetchone()
    if row is None or _normalize(row["status"]) != "approved":
        raise HTTPException(status_code=409, detail="lineage_finalization_approval_required")

    actor = _normalize(current_user.get("email")) or "unknown"
    intake_id = _normalize(workflow["intake_id"])
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            parent_cursor = await db.execute(
                """
                SELECT lineage_hash
                FROM source_lineage_entries
                WHERE intake_id = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (intake_id,),
            )
            parent_row = await parent_cursor.fetchone()
            parent_hash = _normalize(parent_row["lineage_hash"]) if parent_row else ""
            payload = {
                "workflow_id": workflow_id,
                "snapshot_id": _normalize(workflow["snapshot_id"]),
                "task_id": _normalize(workflow.get("task_id")),
                "state": state,
                "replay_trust_valid": int(workflow.get("replay_trust_valid") or 0),
            }
            payload_json = _stable_json(payload)
            lineage_hash = _sha256(f"{parent_hash}|replay_evidence|{payload_json}|{actor}")
            await db.execute(
                """
                INSERT INTO source_lineage_entries (
                    intake_id, lineage_stage, parent_lineage_hash, lineage_payload, lineage_hash, created_by
                ) VALUES (?, 'replay_evidence', ?, ?, ?, ?)
                """,
                (intake_id, parent_hash or None, payload_json, lineage_hash, actor),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="lineage_finalized",
                from_state=state,
                to_state="lineage_finalized",
                payload={"lineage_hash": lineage_hash},
                actor=actor,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_lineage_finalize_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_lineage_finalize_failed") from exc

    transition = await _transition_workflow(
        workflow_id=workflow_id,
        to_state="lineage_finalized",
        current_user=current_user,
        reason="lineage_evidence_persisted",
    )
    return {
        "workflow_id": workflow_id,
        "state": transition["to_state"],
        "lineage_hash": lineage_hash,
    }


@router.post("/workflows/{workflow_id}/evidence")
async def link_workflow_evidence(
    workflow_id: str,
    body: EvidenceLinkRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_evidence_link")
    _ = await _load_workflow(workflow_id)
    actor = _normalize(current_user.get("email")) or "unknown"
    content = _normalize(body.evidence_content)
    evidence_ref = _normalize(body.evidence_ref)
    if not _normalize(body.evidence_type) or not evidence_ref:
        raise HTTPException(status_code=400, detail="missing_evidence_fields")
    evidence_hash = _sha256(content if content else evidence_ref)

    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        try:
            await db.execute(
                """
                INSERT INTO engineering_evidence_links (
                    workflow_id, evidence_type, evidence_ref, evidence_hash, created_by
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (workflow_id, _normalize(body.evidence_type), evidence_ref, evidence_hash, actor),
            )
            await _append_workflow_event(
                db,
                workflow_id=workflow_id,
                event_type="evidence_linked",
                from_state="",
                to_state="",
                payload={"evidence_type": _normalize(body.evidence_type), "evidence_ref": evidence_ref},
                actor=actor,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("engineering_evidence_link_failed", workflow_id=workflow_id, error=str(exc))
            raise HTTPException(status_code=500, detail="engineering_evidence_link_failed") from exc

    return {
        "workflow_id": workflow_id,
        "evidence_type": _normalize(body.evidence_type),
        "evidence_hash": evidence_hash,
    }


@router.get("/workflows/{workflow_id}/reconstruct")
async def reconstruct_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_reconstruct")
    workflow = await _load_workflow(workflow_id)
    snapshot = await _load_engineering_snapshot(_normalize(workflow["snapshot_id"]))

    async with get_db() as db:
        events_cursor = await db.execute(
            """
            SELECT id, event_type, from_state, to_state, event_payload, actor, created_at, event_hash
            FROM engineering_workflow_events
            WHERE workflow_id = ?
            ORDER BY id
            """,
            (workflow_id,),
        )
        event_rows = [dict(row) for row in await events_cursor.fetchall()]

        validation_cursor = await db.execute(
            """
            SELECT run_sequence, tool_name, tool_version, passed, findings_json, confidence, output_hash, executed_at
            FROM engineering_validation_runs
            WHERE workflow_id = ?
            ORDER BY run_sequence, tool_name
            """,
            (workflow_id,),
        )
        validation_rows = [dict(row) for row in await validation_cursor.fetchall()]

        governance_cursor = await db.execute(
            """
            SELECT id, operation, status, reason, requested_by, decided_by, created_at
            FROM engineering_governance_actions
            WHERE workflow_id = ?
            ORDER BY id
            """,
            (workflow_id,),
        )
        governance_rows = [dict(row) for row in await governance_cursor.fetchall()]

        evidence_cursor = await db.execute(
            """
            SELECT id, evidence_type, evidence_ref, evidence_hash, created_by, created_at
            FROM engineering_evidence_links
            WHERE workflow_id = ?
            ORDER BY id
            """,
            (workflow_id,),
        )
        evidence_rows = [dict(row) for row in await evidence_cursor.fetchall()]

    normalized_events: list[dict[str, Any]] = []
    for row in event_rows:
        normalized_events.append(
            {
                "id": int(row["id"]),
                "event_type": _normalize(row["event_type"]),
                "from_state": _normalize(row.get("from_state")),
                "to_state": _normalize(row.get("to_state")),
                "payload": json.loads(row.get("event_payload") or "{}"),
                "actor": _normalize(row["actor"]),
                "created_at": int(row["created_at"] or 0),
                "event_hash": _normalize(row["event_hash"]),
            }
        )

    normalized_validation: list[dict[str, Any]] = []
    for row in validation_rows:
        normalized_validation.append(
            {
                "run_sequence": int(row["run_sequence"] or 0),
                "tool_name": _normalize(row["tool_name"]),
                "tool_version": _normalize(row["tool_version"]),
                "passed": bool(int(row["passed"] or 0)),
                "findings": json.loads(row.get("findings_json") or "[]"),
                "confidence": float(row["confidence"] or 0.0),
                "output_hash": _normalize(row["output_hash"]),
                "executed_at": int(row["executed_at"] or 0),
            }
        )

    normalized_governance: list[dict[str, Any]] = []
    for row in governance_rows:
        normalized_governance.append(
            {
                "id": int(row["id"]),
                "operation": _normalize(row["operation"]),
                "status": _normalize(row["status"]),
                "reason": _normalize(row["reason"]),
                "requested_by": _normalize(row["requested_by"]),
                "decided_by": _normalize(row["decided_by"]),
                "created_at": int(row["created_at"] or 0),
            }
        )

    normalized_evidence: list[dict[str, Any]] = []
    for row in evidence_rows:
        normalized_evidence.append(
            {
                "id": int(row["id"]),
                "evidence_type": _normalize(row["evidence_type"]),
                "evidence_ref": _normalize(row["evidence_ref"]),
                "evidence_hash": _normalize(row["evidence_hash"]),
                "created_by": _normalize(row["created_by"]),
                "created_at": int(row["created_at"] or 0),
            }
        )

    failures: list[str] = []
    recomputed_snapshot_hash = _sha256(_stable_json(snapshot["snapshot"]))
    if recomputed_snapshot_hash != _normalize(snapshot["snapshot_hash"]):
        failures.append("snapshot_hash_mismatch")

    transition_events = [item for item in normalized_events if item["event_type"] == "state_transition"]
    for idx in range(1, len(transition_events)):
        prev = transition_events[idx - 1]
        curr = transition_events[idx]
        if curr["from_state"] and prev["to_state"] and curr["from_state"] != prev["to_state"]:
            failures.append(f"state_chain_break_at_event:{curr['id']}")
        if curr["from_state"] and curr["to_state"]:
            if curr["to_state"] not in _ALLOWED_TRANSITIONS.get(curr["from_state"], set()):
                failures.append(f"invalid_transition_recorded:{curr['from_state']}->{curr['to_state']}")

    if transition_events:
        latest_state = transition_events[-1]["to_state"] or transition_events[-1]["from_state"]
        if latest_state and latest_state != _normalize(workflow["state"]):
            failures.append("workflow_state_event_mismatch")

    if _normalize(workflow["state"]) in {"approved", "rejected", "lineage_finalized"}:
        decisions = [
            item for item in normalized_governance
            if item["operation"] == "transformation_proposal" and item["status"] in {"approved", "rejected"}
        ]
        if not decisions:
            failures.append("missing_transformation_governance_decision")

    if _normalize(workflow["state"]) == "lineage_finalized":
        lineage_ok = False
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT 1
                FROM source_lineage_entries
                WHERE intake_id = ? AND lineage_stage = 'replay_evidence'
                  AND json_extract(lineage_payload, '$.workflow_id') = ?
                ORDER BY created_at DESC, rowid DESC
                LIMIT 1
                """,
                (_normalize(workflow["intake_id"]), workflow_id),
            )
            lineage_ok = (await cursor.fetchone()) is not None
        if not lineage_ok:
            failures.append("missing_replay_evidence_lineage_entry")

    replay_result: dict[str, Any] = {}
    replay_integrity_ok = False
    task_id = _normalize(workflow.get("task_id"))
    if task_id:
        engine = ReplayEngine(TaskRecorder(Config.SQLITE_PATH))
        replay_result = await engine.replay(task_id)
        replay_integrity_ok = engine.verify_integrity(task_id)
        if not replay_result.get("success"):
            failures.append("task_replay_failed")
        if not replay_integrity_ok:
            failures.append("task_replay_integrity_failed")

    reconstruction = {
        "workflow": {
            "id": _normalize(workflow["id"]),
            "intake_id": _normalize(workflow["intake_id"]),
            "snapshot_id": _normalize(workflow["snapshot_id"]),
            "provenance_lineage_hash": _normalize(workflow["provenance_lineage_hash"]),
            "task_id": task_id,
            "state": _normalize(workflow["state"]),
            "validation_status": _normalize(workflow["validation_status"]),
            "governance_state": _normalize(workflow["governance_state"]),
            "replay_trust_valid": int(workflow["replay_trust_valid"] or 0),
            "created_at": int(workflow["created_at"] or 0),
            "updated_at": int(workflow["updated_at"] or 0),
        },
        "snapshot": snapshot["snapshot"],
        "events": normalized_events,
        "validation_runs": normalized_validation,
        "governance_actions": normalized_governance,
        "evidence_links": normalized_evidence,
        "task_replay": {
            "task_id": task_id,
            "integrity_ok": replay_integrity_ok,
            "replay": replay_result,
        },
    }
    reconstruction_hash = _sha256(_stable_json(reconstruction))
    trust_valid = len(failures) == 0

    if not trust_valid and int(workflow["replay_trust_valid"] or 0) != 0:
        actor = _normalize(current_user.get("email")) or "unknown"
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await db.execute(
                    "UPDATE engineering_workflows SET replay_trust_valid = 0, updated_at = ? WHERE id = ?",
                    (_unix_ts(), workflow_id),
                )
                await _append_workflow_event(
                    db,
                    workflow_id=workflow_id,
                    event_type="reconstruction_failed",
                    from_state=_normalize(workflow["state"]),
                    to_state=_normalize(workflow["state"]),
                    payload={"failures": failures},
                    actor=actor,
                )
                await _audit_row(
                    db,
                    current_user=current_user,
                    event_type="task.failed",
                    target_type="engineering_workflow",
                    target_id=workflow_id,
                    before_state={"replay_trust_valid": 1},
                    after_state={"replay_trust_valid": 0, "failures": failures},
                )
                await db.commit()
            except Exception as exc:
                await db.rollback()
                logger.exception("engineering_reconstruction_invalidation_failed", workflow_id=workflow_id, error=str(exc))
                raise HTTPException(status_code=500, detail="engineering_reconstruction_invalidation_failed") from exc

    return {
        "workflow_id": workflow_id,
        "trust_valid": trust_valid,
        "failures": failures,
        "reconstruction_hash": reconstruction_hash,
        "reconstruction": reconstruction,
    }


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_get")
    workflow = await _load_workflow(workflow_id)
    return {
        "workflow_id": _normalize(workflow["id"]),
        "intake_id": _normalize(workflow["intake_id"]),
        "snapshot_id": _normalize(workflow["snapshot_id"]),
        "provenance_lineage_hash": _normalize(workflow["provenance_lineage_hash"]),
        "task_id": _normalize(workflow.get("task_id")),
        "state": _normalize(workflow["state"]),
        "validation_status": _normalize(workflow["validation_status"]),
        "governance_state": _normalize(workflow["governance_state"]),
        "replay_trust_valid": bool(int(workflow.get("replay_trust_valid") or 0)),
        "created_at": int(workflow["created_at"] or 0),
        "updated_at": int(workflow["updated_at"] or 0),
    }


@router.get("/workflows")
async def list_workflows(
    state: str = "",
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "workflow_list")
    state_filter = _normalize(state)
    if state_filter and state_filter not in _WORKFLOW_STATES:
        raise HTTPException(status_code=400, detail=f"invalid_workflow_state_filter:{state_filter}")
    capped = max(1, min(limit, 500))

    async with get_db() as db:
        if state_filter:
            cursor = await db.execute(
                """
                SELECT id, intake_id, snapshot_id, state, validation_status, governance_state,
                       replay_trust_valid, task_id, created_at, updated_at
                FROM engineering_workflows
                WHERE state = ?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT ?
                """,
                (state_filter, capped),
            )
        else:
            cursor = await db.execute(
                """
                SELECT id, intake_id, snapshot_id, state, validation_status, governance_state,
                       replay_trust_valid, task_id, created_at, updated_at
                FROM engineering_workflows
                ORDER BY updated_at DESC, rowid DESC
                LIMIT ?
                """,
                (capped,),
            )
        rows = await cursor.fetchall()

    items = []
    for row in rows:
        item = dict(row)
        items.append(
            {
                "workflow_id": _normalize(item["id"]),
                "intake_id": _normalize(item["intake_id"]),
                "snapshot_id": _normalize(item["snapshot_id"]),
                "task_id": _normalize(item.get("task_id")),
                "state": _normalize(item["state"]),
                "validation_status": _normalize(item["validation_status"]),
                "governance_state": _normalize(item["governance_state"]),
                "replay_trust_valid": bool(int(item.get("replay_trust_valid") or 0)),
                "created_at": int(item["created_at"] or 0),
                "updated_at": int(item["updated_at"] or 0),
            }
        )
    return {"items": items, "count": len(items)}
