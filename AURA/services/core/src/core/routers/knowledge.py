"""Knowledge base endpoints — rules, search, export."""

import csv
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from core.contracts.transport_artifact_contracts import resolve_repo_root
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

_EVIDENCE_ALLOWED_SUFFIXES = {".md", ".json", ".txt", ".log", ".csv"}
_EVIDENCE_MAX_BYTES = 400_000


def _resolve_repo_root() -> Path:
    """Resolve repository root without brittle fixed parent-index assumptions."""
    return resolve_repo_root()


def _evidence_sections(repo_root: Path) -> dict[str, Path]:
    mapping = {
        "runtime_evidence": repo_root / "evidence",
        "transport_artifacts": repo_root / "docs" / "operations" / "transport",
        "architecture_consolidation": repo_root / "docs" / "architecture-consolidation",
        "p1_docs": repo_root / "p1",
        "p2_docs": repo_root / "p2",
        "phase0_docs": repo_root / "phase0",
    }
    return {name: path.resolve() for name, path in mapping.items() if path.exists()}


def _collect_files(root: Path, *, max_depth: int, limit: int) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    root_resolved = root.resolve()
    for file_path in sorted(root.rglob("*")):
        if len(collected) >= limit:
            break
        if not file_path.is_file():
            continue
        try:
            rel = file_path.resolve().relative_to(root_resolved)
        except Exception:
            continue
        if len(rel.parts) > max_depth:
            continue
        suffix = file_path.suffix.lower()
        if suffix and suffix not in _EVIDENCE_ALLOWED_SUFFIXES:
            continue
        stat = file_path.stat()
        collected.append(
            {
                "path": str(rel),
                "name": file_path.name,
                "extension": suffix or "",
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )
    return collected


def _resolve_section_file(
    *,
    sections: dict[str, Path],
    section: str,
    relative_path: str,
) -> Path:
    if section not in sections:
        raise HTTPException(status_code=404, detail=f"Unknown evidence section: {section}")
    if not relative_path or relative_path.strip() in {".", "/"}:
        raise HTTPException(status_code=400, detail="relative_path is required")
    root = sections[section]
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Path escapes evidence section root") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail=f"Evidence file not found: {relative_path}")
    suffix = candidate.suffix.lower()
    if suffix and suffix not in _EVIDENCE_ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail=f"Unsupported evidence file type: {suffix}")
    return candidate


class ExportKnowledgeRequest(BaseModel):
    """Knowledge export request payload."""

    format: str = "json"
    subsystem: str | None = None


@router.get("/evidence/index")
async def evidence_index(
    section: str = "",
    max_depth: int = 4,
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
):
    """List evidence files for operator evidence navigation."""
    _ = current_user
    if max_depth < 1 or max_depth > 10:
        raise HTTPException(status_code=400, detail="max_depth must be between 1 and 10")
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")

    try:
        repo_root = _resolve_repo_root()
        sections = _evidence_sections(repo_root)
    except Exception as exc:
        logger.exception("evidence_index_failed", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "code": "evidence_index_unavailable",
                "message": str(exc),
                "classification": "FAIL_CLOSED",
            },
        ) from exc
    if not sections:
        return {"repo_root": str(repo_root), "sections": {}}

    selected = section.strip()
    payload: dict[str, Any] = {}
    for name, root in sections.items():
        if selected and selected != name:
            continue
        payload[name] = {
            "root": str(root),
            "files": _collect_files(root, max_depth=max_depth, limit=limit),
        }
    return {
        "repo_root": str(repo_root),
        "sections": payload,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/evidence/read")
async def evidence_read(
    section: str,
    relative_path: str,
    max_bytes: int = 120_000,
    current_user: dict = Depends(get_current_user),
):
    """Read one evidence file from an allowed evidence section."""
    _ = current_user
    if max_bytes < 1 or max_bytes > _EVIDENCE_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"max_bytes must be between 1 and {_EVIDENCE_MAX_BYTES}",
        )
    try:
        repo_root = _resolve_repo_root()
        sections = _evidence_sections(repo_root)
        file_path = _resolve_section_file(
            sections=sections, section=section.strip(), relative_path=relative_path.strip()
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("evidence_read_failed", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "code": "evidence_read_unavailable",
                "message": str(exc),
                "classification": "FAIL_CLOSED",
            },
        ) from exc
    file_size = int(file_path.stat().st_size)
    raw = file_path.read_bytes()
    truncated = len(raw) > max_bytes
    raw = raw[:max_bytes]
    content = raw.decode("utf-8", errors="replace")
    return {
        "section": section,
        "relative_path": relative_path,
        "absolute_path": str(file_path),
        "size_bytes": file_size,
        "returned_bytes": len(raw),
        "truncated": truncated,
        "content": content,
    }


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
