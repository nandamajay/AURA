"""Audit ledger — append-only writer with integrity chain."""

import hashlib
import json
import time
from typing import Any

from aura_sdk.db.connection import get_db


async def write_audit_entry(
    user_id: str,
    session_id: str,
    event_type: str,
    target_type: str,
    target_id: str,
    before_state: dict[str, Any] | None = None,
    after_state: dict[str, Any] | None = None,
) -> int:
    """Write an entry to the append-only audit ledger.

    Returns:
        The ID of the new ledger entry.
    """
    before_json = json.dumps(before_state) if before_state else None
    after_json = json.dumps(after_state) if after_state else None

    async with get_db() as db:
        cursor = await db.execute(
            """INSERT INTO audit_ledger
            (user_id, session_id, event_type, target_type, target_id,
             before_state, after_state, evidence_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                session_id,
                event_type,
                target_type,
                target_id,
                before_json,
                after_json,
                hashlib.sha256((after_json or "").encode()).hexdigest(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def verify_chain(limit: int = 1000) -> list[dict[str, Any]]:
    """Verify the integrity chain of recent audit entries.

    Returns:
        List of entries with integrity issues (empty if all good).
    """
    issues = []
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, timestamp, event_type, target_type, target_id,
                user_id, chain_hash
            FROM audit_ledger
            ORDER BY id DESC
            LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()

        for row in rows:
            entry = dict(row)
            # Verify chain hash
            prev_cursor = await db.execute(
                "SELECT chain_hash FROM audit_ledger WHERE id = ?",
                (entry["id"] - 1,),
            )
            prev_row = await prev_cursor.fetchone()
            prev_hash = prev_row[0] if prev_row else "0" * 64

            expected = hashlib.sha256(
                f"{prev_hash}{entry['timestamp']}{entry['event_type']}{entry['target_type']}{entry['target_id']}{entry.get('user_id', '')}".encode()
            ).hexdigest()

            if entry["chain_hash"] != expected:
                issues.append({
                    "id": entry["id"],
                    "expected": expected,
                    "actual": entry["chain_hash"],
                })

    return issues
