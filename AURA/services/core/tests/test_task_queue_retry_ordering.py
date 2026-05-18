"""Task queue retry ordering and lineage regression tests."""

from __future__ import annotations

import asyncio

import pytest

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.models.agent import AgentType
from aura_sdk.models.event import EventEnvelope, EventSource, EventType
from aura_sdk.models.task import TaskCreate, TaskStatus
from aura_sdk.protocol.constants import ExitCode
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
            "agent_id": f"{agent_type}-fake-{self.spawn_calls:03d}",
            "task_id": task_id or f"task-fake-{self.spawn_calls:03d}",
            "pid": 1000 + self.spawn_calls,
            "status": "running",
        }


def _failed_event(task_id: str, exit_code: int, error: str, agent_id: str = "learning-fake-001") -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.AGENT_FAILED,
        source=EventSource(
            subsystem="S1",
            service="core",
            task_id=task_id,
            agent_type="learning",
            agent_id=agent_id,
        ),
        payload={"exit_code": exit_code, "error": error},
        trace_id=task_id,
    )


def _completed_event(task_id: str) -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.TASK_COMPLETED,
        source=EventSource(
            subsystem="S1",
            service="core",
            task_id=task_id,
            agent_type="learning",
            agent_id="learning-fake-done",
        ),
        payload={"task_id": task_id, "results": {"status": "ok"}},
        trace_id=task_id,
    )


@pytest.mark.asyncio
async def test_retryable_failures_requeue_with_monotonic_lineage_and_events():
    bus = EventBus()
    retry_events: list[dict] = []

    async def _capture(event: EventEnvelope) -> None:
        retry_events.append(dict(event.payload))

    bus.subscribe(EventType.TASK_QUEUED, _capture)
    await bus.start()
    queue = TaskQueueManager(runtime=_FakeRuntime(), event_bus=bus, max_concurrent_agents=1)

    try:
        task = await queue.create_task(
            TaskCreate(agent_type=AgentType.LEARNING, max_retries=3, description="retry-ordering"),
            requested_by="tester",
        )

        await queue._dispatch_once()
        t1 = await queue.get_task(task.id)
        assert t1 is not None
        assert t1.status == TaskStatus.RUNNING
        assert t1.current_attempt == 1

        await queue._on_agent_failed(_failed_event(task.id, int(ExitCode.TIMEOUT), "timeout"))
        await asyncio.sleep(0.05)
        t_after_1 = await queue.get_task(task.id)
        assert t_after_1 is not None
        assert t_after_1.status == TaskStatus.QUEUED

        await queue._dispatch_once()
        t2 = await queue.get_task(task.id)
        assert t2 is not None
        assert t2.status == TaskStatus.RUNNING
        assert t2.current_attempt == 2

        await queue._on_agent_failed(_failed_event(task.id, int(ExitCode.LLM_UNAVAILABLE), "llm-down"))
        await asyncio.sleep(0.05)
        t_after_2 = await queue.get_task(task.id)
        assert t_after_2 is not None
        assert t_after_2.status == TaskStatus.QUEUED

        await queue._dispatch_once()
        t3 = await queue.get_task(task.id)
        assert t3 is not None
        assert t3.status == TaskStatus.RUNNING
        assert t3.current_attempt == 3

        await queue._on_task_completed(_completed_event(task.id))
        final = await queue.get_task(task.id)
        assert final is not None
        assert final.status == TaskStatus.COMPLETED
        assert final.current_attempt == 3

        lineage = final.result_data.get("retry_lineage", [])
        assert [entry["retry_sequence"] for entry in lineage] == [1, 2]
        assert [entry["failed_attempt"] for entry in lineage] == [1, 2]
        assert [entry["next_attempt"] for entry in lineage] == [2, 3]
        assert final.result_data.get("retry_pending") is False

        assert len(retry_events) == 2
        assert [evt["retry"]["retry_sequence"] for evt in retry_events] == [1, 2]
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_non_retryable_failure_marks_failed_without_retry_event():
    bus = EventBus()
    retry_events: list[dict] = []

    async def _capture(event: EventEnvelope) -> None:
        retry_events.append(dict(event.payload))

    bus.subscribe(EventType.TASK_QUEUED, _capture)
    await bus.start()
    queue = TaskQueueManager(runtime=_FakeRuntime(), event_bus=bus, max_concurrent_agents=1)

    try:
        task = await queue.create_task(
            TaskCreate(agent_type=AgentType.LEARNING, max_retries=3, description="non-retryable"),
            requested_by="tester",
        )
        await queue._dispatch_once()
        await queue._on_agent_failed(_failed_event(task.id, int(ExitCode.UNRECOVERABLE), "bad-input"))
        await asyncio.sleep(0.05)

        failed = await queue.get_task(task.id)
        assert failed is not None
        assert failed.status == TaskStatus.FAILED
        assert failed.current_attempt == 1
        assert failed.result_data.get("retry_lineage", []) == []
        assert failed.result_data.get("retry_pending") is False
        assert retry_events == []
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_duplicate_failed_event_does_not_double_schedule_retry():
    bus = EventBus()
    retry_events: list[dict] = []

    async def _capture(event: EventEnvelope) -> None:
        retry_events.append(dict(event.payload))

    bus.subscribe(EventType.TASK_QUEUED, _capture)
    await bus.start()
    queue = TaskQueueManager(runtime=_FakeRuntime(), event_bus=bus, max_concurrent_agents=1)

    try:
        task = await queue.create_task(
            TaskCreate(agent_type=AgentType.LEARNING, max_retries=3, description="dedupe"),
            requested_by="tester",
        )
        await queue._dispatch_once()
        event = _failed_event(task.id, int(ExitCode.TIMEOUT), "timeout")
        await queue._on_agent_failed(event)
        await queue._on_agent_failed(event)
        await asyncio.sleep(0.05)

        queued = await queue.get_task(task.id)
        assert queued is not None
        assert queued.status == TaskStatus.QUEUED
        lineage = queued.result_data.get("retry_lineage", [])
        assert len(lineage) == 1
        assert lineage[0]["retry_sequence"] == 1
        assert len(retry_events) == 1
    finally:
        await bus.stop()
