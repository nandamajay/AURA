"""Engineering source intake + provenance runtime endpoints."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from core.routers.auth import get_current_user

logger = get_logger("core.provenance")
router = APIRouter()

_TRUSTED = "trusted"
_BOUNDED = "bounded-trust"
_UNTRUSTED = "untrusted/manual-review-required"
_TRUST_VALUES = {_TRUSTED, _BOUNDED, _UNTRUSTED}

_REF_KIND_VALUES = {"branch", "tag", "commit"}
_LINEAGE_STAGE_VALUES = {
    "downstream_intake",
    "patch_transform",
    "upstream_prep",
    "validation",
    "approval",
    "replay_evidence",
    "retry",
    "rebase",
}

_APPROVER_ROLES = {"approver", "architect", "admin"}
_REVIEWER_ROLES = {"reviewer", "approver", "architect", "admin"}
_ADMIN_OVERRIDE_ROLES = {"architect", "admin"}

_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


class SourceRegisterRequest(BaseModel):
    downstream_repo_url: str = ""
    downstream_ref_kind: str = "branch"
    downstream_ref: str = ""
    bsp_lineage: str = ""
    commit_anchors: list[str] = Field(default_factory=list)
    subsystem_name: str = ""
    subsystem_owner: str = ""
    upstream_repo_url: str = ""
    target_kernel: str = "linux"
    target_kernel_version: str = ""
    maintainer_refs: list[str] = Field(default_factory=list)
    patchset_lineage: list[str] = Field(default_factory=list)


class IntakeDecisionRequest(BaseModel):
    decision: str = "approve"  # approve|reject
    comment: str = ""


class TrustOverrideRequest(BaseModel):
    trust_classification: str = _BOUNDED
    reason: str = ""


class SnapshotCreateRequest(BaseModel):
    reason: str = ""


class LineageHookRequest(BaseModel):
    stage: str = "downstream_intake"
    payload: dict[str, Any] = Field(default_factory=dict)


class ValidationRerunRequest(BaseModel):
    reason: str = ""


class RebaseRecordRequest(BaseModel):
    from_commit: str = ""
    to_commit: str = ""
    reason: str = ""


def _require_role(current_user: dict[str, Any], allowed_roles: set[str], action: str) -> None:
    role = str(current_user.get("role") or "viewer").strip().lower()
    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"insufficient_role_for_{action}:{role}")


def _normalize_str(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(values: list[str], *, lower: bool = False) -> list[str]:
    cleaned: list[str] = []
    for raw in values:
        val = _normalize_str(raw)
        if not val:
            continue
        if lower:
            val = val.lower()
        cleaned.append(val)
    # Stable deterministic ordering.
    return sorted(dict.fromkeys(cleaned))


def _validate_git_url(url: str) -> bool:
    value = _normalize_str(url)
    if not value:
        return False
    if value.startswith("git@") and ":" in value:
        return True
    parsed = urlparse(value)
    if parsed.scheme in {"https", "http", "ssh", "git"} and parsed.netloc:
        return True
    return False


def _is_commit_hash(value: str) -> bool:
    return bool(_COMMIT_RE.fullmatch(value.strip().lower()))


def _canonical_intake_payload(request: SourceRegisterRequest) -> dict[str, Any]:
    ref_kind = _normalize_str(request.downstream_ref_kind).lower()
    if ref_kind not in _REF_KIND_VALUES:
        raise HTTPException(status_code=400, detail=f"invalid_downstream_ref_kind:{ref_kind}")

    commit_anchors = _normalize_list(request.commit_anchors, lower=True)
    patchset_lineage = _normalize_list(request.patchset_lineage, lower=True)

    for commit in commit_anchors + patchset_lineage:
        if not _is_commit_hash(commit):
            raise HTTPException(status_code=400, detail=f"invalid_commit_hash:{commit}")

    payload = {
        "downstream_repo_url": _normalize_str(request.downstream_repo_url),
        "downstream_ref_kind": ref_kind,
        "downstream_ref": _normalize_str(request.downstream_ref),
        "bsp_lineage": _normalize_str(request.bsp_lineage),
        "commit_anchors": commit_anchors,
        "subsystem_name": _normalize_str(request.subsystem_name).lower(),
        "subsystem_owner": _normalize_str(request.subsystem_owner),
        "upstream_repo_url": _normalize_str(request.upstream_repo_url),
        "target_kernel": _normalize_str(request.target_kernel).lower() or "linux",
        "target_kernel_version": _normalize_str(request.target_kernel_version),
        "maintainer_refs": _normalize_list(request.maintainer_refs),
        "patchset_lineage": patchset_lineage,
    }

    required = [
        "downstream_repo_url",
        "downstream_ref",
        "subsystem_name",
        "subsystem_owner",
        "upstream_repo_url",
        "target_kernel_version",
    ]
    missing = [name for name in required if not payload[name]]
    if missing:
        raise HTTPException(status_code=400, detail=f"missing_required_fields:{','.join(missing)}")

    return payload


def _stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _classify_trust(validation: dict[str, Any], intake_payload: dict[str, Any]) -> str:
    issues = list(validation.get("issues") or [])
    has_invalid_url = any(issue.startswith("invalid_url") for issue in issues)
    has_commit_anchors = len(intake_payload.get("commit_anchors", [])) > 0
    has_maintainers = len(intake_payload.get("maintainer_refs", [])) > 0

    if has_invalid_url or not validation.get("valid", False):
        return _UNTRUSTED
    if has_commit_anchors and has_maintainers:
        return _TRUSTED
    return _BOUNDED


def _validate_intake_payload(payload: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []

    down_url = str(payload.get("downstream_repo_url") or "")
    up_url = str(payload.get("upstream_repo_url") or "")
    if not _validate_git_url(down_url):
        issues.append("invalid_url:downstream_repo_url")
    if not _validate_git_url(up_url):
        issues.append("invalid_url:upstream_repo_url")

    if str(payload.get("downstream_ref_kind") or "") == "commit":
        ref = str(payload.get("downstream_ref") or "").lower()
        if not _is_commit_hash(ref):
            issues.append("invalid_ref:downstream_ref_commit")

    if not str(payload.get("target_kernel_version") or ""):
        issues.append("missing:target_kernel_version")

    commit_anchors = payload.get("commit_anchors") or []
    if not isinstance(commit_anchors, list) or not commit_anchors:
        issues.append("weak_lineage:no_commit_anchors")

    maintainers = payload.get("maintainer_refs") or []
    if not isinstance(maintainers, list) or not maintainers:
        issues.append("weak_lineage:no_maintainer_refs")

    return {
        "valid": not any(item.startswith("invalid_") or item.startswith("missing:") for item in issues),
        "issues": issues,
    }


async def _load_intake(intake_id: str) -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM source_intakes WHERE id = ?", (intake_id,))
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"source_intake_not_found:{intake_id}")
    intake = dict(row)
    intake["commit_anchors"] = json.loads(intake.get("commit_anchors_json") or "[]")
    intake["maintainer_refs"] = json.loads(intake.get("maintainer_refs_json") or "[]")
    intake["patchset_lineage"] = json.loads(intake.get("patchset_lineage_json") or "[]")
    intake["canonical_payload"] = json.loads(intake.get("canonical_json") or "{}")
    return intake


async def _append_intake_event(
    *,
    intake_id: str,
    event_type: str,
    payload: dict[str, Any],
    actor: str,
) -> int:
    event_payload_json = _stable_json(payload)
    event_hash = _sha256(f"{intake_id}|{event_type}|{event_payload_json}|{actor}")
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO source_intake_events (intake_id, event_type, event_payload, actor, event_hash)
            VALUES (?, ?, ?, ?, ?)
            """,
            (intake_id, event_type, event_payload_json, actor, event_hash),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def _list_events(intake_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, intake_id, event_type, event_payload, actor, created_at, event_hash "
            "FROM source_intake_events WHERE intake_id = ? ORDER BY id",
            (intake_id,),
        )
        rows = await cursor.fetchall()
    events = [dict(row) for row in rows]
    for event in events:
        event["payload"] = json.loads(event.pop("event_payload") or "{}")
    return events


