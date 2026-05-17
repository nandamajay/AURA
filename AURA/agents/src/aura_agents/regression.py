"""Regression Agent — detects regressions from baseline vs current signals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class RegressionAgent(BaseAgent):
    """Regression intelligence agent."""

    AGENT_TYPE = "regression"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading regression context")

        context = self._load_context()
        baseline, current = self._extract_metrics(context)
        threshold_percent = float(context.get("threshold_percent", 10.0))
        flaky_threshold = float(context.get("flaky_threshold", 0.2))
        await self._send_progress(
            20,
            "context_loaded",
            f"Loaded {len(baseline)} baseline metric(s) and {len(current)} current metric(s)",
        )

        analysis = self._analyze(baseline, current, threshold_percent, flaky_threshold, context)
        await self._send_progress(
            70,
            "analysis_complete",
            f"Detected {analysis['summary']['regression_count']} regression(s)",
        )

        analysis["recommendations"] = await self._recommend(analysis)

        json_path = self.output_dir / "regression_report.json"
        markdown_path = self.output_dir / "regression_report.md"
        json_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        self._write_markdown(markdown_path, analysis)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {markdown_path.name}",
        )

        summary = analysis["summary"]
        return {
            "metrics_compared": summary["metrics_compared"],
            "regression_count": summary["regression_count"],
            "flaky_tests_detected": summary["flaky_tests_detected"],
            "status": summary["status"],
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

    def _extract_metrics(self, context: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
        base = context.get("baseline_metrics")
        curr = context.get("current_metrics")
        if isinstance(base, dict) and isinstance(curr, dict):
            return self._to_float_map(base), self._to_float_map(curr)
        # Deterministic fallback sample.
        return (
            {"latency_ms": 120.0, "memory_mb": 240.0, "error_rate": 0.01, "throughput": 45.0},
            {"latency_ms": 138.0, "memory_mb": 272.0, "error_rate": 0.018, "throughput": 40.0},
        )

    def _to_float_map(self, data: dict[str, Any]) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in data.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
        return out

    def _analyze(
        self,
        baseline: dict[str, float],
        current: dict[str, float],
        threshold_percent: float,
        flaky_threshold: float,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        # Metrics where an increase indicates degradation.
        higher_is_worse = {"latency_ms", "memory_mb", "error_rate", "failures", "cpu_percent"}
        lower_is_worse = {"throughput", "pass_rate", "success_rate"}

        metric_results: list[dict[str, Any]] = []
        regressions: list[dict[str, Any]] = []

        for name, base_val in baseline.items():
            if name not in current:
                continue
            curr_val = current[name]
            if base_val == 0:
                delta_percent = 0.0 if curr_val == 0 else 100.0
            else:
                delta_percent = ((curr_val - base_val) / abs(base_val)) * 100.0

            if name in higher_is_worse:
                is_regression = delta_percent > threshold_percent
            elif name in lower_is_worse:
                is_regression = (-delta_percent) > threshold_percent
            else:
                is_regression = abs(delta_percent) > threshold_percent

            entry = {
                "metric": name,
                "baseline": round(base_val, 6),
                "current": round(curr_val, 6),
                "delta_percent": round(delta_percent, 3),
                "threshold_percent": threshold_percent,
                "regression": bool(is_regression),
            }
            metric_results.append(entry)
            if is_regression:
                regressions.append(entry)

        flaky = self._analyze_flaky_tests(context, flaky_threshold)

        status = "regression_detected" if regressions else "stable"
        if flaky:
            status = "regression_and_flakiness" if regressions else "flaky_detected"

        return {
            "agent_type": self.AGENT_TYPE,
            "threshold_percent": threshold_percent,
            "flaky_threshold": flaky_threshold,
            "metrics": metric_results,
            "regressions": regressions,
            "flaky_tests": flaky,
            "summary": {
                "metrics_compared": len(metric_results),
                "regression_count": len(regressions),
                "flaky_tests_detected": len(flaky),
                "status": status,
            },
        }

    def _analyze_flaky_tests(self, context: dict[str, Any], flaky_threshold: float) -> list[dict[str, Any]]:
        raw = context.get("test_histories")
        if not isinstance(raw, dict):
            return []

        findings: list[dict[str, Any]] = []
        for test_name, runs in raw.items():
            if not isinstance(runs, list) or not runs:
                continue
            normalized = [self._normalize_test_result(v) for v in runs]
            pass_count = sum(1 for r in normalized if r == "pass")
            pass_rate = pass_count / len(normalized)
            # Flaky if both pass and fail outcomes are present with enough spread.
            has_pass = any(r == "pass" for r in normalized)
            has_fail = any(r == "fail" for r in normalized)
            flaky = has_pass and has_fail and min(pass_rate, 1 - pass_rate) >= flaky_threshold
            if flaky:
                findings.append(
                    {
                        "test_name": str(test_name),
                        "run_count": len(normalized),
                        "pass_rate": round(pass_rate, 3),
                        "distribution": {
                            "pass": pass_count,
                            "fail": len(normalized) - pass_count,
                        },
                    }
                )
        return findings

    def _normalize_test_result(self, value: Any) -> str:
        if isinstance(value, bool):
            return "pass" if value else "fail"
        s = str(value).strip().lower()
        if s in {"pass", "passed", "ok", "true", "1"}:
            return "pass"
        return "fail"

    async def _recommend(self, analysis: dict[str, Any]) -> list[str]:
        regressions = analysis["regressions"]
        flaky = analysis["flaky_tests"]
        if not regressions and not flaky:
            return ["No regressions detected. Keep monitoring over additional runs."]

        fallback: list[str] = []
        for r in regressions:
            fallback.append(
                f"Investigate metric '{r['metric']}' (delta {r['delta_percent']}%) and bisect recent changes."
            )
        for f in flaky:
            fallback.append(
                f"Stabilize flaky test '{f['test_name']}' (pass_rate={f['pass_rate']}) by removing timing dependencies."
            )

        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Provide concise regression triage actions. Return JSON only: "
                            '{"recommendations":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "regressions": regressions,
                                "flaky_tests": flaky,
                                "status": analysis["summary"]["status"],
                            }
                        ),
                    },
                ],
                max_tokens=500,
            )
            parsed = json.loads(response)
            recs = parsed.get("recommendations", [])
            if isinstance(recs, list):
                clean = [str(r).strip() for r in recs if str(r).strip()]
                if clean:
                    return clean[:10]
        except Exception:
            pass
        return fallback[:10]

    def _write_markdown(self, path: Path, analysis: dict[str, Any]) -> None:
        summary = analysis["summary"]
        with path.open("w", encoding="utf-8") as f:
            f.write("# Regression Intelligence Report\n\n")
            f.write(f"- Metrics compared: {summary['metrics_compared']}\n")
            f.write(f"- Regressions: {summary['regression_count']}\n")
            f.write(f"- Flaky tests: {summary['flaky_tests_detected']}\n")
            f.write(f"- Status: {summary['status']}\n\n")
            f.write("## Metric Deltas\n\n")
            for m in analysis["metrics"]:
                mark = "REGRESSION" if m["regression"] else "OK"
                f.write(
                    f"- [{mark}] {m['metric']}: baseline={m['baseline']}, current={m['current']}, "
                    f"delta={m['delta_percent']}%\n"
                )
            if analysis["flaky_tests"]:
                f.write("\n## Flaky Tests\n\n")
                for t in analysis["flaky_tests"]:
                    f.write(
                        f"- {t['test_name']}: pass_rate={t['pass_rate']}, "
                        f"runs={t['run_count']}, distribution={t['distribution']}\n"
                    )
            f.write("\n## Recommendations\n\n")
            for rec in analysis["recommendations"]:
                f.write(f"- {rec}\n")


if __name__ == "__main__":
    RegressionAgent.main()
