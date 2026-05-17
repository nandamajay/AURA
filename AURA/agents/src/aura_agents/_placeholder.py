"""Placeholder agent implementation for declared-but-not-yet-built agents."""

from aura_agents.base import BaseAgent


class PlaceholderAgent(BaseAgent):
    """Base class for placeholder agents that are not implemented yet."""

    PURPOSE: str = "not specified"

    async def execute(self) -> dict:
        await self._send_progress(
            5,
            "not_implemented",
            f"Agent '{self.AGENT_TYPE}' is declared but not implemented yet.",
        )
        raise RuntimeError(f"Agent '{self.AGENT_TYPE}' is not implemented yet ({self.PURPOSE}).")
