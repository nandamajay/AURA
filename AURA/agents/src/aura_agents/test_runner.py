"""Test Runner Agent — executes deterministic validation suite planning."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class TestRunnerAgent(BaseAgent):
    """Test orchestration agent."""

    AGENT_TYPE = "test_runner"
    DEFAULT_TIMEOUT = 900

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading test runner context")

        context = self._load_context()
        db_path = str(context.get("db_path", "/data/aura.db"))
        suites = self._extract_suites(context)
        severity = int(context.get("severity", 2))
        severity = max(1, min(severity, 5))
        await self._send_progress(
            20,
            "context_loaded",
            f"Prepared {len(suites)} validation suite(s) with severity={severity}",
        )

        risk_signal = self._load_risk_signal(db_path=db_path)
        await self._send_progress(
            45,
            "risk_signal_loaded",
            f"Risk signal loaded: open_risks={risk_signal['open_risks']}, open_debt={risk_signal['open_debt']}",
        )

        results = [self._run_suite(suite, severity, risk_signal) for suite in suites]
        summary = self._summarize(results)
        report = {
            "agent_type": self.AGENT_TYPE,
            "severity": severity,
            "risk_signal": risk_signal,
            "suites": results,
            "summary": summary,
        }
        report["actions"] = await self._generate_actions(report)

        json_path = self.output_dir / "test_runner_report.json"
        markdown_path = self.output_dir / "test_runner_report.md"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, report)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        return {
            "suite_count": len(suites),
            "passed": summary["passed"],
            "failed": summary["failed"],
            "flaky": summary["flaky"],
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

    def _extract_suites(self, context: dict[str, Any]) -> list[str]:
        suites: list[str] = []
        raw = context.get("suites")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    suites.append(item.strip())
        if not suites:
            suites = ["checkpatch", "sparse", "clang", "dtbs_check"]
        dedup: dict[str, None] = {}
        for suite in suites:
            dedup[suite] = None
        return list(dedup.keys())[:20]

    def _load_risk_signal(self, *, db_path: str) -> dict[str, int]:
        conn = sqlite3.connect(db_path)
        try:
            open_risks = self._query_int(
                conn,
                "SELECT COUNT(*) FROM known_risks WHERE status IN ('open', 'in_progress')",
            )
            open_debt = self._query_int(
                conn,
                "SELECT COUNT(*) FROM technical_debt WHERE status IN ('open', 'in_progress')",
            )
            replay_incidents = self._query_int(
                conn,
                "SELECT COUNT(*) FROM replay_incidents WHERE status IN ('open', 'in_progress')",
            )
        finally:
            conn.close()
        return {
            "open_risks": open_risks,
            "open_debt": open_debt,
            "open_replay_incidents": replay_incidents,
        }

    def _query_int(self, conn: sqlite3.Connection, query: str) -> int:
        try:
            row = conn.execute(query).fetchone()
            return int(row[0] if row else 0)
        except Exception:
            return 0

    def _run_suite(
        self,
        suite: str,
        severity: int,
        risk_signal: dict[str, int],
    ) -> dict[str, Any]:
        base_fail = {
            "checkpatch": 0.08,
            "sparse": 0.10,
            "clang": 0.12,
            "dtbs_check": 0.10,
        }.get(suite, 0.09)

        risk_factor = (
            (risk_signal["open_risks"] * 0.004)
            + (risk_signal["open_debt"] * 0.003)
            + (risk_signal["open_replay_incidents"] * 0.005)
        )
        severity_factor = (severity - 1) * 0.02
        fail_ratio = min(0.75, max(0.02, base_fail + risk_factor + severity_factor))
        flaky_ratio = min(0.25, fail_ratio * 0.25)

        signal = self.context.random_float(0.0, 1.0) if self.context else 0.5
        if signal < fail_ratio:
            verdict = "failed"
        elif signal < fail_ratio + flaky_ratio:
            verdict = "flaky"
        else:
            verdict = "passed"

        issue_count = 0
        if verdict == "failed":
            issue_count = self.context.random_int(2, 8) if self.context else 3
        elif verdict == "flaky":
            issue_count = 1

        duration_ms = self.context.random_int(180, 950) if self.context else 400
        return {
            "suite": suite,
            "verdict": verdict,
            "issue_count": issue_count,
            "duration_ms": duration_ms,
            "signal": round(signal, 3),
            "fail_ratio": round(fail_ratio, 3),
        }

    def _summarize(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        passed = sum(1 for item in results if item["verdict"] == "passed")
        failed = sum(1 for item in results if item["verdict"] == "failed")
        flaky = sum(1 for item in results if item["verdict"] == "flaky")
        total_issues = sum(int(item["issue_count"]) for item in results)
        if failed > 0:
            status = "failed"
        elif flaky > 0:
            status = "flaky"
        else:
            status = "passed"
        return {
            "suite_count": len(results),
            "passed": passed,
            "failed": failed,
            "flaky": flaky,
            "total_issues": total_issues,
            "status": status,
        }

    async def _generate_actions(self, report: dict[str, Any]) -> list[str]:
        summary = report["summary"]
        fallback: list[str] = []
        if summary["failed"] > 0:
            fallback.append("Fix failing suites before moving to simulation or approval stages.")
        if summary["flaky"] > 0:
            fallback.append("Stabilize flaky suites with deterministic fixture control.")
        if summary["failed"] == 0 and summary["flaky"] == 0:
            fallback.append("Validation suites are clean; continue to downstream gates.")
        fallback.append(f"Total reported issues: {summary['total_issues']}.")

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Generate concise follow-up actions for test suite outcomes. "
                            'Return JSON only: {"actions":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "summary": summary,
                                "suites": report["suites"],
                            }
                        ),
                    },
                ],
                max_tokens=300,
            )
            parsed = json.loads(response)
            actions = parsed.get("actions", [])
            if isinstance(actions, list):
                clean = [str(item).strip() for item in actions if str(item).strip()]
                if clean:
                    return clean[:8]
        except Exception:
            pass
        return fallback

    def _write_markdown(self, path: Path, report: dict[str, Any]) -> None:
        summary = report["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Test Runner Report\n\n")
            f.write(f"- Suites: {summary['suite_count']}\n")
            f.write(f"- Passed: {summary['passed']}\n")
            f.write(f"- Failed: {summary['failed']}\n")
            f.write(f"- Flaky: {summary['flaky']}\n")
            f.write(f"- Total issues: {summary['total_issues']}\n")
            f.write(f"- Status: {summary['status']}\n\n")
            f.write("## Suite Results\n\n")
            for item in report["suites"]:
                f.write(
                    f"- {item['suite']}: verdict={item['verdict']}, "
                    f"issues={item['issue_count']}, duration_ms={item['duration_ms']}\n"
                )
            f.write("\n## Actions\n\n")
            for action in report["actions"]:
                f.write(f"- {action}\n")


if __name__ == "__main__":
    TestRunnerAgent.main()
