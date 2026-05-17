"""Governance endpoints — approvals, audit log."""

from fastapi import APIRouter, Depends, HTTPException

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.governance import ApprovalAction
from core.routers.auth import get_current_user

logger = get_logger("core.governance")
router = APIRouter()


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
    comment = action.get("comment", "")

    if action_type not in [a.value for a in ApprovalAction]:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action_type}")

    user_id = current_user.get("sub", "")

    async with get_db() as db:
        # Update approval
        new_status = {
            "grant": "passed",
            "reject": "failed",
            "escalate": "escalated",
            "comment": None,  # Don't change status on comment
        }.get(action_type)

        if new_status:
            await db.execute(
                """UPDATE approvals SET status = ?, reviewed_by = ?, reviewed_at = ?, comments = ?
                WHERE id = ?""",
                (new_status, user_id, int(__import__("time").time()), comment, approval_id),
            )
            await db.commit()

        # Write to audit ledger
        await db.execute(
            """INSERT INTO audit_ledger
            (user_id, session_id, event_type, target_type, target_id, after_state)
            VALUES (?, ?, ?, 'approval', ?, ?)""",
            (
                user_id,
                current_user.get("email", ""),
                f"approval.{action_type}ed",
                approval_id,
                f'{{"status":"{new_status}","action":"{action_type}"}}',
            ),
        )
        await db.commit()

    logger.info("approval_processed", approval_id=approval_id, action=action_type, user=user_id)
    return {"approval_id": approval_id, "action": action_type, "status": new_status or "unchanged"}


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
