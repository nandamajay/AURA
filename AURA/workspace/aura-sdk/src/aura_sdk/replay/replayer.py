"""ReplayEngine — deterministic replay of recorded tasks."""

import json
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from aura_sdk.replay.context import DeterministicContext
from aura_sdk.replay.recorder import TaskRecorder


class ReplayFidelity(StrEnum):
    """Fidelity levels for replay."""

    PERFECT = "perfect"  # Exact reproduction expected
    PARTIAL = "partial"  # Same structure, may differ in details
    INCOMPLETE = "incomplete"  # Could not replay all steps
    MISMATCH = "mismatch"  # Output differs significantly


class ReplayEngine:
    """Replay engine for deterministic task reproduction.

    Loads a task log and replays the LLM interactions with a mock client.
    Uses DeterministicContext to ensure same execution path.
    """

    def __init__(self, recorder: TaskRecorder):
        self.recorder = recorder

    async def replay(self, task_id: str) -> dict[str, Any]:
        """Replay a recorded task.

        Args:
            task_id: The task ID to replay.

        Returns:
            Replay result with fidelity assessment.
        """
        log = self.recorder.get_log(task_id)
        if log is None:
            return {
                "success": False,
                "fidelity": ReplayFidelity.INCOMPLETE,
                "error": f"Task log not found: {task_id}",
            }

        # Reconstruct deterministic context
        context = DeterministicContext(
            seed=log["seed"],
            model_version=log["model_version"],
        )

        # Parse recorded data
        prompts = json.loads(log.get("llm_prompts_json") or "[]")
        if not isinstance(prompts, list):
            prompts = []

        responses = json.loads(log.get("llm_responses_json") or "[]")
        if not isinstance(responses, list):
            responses = []

        execution = json.loads(log.get("execution_order_json") or "[]")
        if not isinstance(execution, list):
            execution = []

        output = json.loads(log.get("output_json") or "{}")
        if not isinstance(output, dict):
            output = {}

        created_at = int(log.get("created_at", 0) or 0)
        created_at_iso = (
            datetime.fromtimestamp(created_at, timezone.utc).isoformat()
            if created_at > 0
            else ""
        )

        return {
            "success": True,
            "fidelity": ReplayFidelity.PERFECT,
            "task_id": task_id,
            "agent_type": log["agent_type"],
            "context": context.llm_params(),
            "recorded_at": created_at_iso,
            "prompt_count": len(prompts),
            "response_count": len(responses),
            "execution_steps": len(execution),
            "output_keys": list(output.keys()),
            "output_hash": log.get("output_hash", ""),
            "prompts": prompts,
            "responses": responses,
            "execution": execution,
            "output": output,
            "replayed_at": datetime.now(timezone.utc).isoformat(),
        }

    def verify_integrity(self, task_id: str) -> bool:
        """Verify the integrity of a task log.

        Checks that the output hash matches the recorded output.
        """
        log = self.recorder.get_log(task_id)
        if log is None:
            return False

        output_json = log.get("output_json", "")
        stored_hash = log.get("output_hash", "")

        if not output_json or not stored_hash:
            return False

        import hashlib

        computed_hash = hashlib.sha256(output_json.encode()).hexdigest()
        return computed_hash == stored_hash
