"""ExplainabilityTracker — captures all 6 required lineage types.

Every major autonomous action must preserve:
- reasoning trace
- execution trace
- event lineage
- dependency lineage
- replay lineage
- rollback lineage
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from aura_sdk.governance.charter import ExplainabilityRequirement
from aura_sdk.logging.logger import get_logger

logger = get_logger("governance.explainability")


class ExplainabilityTracker:
    """Tracks explainability for autonomous actions.

    Ensures all 6 lineage types are captured and can be retrieved.
    """

    def __init__(self):
        self._traces: dict[str, dict[str, Any]] = {}  # trace_id -> trace

    def start_trace(
        self,
        action: str,
        actor: str,
        reasoning: str = "",
    ) -> str:
        """Start tracking explainability for an action.

        Returns:
            trace_id — use this to add lineage and complete the trace.
        """
        trace_id = str(uuid4())
        self._traces[trace_id] = {
            "trace_id": trace_id,
            "action": action,
            "actor": actor,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            ExplainabilityRequirement.REASONING_TRACE.value: {
                "initial_reasoning": reasoning,
                "reasoning_steps": [],
            },
            ExplainabilityRequirement.EXECUTION_TRACE.value: {
                "steps": [],
                "current_step": 0,
            },
            ExplainabilityRequirement.EVENT_LINEAGE.value: {
                "events": [],
            },
            ExplainabilityRequirement.DEPENDENCY_LINEAGE.value: {
                "dependencies": [],
                "dependent_on": [],
            },
            ExplainabilityRequirement.REPLAY_LINEAGE.value: {
                "task_id": None,
                "seed": None,
                "model_version": None,
                "snapshots": [],
            },
            ExplainabilityRequirement.ROLLBACK_LINEAGE.value: {
                "rollback_points": [],
                "rollback_procedure": None,
            },
            "completeness": {},
        }
        return trace_id

    def add_reasoning(self, trace_id: str, step: str, detail: str = "") -> None:
        """Add a reasoning step."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.REASONING_TRACE.value]["reasoning_steps"].append(
                {"step": step, "detail": detail, "at": datetime.now(timezone.utc).isoformat()}
            )

    def add_execution_step(self, trace_id: str, step: str, status: str = "ok", detail: dict[str, Any] | None = None) -> None:
        """Add an execution step."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.EXECUTION_TRACE.value]["steps"].append(
                {
                    "step": step,
                    "status": status,
                    "detail": detail or {},
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            self._traces[trace_id][ExplainabilityRequirement.EXECUTION_TRACE.value]["current_step"] += 1

    def add_event(self, trace_id: str, event_type: str, event_id: str, payload: dict[str, Any] | None = None) -> None:
        """Add an event to the lineage."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.EVENT_LINEAGE.value]["events"].append(
                {"type": event_type, "id": event_id, "payload": payload or {}, "at": datetime.now(timezone.utc).isoformat()}
            )

    def add_dependency(self, trace_id: str, depends_on: str, dependency_type: str = "service") -> None:
        """Add a dependency relationship."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.DEPENDENCY_LINEAGE.value]["dependent_on"].append(
                {"service": depends_on, "type": dependency_type, "at": datetime.now(timezone.utc).isoformat()}
            )

    def add_replay_context(
        self, trace_id: str, task_id: str, seed: int, model_version: str
    ) -> None:
        """Add replay lineage context."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.REPLAY_LINEAGE.value].update(
                {"task_id": task_id, "seed": seed, "model_version": model_version}
            )

    def add_snapshot(self, trace_id: str, snapshot_type: str, snapshot_data: dict[str, Any]) -> None:
        """Add a snapshot for replay/rollback."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.REPLAY_LINEAGE.value]["snapshots"].append(
                {"type": snapshot_type, "data": snapshot_data, "at": datetime.now(timezone.utc).isoformat()}
            )

    def add_rollback_point(self, trace_id: str, description: str, procedure: str = "") -> None:
        """Add a rollback point."""
        if trace_id in self._traces:
            self._traces[trace_id][ExplainabilityRequirement.ROLLBACK_LINEAGE.value]["rollback_points"].append(
                {"description": description, "at": datetime.now(timezone.utc).isoformat()}
            )
            if procedure:
                self._traces[trace_id][ExplainabilityRequirement.ROLLBACK_LINEAGE.value]["rollback_procedure"] = procedure

    def complete_trace(self, trace_id: str, final_status: str = "completed") -> dict[str, Any]:
        """Complete the trace and check completeness.

        Returns:
            The complete trace with completeness assessment.
        """
        if trace_id not in self._traces:
            return {"error": "Trace not found"}

        trace = self._traces[trace_id]
        trace["completed_at"] = datetime.now(timezone.utc).isoformat()
        trace["final_status"] = final_status

        # Check completeness
        completeness = {}
        for req in ExplainabilityRequirement:
            section = trace.get(req.value, {})
            has_content = False
            if isinstance(section, dict):
                for key, val in section.items():
                    if val and val != [] and val != {}:
                        has_content = True
                        break
            completeness[req.value] = has_content

        trace["completeness"] = completeness
        trace["completeness_score"] = sum(completeness.values()) / len(completeness)
        trace["is_complete"] = all(completeness.values())

        if not trace["is_complete"]:
            missing = [k for k, v in completeness.items() if not v]
            trace["missing_lineage"] = missing
            logger.warning(
                "incomplete_explainability_trace",
                trace_id=trace_id,
                score=trace["completeness_score"],
                missing=missing,
            )

        return trace

    def get_trace(self, trace_id: str) -> dict[str, Any] | None:
        return self._traces.get(trace_id)

    def get_completeness_report(self) -> dict[str, Any]:
        """Get a report of explainability across all traces."""
        if not self._traces:
            return {"total_traces": 0, "message": "No traces recorded"}

        total = len(self._traces)
        complete = sum(1 for t in self._traces.values() if t.get("is_complete", False))

        by_type: dict[str, int] = {}
        for trace in self._traces.values():
            for req in ExplainabilityRequirement:
                val = trace.get("completeness", {}).get(req.value, False)
                key = req.value
                if key not in by_type:
                    by_type[key] = 0
                if val:
                    by_type[key] += 1

        return {
            "total_traces": total,
            "complete_traces": complete,
            "incomplete_traces": total - complete,
            "completeness_rate": round(complete / total, 3) if total > 0 else 0,
            "by_lineage_type": {k: {"present": v, "missing": total - v} for k, v in by_type.items()},
            "recommendation": (
                "All traces have complete explainability."
                if complete == total else
                f"{total - complete} trace(s) have incomplete explainability. "
                f"Ensure all 6 lineage types are captured for every major action."
            ),
        }
