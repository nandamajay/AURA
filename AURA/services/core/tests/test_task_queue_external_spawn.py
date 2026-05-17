"""Task queue regression tests for externally spawned agents."""

from datetime import datetime, timezone

import pytest

from aura_sdk.models.agent import AgentType
from aura_sdk.models.task import TaskCreate, TaskStatus
from core.services.task_queue import TaskQueueManager


class _DummyRuntime:
    """Placeholder runtime for queue unit tests."""


@pytest.mark.asyncio
async def test_register_external_spawn_creates_running_task():
    queue = TaskQueueManager(runtime=_DummyRuntime(), event_bus=None)

    task = await queue.register_external_spawn(
        task_id="task-ext-1",
        agent_type=AgentType.LEARNING.value,
        requested_by="tester@example.com",
        agent_id="learning-task-ext",
        agent_pid=1234,
        input_data={"goal": "verify external spawn tracking"},
        description="external spawn test",
    )

    assert task.id == "task-ext-1"
    assert task.status == TaskStatus.RUNNING
    assert task.agent_pid == 1234

    fetched = await queue.get_task("task-ext-1")
    assert fetched is not None
    assert fetched.status == TaskStatus.RUNNING

    stats = await queue.get_queue_stats()
    assert stats["running"] == 1
    assert stats["P0_critical"] == 0
    assert stats["P1_normal"] == 0
    assert stats["P2_background"] == 0


@pytest.mark.asyncio
async def test_register_external_spawn_promotes_existing_queued_task():
    queue = TaskQueueManager(runtime=_DummyRuntime(), event_bus=None)
    created = await queue.create_task(
        TaskCreate(
            agent_type=AgentType.LEARNING,
            description="queued task",
            input_data={"goal": "queue then external spawn"},
        ),
        requested_by="tester@example.com",
    )
    assert created.status == TaskStatus.QUEUED

    promoted = await queue.register_external_spawn(
        task_id=created.id,
        agent_type=AgentType.LEARNING.value,
        requested_by="tester@example.com",
        agent_id="learning-promoted",
        agent_pid=4321,
        input_data=created.input_data,
        description=created.description,
    )

    assert promoted.status == TaskStatus.RUNNING
    assert promoted.agent_pid == 4321
    stats = await queue.get_queue_stats()
    assert stats["running"] == 1
    assert stats["P1_normal"] == 0


@pytest.mark.asyncio
async def test_register_external_spawn_rejects_terminal_task_id_conflict():
    queue = TaskQueueManager(runtime=_DummyRuntime(), event_bus=None)
    task = await queue.register_external_spawn(
        task_id="task-ext-terminal",
        agent_type=AgentType.LEARNING.value,
        requested_by="tester@example.com",
        agent_id="learning-terminal",
        agent_pid=999,
    )
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="task_id_conflict_terminal_status:completed"):
        await queue.register_external_spawn(
            task_id="task-ext-terminal",
            agent_type=AgentType.LEARNING.value,
            requested_by="tester@example.com",
            agent_id="learning-terminal-2",
            agent_pid=1000,
        )
