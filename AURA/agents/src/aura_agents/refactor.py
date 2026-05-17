"""Refactor Agent — generates incremental refactor plans for upstreaming."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent


class RefactorAgent(BaseAgent):
    """Code refactor planning agent."""

    AGENT_TYPE = "refactor"
    DEFAULT_TIMEOUT = 600

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading refactor context")

        context = self._load_context()
        targets = self._extract_targets(context)
        constraints = self._extract_constraints(context)
        await self._send_progress(
            20,
            "context_loaded",
            f"Loaded {len(targets)} target(s) with {len(constraints)} constraint(s)",
        )

        plan = self._build_baseline_plan(targets, constraints)
        await self._send_progress(
            55,
            "baseline_plan",
            f"Built baseline plan with {len(plan['steps'])} step(s)",
        )

        plan = await self._enrich_plan_with_llm(plan, targets, constraints)
        await self._send_progress(
            75,
            "enriched_plan",
            f"Final plan contains {len(plan['steps'])} step(s)",
        )

        json_path = self.output_dir / "refactor_plan.json"
        report_path = self.output_dir / "refactor_plan.md"
        json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        self._write_report(report_path, plan)

        await self._send_progress(
            95,
            "artifacts_written",
            f"Artifacts written: {json_path.name}, {report_path.name}",
        )

        return {
            "targets": len(targets),
            "steps": len(plan["steps"]),
            "risk_level": plan["summary"]["risk_level"],
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

    def _extract_targets(self, context: dict[str, Any]) -> list[str]:
        targets: list[str] = []
        for key in ("targets", "files", "drivers", "components", "items"):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        targets.append(item.strip())
        if not targets:
            targets = [
                "sound/soc/qcom/common.c",
                "sound/soc/qcom/qdsp6/qdsp6.c",
                "sound/soc/qcom/sm8250.c",
            ]
        dedup: dict[str, None] = {}
        for t in targets:
            dedup[t] = None
        return list(dedup.keys())[:30]

    def _extract_constraints(self, context: dict[str, Any]) -> list[str]:
        constraints: list[str] = []
        for key in ("constraints", "principles", "governance", "notes"):
            value = context.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item.strip():
                        constraints.append(item.strip())
        if not constraints:
            constraints = [
                "Keep changes incremental and reviewable",
                "Prefer upstream kernel abstractions over vendor-only logic",
                "Preserve deterministic behavior and auditable decisions",
            ]
        return constraints[:20]

    def _build_baseline_plan(
        self,
        targets: list[str],
        constraints: list[str],
    ) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        for idx, target in enumerate(targets, start=1):
            steps.append(
                {
                    "step_id": idx,
                    "title": f"Analyze {target}",
                    "goal": "Identify vendor-specific logic and extraction boundaries",
                    "target": target,
                    "risk": "medium" if "qdsp6" in target else "low",
                    "validation": ["checkpatch", "sparse", "clang", "dtbs_check"],
                }
            )
            steps.append(
                {
                    "step_id": idx + 100,
                    "title": f"Refactor {target}",
                    "goal": "Apply minimal structural refactor without behavior drift",
                    "target": target,
                    "risk": "high" if "qdsp6" in target else "medium",
                    "validation": ["build", "runtime smoke", "replay compare"],
                }
            )

        risk_levels = [s["risk"] for s in steps]
        overall = "high" if "high" in risk_levels else "medium" if "medium" in risk_levels else "low"
        return {
            "agent_type": self.AGENT_TYPE,
            "targets": targets,
            "constraints": constraints,
            "steps": steps,
            "summary": {
                "step_count": len(steps),
                "risk_level": overall,
                "requires_human_review": True,
            },
        }

    async def _enrich_plan_with_llm(
        self,
        plan: dict[str, Any],
        targets: list[str],
        constraints: list[str],
    ) -> dict[str, Any]:
        try:
            response = await self.call_llm(
                [
                    {
                        "role": "system",
                        "content": (
                            "Create concise Linux upstream refactor guidance. "
                            "Return JSON only: "
                            '{"additional_steps":[{"title":"...","goal":"...","risk":"low|medium|high","validation":["..."]}],'
                            '"review_notes":["..."]}'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Targets: {targets}\n"
                            f"Constraints: {constraints}\n"
                            "Provide up to 4 additional steps."
                        ),
                    },
                ],
                max_tokens=700,
            )
            parsed = json.loads(response)
            extra = parsed.get("additional_steps", [])
            notes = parsed.get("review_notes", [])
            next_id = max((s["step_id"] for s in plan["steps"]), default=0) + 1
            if isinstance(extra, list):
                for step in extra[:4]:
                    if not isinstance(step, dict):
                        continue
                    plan["steps"].append(
                        {
                            "step_id": next_id,
                            "title": str(step.get("title", "Additional refactor step")),
                            "goal": str(step.get("goal", "")),
                            "target": "cross-cutting",
                            "risk": str(step.get("risk", "medium")),
                            "validation": step.get("validation", ["checkpatch"]),
                        }
                    )
                    next_id += 1
            if isinstance(notes, list):
                clean_notes = [str(n).strip() for n in notes if str(n).strip()]
                if clean_notes:
                    plan["review_notes"] = clean_notes[:8]
        except Exception:
            plan.setdefault("review_notes", [])
        plan["summary"]["step_count"] = len(plan["steps"])
        return plan

    def _write_report(self, path: Path, plan: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write("# Refactor Plan\n\n")
            f.write(f"- Targets: {len(plan['targets'])}\n")
            f.write(f"- Steps: {plan['summary']['step_count']}\n")
            f.write(f"- Risk level: {plan['summary']['risk_level']}\n")
            f.write(f"- Requires human review: {plan['summary']['requires_human_review']}\n\n")
            f.write("## Constraints\n\n")
            for c in plan["constraints"]:
                f.write(f"- {c}\n")
            f.write("\n## Steps\n\n")
            for s in plan["steps"]:
                f.write(
                    f"- [{s['step_id']}] {s['title']} ({s['risk']}): {s['goal']} "
                    f"[target={s['target']}]\n"
                )
            notes = plan.get("review_notes", [])
            if notes:
                f.write("\n## Review Notes\n\n")
                for n in notes:
                    f.write(f"- {n}\n")


if __name__ == "__main__":
    RefactorAgent.main()
