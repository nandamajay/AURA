"""FTS5 search for the knowledge base."""

from aura_sdk.db.connection import get_db


async def search_rules(query: str, limit: int = 20):
    """Full-text search over migration rules."""
    async with get_db() as db:
        try:
            cursor = await db.execute(
                """SELECT r.id, r.category, r.downstream_pattern,
                    r.upstream_equivalent, r.description, r.confidence
                FROM rules_fts fts
                JOIN migration_rules r ON fts.rowid = r.rowid
                WHERE rules_fts MATCH ?
                ORDER BY rank
                LIMIT ?""",
                (query, limit),
            )
            return [dict(row) for row in await cursor.fetchall()]
        except Exception:
            # Fallback to LIKE if FTS5 fails
            cursor = await db.execute(
                """SELECT id, category, downstream_pattern,
                    upstream_equivalent, description, confidence
                FROM migration_rules
                WHERE downstream_pattern LIKE ? OR upstream_equivalent LIKE ?
                LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            )
            return [dict(row) for row in await cursor.fetchall()]
