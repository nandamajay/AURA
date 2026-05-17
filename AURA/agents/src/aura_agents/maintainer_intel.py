"""Maintainer Intelligence Agent — builds deterministic maintainer engagement briefs."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class MaintainerIntelAgent(BaseAgent):
    """Maintainer intelligence profiling agent."""

    AGENT_TYPE = "maintainer_intel"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading maintainer intelligence context")

        context = self._load_context()
        db_path = str(context.get("db_path", "/data/aura.db"))
        subsystem_filter = str(context.get("subsystem", "audio-qualcomm"))
        limit = int(context.get("limit", 25))
        limit = max(5, min(limit, 100))
        await self._send_progress(
            20,
            "context_loaded",
            f"Using db_path={db_path}, subsystem={subsystem_filter}, limit={limit}",
        )

        report = self._collect_report(
            db_path=db_path,
            subsystem_filter=subsystem_filter,
            limit=limit,
        )
        await self._send_progress(
            70,
            "report_collected",
            f"Collected {len(report['maintainers'])} maintainer profile(s)",
        )

        report["engagement_notes"] = await self._generate_engagement_notes(report)

        json_path = self.output_dir / "maintainer_intel.json"
        markdown_path = self.output_dir / "maintainer_intel.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, report)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        summary = report["summary"]
        return {
            "maintainers": summary["maintainer_count"],
            "high_priority_contacts": summary["high_priority_contacts"],
            "subsystem": summary["subsystem"],
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

    def _collect_report(
        self,
        *,
        db_path: str,
        subsystem_filter: str,
        limit: int,
    ) -> dict[str, Any]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            maintainers = self._query_rows(
                conn,
                """
                SELECT
                    m.id,
                    m.name,
                    m.email,
                    m.acceptance_rate,
                    m.review_count,
                    m.common_nak_reasons,
                    m.preferred_patterns,
                    s.name AS subsystem_name,
                    s.display_name AS subsystem_display_name
                FROM maintainer_profiles m
                LEFT JOIN subsystems s ON s.id = m.subsystem_id
                WHERE (? = '' OR s.name = ? OR s.display_name = ?)
                ORDER BY COALESCE(m.acceptance_rate, 0.0) DESC, COALESCE(m.review_count, 0) DESC
                LIMIT ?
                """,
                (subsystem_filter, subsystem_filter, subsystem_filter, limit),
            )
            if not maintainers:
                maintainers = self._query_rows(
                    conn,
                    """
                    SELECT
                        m.id,
                        m.name,
                        m.email,
                        m.acceptance_rate,
                        m.review_count,
                        m.common_nak_reasons,
                        m.preferred_patterns,
                        s.name AS subsystem_name,
                        s.display_name AS subsystem_display_name
                    FROM maintainer_profiles m
                    LEFT JOIN subsystems s ON s.id = m.subsystem_id
                    ORDER BY COALESCE(m.acceptance_rate, 0.0) DESC, COALESCE(m.review_count, 0) DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

            for profile in maintainers:
                profile["engagement_priority"] = self._priority(profile)
                profile["risk_flags"] = self._risk_flags(profile)

            risk_owner_rows = self._query_rows(
                conn,
                """
                SELECT owner, COUNT(*) AS open_risks
                FROM known_risks
                WHERE status IN ('open', 'in_progress')
                GROUP BY owner
                ORDER BY open_risks DESC, owner
                """,
                (),
            )
            risk_owner_map = {
                str(row.get("owner", "")).strip().lower(): int(row.get("open_risks", 0))
                for row in risk_owner_rows
                if str(row.get("owner", "")).strip()
            }
            for profile in maintainers:
                email = str(profile.get("email") or "").strip().lower()
                profile["open_risks_owned"] = risk_owner_map.get(email, 0)

            top_rules = self._query_rows(
                conn,
                """
                SELECT category, COUNT(*) AS count
                FROM migration_rules
                GROUP BY category
                ORDER BY count DESC, category
                """,
                (),
            )
        finally:
            conn.close()

        maintainers_sorted = sorted(
            maintainers,
            key=lambda item: (
                self._priority_rank(item.get("engagement_priority", "low")),
                -float(item.get("acceptance_rate") or 0.0),
                -int(item.get("review_count") or 0),
                str(item.get("name") or ""),
            ),
        )

        summary = {
            "subsystem": subsystem_filter,
            "maintainer_count": len(maintainers_sorted),
            "high_priority_contacts": sum(
                1 for item in maintainers_sorted if item.get("engagement_priority") == "high"
            ),
            "top_rule_categories": top_rules[:5],
        }

        return {
            "agent_type": self.AGENT_TYPE,
            "summary": summary,
            "maintainers": maintainers_sorted,
            "risk_owner_map": risk_owner_rows,
            "top_rule_categories": top_rules,
        }

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

    def _priority(self, profile: dict[str, Any]) -> str:
        acceptance_rate = float(profile.get("acceptance_rate") or 0.0)
        review_count = int(profile.get("review_count") or 0)
        if acceptance_rate >= 0.75 and review_count >= 10:
            return "high"
        if acceptance_rate >= 0.5 or review_count >= 5:
            return "medium"
        return "low"

    def _priority_rank(self, priority: str) -> int:
        if priority == "high":
            return 0
        if priority == "medium":
            return 1
        return 2

    def _risk_flags(self, profile: dict[str, Any]) -> list[str]:
        flags: list[str] = []
        acceptance_rate = float(profile.get("acceptance_rate") or 0.0)
        review_count = int(profile.get("review_count") or 0)
        if review_count < 3:
            flags.append("low_review_sample")
        if acceptance_rate < 0.4:
            flags.append("low_acceptance_rate")
        if not str(profile.get("email") or "").strip():
            flags.append("missing_email")
        return flags

    async def _generate_engagement_notes(self, report: dict[str, Any]) -> list[str]:
        summary = report["summary"]
        fallback = [
            (
                f"Maintainers analyzed={summary['maintainer_count']}, "
                f"high-priority contacts={summary['high_priority_contacts']}."
            ),
            "Prioritize high acceptance-rate maintainers for early RFC feedback loops.",
        ]
        if summary["top_rule_categories"]:
            fallback.append(
                "Top migration rule categories: "
                + ", ".join(
                    f"{row['category']}({row['count']})"
                    for row in summary["top_rule_categories"][:3]
                )
            )

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate concise maintainer engagement notes for kernel upstreaming. "
                            'Return JSON only: {"notes":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "summary": summary,
                                "maintainers": report["maintainers"][:8],
                            }
                        ),
                    },
                ],
                max_tokens=350,
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

    def _write_markdown(self, path: Path, report: dict[str, Any]) -> None:
        summary = report["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Maintainer Intelligence Report\n\n")
            f.write(f"- Subsystem filter: {summary['subsystem']}\n")
            f.write(f"- Maintainers analyzed: {summary['maintainer_count']}\n")
            f.write(f"- High priority contacts: {summary['high_priority_contacts']}\n\n")
            f.write("## Maintainer Ranking\n\n")
            for item in report["maintainers"]:
                f.write(
                    f"- {item.get('name', 'unknown')} <{item.get('email', 'n/a')}> "
                    f"[priority={item.get('engagement_priority')}, "
                    f"acceptance_rate={item.get('acceptance_rate')}, "
                    f"reviews={item.get('review_count')}, "
                    f"open_risks_owned={item.get('open_risks_owned')}]\n"
                )
            f.write("\n## Engagement Notes\n\n")
            for note in report.get("engagement_notes", []):
                f.write(f"- {note}\n")


if __name__ == "__main__":
    MaintainerIntelAgent.main()
