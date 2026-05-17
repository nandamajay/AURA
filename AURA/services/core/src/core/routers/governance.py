"""Governance endpoints — approvals, audit log."""

import json
import time

from fastapi import APIRouter, Depends, HTTPException

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
