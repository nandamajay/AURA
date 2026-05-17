"""Knowledge Base Agent — curates a deterministic knowledge snapshot for operators."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class KnowledgeBaseAgent(BaseAgent):
    """Knowledge curation and retrieval agent."""

    AGENT_TYPE = "knowledge_base"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading knowledge curation context")

        context = self._load_context()
        limit = int(context.get("limit", 25))
        limit = max(5, min(limit, 100))
        db_path = str(context.get("db_path", "/data/aura.db"))
        await self._send_progress(20, "context_loaded", f"Using db_path={db_path}, limit={limit}")

        snapshot = self._collect_snapshot(db_path=db_path, limit=limit)
        await self._send_progress(
            65,
            "snapshot_collected",
            f"Collected {snapshot['summary']['tables_scanned']} table(s)",
        )

        snapshot["operator_notes"] = await self._generate_operator_notes(snapshot)

        json_path = self.output_dir / "knowledge_snapshot.json"
        markdown_path = self.output_dir / "knowledge_digest.md"
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
            "records_collected": summary["records_collected"],
            "subsystems": summary["subsystem_count"],
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

    def _collect_snapshot(self, *, db_path: str, limit: int) -> dict[str, Any]:
        tables = [
            ("subsystems", "SELECT id, name, display_name, version, is_active, created_at FROM subsystems LIMIT ?"),
            ("known_risks", "SELECT risk_id, title, severity, status, owner, created_at FROM known_risks ORDER BY created_at DESC LIMIT ?"),
            ("technical_debt", "SELECT debt_id, title, subsystem, debt_type, status, severity, created_at FROM technical_debt ORDER BY created_at DESC LIMIT ?"),
            ("future_migrations", "SELECT migration_id, title, trigger_phase, status, priority, created_at FROM future_migrations ORDER BY created_at DESC LIMIT ?"),
            ("deferred_scalability", "SELECT item_id, title, subsystem, status, priority, created_at FROM deferred_scalability ORDER BY created_at DESC LIMIT ?"),
            ("engineering_decisions", "SELECT decision_id, title, subsystem, decided_by, created_at FROM engineering_decisions ORDER BY created_at DESC LIMIT ?"),
            ("task_logs", "SELECT task_id, agent_type, model_version, created_at FROM task_logs ORDER BY created_at DESC LIMIT ?"),
            ("migration_rules", "SELECT id, subsystem_id, category, downstream_pattern, upstream_equivalent, confidence FROM migration_rules ORDER BY created_at DESC LIMIT ?"),
            ("maintainer_profiles", "SELECT id, name, email, subsystem_id, acceptance_rate, review_count FROM maintainer_profiles LIMIT ?"),
            ("evidence_links", "SELECT id, patch_id, rule_id, evidence_type, confidence, created_at FROM evidence_links ORDER BY created_at DESC LIMIT ?"),
        ]

        snapshot: dict[str, Any] = {"agent_type": self.AGENT_TYPE, "tables": {}, "summary": {}}
        records_collected = 0
        scanned = 0

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            for table, query in tables:
                try:
                    rows = conn.execute(query, (limit,)).fetchall()
                    items = [dict(row) for row in rows]
                    snapshot["tables"][table] = {
                        "count": len(items),
                        "records": items,
                    }
                    records_collected += len(items)
                    scanned += 1
                except Exception as exc:
                    snapshot["tables"][table] = {"count": 0, "records": [], "error": str(exc)}
                    scanned += 1
        finally:
            conn.close()

        subsystem_count = snapshot["tables"].get("subsystems", {}).get("count", 0)
        snapshot["summary"] = {
            "tables_scanned": scanned,
            "records_collected": records_collected,
            "subsystem_count": subsystem_count,
            "top_knowledge_sources": self._top_sources(snapshot),
        }
        return snapshot

    def _top_sources(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        ranking = []
        for name, content in snapshot["tables"].items():
            ranking.append({"table": name, "count": int(content.get("count", 0))})
        ranking.sort(key=lambda x: (-x["count"], x["table"]))
        return ranking[:6]

    async def _generate_operator_notes(self, snapshot: dict[str, Any]) -> list[str]:
        fallback = [
            f"Collected {snapshot['summary']['records_collected']} records across {snapshot['summary']['tables_scanned']} tables.",
            "Use high-count tables as primary evidence for migration guidance.",
        ]
        top = snapshot["summary"]["top_knowledge_sources"]
        if top:
            fallback.append(
                "Primary sources: " + ", ".join(f"{entry['table']}({entry['count']})" for entry in top[:3])
            )

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Produce concise operator notes for a knowledge snapshot. "
                            'Return JSON only: {"notes":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "summary": snapshot["summary"],
                                "table_counts": {
                                    name: payload.get("count", 0)
                                    for name, payload in snapshot["tables"].items()
                                },
                            }
                        ),
                    },
                ],
                max_tokens=400,
            )
            parsed = json.loads(response)
            notes = parsed.get("notes", [])
            if isinstance(notes, list):
                clean = [str(n).strip() for n in notes if str(n).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_markdown(self, path: Path, snapshot: dict[str, Any]) -> None:
        summary = snapshot["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Knowledge Digest\n\n")
            f.write(f"- Tables scanned: {summary['tables_scanned']}\n")
            f.write(f"- Records collected: {summary['records_collected']}\n")
            f.write(f"- Subsystems: {summary['subsystem_count']}\n\n")
            f.write("## Top Sources\n\n")
            for src in summary["top_knowledge_sources"]:
                f.write(f"- {src['table']}: {src['count']}\n")
            f.write("\n## Operator Notes\n\n")
            for note in snapshot.get("operator_notes", []):
                f.write(f"- {note}\n")


if __name__ == "__main__":
    KnowledgeBaseAgent.main()
