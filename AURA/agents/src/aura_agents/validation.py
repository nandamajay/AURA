"""Validation Agent — executes adversarial validation plans and reports truthfully."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent
from aura_sdk.validation import TestCategory, ValidationOrchestrator, ValidationPlan


class ValidationAgent(BaseAgent):
    """Validation execution agent."""

    AGENT_TYPE = "validation"
    DEFAULT_TIMEOUT = 900

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Preparing adversarial validation plan")

        context = self._load_context()
        target = str(context.get("target", "aura-core"))
        attempts = int(context.get("attempts", 2))
        attempts = max(1, min(attempts, 5))
        categories = self._extract_categories(context)
        plan = ValidationPlan(
            target=target,
            description="Validation Agent generated adversarial plan",
            tests=[
                {
                    "category": category.value,
                    "name": f"{target}:{category.value}",
                    "severity": int(context.get("severity", 3)),
                }
                for category in categories
            ],
        )
        await self._send_progress(
            20,
            "plan_ready",
            f"Plan includes {len(plan.tests)} test(s) across {len(categories)} categories",
        )

        orchestrator = ValidationOrchestrator(db_path="/data/aura.db")
        report = await orchestrator.run_plan(plan, attempts=attempts)
        await self._send_progress(
            70,
            "validation_executed",
            f"Completed {len(report.results)} test(s), blocking={report.blocking_count}",
        )

        edge_cases = await orchestrator.generate_edge_case_matrix(target)
        failure_prob = await orchestrator.generate_failure_probability_analysis(target)

        artifacts = self._serialize(report, edge_cases, failure_prob)
        json_path = self.output_dir / "validation_report.json"
        markdown_path = self.output_dir / "validation_report.md"
        json_path.write_text(json.dumps(artifacts, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, artifacts)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        summary = artifacts["report"]["summary"]
        return {
            "target": target,
            "attempts": attempts,
            "total_tests": artifacts["report"]["total_tests"],
            "blocking_count": artifacts["report"]["blocking_count"],
            "has_blocking_issues": artifacts["report"]["has_blocking_issues"],
            "summary_status": summary.get("status", "unknown"),
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

    def _extract_categories(self, context: dict[str, Any]) -> list[TestCategory]:
        raw = context.get("categories")
        if isinstance(raw, list):
            selected: list[TestCategory] = []
            for item in raw:
                try:
                    selected.append(TestCategory(str(item)))
                except Exception:
                    continue
            if selected:
                return selected
        # Default to first 20 categories for broad coverage.
        return list(TestCategory)[:20]

    def _serialize(self, report, edge_cases, failure_prob) -> dict[str, Any]:
        return {
            "agent_type": self.AGENT_TYPE,
            "report": {
                "report_id": report.report_id,
                "target": report.target,
                "started_at": report.started_at.isoformat(),
                "completed_at": report.completed_at.isoformat() if report.completed_at else None,
                "duration_ms": report.duration_ms,
                "total_tests": len(report.results),
                "pass_count": report.pass_count,
                "fail_count": report.fail_count,
                "crash_count": report.crash_count,
                "flaky_count": report.flaky_count,
                "skip_count": report.skip_count,
                "blocking_count": report.blocking_count,
                "has_blocking_issues": report.has_blocking_issues,
                "summary": report.summary,
                "results": [
                    {
                        "test_name": r.test_name,
                        "category": r.category.value,
                        "verdict": r.verdict.value,
                        "duration_ms": r.duration_ms,
                        "attempts": r.attempts,
                        "attempt_results": r.attempt_results,
                        "error_type": r.error_type,
                        "error_message": r.error_message,
                        "recovered": r.recovered,
                    }
                    for r in report.results
                ],
            },
            "edge_case_count": len(edge_cases),
            "edge_cases_sample": [
                {
                    "category": e.category.value,
                    "description": e.description,
                    "severity": e.severity,
                    "probability": e.probability,
                    "expected_behavior": e.expected_behavior,
                }
                for e in edge_cases[:12]
            ],
            "failure_probability": {
                "component": failure_prob.component,
                "overall_risk": failure_prob.overall_risk,
                "requires_action": failure_prob.requires_action,
                "crash_probability": failure_prob.crash_probability,
                "data_loss_probability": failure_prob.data_loss_probability,
                "hang_probability": failure_prob.hang_probability,
                "silent_corruption_probability": failure_prob.silent_corruption_probability,
                "cascade_probability": failure_prob.cascade_probability,
                "contributing_factors": failure_prob.contributing_factors,
                "mitigations": failure_prob.mitigations,
            },
        }

    def _write_markdown(self, path: Path, artifacts: dict[str, Any]) -> None:
        report = artifacts["report"]
        summary = report["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Validation Agent Report\n\n")
            f.write(f"- Target: {report['target']}\n")
            f.write(f"- Total tests: {report['total_tests']}\n")
            f.write(f"- Blocking issues: {report['blocking_count']}\n")
            f.write(f"- Status: {summary.get('status', 'unknown')}\n\n")
            f.write("## Verdict Counts\n\n")
            f.write(f"- Pass: {report['pass_count']}\n")
            f.write(f"- Fail: {report['fail_count']}\n")
            f.write(f"- Crash: {report['crash_count']}\n")
            f.write(f"- Flaky: {report['flaky_count']}\n")
            f.write(f"- Skip: {report['skip_count']}\n\n")
            f.write("## Summary Message\n\n")
            f.write(f"{summary.get('message', '')}\n\n")
            f.write("## Failure Probability\n\n")
            prob = artifacts["failure_probability"]
            f.write(f"- Overall risk: {prob['overall_risk']}\n")
            f.write(f"- Requires action: {prob['requires_action']}\n")
            f.write(f"- Crash probability: {prob['crash_probability']}\n")
            f.write(f"- Data loss probability: {prob['data_loss_probability']}\n")


if __name__ == "__main__":
    ValidationAgent.main()
