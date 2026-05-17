"""Knowledge base endpoints — rules, search, export."""

import csv
import io

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from core.routers.auth import get_current_user

logger = get_logger("core.knowledge")
router = APIRouter()

_CSV_EXPORT_FIELDS = [
    "id",
    "subsystem_id",
    "category",
    "downstream_pattern",
    "upstream_equivalent",
    "description",
    "confidence",
    "evidence_count",
    "source_refs",
    "created_at",
    "last_applied_at",
    "success_count",
    "failure_count",
]


class ExportKnowledgeRequest(BaseModel):
    """Knowledge export request payload."""

    format: str = "json"
    subsystem: str | None = None


@router.get("/rules")
async def list_rules(
    subsystem: str | None = None,
    category: str | None = None,
    page: int = 1,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """List migration rules with filtering."""
    async with get_db() as db:
        where_clauses = []
        params = []

        if subsystem:
            # Resolve subsystem name to ID
            cursor = await db.execute(
                "SELECT id FROM subsystems WHERE name = ?", (subsystem,)
            )
            row = await cursor.fetchone()
            if row:
                where_clauses.append("subsystem_id = ?")
                params.append(row[0])

        if category:
            where_clauses.append("category = ?")
            params.append(category)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Get total count
        count_cursor = await db.execute(
            f"SELECT COUNT(*) FROM migration_rules WHERE {where_sql}", params,
        )
        count_row = await count_cursor.fetchone()
        total = count_row[0] if count_row else 0

        # Get page
        offset = (page - 1) * limit
        cursor = await db.execute(
            f"""SELECT id, subsystem_id, category, downstream_pattern, upstream_equivalent,
                description, confidence, evidence_count, source_refs, created_at,
                success_count, failure_count
            FROM migration_rules WHERE {where_sql}
            ORDER BY confidence DESC, created_at DESC
            LIMIT ? OFFSET ?""",
            params + [limit, offset],
        )
        rows = await cursor.fetchall()

        rules = [dict(row) for row in rows]

    return {"rules": rules, "page": page, "limit": limit, "total": total}


@router.get("/rules/{rule_id}")
async def get_rule(rule_id: str, current_user: dict = Depends(get_current_user)):
    """Get rule details."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM migration_rules WHERE id = ?", (rule_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Rule not found")
        return dict(row)


@router.get("/search")
async def search_knowledge(
    q: str = "",
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Full-text search over migration rules using FTS5."""
    if not q:
        return {"results": [], "query": q}

    async with get_db() as db:
        try:
            cursor = await db.execute(
                """SELECT r.id, r.subsystem_id, r.category, r.downstream_pattern,
                    r.upstream_equivalent, r.description, r.confidence
                FROM rules_fts fts
                JOIN migration_rules r ON fts.rowid = r.rowid
                WHERE rules_fts MATCH ?
                ORDER BY rank
                LIMIT ?""",
                (q, limit),
            )
            rows = await cursor.fetchall()
            results = [dict(row) for row in rows]
        except Exception as e:
            logger.warning("fts_search_failed", query=q, error=str(e))
            # Fallback to LIKE search
            cursor = await db.execute(
                """SELECT id, subsystem_id, category, downstream_pattern,
                    upstream_equivalent, description, confidence
                FROM migration_rules
                WHERE downstream_pattern LIKE ? OR upstream_equivalent LIKE ?
                LIMIT ?""",
                (f"%{q}%", f"%{q}%", limit),
            )
            rows = await cursor.fetchall()
            results = [dict(row) for row in rows]

    return {"results": results, "query": q, "count": len(results)}


@router.post("/export")
async def export_knowledge(
    request: ExportKnowledgeRequest = Body(default_factory=ExportKnowledgeRequest),
    current_user: dict = Depends(get_current_user),
):
    """Export knowledge base as JSON or CSV."""
    format_type = request.format.strip().lower()
    subsystem = (request.subsystem or "").strip()

    if format_type not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="Unsupported export format. Use 'json' or 'csv'.")

    async with get_db() as db:
        if subsystem:
            cursor = await db.execute(
                "SELECT id FROM subsystems WHERE name = ?", (subsystem,)
            )
            row = await cursor.fetchone()
            subsys_id = row[0] if row else None
            if subsys_id:
                cursor = await db.execute(
                    "SELECT * FROM migration_rules WHERE subsystem_id = ?",
                    (subsys_id,),
                )
            else:
                raise HTTPException(status_code=404, detail=f"Subsystem not found: {subsystem}")
        else:
            cursor = await db.execute("SELECT * FROM migration_rules")

        rows = await cursor.fetchall()
        rules = [dict(row) for row in rows]

    if format_type == "json":
        return {"format": "json", "count": len(rules), "data": rules}

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_EXPORT_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rules)

    return {"format": "csv", "count": len(rules), "data": output.getvalue()}
