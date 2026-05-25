"""Governance endpoints — approvals, audit log."""

from datetime import datetime, timezone
import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.governance import ApprovalAction
from core.routers.auth import get_current_user

logger = get_logger("core.governance")
router = APIRouter()

TERMINAL_APPROVAL_STATUSES = {"passed", "failed", "skipped"}

ACTION_TO_STATUS: dict[str, str | None] = {
    "grant": "passed",
    "reject": "failed",
    "escalate": "in_progress",
    "comment": None,
}

ACTION_TO_EVENT_TYPE: dict[str, str] = {
    "grant": "approval.granted",
    "reject": "approval.rejected",
    "escalate": "approval.escalated",
    # Schema does not currently include approval.commented.
    "comment": "approval.submitted",
}


class GovernanceEvidenceSummaryResponse(BaseModel):
    generated_at: str
    classification: str
    fail_closed_reasons: list[str] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, Any] = Field(default_factory=dict)
    charter_requests: dict[str, Any] = Field(default_factory=dict)
    audit_history: dict[str, Any] = Field(default_factory=dict)
    failsafe_reports: dict[str, Any] = Field(default_factory=dict)
    integrity_reports: dict[str, Any] = Field(default_factory=dict)
    replay_incidents: dict[str, Any] = Field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso_from_epoch(value: Any) -> str:
    if value in (None, "", 0):
        return ""
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except Exception:
        return ""


async def _table_exists(db, table_name: str) -> bool:
    cursor = await db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return await cursor.fetchone() is not None


async def _table_columns(db, table_name: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table_name})")
    rows = await cursor.fetchall()
    return {str(row["name"]) for row in rows if row and row["name"]}


