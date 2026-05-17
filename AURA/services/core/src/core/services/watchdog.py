"""Watchdog manager for agent heartbeat and termination enforcement.

Operational policy:
    - Heartbeat interval: 30s
    - Missed threshold: 3 heartbeats (90s total)
    - Scan interval: 5s
    - Timeout chain: SIGTERM -> wait 10s -> SIGKILL
"""

from __future__ import annotations

import asyncio
import signal
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventSource, EventType
from aura_sdk.protocol.envelope import AgentHeartbeat

logger = get_logger("core.watchdog")


class ProcessHandle(Protocol):
    """Minimal process API used by watchdog."""

    returncode: int | None

    def send_signal(self, sig: int) -> None: ...
    def kill(self) -> None: ...
    async def wait(self) -> int: ...


@dataclass(slots=True)
class WatchdogConfig:
    heartbeat_interval_seconds: float = 30.0
    missed_threshold: int = 3
    check_interval_seconds: float = 5.0
    sigterm_wait_seconds: float = 10.0
    max_watches: int = 50


@dataclass(slots=True)
class AgentWatch:
    agent_id: str
    task_id: str
    agent_type: str
    process: ProcessHandle
    started_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    heartbeats_missed: int = 0
    memory_mb: int = 0
    cpu_percent: float = 0.0
    status: str = "running"


class WatchdogManager:
    """Monitors registered agent processes and enforces timeout termination."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        config: WatchdogConfig | None = None,
        now_fn: Callable[[], float] | None = None,
    ):
        self._event_bus = event_bus
        self._config = config or WatchdogConfig()
        self._now = now_fn or time.time
        self._watches: dict[str, AgentWatch] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def config(self) -> WatchdogConfig:
        return self._config

    @property
    def watch_count(self) -> int:
        return len(self._watches)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._watch_loop(), name="watchdog")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        for watch in list(self._watches.values()):
            await self._terminate_watch(watch, reason="watchdog_shutdown")

    def register(self, watch: AgentWatch) -> None:
        """Register a process for monitoring."""
        if len(self._watches) >= self._config.max_watches:
            raise RuntimeError("watchdog_max_watches_exceeded")
        self._watches[watch.agent_id] = watch
        logger.info(
            "watchdog_registered",
            agent_id=watch.agent_id,
            agent_type=watch.agent_type,
            task_id=watch.task_id,
            watch_count=len(self._watches),
        )

    def unregister(self, agent_id: str) -> bool:
        removed = self._watches.pop(agent_id, None)
        if removed is not None:
            logger.info(
                "watchdog_unregistered",
                agent_id=agent_id,
                agent_type=removed.agent_type,
                task_id=removed.task_id,
                watch_count=len(self._watches),
            )
            return True
        return False

    def on_heartbeat(self, agent_id: str, heartbeat: AgentHeartbeat) -> bool:
        watch = self._watches.get(agent_id)
        if watch is None:
            return False

        watch.last_heartbeat = heartbeat.timestamp or self._now()
        watch.heartbeats_missed = 0
        watch.memory_mb = heartbeat.memory_mb
        watch.cpu_percent = heartbeat.cpu_percent
        return True

    def get_state(self, agent_id: str) -> dict[str, object]:
        watch = self._watches.get(agent_id)
        if watch is None:
            raise KeyError(agent_id)

        now = self._now()
        elapsed = max(0.0, now - watch.last_heartbeat)
        missed = int(elapsed / self._config.heartbeat_interval_seconds)
        return {
            "agent_id": watch.agent_id,
            "task_id": watch.task_id,
            "agent_type": watch.agent_type,
            "status": watch.status,
            "last_heartbeat": watch.last_heartbeat,
            "heartbeats_missed": max(watch.heartbeats_missed, missed),
            "memory_mb": watch.memory_mb,
            "cpu_percent": watch.cpu_percent,
            "lifetime_seconds": round(now - watch.started_at, 3),
        }

    def list_states(self) -> dict[str, dict[str, object]]:
        return {agent_id: self.get_state(agent_id) for agent_id in list(self._watches)}

    async def _watch_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._config.check_interval_seconds)
                now = self._now()

                for watch in list(self._watches.values()):
                    if watch.status != "running":
                        continue
                    if watch.process.returncode is not None:
                        self.unregister(watch.agent_id)
                        continue

                    elapsed = max(0.0, now - watch.last_heartbeat)
                    missed = int(elapsed / self._config.heartbeat_interval_seconds)
                    if missed > watch.heartbeats_missed:
                        watch.heartbeats_missed = missed

                    if missed >= self._config.missed_threshold:
                        await self._handle_timeout(watch)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("watchdog_loop_error", error=str(exc))

    async def _handle_timeout(self, watch: AgentWatch) -> None:
        logger.warning(
            "watchdog_timeout_detected",
            agent_id=watch.agent_id,
            agent_type=watch.agent_type,
            task_id=watch.task_id,
            heartbeats_missed=watch.heartbeats_missed,
        )
        await self._publish_event(
            EventType.AGENT_TIMEOUT,
            watch,
            payload={
                "reason": "watchdog_timeout",
                "heartbeats_missed": watch.heartbeats_missed,
                "heartbeat_interval_seconds": self._config.heartbeat_interval_seconds,
            },
            trace_id=watch.task_id,
        )
        await self._terminate_watch(watch, reason="watchdog_timeout")

    async def _terminate_watch(self, watch: AgentWatch, reason: str) -> None:
        watch.status = "stopping"
        try:
            watch.process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as exc:
            logger.warning(
                "watchdog_sigterm_error",
                agent_id=watch.agent_id,
                reason=reason,
                error=str(exc),
            )

        graceful = False
        try:
            await asyncio.wait_for(watch.process.wait(), timeout=self._config.sigterm_wait_seconds)
            graceful = True
        except asyncio.TimeoutError:
            graceful = False
        except ProcessLookupError:
            graceful = True
        except Exception as exc:
            logger.warning(
                "watchdog_wait_error",
                agent_id=watch.agent_id,
                reason=reason,
                error=str(exc),
            )

        if not graceful:
            watch.status = "killing"
            try:
                watch.process.kill()
                await watch.process.wait()
            except ProcessLookupError:
                pass
            except Exception as exc:
                logger.warning(
                    "watchdog_sigkill_error",
                    agent_id=watch.agent_id,
                    reason=reason,
                    error=str(exc),
                )

            await self._publish_event(
                EventType.AGENT_KILLED,
                watch,
                payload={
                    "reason": reason,
                    "signal": "SIGKILL",
                    "heartbeats_missed": watch.heartbeats_missed,
                },
                trace_id=watch.task_id,
            )
            watch.status = "killed"
        else:
            watch.status = "completed"

        self.unregister(watch.agent_id)

    async def _publish_event(
        self,
        event_type: EventType,
        watch: AgentWatch,
        *,
        payload: dict[str, object],
        trace_id: str = "",
    ) -> None:
        if self._event_bus is None:
            return
        event = EventEnvelope(
            event_type=event_type,
            source=EventSource(
                subsystem="S1",
                service="core",
                task_id=watch.task_id,
                agent_type=watch.agent_type,
                agent_id=watch.agent_id,
            ),
            payload=payload,
            trace_id=trace_id,
        )
        await self._event_bus.publish(event)
