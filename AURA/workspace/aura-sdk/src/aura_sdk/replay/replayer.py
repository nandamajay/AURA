"""ReplayEngine — deterministic replay of recorded tasks."""

import hashlib
import json
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from aura_sdk.replay.context import DeterministicContext
from aura_sdk.replay.recorder import TaskRecorder


class ReplayFidelity(StrEnum):
    """Fidelity levels for replay."""

    PERFECT = "perfect"  # Exact reproduction expected
    PARTIAL = "partial"  # Same structure, may differ in details
    INCOMPLETE = "incomplete"  # Could not replay all steps
    MISMATCH = "mismatch"  # Output differs significantly


def _safe_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _safe_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class ReplayEngine:
    """Replay engine for deterministic task reproduction."""

    def __init__(self, recorder: TaskRecorder):
        self.recorder = recorder

    async def replay(self, task_id: str) -> dict[str, Any]:
        """Replay a recorded task from immutable finalized snapshot."""
        log = self.recorder.get_log(task_id)
        if log is None:
            return {
                "success": False,
                "fidelity": ReplayFidelity.INCOMPLETE,
                "error": f"Task log not found: {task_id}",
            }

        state = str(log.get("recording_state") or "mutable")
        if state != "finalized":
            return {
                "success": False,
                "fidelity": ReplayFidelity.INCOMPLETE,
                "error": f"Task log not finalized: {task_id}",
                "recording_state": state,
                "revision": int(log.get("revision") or 0),
            }

        snapshot = _safe_dict(log.get("snapshot_json"))
        if snapshot:
            prompts = snapshot.get("prompts", [])
            responses = snapshot.get("responses", [])
            execution = snapshot.get("execution", [])
            output = snapshot.get("output", {})
            output_hash = str(snapshot.get("output_hash") or log.get("output_hash") or "")
        else:
            prompts = _safe_list(log.get("llm_prompts_json"))
            responses = _safe_list(log.get("llm_responses_json"))
            execution = _safe_list(log.get("execution_order_json"))
            output = _safe_dict(log.get("output_json"))
            output_hash = str(log.get("output_hash") or "")

        if not isinstance(prompts, list):
            prompts = []
        if not isinstance(responses, list):
            responses = []
        if not isinstance(execution, list):
            execution = []
        if not isinstance(output, dict):
            output = {}

        context = DeterministicContext(
            seed=int(log["seed"]),
            model_version=str(log["model_version"]),
        )

        created_at = int(log.get("created_at", 0) or 0)
        created_at_iso = (
            datetime.fromtimestamp(created_at, timezone.utc).isoformat()
            if created_at > 0
            else ""
        )
        finalized_at = int(log.get("finalized_at", 0) or 0)
        finalized_at_iso = (
            datetime.fromtimestamp(finalized_at, timezone.utc).isoformat()
            if finalized_at > 0
            else ""
        )

        return {
            "success": True,
            "fidelity": ReplayFidelity.PERFECT,
            "task_id": task_id,
            "agent_type": log["agent_type"],
            "context": context.llm_params(),
            "recording_state": state,
            "revision": int(log.get("revision") or 0),
            "recorded_at": created_at_iso,
            "finalized_at": finalized_at_iso,
            "prompt_count": len(prompts),
            "response_count": len(responses),
            "execution_steps": len(execution),
            "output_keys": list(output.keys()),
            "output_hash": output_hash,
            "snapshot_hash": str(log.get("snapshot_hash") or ""),
            "prompts": prompts,
            "responses": responses,
            "execution": execution,
            "output": output,
            "replayed_at": datetime.now(timezone.utc).isoformat(),
        }

    def verify_integrity(self, task_id: str) -> bool:
        """Verify finalized snapshot and output hashes."""
        log = self.recorder.get_log(task_id)
        if log is None:
            return False

        state = str(log.get("recording_state") or "mutable")
        if state != "finalized":
            return False

        output_json = str(log.get("output_json") or "")
        stored_output_hash = str(log.get("output_hash") or "")
        if not output_json or not stored_output_hash:
            return False
        computed_output_hash = hashlib.sha256(output_json.encode()).hexdigest()
        if computed_output_hash != stored_output_hash:
            return False

        snapshot_json = str(log.get("snapshot_json") or "")
        stored_snapshot_hash = str(log.get("snapshot_hash") or "")
        if snapshot_json and stored_snapshot_hash:
            computed_snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
            return computed_snapshot_hash == stored_snapshot_hash

        return True
