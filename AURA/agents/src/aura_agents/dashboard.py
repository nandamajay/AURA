"""Dashboard Agent — synthesizes operational dashboard snapshots from SQLite state."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class DashboardAgent(BaseAgent):
    """Dashboard synthesis support agent."""

    AGENT_TYPE = "dashboard"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading dashboard synthesis context")

        context = self._load_context()
        db_path = str(context.get("db_path", "/data/aura.db"))
        table_limit = int(context.get("table_limit", 20))
        table_limit = max(5, min(table_limit, 100))
        await self._send_progress(
            20,
            "context_loaded",
            f"Using db_path={db_path}, table_limit={table_limit}",
        )

        snapshot = self._collect_snapshot(db_path=db_path, table_limit=table_limit)
        await self._send_progress(
            65,
            "snapshot_collected",
            f"Collected {snapshot['summary']['tables_scanned']} table metrics",
        )

        snapshot["operator_highlights"] = await self._generate_operator_highlights(snapshot)

        json_path = self.output_dir / "dashboard_snapshot.json"
        markdown_path = self.output_dir / "dashboard_digest.md"
        json_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, snapshot)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        summary = snapshot["summary"]
        return {
            "tables_scanned": summary["tables_scanned"],
            "rows_indexed": summary["rows_indexed"],
            "pending_approvals": snapshot["metrics"]["pending_approvals"],
            "open_risks": snapshot["metrics"]["open_known_risks"],
            "json_path": str(json_path),
            "markdown_path": str(markdown_path),
        }

    def _load_context(self) -> dict[str, Any]:
        raw = getattr(self, "input_json", "")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        return {}

    def _collect_snapshot(self, *, db_path: str, table_limit: int) -> dict[str, Any]:
        tracked_tables = [
            "users",
            "subsystems",
            "migration_rules",
            "maintainer_profiles",
            "patches",
            "approvals",
            "evidence_links",
            "audit_ledger",
            "simulation_results",
            "learning_events",
            "task_logs",
            "engineering_decisions",
            "technical_debt",
            "known_risks",
            "future_migrations",
            "deferred_scalability",
            "replay_incidents",
            "architecture_drift",
            "operational_incidents",
            "stabilization_timeline",
        ]

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            table_counts: dict[str, int] = {}
            for table in tracked_tables:
                table_counts[table] = self._query_int(conn, f"SELECT COUNT(*) AS c FROM {table}")

            metrics = {
                "active_users": self._query_int(conn, "SELECT COUNT(*) FROM users WHERE is_active = 1"),
                "pending_approvals": self._query_int(
                    conn,
                    "SELECT COUNT(*) FROM approvals WHERE status IN ('pending', 'in_progress')",
                ),
                "open_known_risks": self._query_int(
                    conn,
                    "SELECT COUNT(*) FROM known_risks WHERE status IN ('open', 'in_progress')",
                ),
                "open_technical_debt": self._query_int(
                    conn,
                    "SELECT COUNT(*) FROM technical_debt WHERE status IN ('open', 'in_progress')",
                ),
                "deferred_migrations": self._query_int(
                    conn,
                    "SELECT COUNT(*) FROM future_migrations WHERE status = 'deferred'",
                ),
                "task_logs": table_counts.get("task_logs", 0),
                "learning_events": table_counts.get("learning_events", 0),
            }

            recent_activity = {
                "task_logs": self._query_rows(
                    conn,
                    """
                    SELECT task_id, agent_type, model_version, created_at
                    FROM task_logs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (table_limit,),
                ),
                "audit_events": self._query_rows(
                    conn,
                    """
                    SELECT id, event_type, target_type, target_id, timestamp
                    FROM audit_ledger
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (table_limit,),
                ),
                "patches": self._query_rows(
                    conn,
                    """
                    SELECT id, status, title, generated_by, updated_at
                    FROM patches
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (table_limit,),
                ),
                "approvals": self._query_rows(
                    conn,
                    """
                    SELECT id, patch_id, dimension, stage, status, updated_at
                    FROM approvals
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (table_limit,),
                ),
            }
        finally:
            conn.close()

        ranked_tables = sorted(table_counts.items(), key=lambda item: (-item[1], item[0]))
        rows_indexed = sum(table_counts.values())
        snapshot = {
            "agent_type": self.AGENT_TYPE,
            "metrics": metrics,
            "table_counts": table_counts,
            "recent_activity": recent_activity,
            "summary": {
                "tables_scanned": len(tracked_tables),
                "rows_indexed": rows_indexed,
                "top_tables": [
                    {"table": name, "rows": rows}
                    for name, rows in ranked_tables[:6]
                ],
            },
        }
        return snapshot

    def _query_int(self, conn: sqlite3.Connection, query: str) -> int:
        try:
            row = conn.execute(query).fetchone()
            if row is None:
                return 0
            if isinstance(row, sqlite3.Row):
                value = row[0]
            else:
                value = row[0]
            return int(value or 0)
        except Exception:
            return 0

    def _query_rows(
        self,
        conn: sqlite3.Connection,
        query: str,
        params: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        try:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []

    async def _generate_operator_highlights(self, snapshot: dict[str, Any]) -> list[str]:
        metrics = snapshot["metrics"]
        fallback = [
            (
                f"Pending approvals={metrics['pending_approvals']}, "
                f"open risks={metrics['open_known_risks']}, "
                f"open technical debt={metrics['open_technical_debt']}."
            ),
            f"Task logs recorded={metrics['task_logs']}, learning events={metrics['learning_events']}.",
        ]

        top_tables = snapshot["summary"]["top_tables"]
        if top_tables:
            fallback.append(
                "Highest-volume tables: "
                + ", ".join(f"{entry['table']}({entry['rows']})" for entry in top_tables[:3])
            )

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate concise dashboard operator highlights. "
                            'Return JSON only: {"highlights":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "metrics": metrics,
                                "top_tables": top_tables,
                                "recent_activity_counts": {
                                    key: len(value)
                                    for key, value in snapshot["recent_activity"].items()
                                },
                            }
                        ),
                    },
                ],
                max_tokens=350,
            )
            parsed = json.loads(response)
            highlights = parsed.get("highlights", [])
            if isinstance(highlights, list):
                clean = [str(h).strip() for h in highlights if str(h).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_markdown(self, path: Path, snapshot: dict[str, Any]) -> None:
        summary = snapshot["summary"]
        metrics = snapshot["metrics"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Dashboard Digest\n\n")
            f.write(f"- Tables scanned: {summary['tables_scanned']}\n")
            f.write(f"- Rows indexed: {summary['rows_indexed']}\n")
            f.write(f"- Pending approvals: {metrics['pending_approvals']}\n")
            f.write(f"- Open known risks: {metrics['open_known_risks']}\n")
            f.write(f"- Open technical debt: {metrics['open_technical_debt']}\n\n")
            f.write("## Top Tables\n\n")
            for entry in summary["top_tables"]:
                f.write(f"- {entry['table']}: {entry['rows']}\n")
            f.write("\n## Operator Highlights\n\n")
            for highlight in snapshot.get("operator_highlights", []):
                f.write(f"- {highlight}\n")


if __name__ == "__main__":
    DashboardAgent.main()
