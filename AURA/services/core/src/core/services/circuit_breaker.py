"""Circuit breaker manager for agent/runtime dependency protection.

Implements a 3-state FSM:
    CLOSED -> OPEN -> HALF_OPEN -> CLOSED

Default policy:
    - Open after 3 failures within 60 seconds
    - Stay open for 30 seconds cooldown
    - Allow exactly one probe in HALF_OPEN
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import time
from typing import Callable

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventSource, EventType

logger = get_logger("core.circuit_breaker")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(slots=True)
class CircuitBreakerConfig:
    failure_threshold: int = 3
    window_seconds: float = 60.0
    cooldown_seconds: float = 30.0


@dataclass(slots=True)
class CircuitBreakerStatus:
    agent_type: str
    state: CircuitState = CircuitState.CLOSED
    failures: list[float] = field(default_factory=list)
    opened_at: float = 0.0
    half_open_probe_in_flight: bool = False


class CircuitBreakerManager:
    """Per-agent-type circuit breaker manager."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        config: CircuitBreakerConfig | None = None,
        now_fn: Callable[[], float] | None = None,
    ):
        self._event_bus = event_bus
        self._config = config or CircuitBreakerConfig()
        self._now = now_fn or time.time
        self._breakers: dict[str, CircuitBreakerStatus] = {}

    @property
    def config(self) -> CircuitBreakerConfig:
        return self._config

    def _get(self, agent_type: str) -> CircuitBreakerStatus:
        if agent_type not in self._breakers:
            self._breakers[agent_type] = CircuitBreakerStatus(agent_type=agent_type)
        return self._breakers[agent_type]

    def _prune_failures(self, breaker: CircuitBreakerStatus, now: float) -> None:
        window = self._config.window_seconds
        breaker.failures = [ts for ts in breaker.failures if now - ts <= window]

    async def _transition(
        self, breaker: CircuitBreakerStatus, new_state: CircuitState, reason: str
    ) -> None:
        old_state = breaker.state
        if old_state == new_state:
            return

        breaker.state = new_state
        if new_state == CircuitState.OPEN:
            breaker.opened_at = self._now()
            breaker.half_open_probe_in_flight = False
        elif new_state == CircuitState.CLOSED:
            breaker.failures = []
            breaker.opened_at = 0.0
            breaker.half_open_probe_in_flight = False
        elif new_state == CircuitState.HALF_OPEN:
            breaker.half_open_probe_in_flight = False

        logger.warning(
            "circuit_breaker_transition",
            agent_type=breaker.agent_type,
            from_state=old_state.value,
            to_state=new_state.value,
            reason=reason,
            failures=len(breaker.failures),
        )

        if self._event_bus is not None:
            event = EventEnvelope(
                event_type=EventType.CIRCUIT_BREAKER_STATE,
                source=EventSource(subsystem="S1", service="core", agent_type=breaker.agent_type),
                payload={
                    "agent_type": breaker.agent_type,
                    "from_state": old_state.value,
                    "to_state": new_state.value,
                    "reason": reason,
                    "failure_count": len(breaker.failures),
                    "failure_threshold": self._config.failure_threshold,
                    "window_seconds": self._config.window_seconds,
                    "cooldown_seconds": self._config.cooldown_seconds,
                },
                trace_id=f"cb-{breaker.agent_type}",
            )
            await self._event_bus.publish(event)

    async def allow_request(self, agent_type: str) -> tuple[bool, str]:
        """Check whether request for agent_type should be allowed."""
        breaker = self._get(agent_type)
        now = self._now()
        self._prune_failures(breaker, now)

        if breaker.state == CircuitState.OPEN:
            elapsed = now - breaker.opened_at
            if elapsed >= self._config.cooldown_seconds:
                await self._transition(breaker, CircuitState.HALF_OPEN, "cooldown_elapsed")
            else:
                remaining = self._config.cooldown_seconds - elapsed
                return False, f"circuit_open:{remaining:.1f}s_remaining"

        if breaker.state == CircuitState.HALF_OPEN:
            if breaker.half_open_probe_in_flight:
                return False, "half_open_probe_in_flight"
            breaker.half_open_probe_in_flight = True
            return True, "half_open_probe_allowed"

        return True, "closed"

    async def record_success(self, agent_type: str) -> None:
        breaker = self._get(agent_type)
        if breaker.state == CircuitState.HALF_OPEN:
            await self._transition(breaker, CircuitState.CLOSED, "probe_success")
            return

        if breaker.state == CircuitState.CLOSED:
            # Success in closed state: keep failure window fresh.
            self._prune_failures(breaker, self._now())

    async def record_failure(self, agent_type: str, reason: str = "failure") -> None:
        breaker = self._get(agent_type)
        now = self._now()
        self._prune_failures(breaker, now)

        if breaker.state == CircuitState.HALF_OPEN:
            breaker.failures = [now]
            await self._transition(breaker, CircuitState.OPEN, f"probe_failed:{reason}")
            return

        if breaker.state == CircuitState.OPEN:
            breaker.failures.append(now)
            return

        breaker.failures.append(now)
        if len(breaker.failures) >= self._config.failure_threshold:
            await self._transition(breaker, CircuitState.OPEN, f"threshold_reached:{reason}")

    async def reset(self, agent_type: str, reason: str = "manual_reset") -> None:
        breaker = self._get(agent_type)
        breaker.failures = []
        await self._transition(breaker, CircuitState.CLOSED, reason)

    def get_state(self, agent_type: str) -> dict[str, object]:
        breaker = self._get(agent_type)
        now = self._now()
        self._prune_failures(breaker, now)
        cooldown_remaining = 0.0
        if breaker.state == CircuitState.OPEN:
            cooldown_remaining = max(0.0, self._config.cooldown_seconds - (now - breaker.opened_at))
        return {
            "agent_type": breaker.agent_type,
            "state": breaker.state.value,
            "failure_count_window": len(breaker.failures),
            "failure_timestamps": list(breaker.failures),
            "cooldown_remaining_seconds": round(cooldown_remaining, 3),
            "half_open_probe_in_flight": breaker.half_open_probe_in_flight,
        }

    def list_states(self) -> dict[str, dict[str, object]]:
        return {agent_type: self.get_state(agent_type) for agent_type in self._breakers}