def _latest_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    trust = ""
    validation: dict[str, Any] | None = None
    approval_state = "pending"

    for event in events:
        et = event["event_type"]
        payload = event.get("payload", {})
        if et == "validated":
            validation = dict(payload)
        elif et == "classified":
            trust = str(payload.get("trust_classification") or "")
        elif et == "override":
            trust = str(payload.get("trust_classification") or trust)
        elif et == "approved":
            approval_state = "approved"
        elif et == "rejected":
            approval_state = "rejected"
    return {
        "trust_classification": trust,
        "validation": validation,
        "approval_state": approval_state,
    }


async def _audit_override(
    *,
    intake_id: str,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
    current_user: dict[str, Any],
) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO audit_ledger
            (timestamp, user_id, session_id, event_type, target_type, target_id, before_state, after_state)
            VALUES (?, ?, ?, 'config.changed', 'source_intake', ?, ?, ?)
            """,
            (
                int(datetime.now(timezone.utc).timestamp()),
                str(current_user.get("sub") or ""),
                str(current_user.get("email") or "unknown"),
                intake_id,
                _stable_json(before_state),
                _stable_json(after_state),
            ),
        )
        await db.commit()


async def _load_lineage_entries(intake_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, intake_id, lineage_stage, parent_lineage_hash, lineage_payload, lineage_hash, created_by, created_at "
            "FROM source_lineage_entries WHERE intake_id = ? ORDER BY created_at, rowid",
            (intake_id,),
        )
        rows = await cursor.fetchall()
    entries = [dict(row) for row in rows]
    for entry in entries:
        entry["payload"] = json.loads(entry.pop("lineage_payload") or "{}")
    return entries


async def _load_snapshots(intake_id: str) -> list[dict[str, Any]]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, replay_identifier, snapshot_hash, created_by, created_at FROM source_replay_snapshots "
            "WHERE intake_id = ? ORDER BY created_at, id",
            (intake_id,),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@router.post("/sources/register")
async def register_source_intake(
    request: SourceRegisterRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_register")

    payload = _canonical_intake_payload(request)
    canonical_json = _stable_json(payload)
    canonical_hash = _sha256(canonical_json)

    actor = str(current_user.get("email") or "unknown")

    async with get_db() as db:
        try:
            cursor = await db.execute(
                """
                INSERT INTO source_intakes (
                    downstream_repo_url,
                    downstream_ref_kind,
                    downstream_ref,
                    bsp_lineage,
                    commit_anchors_json,
                    subsystem_name,
                    subsystem_owner,
                    upstream_repo_url,
                    target_kernel,
                    target_kernel_version,
                    maintainer_refs_json,
                    patchset_lineage_json,
                    registered_by,
                    canonical_json,
                    canonical_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["downstream_repo_url"],
                    payload["downstream_ref_kind"],
                    payload["downstream_ref"],
                    payload["bsp_lineage"],
                    _stable_json(payload["commit_anchors"]),
                    payload["subsystem_name"],
                    payload["subsystem_owner"],
                    payload["upstream_repo_url"],
                    payload["target_kernel"],
                    payload["target_kernel_version"],
                    _stable_json(payload["maintainer_refs"]),
                    _stable_json(payload["patchset_lineage"]),
                    actor,
                    canonical_json,
                    canonical_hash,
                ),
            )
            intake_id = str(cursor.lastrowid)
            row_cursor = await db.execute(
                "SELECT id FROM source_intakes WHERE canonical_hash = ?",
                (canonical_hash,),
            )
            row = await row_cursor.fetchone()
            intake_id = str(row["id"]) if row else intake_id
            await db.commit()
        except Exception as exc:
            text = str(exc).lower()
            if "unique" in text and "canonical_hash" in text:
                raise HTTPException(status_code=409, detail="duplicate_source_intake") from exc
            raise

    await _append_intake_event(
        intake_id=intake_id,
        event_type="registered",
        payload={"canonical_hash": canonical_hash, "target_kernel": payload["target_kernel"]},
        actor=actor,
    )

    logger.info("source_intake_registered", intake_id=intake_id, subsystem=payload["subsystem_name"], actor=actor)
    return {
        "intake_id": intake_id,
        "canonical_hash": canonical_hash,
        "status": "registered",
    }


