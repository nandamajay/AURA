"""Token budget management."""

from datetime import datetime, timezone


class TokenBudgetManager:
    """Manages daily token budget across all agents.

    Resets at midnight UTC. Tracks usage by agent type.
    """

    def __init__(self, daily_limit: int):
        self.daily_limit = daily_limit
        self._used_today: int = 0
        self._by_agent: dict[str, int] = {}
        self._last_reset: datetime = datetime.now(timezone.utc)

    def check_budget(self, estimated_tokens: int = 0) -> tuple[bool, dict]:
        """Check if request is within budget.

        Returns:
            (allowed, info_dict)
        """
        self._maybe_reset()
        remaining = self.daily_limit - self._used_today
        allowed = remaining >= estimated_tokens
        return allowed, {
            "allowed": allowed,
            "remaining": remaining,
            "used_today": self._used_today,
            "daily_limit": self.daily_limit,
            "estimated_tokens": estimated_tokens,
        }

    def record_usage(self, agent_type: str, tokens: int) -> None:
        """Record token usage from a completed request."""
        self._maybe_reset()
        self._used_today += tokens
        self._by_agent[agent_type] = self._by_agent.get(agent_type, 0) + tokens

    def get_usage(self) -> dict:
        """Get current usage summary."""
        self._maybe_reset()
        remaining = self.daily_limit - self._used_today
        return {
            "daily_limit": self.daily_limit,
            "used_today": self._used_today,
            "remaining": max(0, remaining),
            "utilization": round(self._used_today / self.daily_limit, 4)
            if self.daily_limit > 0 else 0,
            "by_agent": dict(self._by_agent),
            "resets_at": self._last_reset.isoformat(),
        }

    def _maybe_reset(self) -> None:
        """Reset counter if it's a new day."""
        now = datetime.now(timezone.utc)
        if now.date() != self._last_reset.date():
            self._used_today = 0
            self._by_agent.clear()
            self._last_reset = now
