"""Review Coordinator Agent — builds deterministic review packets for governance."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class ReviewCoordinatorAgent(BaseAgent):
    """Patch review coordination agent."""

    AGENT_TYPE = "review_coordinator"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading review coordination context")

        context = self._load_context()
        db_path = str(context.get("db_path", "/data/aura.db"))
        patch_id = str(context.get("patch_id", "")).strip()
        limit = int(context.get("limit", 20))
        limit = max(5, min(limit, 100))
        await self._send_progress(
            20,
            "context_loaded",
            f"Using db_path={db_path}, patch_id={patch_id or 'latest'}, limit={limit}",
        )

        packet = self._build_packet(db_path=db_path, patch_id=patch_id, limit=limit)
        await self._send_progress(
            70,
            "packet_built",
            f"Collected approvals={len(packet['approvals'])}, tasks={len(packet['recent_tasks'])}",
        )

        packet["review_notes"] = await self._generate_review_notes(packet)

        json_path = self.output_dir / "review_packet.json"
        markdown_path = self.output_dir / "review_packet.md"
        json_path.write_text(json.dumps(packet, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, packet)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        summary = packet["summary"]
        return {
            "patch_id": packet.get("patch", {}).get("id", ""),
            "approval_pending": summary["approval_pending"],
            "approval_failed": summary["approval_failed"],
            "recommended_decision": summary["recommended_decision"],
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

    def _build_packet(self, *, db_path: str, patch_id: str, limit: int) -> dict[str, Any]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            patch = self._load_patch(conn, patch_id=patch_id)
            approvals = self._load_approvals(conn, patch_id=patch.get("id", ""), limit=limit)
            recent_tasks = self._query_rows(
                conn,
                """
                SELECT task_id, agent_type, model_version, created_at
                FROM task_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            open_risks = self._query_rows(
                conn,
                """
                SELECT risk_id, title, severity, status, owner
                FROM known_risks
                WHERE status IN ('open', 'in_progress')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            audit_events = self._query_rows(
                conn,
                """
                SELECT id, event_type, target_type, target_id, timestamp
                FROM audit_ledger
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
        finally:
            conn.close()

        pending = sum(1 for item in approvals if item.get("status") in {"pending", "in_progress"})
        failed = sum(1 for item in approvals if item.get("status") == "failed")
        passed = sum(1 for item in approvals if item.get("status") == "passed")

        if failed > 0:
            decision = "reject"
        elif pending > 0:
            decision = "hold"
        elif approvals and passed == len(approvals):
            decision = "approve"
        else:
            decision = "needs_review"

        return {
            "agent_type": self.AGENT_TYPE,
            "patch": patch,
            "approvals": approvals,
            "recent_tasks": recent_tasks,
            "open_risks": open_risks,
            "recent_audit_events": audit_events,
            "summary": {
                "approval_total": len(approvals),
                "approval_pending": pending,
                "approval_failed": failed,
                "approval_passed": passed,
                "open_risk_count": len(open_risks),
                "recommended_decision": decision,
            },
        }

    def _load_patch(self, conn: sqlite3.Connection, *, patch_id: str) -> dict[str, Any]:
        if patch_id:
            rows = self._query_rows(
                conn,
                """
                SELECT id, status, title, description, generated_by, created_at, updated_at
                FROM patches
                WHERE id = ?
                LIMIT 1
                """,
                (patch_id,),
            )
            if rows:
                return rows[0]

        rows = self._query_rows(
            conn,
            """
            SELECT id, status, title, description, generated_by, created_at, updated_at
            FROM patches
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (),
        )
        return rows[0] if rows else {}

    def _load_approvals(
        self,
        conn: sqlite3.Connection,
        *,
        patch_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        if patch_id:
            rows = self._query_rows(
                conn,
                """
                SELECT id, patch_id, dimension, stage, status, assigned_to, reviewed_by, comments, updated_at
                FROM approvals
                WHERE patch_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (patch_id, limit),
            )
            if rows:
                return rows
        return self._query_rows(
            conn,
            """
            SELECT id, patch_id, dimension, stage, status, assigned_to, reviewed_by, comments, updated_at
            FROM approvals
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )

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

    async def _generate_review_notes(self, packet: dict[str, Any]) -> list[str]:
        summary = packet["summary"]
        fallback = [
            (
                f"Approvals: total={summary['approval_total']} "
                f"pending={summary['approval_pending']} failed={summary['approval_failed']}."
            ),
            f"Recommended decision: {summary['recommended_decision']}.",
            "Review open risks before final sign-off on lifecycle and quality dimensions.",
        ]

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate concise review coordinator notes for governance board. "
                            'Return JSON only: {"notes":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "summary": summary,
                                "patch": packet.get("patch", {}),
                                "approvals": packet.get("approvals", [])[:8],
                                "open_risks": packet.get("open_risks", [])[:8],
                            }
                        ),
                    },
                ],
                max_tokens=350,
            )
            parsed = json.loads(response)
            notes = parsed.get("notes", [])
            if isinstance(notes, list):
                clean = [str(note).strip() for note in notes if str(note).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_markdown(self, path: Path, packet: dict[str, Any]) -> None:
        summary = packet["summary"]
        patch = packet.get("patch", {})
        with path.open("w", encoding="utf-8") as f:
            f.write("# Review Coordination Packet\n\n")
            f.write(f"- Patch ID: {patch.get('id', 'n/a')}\n")
            f.write(f"- Patch status: {patch.get('status', 'n/a')}\n")
            f.write(f"- Approval total: {summary['approval_total']}\n")
            f.write(f"- Approval pending: {summary['approval_pending']}\n")
            f.write(f"- Approval failed: {summary['approval_failed']}\n")
            f.write(f"- Open risks: {summary['open_risk_count']}\n")
            f.write(f"- Recommended decision: {summary['recommended_decision']}\n\n")
            f.write("## Approval Records\n\n")
            for item in packet["approvals"]:
                f.write(
                    f"- {item.get('id')}: patch={item.get('patch_id')} "
                    f"dimension={item.get('dimension')} stage={item.get('stage')} "
                    f"status={item.get('status')}\n"
                )
            f.write("\n## Review Notes\n\n")
            for note in packet.get("review_notes", []):
                f.write(f"- {note}\n")


if __name__ == "__main__":
    ReviewCoordinatorAgent.main()