@router.post("/sources/{intake_id}/validate")
async def validate_source_intake(
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_validate")
    intake = await _load_intake(intake_id)
    validation = _validate_intake_payload(intake.get("canonical_payload") or {})
    trust = _classify_trust(validation, intake.get("canonical_payload") or {})
    actor = str(current_user.get("email") or "unknown")

    await _append_intake_event(
        intake_id=intake_id,
        event_type="validated",
        payload=validation,
        actor=actor,
    )
    await _append_intake_event(
        intake_id=intake_id,
        event_type="classified",
        payload={"trust_classification": trust},
        actor=actor,
    )
    if trust == _UNTRUSTED:
        await _append_intake_event(
            intake_id=intake_id,
            event_type="approval_requested",
            payload={"reason": "untrusted_source_requires_operator_approval"},
            actor=actor,
        )

    return {
        "intake_id": intake_id,
        "valid": validation["valid"],
        "issues": validation["issues"],
        "trust_classification": trust,
    }


@router.post("/sources/{intake_id}/approve")
async def approve_source_intake(
    intake_id: str,
    request: IntakeDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    intake = await _load_intake(intake_id)
    _ = intake
    events = await _list_events(intake_id)
    state = _latest_state(events)
    trust = str(state.get("trust_classification") or "")

    decision = _normalize_str(request.decision).lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail=f"invalid_decision:{decision}")

    if trust == _UNTRUSTED:
        _require_role(current_user, _APPROVER_ROLES, "source_approve_untrusted")
    else:
        _require_role(current_user, _REVIEWER_ROLES, "source_approve")

    actor = str(current_user.get("email") or "unknown")
    event_type = "approved" if decision == "approve" else "rejected"
    await _append_intake_event(
        intake_id=intake_id,
        event_type=event_type,
        payload={
            "decision": decision,
            "comment": _normalize_str(request.comment),
            "trust_classification": trust,
        },
        actor=actor,
    )

    return {
        "intake_id": intake_id,
        "decision": decision,
        "trust_classification": trust,
    }


@router.post("/sources/{intake_id}/override-trust")
async def override_trust_classification(
    intake_id: str,
    request: TrustOverrideRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _ADMIN_OVERRIDE_ROLES, "source_trust_override")
    if request.trust_classification not in _TRUST_VALUES:
        raise HTTPException(status_code=400, detail="invalid_trust_classification")
    reason = _normalize_str(request.reason)
    if not reason:
        raise HTTPException(status_code=400, detail="override_reason_required")

    events = await _list_events(intake_id)
    state = _latest_state(events)
    before_trust = str(state.get("trust_classification") or "")
    actor = str(current_user.get("email") or "unknown")

    payload = {
        "before_trust_classification": before_trust,
        "trust_classification": request.trust_classification,
        "reason": reason,
    }
    await _append_intake_event(
        intake_id=intake_id,
        event_type="override",
        payload=payload,
        actor=actor,
    )

    await _audit_override(
        intake_id=intake_id,
        before_state={"trust_classification": before_trust},
        after_state=payload,
        current_user=current_user,
    )

    return {
        "intake_id": intake_id,
        "trust_classification": request.trust_classification,
        "overridden": True,
    }


@router.post("/sources/{intake_id}/snapshot")
async def create_source_snapshot(
    intake_id: str,
    request: SnapshotCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_snapshot")
    intake = await _load_intake(intake_id)
    events = await _list_events(intake_id)
    state = _latest_state(events)
    if state.get("approval_state") != "approved":
        raise HTTPException(status_code=409, detail="source_intake_not_approved")

    actor = str(current_user.get("email") or "unknown")
    snapshot_payload = {
        "intake": intake.get("canonical_payload") or {},
        "registered_by": intake.get("registered_by"),
        "events": [{
            "id": int(item["id"]),
            "event_type": item["event_type"],
            "payload": item.get("payload", {}),
            "actor": item["actor"],
            "event_hash": item["event_hash"],
            "created_at": int(item["created_at"]),
        } for item in events],
        "reason": _normalize_str(request.reason),
    }
    snapshot_json = _stable_json(snapshot_payload)
    snapshot_hash = _sha256(snapshot_json)
    replay_identifier = f"source-intake:{intake_id}:events:{len(events)}"

    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO source_replay_snapshots (intake_id, replay_identifier, snapshot_json, snapshot_hash, created_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (intake_id, replay_identifier, snapshot_json, snapshot_hash, actor),
        )
        await db.commit()
        snapshot_id = str(cursor.lastrowid)
        row_cursor = await db.execute(
            "SELECT id FROM source_replay_snapshots WHERE replay_identifier = ?",
            (replay_identifier,),
        )
        row = await row_cursor.fetchone()
        if row is not None:
            snapshot_id = str(row["id"])

    await _append_intake_event(
        intake_id=intake_id,
        event_type="snapshot_created",
        payload={
            "snapshot_id": snapshot_id,
            "snapshot_hash": snapshot_hash,
            "replay_identifier": replay_identifier,
        },
        actor=actor,
    )

    return {
        "intake_id": intake_id,
        "snapshot_id": snapshot_id,
        "snapshot_hash": snapshot_hash,
        "replay_identifier": replay_identifier,
    }


@router.post("/sources/{intake_id}/lineage")
async def record_lineage(
    intake_id: str,
    request: LineageHookRequest,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_lineage")

    stage = _normalize_str(request.stage)
    if stage not in _LINEAGE_STAGE_VALUES:
        raise HTTPException(status_code=400, detail=f"invalid_lineage_stage:{stage}")

    events = await _list_events(intake_id)
    state = _latest_state(events)
    if state.get("approval_state") != "approved":
        raise HTTPException(status_code=409, detail="source_intake_not_approved")

    lineage_payload = request.payload if isinstance(request.payload, dict) else {}
    actor = str(current_user.get("email") or "unknown")

    entries = await _load_lineage_entries(intake_id)
    parent_hash = str(entries[-1]["lineage_hash"]) if entries else ""
    payload_json = _stable_json(lineage_payload)
    lineage_hash = _sha256(f"{parent_hash}|{stage}|{payload_json}|{actor}")

    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO source_lineage_entries (
                intake_id,
                lineage_stage,
                parent_lineage_hash,
                lineage_payload,
                lineage_hash,
                created_by
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                intake_id,
                stage,
                parent_hash or None,
                payload_json,
                lineage_hash,
                actor,
            ),
        )
        await db.commit()
        lineage_id = str(cursor.lastrowid)
        row_cursor = await db.execute(
            "SELECT id FROM source_lineage_entries WHERE intake_id = ? AND lineage_hash = ?",
            (intake_id, lineage_hash),
        )
        row = await row_cursor.fetchone()
        if row is not None:
            lineage_id = str(row["id"])

    event_type = "lineage_recorded"
    if stage == "retry":
        event_type = "retry_recorded"
    elif stage == "rebase":
        event_type = "rebase_recorded"

    await _append_intake_event(
        intake_id=intake_id,
        event_type=event_type,
        payload={"lineage_id": lineage_id, "lineage_stage": stage, "lineage_hash": lineage_hash},
        actor=actor,
    )

    return {
        "intake_id": intake_id,
        "lineage_id": lineage_id,
        "lineage_stage": stage,
        "lineage_hash": lineage_hash,
    }


@router.post("/sources/{intake_id}/lineage/retry")
async def record_validation_retry(
    intake_id: str,
    request: ValidationRerunRequest,
    current_user: dict = Depends(get_current_user),
):
    entries = await _load_lineage_entries(intake_id)
    retry_sequence = 1 + sum(1 for item in entries if item["lineage_stage"] == "retry")
    payload = {
        "retry_sequence": retry_sequence,
        "reason": _normalize_str(request.reason),
    }
    return await record_lineage(
        intake_id,
        LineageHookRequest(stage="retry", payload=payload),
        current_user=current_user,
    )


@router.post("/sources/{intake_id}/lineage/rebase")
async def record_rebase(
    intake_id: str,
    request: RebaseRecordRequest,
    current_user: dict = Depends(get_current_user),
):
    from_commit = _normalize_str(request.from_commit).lower()
    to_commit = _normalize_str(request.to_commit).lower()
    if not _is_commit_hash(from_commit) or not _is_commit_hash(to_commit):
        raise HTTPException(status_code=400, detail="invalid_rebase_commit_hash")
    payload = {
        "from_commit": from_commit,
        "to_commit": to_commit,
        "reason": _normalize_str(request.reason),
        "explicit_rebase": True,
    }
    return await record_lineage(
        intake_id,
        LineageHookRequest(stage="rebase", payload=payload),
        current_user=current_user,
    )


@router.get("/sources/{intake_id}")
async def get_source_intake(
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_get")
    intake = await _load_intake(intake_id)
    events = await _list_events(intake_id)
    state = _latest_state(events)

    return {
        "intake_id": intake["id"],
        "registered_by": intake["registered_by"],
        "registered_at": int(intake["registered_at"]),
        "canonical_hash": intake["canonical_hash"],
        "source": intake["canonical_payload"],
        "state": state,
        "event_count": len(events),
    }


@router.get("/sources/{intake_id}/reconstruct")
async def reconstruct_source_intake(
    intake_id: str,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_reconstruct")

    intake = await _load_intake(intake_id)
    events = await _list_events(intake_id)
    snapshots = await _load_snapshots(intake_id)
    lineage = await _load_lineage_entries(intake_id)

    normalized = {
        "intake": {
            "intake_id": intake["id"],
            "canonical_hash": intake["canonical_hash"],
            "registered_by": intake["registered_by"],
            "registered_at": int(intake["registered_at"]),
            "source": intake["canonical_payload"],
        },
        "events": [
            {
                "id": int(item["id"]),
                "event_type": item["event_type"],
                "payload": item["payload"],
                "actor": item["actor"],
                "created_at": int(item["created_at"]),
                "event_hash": item["event_hash"],
            }
            for item in events
        ],
        "lineage": [
            {
                "id": item["id"],
                "lineage_stage": item["lineage_stage"],
                "parent_lineage_hash": item.get("parent_lineage_hash"),
                "payload": item["payload"],
                "lineage_hash": item["lineage_hash"],
                "created_by": item["created_by"],
                "created_at": int(item["created_at"]),
            }
            for item in lineage
        ],
        "snapshots": [
            {
                "id": item["id"],
                "replay_identifier": item["replay_identifier"],
                "snapshot_hash": item["snapshot_hash"],
                "created_by": item["created_by"],
                "created_at": int(item["created_at"]),
            }
            for item in snapshots
        ],
    }
    reconstruction_json = _stable_json(normalized)
    reconstruction_hash = _sha256(reconstruction_json)

    return {
        "intake_id": intake_id,
        "reconstruction_hash": reconstruction_hash,
        "reconstruction": normalized,
    }


@router.get("/sources")
async def list_source_intakes(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    _require_role(current_user, _REVIEWER_ROLES, "source_list")
    capped = max(1, min(limit, 500))

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, canonical_hash, subsystem_name, registered_by, registered_at FROM source_intakes "
            "ORDER BY registered_at DESC LIMIT ?",
            (capped,),
        )
        rows = await cursor.fetchall()

    records: list[dict[str, Any]] = []
    for row in rows:
        intake_id = str(row["id"])
        events = await _list_events(intake_id)
        state = _latest_state(events)
        records.append(
            {
                "intake_id": intake_id,
                "canonical_hash": row["canonical_hash"],
                "subsystem_name": row["subsystem_name"],
                "registered_by": row["registered_by"],
                "registered_at": int(row["registered_at"]),
                "state": state,
                "event_count": len(events),
            }
        )

    return {"items": records, "count": len(records)}
