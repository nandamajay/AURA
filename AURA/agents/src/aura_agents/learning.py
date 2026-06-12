"""Learning Agent — deterministic Track B stage execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from aura_agents.base import BaseAgent
from aura_agents.track_b_stage_execution import TrackBStageExecutor


class LearningAgent(BaseAgent):
    """Executes deterministic discovery stages for Track B."""

    AGENT_TYPE = "learning"
    DEFAULT_TIMEOUT = 600  # 10 minutes

    async def execute(self) -> dict[str, Any]:
        await self._send_progress(5, "starting", "Loading Track B stage execution context")
        context = self._load_context()
        context.setdefault("task_id", self.task_id)
        context.setdefault("workflow_kind", "track_b_discovery")

        await self._send_progress(20, "context_loaded", "Running deterministic stage state machine")
        executor = TrackBStageExecutor(output_dir=Path(self.output_dir))
        result = executor.execute(context=context)

        await self._send_progress(
            85,
            "stages_completed",
            f"Reached terminal stage {result['terminal_stage']} with {len(result['transitions'])} transition(s)",
        )
        await self._send_progress(
            95,
            "artifacts_written",
            f"Execution artifact: {result['execution_artifact_path']}",
        )

        return {
            "classification": result["classification"],
            "initial_stage": result["initial_stage"],
            "target_stage": result["target_stage"],
            "terminal_stage": result["terminal_stage"],
            "transitions": result["transitions"],
            "stage_confidence": result["stage_confidence"],
            "stage_confidence_details": result["stage_confidence_details"],
            "execution_artifact_path": result["execution_artifact_path"],
            "artifact_manifest_path": result["artifact_manifest_path"],
            "stage_artifacts": result["stage_artifacts"],
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


if __name__ == "__main__":
    LearningAgent.main()
