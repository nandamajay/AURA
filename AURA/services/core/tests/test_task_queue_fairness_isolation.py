"""Queue fairness and runtime-isolation metadata regression tests."""

from __future__ import annotations

import asyncio

import pytest

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.models.agent import AgentType
from aura_sdk.models.event import EventEnvelope, EventType
from aura_sdk.models.task import TaskCreate, TaskPriority, TaskStatus
from core.services.task_queue import TaskQueueManager


class _FakeRuntime:
    def __init__(self) -> None:
        self.spawn_calls = 0

    async def spawn(
        self,
        *,
        agent_type: str,
        requested_by: str,
        task_id: str | None = None,
        input_data: dict | None = None,
    ) -> dict:
        _ = (requested_by, input_data)
        self.spawn_calls += 1
        return {
            "agent_type": agent_type,
            "agent_id": f"{agent_type}-fair-{self.spawn_calls:03d}",
            "task_id": task_id or f"task-fair-{self.spawn_calls:03d}",
            "pid": 3000 + self.spawn_calls,
            "status": "running",
        }


@pytest.mark.asyncio
async def test_p2_fairness_override_selects_background_after_wait_threshold():
    bus = EventBus()
    await bus.start()
    queue = TaskQueueManager(runtime=_FakeRuntime(), event_bus=bus, max_concurrent_agents=4)
    queue._p2_wait_override_seconds = 0.0
    queue._p2_fairness_window = 1

    try:
        task = await queue.create_task(
            TaskCreate(
                agent_type=AgentType.TEST_RUNNER,
                priority=TaskPriority.BACKGROUND,
                description="p2-fairness",
                input_data={"plugin_domain": "automation"},
            ),
            requested_by="tester",
        )
        selected_task_id, meta = queue._select_next_task_locked(running_count=2)
        assert selected_task_id == task.id
        assert meta["fairness_override"] is True
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_dispatch_persists_queue_ordering_metadata_and_task_started_event():
    bus = EventBus()
    started_events: list[EventEnvelope] = []

    async def _capture(event: EventEnvelope) -> None:
        started_events.append(event)

    bus.subscribe(EventType.TASK_STARTED, _capture)
    await bus.start()

    queue = TaskQueueManager(runtime=_FakeRuntime(), event_bus=bus, max_concurrent_agents=2)
    queue._p2_wait_override_seconds = 0.0
    queue._p2_fairness_window = 1

    try:
        task = await queue.create_task(
            TaskCreate(
                agent_type=AgentType.LEARNING,
                priority=TaskPriority.BACKGROUND,
                description="queue-ordering",
                input_data={"plugin_domain": "automation"},
            ),
            requested_by="tester",
        )

        await queue._dispatch_once()
        await asyncio.sleep(0.05)

        running = await queue.get_task(task.id)
        assert running is not None
        assert running.status == TaskStatus.RUNNING

        queue_ordering = running.result_data.get("queue_ordering", {})
        assert queue_ordering["plugin_domain"] == "automation"
        assert queue_ordering["policy_version"] == "p2-isolation-v1"
        assert isinstance(queue_ordering["dispatch_sequence"], int)

        assert len(started_events) == 1
        payload = started_events[0].payload
        assert payload["plugin_domain"] == "automation"
        assert payload["runtime_cell_scope"] == "domain:automation"
        assert payload["queue_policy_version"] == "p2-isolation-v1"
        assert payload["queue_ordering"]["plugin_domain"] == "automation"

        iso = await queue.get_isolation_stats()
        per_domain = iso["per_domain"]
        assert per_domain["automation"]["dispatches"] >= 1
    finally:
        await bus.stop()
