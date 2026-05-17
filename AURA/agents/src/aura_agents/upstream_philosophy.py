"""Upstream Philosophy Agent — evaluates change proposals against upstream principles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class UpstreamPhilosophyAgent(BaseAgent):
    """Linux upstream philosophy guidance agent."""

    AGENT_TYPE = "upstream_philosophy"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading proposal context")

        context = self._load_context()
        proposal_text = self._extract_proposal_text(context)
        await self._send_progress(
            20,
            "context_loaded",
            f"Loaded proposal context ({len(proposal_text)} characters)",
        )

        principles = self._principles()
        assessment = self._assess(proposal_text, principles)
        await self._send_progress(
            65,
            "assessment_complete",
            f"Assessed {len(principles)} principle(s), score={assessment['score']}/100",
        )

        recommendations = await self._recommend(proposal_text, assessment)
        assessment["recommendations"] = recommendations

        json_path = self.output_dir / "upstream_philosophy_assessment.json"
        report_path = self.output_dir / "upstream_philosophy_report.md"
        json_path.write_text(json.dumps(assessment, indent=2), encoding="utf-8")
        self._write_report(report_path, assessment)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {report_path.name}",
        )

        return {
            "score": assessment["score"],
            "status": assessment["status"],
            "principles_evaluated": len(assessment["checks"]),
            "json_path": str(json_path),
            "report_path": str(report_path),
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

    def _extract_proposal_text(self, context: dict[str, Any]) -> str:
        fields = [
            context.get("proposal", ""),
            context.get("description", ""),
            context.get("patch_summary", ""),
            context.get("change_notes", ""),
            context.get("rationale", ""),
            context.get("test_evidence", ""),
            context.get("risk_notes", ""),
        ]
        parts = [str(v).strip() for v in fields if str(v).strip()]
        if parts:
            return "\n\n".join(parts)
        return (
            "Qualcomm audio upstream migration proposal. "
            "Focus on minimal patch scope, clear rationale, reusable abstractions, "
            "and documented test evidence."
        )

    def _principles(self) -> list[dict[str, str]]:
        return [
            {
                "id": "minimal_scope",
                "title": "Minimal and reviewable scope",
                "expectation": "Change set should be small, targeted, and split logically.",
            },
            {
                "id": "clear_rationale",
                "title": "Clear rationale",
                "expectation": "Proposal should explain why the change is required.",
            },
            {
                "id": "generic_abstractions",
                "title": "Prefer generic abstractions",
                "expectation": "Avoid vendor-only hooks when kernel abstractions exist.",
            },
            {
                "id": "dt_binding_hygiene",
                "title": "Device-tree binding hygiene",
                "expectation": "DT bindings should map to documented YAML schema expectations.",
            },
            {
                "id": "test_evidence",
                "title": "Test evidence present",
                "expectation": "Validation evidence should be included (build/runtime/checks).",
            },
            {
                "id": "maintainability",
                "title": "Long-term maintainability",
                "expectation": "Avoid temporary hacks and hidden behavior.",
            },
        ]

    def _assess(self, text: str, principles: list[dict[str, str]]) -> dict[str, Any]:
        lower = text.lower()
        checks: list[dict[str, Any]] = []

        def has_any(*terms: str) -> bool:
            return any(term in lower for term in terms)

        for p in principles:
            pid = p["id"]
            if pid == "minimal_scope":
                ok = has_any("minimal", "small", "incremental", "split")
                confidence = 0.8 if ok else 0.45
            elif pid == "clear_rationale":
                ok = has_any("because", "rationale", "reason", "motivation")
                confidence = 0.85 if ok else 0.5
            elif pid == "generic_abstractions":
                bad = has_any("vendor-only", "private api", "downstream-only", "hack")
                ok = not bad
                confidence = 0.75 if ok else 0.25
            elif pid == "dt_binding_hygiene":
                ok = has_any("binding", "yaml", "device-tree", "dt")
                confidence = 0.8 if ok else 0.45
            elif pid == "test_evidence":
                ok = has_any("test", "checkpatch", "sparse", "dtbs_check", "validated")
                confidence = 0.9 if ok else 0.35
            elif pid == "maintainability":
                bad = has_any("temporary", "workaround", "quick fix", "hack")
                ok = not bad
                confidence = 0.8 if ok else 0.2
            else:
                ok = False
                confidence = 0.0

            checks.append(
                {
                    "id": pid,
                    "title": p["title"],
                    "expectation": p["expectation"],
                    "pass": ok,
                    "confidence": round(confidence, 2),
                }
            )

        passed = sum(1 for c in checks if c["pass"])
        score = int(round((passed / max(len(checks), 1)) * 100))
        if score >= 80:
            status = "strong"
        elif score >= 60:
            status = "acceptable_with_rework"
        else:
            status = "needs_rework"

        return {
            "agent_type": self.AGENT_TYPE,
            "score": score,
            "status": status,
            "proposal_excerpt": text[:500],
            "checks": checks,
            "summary": {
                "total": len(checks),
                "passed": passed,
                "failed": len(checks) - passed,
            },
        }

    async def _recommend(self, text: str, assessment: dict[str, Any]) -> list[str]:
        failed = [c["title"] for c in assessment["checks"] if not c["pass"]]
        if not failed:
            return ["Proposal aligns with baseline upstream principles. Maintain current structure."]

        fallback = [f"Improve: {title}" for title in failed]
        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "You provide Linux upstreaming guidance. Return JSON only: "
                            '{"recommendations":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Proposal excerpt:\n"
                            f"{text[:1200]}\n\n"
                            f"Failed principles: {', '.join(failed)}"
                        ),
                    },
                ],
                max_tokens=500,
            )
            parsed = json.loads(response)
            recs = parsed.get("recommendations", [])
            if isinstance(recs, list):
                cleaned = [str(r).strip() for r in recs if str(r).strip()]
                if cleaned:
                    return cleaned[:10]
        except Exception:
            pass
        return fallback

    def _write_report(self, path: Path, assessment: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write("# Upstream Philosophy Report\n\n")
            f.write(f"- Score: {assessment['score']}/100\n")
            f.write(f"- Status: {assessment['status']}\n")
            f.write(f"- Passed: {assessment['summary']['passed']}/{assessment['summary']['total']}\n\n")
            f.write("## Principle Checks\n\n")
            for c in assessment["checks"]:
                mark = "PASS" if c["pass"] else "FAIL"
                f.write(
                    f"- [{mark}] {c['title']} (confidence={c['confidence']}): {c['expectation']}\n"
                )
            f.write("\n## Recommendations\n\n")
            for r in assessment["recommendations"]:
                f.write(f"- {r}\n")


if __name__ == "__main__":
    UpstreamPhilosophyAgent.main()
