"""FailSafeController — graceful degradation when uncertainty exceeds confidence.

When confidence is below threshold:
- Degrade gracefully
- Request human review
- Avoid destructive action
- Preserve state
- Preserve evidence
"""

from datetime import datetime, timezone
from typing import Any

from aura_sdk.logging.logger import get_logger

logger = get_logger("governance.failsafe")


class FailSafeController:
    """Fail-safe controller for autonomous actions.

    Intercepts actions when confidence is insufficient.
    Escalates to human review rather than proceeding destructively.
    """

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self._incidents: list[dict[str, Any]] = []
        self._state_preserved: list[dict[str, Any]] = []

    def evaluate(
        self,
        action: str,
        confidence: float,
        is_destructive: bool = False,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether an action should proceed under fail-safe rules.

        Returns:
            Dict with: proceed (bool), action (str), reason (str), state
        """
        ctx = context or {}

        result = {
            "action": action,
            "confidence": confidence,
            "threshold": self.confidence_threshold,
            "is_destructive": is_destructive,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Critical: destructive actions with low confidence ALWAYS blocked
        if is_destructive and confidence < self.confidence_threshold:
            incident = {
                "type": "destructive_action_blocked",
                "action": action,
                "confidence": confidence,
                "reason": (
                    f"DESTRUCTIVE ACTION BLOCKED: '{action}' has confidence {confidence:.2f} "
                    f"below threshold {self.confidence_threshold:.2f}. "
                    f"Destructive actions require high confidence or explicit human approval."
                ),
                "state_preserved": True,
            }
            self._incidents.append(incident)
            result.update(incident)
            result["proceed"] = False

            logger.critical(
                "failsafe_blocked_destructive",
                action=action,
                confidence=confidence,
                threshold=self.confidence_threshold,
            )
            return result

        # Non-destructive actions: degrade gracefully
        if confidence < self.confidence_threshold:
            incident = {
                "type": "low_confidence_degraded",
                "action": action,
                "confidence": confidence,
                "reason": (
                    f"LOW CONFIDENCE: '{action}' confidence {confidence:.2f} below threshold. "
                    f"Proceeding in degraded mode with human review request."
                ),
            }
            self._incidents.append(incident)
            result.update(incident)
            result["proceed"] = True
            result["degraded"] = True
            result["human_review_required"] = True

            logger.warning(
                "failsafe_degraded_mode",
                action=action,
                confidence=confidence,
            )
            return result

        # Normal operation
        result["proceed"] = True
        result["reason"] = f"Confidence {confidence:.2f} above threshold. Proceeding normally."
        return result

    def preserve_state(self, trace_id: str, state: dict[str, Any]) -> None:
        """Preserve current state before an uncertain action."""
        preserved = {
            "trace_id": trace_id,
            "state": state,
            "preserved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._state_preserved.append(preserved)
        logger.info("state_preserved", trace_id=trace_id)

    def request_human_review(
        self, action: str, reason: str, trace_id: str, evidence: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a human review request.

        Returns:
            The review request details.
        """
        review = {
            "review_id": trace_id,
            "action": action,
            "reason": reason,
            "evidence": evidence,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_review",
            "urgency": "high" if "destructive" in action.lower() else "medium",
        }

        logger.warning(
            "human_review_requested",
            action=action,
            reason=reason,
            review_id=trace_id,
        )

        return review

    @property
    def incidents(self) -> list[dict[str, Any]]:
        return list(self._incidents)

    @property
    def blocked_count(self) -> int:
        return sum(1 for i in self._incidents if i.get("type") == "destructive_action_blocked")

    @property
    def degraded_count(self) -> int:
        return sum(1 for i in self._incidents if i.get("type") == "low_confidence_degraded")

    def get_report(self) -> dict[str, Any]:
        """Get a summary of all fail-safe activations."""
        return {
            "total_incidents": len(self._incidents),
            "blocked_destructive": self.blocked_count,
            "degraded_mode": self.degraded_count,
            "state_preservations": len(self._state_preserved),
            "incidents": self._incidents,
            "recommendation": (
                f"Fail-safe activated {len(self._incidents)} time(s). "
                f"{self.blocked_count} destructive action(s) blocked. "
                f"{self.degraded_count} action(s) ran in degraded mode. "
                + ("Review all incidents." if self._incidents else "No incidents — normal operation.")
            ),
        }
