"""Knowledge base export utilities."""

import json
from pathlib import Path

from aura_sdk.db.connection import get_db


async def export_json(output_path: str, subsystem: str | None = None):
    """Export all rules as JSON."""
    async with get_db() as db:
        if subsystem:
            cursor = await db.execute(
                """SELECT r.* FROM migration_rules r
                JOIN subsystems s ON r.subsystem_id = s.id
                WHERE s.name = ?""",
                (subsystem,),
            )
        else:
            cursor = await db.execute("SELECT * FROM migration_rules")

        rows = await cursor.fetchall()
        rules = [dict(row) for row in rows]

    Path(output_path).write_text(json.dumps(rules, indent=2, default=str))
    return len(rules)


async def export_csv(output_path: str, subsystem: str | None = None):
    """Export all rules as CSV."""
    import csv

    async with get_db() as db:
        if subsystem:
            cursor = await db.execute(
                """SELECT r.* FROM migration_rules r
                JOIN subsystems s ON r.subsystem_id = s.id
                WHERE s.name = ?""",
                (subsystem,),
            )
        else:
            cursor = await db.execute("SELECT * FROM migration_rules")

        rows = await cursor.fetchall()
        if not rows:
            return 0

        fieldnames = rows[0].keys()
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows([dict(row) for row in rows])

        return len(rows)
