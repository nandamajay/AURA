"""Watchdog heartbeat and termination-chain regression tests."""

from __future__ import annotations

import asyncio
import signal

import pytest

from aura_sdk.protocol.envelope import AgentHeartbeat
from core.services.watchdog import AgentWatch, WatchdogConfig, WatchdogManager


class FakeProcess:
    """Minimal async process double for watchdog tests."""

    def __init__(self, *, graceful_exit: bool):
        self.returncode: int | None = None
        self.graceful_exit = graceful_exit
        self.sent_signals: list[int] = []
        self.kill_calls = 0

    def send_signal(self, sig: int) -> None:
        self.sent_signals.append(sig)
        if self.graceful_exit:
            self.returncode = 0

    def kill(self) -> None:
        self.kill_calls += 1
        self.returncode = -9

    async def wait(self) -> int:
        if self.graceful_exit:
            await asyncio.sleep(0)
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        if self.kill_calls > 0:
            await asyncio.sleep(0)
            return self.returncode if self.returncode is not None else -9

        await asyncio.sleep(3600)
        return -9


def test_watchdog_on_heartbeat_updates_agent_state():
    now = {"value": 100.0}
    manager = WatchdogManager(
        config=WatchdogConfig(),
        now_fn=lambda: now["value"],
    )
    process = FakeProcess(graceful_exit=True)
    watch = AgentWatch(
        agent_id="learning-a1",
        task_id="task-1",
        agent_type="learning",
        process=process,
        started_at=90.0,
        last_heartbeat=90.0,
    )
    manager.register(watch)

    accepted = manager.on_heartbeat(
        "learning-a1",
        AgentHeartbeat(
            agent_id="learning-a1",
            task_id="task-1",
            timestamp=100.0,
            memory_mb=128,
            cpu_percent=12.5,
        ),
    )
    assert accepted is True

    state = manager.get_state("learning-a1")
    assert state["heartbeats_missed"] == 0
    assert state["memory_mb"] == 128
    assert state["cpu_percent"] == 12.5


@pytest.mark.asyncio
async def test_watchdog_terminate_watch_graceful_sigterm_only():
    manager = WatchdogManager(
        config=WatchdogConfig(sigterm_wait_seconds=0.01),
    )
    process = FakeProcess(graceful_exit=True)
    watch = AgentWatch(
        agent_id="learning-a2",
        task_id="task-2",
        agent_type="learning",
        process=process,
    )
    manager.register(watch)

    await manager._terminate_watch(watch, reason="unit_test")

    assert process.sent_signals == [signal.SIGTERM]
    assert process.kill_calls == 0
    assert watch.status == "completed"
    assert manager.watch_count == 0


@pytest.mark.asyncio
async def test_watchdog_terminate_watch_forces_sigkill_after_timeout():
    manager = WatchdogManager(
        config=WatchdogConfig(sigterm_wait_seconds=0.01),
    )
    process = FakeProcess(graceful_exit=False)
    watch = AgentWatch(
        agent_id="learning-a3",
        task_id="task-3",
        agent_type="learning",
        process=process,
    )
    manager.register(watch)

    await manager._terminate_watch(watch, reason="watchdog_timeout")

    assert process.sent_signals == [signal.SIGTERM]
    assert process.kill_calls == 1
    assert watch.status == "killed"
    assert manager.watch_count == 0


@pytest.mark.asyncio
async def test_watchdog_loop_terminates_agent_after_missed_heartbeats():
    now = {"value": 100.0}
    manager = WatchdogManager(
        config=WatchdogConfig(
            heartbeat_interval_seconds=1.0,
            missed_threshold=1,
            check_interval_seconds=0.01,
            sigterm_wait_seconds=0.01,
        ),
        now_fn=lambda: now["value"],
    )
    process = FakeProcess(graceful_exit=True)
    watch = AgentWatch(
        agent_id="learning-a4",
        task_id="task-4",
        agent_type="learning",
        process=process,
        started_at=95.0,
        last_heartbeat=98.0,
    )
    manager.register(watch)

    await manager.start()
    try:
        await asyncio.sleep(0.05)
    finally:
        await manager.stop()

    assert process.sent_signals == [signal.SIGTERM]
    assert process.kill_calls == 0
    assert manager.watch_count == 0