def _row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _normalize_comment(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _merge_comment(existing: object, new_comment: str) -> str:
    base = str(existing or "").strip()
    if not new_comment:
        return base
    if not base:
        return new_comment
    return f"{base}\n{new_comment}"


@router.get("/approvals")
async def list_approvals(
    status: str = "pending",
    page: int = 1,
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """List approval requests."""
    async with get_db() as db:
        offset = (page - 1) * limit
        cursor = await db.execute(
            """SELECT a.*, p.title as patch_title
            FROM approvals a
            LEFT JOIN patches p ON a.patch_id = p.id
            WHERE a.status = ?
            ORDER BY a.created_at DESC
            LIMIT ? OFFSET ?""",
            (status, limit, offset),
        )
        rows = await cursor.fetchall()
        approvals = [dict(row) for row in rows]

    return {"approvals": approvals, "page": page, "limit": limit}


@router.post("/approvals/{approval_id}")
async def process_approval(
    approval_id: str,
    action: dict,
    current_user: dict = Depends(get_current_user),
):
    """Process an approval action (grant/reject/escalate/comment)."""
    action_type = action.get("action", "")
    comment = _normalize_comment(action.get("comment", ""))

    if action_type not in [a.value for a in ApprovalAction]:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action_type}")

    user_id = current_user.get("sub", "")
    session_id = current_user.get("email", "")
    now_ts = int(time.time())
    new_status = ACTION_TO_STATUS[action_type]
    event_type = ACTION_TO_EVENT_TYPE[action_type]
    outcome = "unchanged"
    response_status = ""

    async with get_db() as db:
        before_status = ""
        before_reviewed_by = ""
        before_reviewed_at = 0
        before_comments = ""
        after_status = ""
        after_reviewed_by = ""
        after_reviewed_at = 0
        after_comments = ""

        try:
            # Serialize approval transitions to deterministic, first-writer behavior.
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT id, status, reviewed_by, reviewed_at, comments FROM approvals WHERE id = ?",
                (approval_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                await db.execute("ROLLBACK")
                raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}")

            before_status = str(row["status"] or "")
            before_reviewed_by = str(row["reviewed_by"] or "")
            before_reviewed_at = int(row["reviewed_at"] or 0)
            before_comments = str(row["comments"] or "")
            merged_comment = _merge_comment(before_comments, comment)

            if action_type == "comment":
                outcome = "commented"
                await db.execute(
                    "UPDATE approvals SET comments = ?, updated_at = ? WHERE id = ?",
                    (merged_comment, now_ts, approval_id),
                )
            elif before_status in TERMINAL_APPROVAL_STATUSES and new_status != before_status:
                await db.execute("ROLLBACK")
                raise HTTPException(status_code=409, detail=f"approval_conflict_terminal:{before_status}")
            elif new_status is None:
                outcome = "unchanged"
            elif before_status == new_status:
                # Idempotent repeat of a terminal transition.
                outcome = "idempotent"
                if comment:
                    await db.execute(
                        "UPDATE approvals SET comments = ?, updated_at = ? WHERE id = ?",
                        (merged_comment, now_ts, approval_id),
                    )
            else:
                update = await db.execute(
                    """UPDATE approvals
                    SET status = ?, reviewed_by = ?, reviewed_at = ?, comments = ?, updated_at = ?
                    WHERE id = ? AND status = ?""",
                    (new_status, user_id, now_ts, merged_comment, now_ts, approval_id, before_status),
                )
                if update.rowcount != 1:
                    await db.execute("ROLLBACK")
                    raise HTTPException(status_code=409, detail="approval_conflict_race")
                outcome = "applied"

            after_cursor = await db.execute(
                "SELECT status, reviewed_by, reviewed_at, comments FROM approvals WHERE id = ?",
                (approval_id,),
            )
            after = await after_cursor.fetchone()
            if after is not None:
                after_status = str(after["status"] or "")
                after_reviewed_by = str(after["reviewed_by"] or "")
                after_reviewed_at = int(after["reviewed_at"] or 0)
                after_comments = str(after["comments"] or "")
            else:
                after_status = before_status
                after_reviewed_by = before_reviewed_by
                after_reviewed_at = before_reviewed_at
                after_comments = before_comments

            before_state = json.dumps(
                {
                    "status": before_status,
                    "reviewed_by": before_reviewed_by,
                    "reviewed_at": before_reviewed_at,
                    "comments": before_comments,
                },
                sort_keys=True,
            )
            after_state = json.dumps(
                {
                    "status": after_status,
                    "reviewed_by": after_reviewed_by,
                    "reviewed_at": after_reviewed_at,
                    "comments": after_comments,
                    "action": action_type,
                    "outcome": outcome,
                },
                sort_keys=True,
            )

            await db.execute(
                """INSERT INTO audit_ledger
                (user_id, session_id, event_type, target_type, target_id, before_state, after_state)
                VALUES (?, ?, ?, 'approval', ?, ?, ?)""",
                (user_id, session_id, event_type, approval_id, before_state, after_state),
            )
            await db.commit()
            response_status = after_status
        except HTTPException:
            raise
        except Exception as exc:
            await db.rollback()
            logger.exception(
                "approval_process_failed",
                approval_id=approval_id,
                action=action_type,
                user=user_id,
                error=str(exc),
            )
            raise HTTPException(status_code=500, detail="Approval processing failed") from exc

    logger.info("approval_processed", approval_id=approval_id, action=action_type, user=user_id)
    return {
        "approval_id": approval_id,
        "action": action_type,
        "status": response_status or (new_status or "unchanged"),
        "outcome": outcome,
    }


@router.get("/audit")
async def audit_log(
    event_type: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Query the audit ledger (append-only)."""
    async with get_db() as db:
        where_clauses = []
        params = []

        if event_type:
            where_clauses.append("event_type = ?")
            params.append(event_type)
        if target_type:
            where_clauses.append("target_type = ?")
            params.append(target_type)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        cursor = await db.execute(
            f"""SELECT id, timestamp, user_id, session_id, event_type,
                target_type, target_id, before_state, after_state, chain_hash
            FROM audit_ledger
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT ?""",
            params + [limit],
        )
        rows = await cursor.fetchall()
        entries = [dict(row) for row in rows]

    return {"entries": entries, "count": len(entries)}


@router.get("/summary/evidence", response_model=GovernanceEvidenceSummaryResponse)
async def governance_evidence_summary(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Evidence-backed governance aggregate across approvals/charter/audit/failsafe/replay."""
    _ = current_user
    safe_limit = max(1, min(limit, 500))
    fail_closed_reasons: list[str] = []
    generated_at = _now_iso()

    approvals_counts: dict[str, int] = {}
    approvals_recent: list[dict[str, Any]] = []

    charter_counts: dict[str, int] = {}
    charter_recent: list[dict[str, Any]] = []
    charter_pending_count = 0

    audit_recent: list[dict[str, Any]] = []
    audit_total = 0
    audit_last_24h = 0

    failsafe_recent: list[dict[str, Any]] = []
    failsafe_total = 0
    failsafe_by_type: dict[str, int] = {}

    integrity_total = 0
    integrity_invalid = 0
    integrity_last_verified = ""

    replay_recent: list[dict[str, Any]] = []
    replay_total = 0
    replay_open = 0

    async with get_db() as db:
        has_approvals = await _table_exists(db, "approvals")
        has_charter_requests = await _table_exists(db, "approval_requests")
        has_audit = await _table_exists(db, "audit_ledger")
        has_failsafe = await _table_exists(db, "failsafe_incidents")
        has_integrity = await _table_exists(db, "integrity_registry")
        has_replay = await _table_exists(db, "replay_incidents")

        if has_approvals:
            approval_columns = await _table_columns(db, "approvals")
            counts_cursor = await db.execute(
                "SELECT status, COUNT(*) AS count FROM approvals GROUP BY status"
            )
            approvals_counts = {
                str(row["status"]): int(row["count"])
                for row in await counts_cursor.fetchall()
            }
            desired = [
                "id",
                "patch_id",
                "dimension",
                "stage",
                "status",
                "actual_confidence",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
                "created_at",
            ]
            selected = [column for column in desired if column in approval_columns]
            if "id" not in selected:
                selected.insert(0, "id")
            order_by = (
                "updated_at" if "updated_at" in approval_columns else
                ("created_at" if "created_at" in approval_columns else "id")
            )
            recent_cursor = await db.execute(
                f"""SELECT {", ".join(selected)}
                    FROM approvals
                    ORDER BY {order_by} DESC
                    LIMIT ?""",
                (safe_limit,),
            )
            approvals_recent = [_row_dict(row) for row in await recent_cursor.fetchall()]
        else:
            fail_closed_reasons.append("governance_table_missing:approvals")

        if has_charter_requests:
            charter_columns = await _table_columns(db, "approval_requests")
            counts_cursor = await db.execute(
                "SELECT status, COUNT(*) AS count FROM approval_requests GROUP BY status"
            )
            charter_counts = {
                str(row["status"]): int(row["count"])
                for row in await counts_cursor.fetchall()
            }
            desired = [
                "request_id",
                "action",
                "action_type",
                "actor",
                "required_role",
                "status",
                "approved_by",
                "approved_at",
                "rejection_reason",
                "created_at",
                "expires_at",
            ]
            selected = [column for column in desired if column in charter_columns]
            if "request_id" not in selected and "id" in charter_columns:
                selected.insert(0, "id")
            order_by = "created_at" if "created_at" in charter_columns else selected[0]
            pending_cursor = await db.execute(
                f"""SELECT {", ".join(selected)}
                    FROM approval_requests
                    ORDER BY {order_by} DESC
                    LIMIT ?""",
                (safe_limit,),
            )
            charter_recent = [_row_dict(row) for row in await pending_cursor.fetchall()]
        else:
            fail_closed_reasons.append("governance_table_missing:approval_requests")

        if has_audit:
            total_cursor = await db.execute("SELECT COUNT(*) AS count FROM audit_ledger")
            total_row = await total_cursor.fetchone()
            audit_total = int(total_row["count"]) if total_row else 0

            last_day_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM audit_ledger WHERE timestamp >= (unixepoch() - 86400)"
            )
            last_day_row = await last_day_cursor.fetchone()
            audit_last_24h = int(last_day_row["count"]) if last_day_row else 0

            audit_cursor = await db.execute(
                """SELECT id, timestamp, user_id, session_id, event_type, target_type, target_id, chain_hash
                   FROM audit_ledger
                   ORDER BY id DESC
                   LIMIT ?""",
                (safe_limit,),
            )
            audit_recent = [_row_dict(row) for row in await audit_cursor.fetchall()]
        else:
            fail_closed_reasons.append("governance_table_missing:audit_ledger")

        if has_failsafe:
            total_cursor = await db.execute("SELECT COUNT(*) AS count FROM failsafe_incidents")
            total_row = await total_cursor.fetchone()
            failsafe_total = int(total_row["count"]) if total_row else 0

            by_type_cursor = await db.execute(
                "SELECT incident_type, COUNT(*) AS count FROM failsafe_incidents GROUP BY incident_type"
            )
            failsafe_by_type = {
                str(row["incident_type"]): int(row["count"])
                for row in await by_type_cursor.fetchall()
            }

            recent_cursor = await db.execute(
                """SELECT incident_id, incident_type, action, confidence, threshold, reason,
                          proceeded, degraded, human_review_required, created_at
                   FROM failsafe_incidents
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (safe_limit,),
            )
            failsafe_recent = [_row_dict(row) for row in await recent_cursor.fetchall()]
        else:
            fail_closed_reasons.append("governance_table_missing:failsafe_incidents")

        if has_integrity:
            total_cursor = await db.execute("SELECT COUNT(*) AS count FROM integrity_registry")
            total_row = await total_cursor.fetchone()
            integrity_total = int(total_row["count"]) if total_row else 0

            invalid_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM integrity_registry WHERE is_valid = 0"
            )
            invalid_row = await invalid_cursor.fetchone()
            integrity_invalid = int(invalid_row["count"]) if invalid_row else 0

            last_cursor = await db.execute(
                "SELECT MAX(COALESCE(last_verified_at, registered_at)) AS ts FROM integrity_registry"
            )
            last_row = await last_cursor.fetchone()
            integrity_last_verified = _to_iso_from_epoch(last_row["ts"] if last_row else None)
        else:
            fail_closed_reasons.append("governance_table_missing:integrity_registry")

        if has_replay:
            total_cursor = await db.execute("SELECT COUNT(*) AS count FROM replay_incidents")
            total_row = await total_cursor.fetchone()
            replay_total = int(total_row["count"]) if total_row else 0

            open_cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM replay_incidents WHERE status NOT IN ('resolved', 'closed')"
            )
            open_row = await open_cursor.fetchone()
            replay_open = int(open_row["count"]) if open_row else 0

            replay_cursor = await db.execute(
                """SELECT incident_id, task_id, agent_type, divergence_cause, status, severity, created_at
                   FROM replay_incidents
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (safe_limit,),
            )
            replay_recent = [_row_dict(row) for row in await replay_cursor.fetchall()]
        else:
            fail_closed_reasons.append("governance_table_missing:replay_incidents")

    # Include charter in-memory pending requests to avoid stale governance views.
    try:
        from core.routers.charter import APPROVAL_GATE  # local import avoids cycle at module load

        charter_pending_count = len(APPROVAL_GATE.get_pending())
    except Exception as exc:
        logger.warning("governance_charter_pending_unavailable", error=str(exc))
        fail_closed_reasons.append("charter_pending_source_unavailable")

    classification = "PASS" if not fail_closed_reasons else "FAIL_CLOSED"
    if classification == "FAIL_CLOSED":
        logger.warning(
            "governance_evidence_summary_fail_closed",
            fail_closed_reasons=fail_closed_reasons,
        )

    return GovernanceEvidenceSummaryResponse(
        generated_at=generated_at,
        classification=classification,
        fail_closed_reasons=sorted(set(fail_closed_reasons)),
        lineage={
            "source": "sqlite",
            "limit": safe_limit,
            "generated_at": generated_at,
            "governance_read_only": True,
        },
        approvals={
            "counts_by_status": approvals_counts,
            "recent": approvals_recent,
            "last_updated_at": _to_iso_from_epoch(
                max(
                    [row.get("updated_at", 0) for row in approvals_recent]
                    + [row.get("created_at", 0) for row in approvals_recent]
                    + [0]
                )
            ),
        },
        charter_requests={
            "counts_by_status": charter_counts,
            "pending_in_memory": charter_pending_count,
            "recent": charter_recent,
            "last_updated_at": _to_iso_from_epoch(
                max([row.get("created_at", 0) for row in charter_recent] + [0])
            ),
        },
        audit_history={
            "total_entries": audit_total,
            "entries_last_24h": audit_last_24h,
            "recent": audit_recent,
            "last_event_at": _to_iso_from_epoch(
                max([row.get("timestamp", 0) for row in audit_recent] + [0])
            ),
        },
        failsafe_reports={
            "total_incidents": failsafe_total,
            "counts_by_type": failsafe_by_type,
            "recent": failsafe_recent,
            "last_incident_at": _to_iso_from_epoch(
                max([row.get("created_at", 0) for row in failsafe_recent] + [0])
            ),
        },
        integrity_reports={
            "total_entries": integrity_total,
            "invalid_entries": integrity_invalid,
            "last_verified_at": integrity_last_verified,
        },
        replay_incidents={
            "total_incidents": replay_total,
            "open_incidents": replay_open,
            "recent": replay_recent,
            "last_incident_at": _to_iso_from_epoch(
                max([row.get("created_at", 0) for row in replay_recent] + [0])
            ),
        },
    )
