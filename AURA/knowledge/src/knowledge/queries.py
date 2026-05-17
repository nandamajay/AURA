"""Query builders for the knowledge base."""

from aura_sdk.db.connection import get_db


async def get_rules_for_subsystem(subsystem_name: str):
    """Get all migration rules for a subsystem."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT r.* FROM migration_rules r
            JOIN subsystems s ON r.subsystem_id = s.id
            WHERE s.name = ? ORDER BY r.confidence DESC""",
            (subsystem_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_maintainers_for_subsystem(subsystem_name: str):
    """Get maintainer profiles for a subsystem."""
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT m.* FROM maintainer_profiles m
            JOIN subsystems s ON m.subsystem_id = s.id
            WHERE s.name = ?""",
            (subsystem_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_patch_with_evidence(patch_id: str):
    """Get a patch with all its evidence links."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM patches WHERE id = ?", (patch_id,)
        )
        patch = await cursor.fetchone()
        if patch is None:
            return None

        cursor = await db.execute(
            "SELECT * FROM evidence_links WHERE patch_id = ?", (patch_id,)
        )
        evidence = [dict(row) for row in await cursor.fetchall()]

        result = dict(patch)
        result["evidence"] = evidence
        return result
