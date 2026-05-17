"""Task queue manager: 3-tier scheduler for orchestrator tasks.

Scheduling policy:
- P0 critical: FIFO
- P1 normal: round-robin across agent types
- P2 background: best-effort (only when running load < 50%)
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import date, datetime, timezone

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventType
from aura_sdk.models.task import Task, TaskCreate, TaskPriority, TaskStatus
from core.services.agent_runtime import AgentRuntimeManager

logger = get_logger("core.task_queue")


class TaskQueueManager:
    """Persistent task queue with 3-tier scheduling and runtime integration."""

    def __init__(
        self,
        *,
        runtime: AgentRuntimeManager,
        event_bus: EventBus | None,
        max_concurrent_agents: int = 50,
        dispatch_interval_seconds: float = 0.5,
    ):
        self._runtime = runtime
        self._event_bus = event_bus
        self._max_concurrent_agents = max_concurrent_agents
        self._dispatch_interval_seconds = dispatch_interval_seconds

        self._lock = asyncio.Lock()
        self._running = False
        self._dispatcher_task: asyncio.Task[None] | None = None

        self._tasks: dict[str, Task] = {}
        self._p0_queue: deque[str] = deque()
        self._p1_by_agent: dict[str, deque[str]] = {}
        self._p1_rr: deque[str] = deque()
        self._p2_queue: deque[str] = deque()

        self._running_task_to_agent: dict[str, str] = {}
        self._running_agent_to_task: dict[str, str] = {}

        self._stats_day: date = datetime.now(timezone.utc).date()
        self._completed_today = 0
        self._failed_today = 0

        self._persistence_enabled = False

    async def start(self) -> None:
        if self._running:
            return

        await self._initialize_persistence()
        if self._persistence_enabled:
            await self._load_persistent_state()
            await self._load_daily_stats()

        self._running = True
        if self._event_bus is not None:
            self._event_bus.subscribe(EventType.TASK_COMPLETED, self._on_task_completed)
            self._event_bus.subscribe(EventType.AGENT_FAILED, self._on_agent_failed)
            self._event_bus.subscribe(EventType.TASK_CANCELLED, self._on_task_cancelled)
        self._dispatcher_task = asyncio.create_task(self._dispatch_loop())
        logger.info(
            "task_queue_started",
            max_concurrent_agents=self._max_concurrent_agents,
            dispatch_interval_seconds=self._dispatch_interval_seconds,
            persistence_enabled=self._persistence_enabled,
        )

    async def stop(self) -> None:
        self._running = False
        if self._dispatcher_task is not None:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None
        logger.info("task_queue_stopped")

    async def create_task(self, task_in: TaskCreate, *, requested_by: str) -> Task:
        actor = requested_by or task_in.requested_by or "unknown"
        task = Task(
            agent_type=task_in.agent_type,
            status=TaskStatus.CREATED,
            priority=task_in.priority,
            input_data=task_in.input_data,
            description=task_in.description,
            requested_by=actor,
            parent_task_id=task_in.parent_task_id,
            max_retries=task_in.max_retries,
        )

        async with self._lock:
            self._rollover_daily_stats_if_needed()
            self._tasks[task.id] = task
            self._enqueue_locked(task.id, task.priority, task.agent_type.value)
            task.status = TaskStatus.QUEUED

        await self._upsert_task(task)
        logger.info(
            "task_enqueued",
            task_id=task.id,
            agent_type=task.agent_type.value,
            priority=task.priority.value,
            requested_by=actor,
        )
        return task

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        agent_type: str | None = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[list[Task], int]:
        page = max(1, page)
        limit = max(1, min(limit, 500))
        status_filter = self._parse_status(status) if status else None
        agent_filter = (agent_type or "").strip().lower()

        async with self._lock:
            items = list(self._tasks.values())

        filtered: list[Task] = []
        for task in items:
            if status_filter is not None and task.status != status_filter:
                continue
            if agent_filter and task.agent_type.value.lower() != agent_filter:
                continue
            filtered.append(task)

        filtered.sort(key=lambda task: task.created_at, reverse=True)
        total = len(filtered)
        start = (page - 1) * limit
        end = start + limit
        return filtered[start:end], total

    async def get_task(self, task_id: str) -> Task | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def register_external_spawn(
        self,
        *,
        task_id: str,
        agent_type: str,
        requested_by: str,
        agent_id: str,
        agent_pid: int | None,
        input_data: dict | None = None,
        description: str = "",
        priority: str = TaskPriority.NORMAL.value,
    ) -> Task:
        """Register a manually spawned agent task into queue state/persistence.

        This keeps `/api/v1/tasks/{task_id}` and replay/audit flows consistent for
        agents launched via `/api/v1/agents/{agent_type}/spawn`.
        """
        task_to_persist: Task | None = None
        async with self._lock:
            existing = self._tasks.get(task_id)
            if existing is None:
                task = Task(
                    id=task_id,
                    agent_type=agent_type,
                    status=TaskStatus.RUNNING,
                    priority=priority,
                    input_data=input_data or {},
                    description=description,
                    requested_by=requested_by or "unknown",
                    current_attempt=1,
                    started_at=datetime.now(timezone.utc),
                    agent_pid=agent_pid,
                )
                self._tasks[task.id] = task
            else:
                task = existing
                if task.status in {
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.TIMED_OUT,
                }:
                    raise ValueError(f"task_id_conflict_terminal_status:{task.status.value}")
                self._remove_from_queues_locked(task.id, task.agent_type.value)
                task.status = TaskStatus.RUNNING
                if task.started_at is None:
                    task.started_at = datetime.now(timezone.utc)
                task.agent_pid = agent_pid

            self._detach_running_locked(task.id)
            self._running_task_to_agent[task.id] = agent_id
            self._running_agent_to_task[agent_id] = task.id
            task_to_persist = task

        await self._upsert_task(task_to_persist)
        logger.info(
            "task_registered_external_spawn",
            task_id=task_to_persist.id,
            agent_type=task_to_persist.agent_type.value,
            agent_id=agent_id,
            requested_by=requested_by,
        )
        return task_to_persist

    async def cancel_task(self, task_id: str, *, requested_by: str) -> Task | None:
        terminate_agent_id: str | None = None
        task_to_persist: Task | None = None
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None

            if task.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.TIMED_OUT,
            }:
                return task

            terminate_agent_id = self._running_task_to_agent.get(task_id)
            self._remove_from_queues_locked(task_id, task.agent_type.value)
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now(timezone.utc)
            self._detach_running_locked(task_id)
            task_to_persist = task

        if terminate_agent_id is not None:
            await self._runtime.terminate(
                terminate_agent_id,
                reason="task_cancelled",
                requested_by=requested_by,
            )

        if task_to_persist is not None:
            await self._upsert_task(task_to_persist)
        logger.info(
            "task_cancelled_in_queue",
            task_id=task_id,
            requested_by=requested_by,
        )
        return task_to_persist

    async def get_queue_stats(self) -> dict[str, int]:
        async with self._lock:
            self._rollover_daily_stats_if_needed()
            return {
                "P0_critical": len(self._p0_queue),
                "P1_normal": sum(len(queue) for queue in self._p1_by_agent.values()),
                "P2_background": len(self._p2_queue),
                "running": len(self._running_task_to_agent),
                "completed_today": self._completed_today,
                "failed_today": self._failed_today,
            }

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                await self._dispatch_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("task_dispatch_loop_error", error=str(exc))
            await asyncio.sleep(self._dispatch_interval_seconds)

    async def _dispatch_once(self) -> None:
        preempt_task_id: str | None = None
        preempt_agent_id: str | None = None
        preempt_task: Task | None = None
        async with self._lock:
            if self._p0_queue and len(self._running_task_to_agent) >= self._max_concurrent_agents:
                p2_running = [
                    self._tasks[task_id]
                    for task_id in self._running_task_to_agent
                    if self._tasks.get(task_id) is not None
                    and self._tasks[task_id].priority == TaskPriority.BACKGROUND
                ]
                if p2_running:
                    p2_running.sort(key=lambda task: task.started_at or task.created_at)
                    preempt_task = p2_running[0]
                    preempt_task_id = preempt_task.id
                    preempt_agent_id = self._running_task_to_agent.get(preempt_task.id)

        if preempt_task_id and preempt_agent_id:
            logger.warning(
                "task_queue_preempt_background",
                task_id=preempt_task_id,
                reason="p0_priority_preemption",
            )
            await self._runtime.terminate(
                preempt_agent_id,
                reason="p0_preemption",
                requested_by="scheduler",
            )
            async with self._lock:
                task = self._tasks.get(preempt_task_id)
                if task is not None:
                    task.status = TaskStatus.CANCELLED
                    task.completed_at = datetime.now(timezone.utc)
                    preempt_task = task
                self._detach_running_locked(preempt_task_id)
            if preempt_task is not None:
                await self._upsert_task(preempt_task)

        while True:
            task: Task | None = None
            async with self._lock:
                self._rollover_daily_stats_if_needed()
                running_count = len(self._running_task_to_agent)
                if running_count >= self._max_concurrent_agents:
                    return

                task_id = self._select_next_task_locked(running_count=running_count)
                if task_id is None:
                    return

                task = self._tasks.get(task_id)
                if task is None or task.status != TaskStatus.QUEUED:
                    continue
                task.status = TaskStatus.STARTED
                task.started_at = datetime.now(timezone.utc)
                task.current_attempt += 1

            if task is None:
                continue
            await self._upsert_task(task)

            try:
                spawned = await self._runtime.spawn(
                    agent_type=task.agent_type.value,
                    requested_by=task.requested_by or "scheduler",
                    task_id=task.id,
                    input_data=task.input_data,
                )
            except Exception as exc:
                async with self._lock:
                    current = self._tasks.get(task.id)
                    if current is not None:
                        current.status = TaskStatus.FAILED
                        current.completed_at = datetime.now(timezone.utc)
                        current.result_data = {"error": str(exc)}
                        self._failed_today += 1
                        task = current
                await self._upsert_task(task)
                logger.exception(
                    "task_spawn_failed_from_queue",
                    task_id=task.id,
                    agent_type=task.agent_type.value,
                    error=str(exc),
                )
                continue

            async with self._lock:
                current = self._tasks.get(task.id)
                if current is None:
                    continue
                current.status = TaskStatus.RUNNING
                current.agent_pid = spawned.get("pid")
                agent_id = spawned["agent_id"]
                self._running_task_to_agent[current.id] = agent_id
                self._running_agent_to_task[agent_id] = current.id
                task = current
            await self._upsert_task(task)

    def _select_next_task_locked(self, *, running_count: int) -> str | None:
        if self._p0_queue:
            return self._p0_queue.popleft()

        if self._p1_rr:
            iterations = len(self._p1_rr)
            for _ in range(iterations):
                agent_type = self._p1_rr[0]
                self._p1_rr.rotate(-1)
                queue = self._p1_by_agent.get(agent_type)
                if queue is None:
                    continue
                while queue:
                    task_id = queue.popleft()
                    task = self._tasks.get(task_id)
                    if task is not None and task.status == TaskStatus.QUEUED:
                        if not queue:
                            self._drop_empty_p1_bucket_locked(agent_type)
                        return task_id
                self._drop_empty_p1_bucket_locked(agent_type)

        p2_running_limit = max(1, self._max_concurrent_agents // 2)
        if self._p2_queue and running_count < p2_running_limit:
            return self._p2_queue.popleft()

        return None

    def _enqueue_locked(self, task_id: str, priority: TaskPriority, agent_type: str) -> None:
        if priority == TaskPriority.CRITICAL:
            self._p0_queue.append(task_id)
            return
        if priority == TaskPriority.NORMAL:
            queue = self._p1_by_agent.get(agent_type)
            if queue is None:
                queue = deque()
                self._p1_by_agent[agent_type] = queue
                self._p1_rr.append(agent_type)
            queue.append(task_id)
            return
        self._p2_queue.append(task_id)

    def _remove_from_queues_locked(self, task_id: str, agent_type: str) -> None:
        self._discard_from_deque(self._p0_queue, task_id)
        self._discard_from_deque(self._p2_queue, task_id)

        queue = self._p1_by_agent.get(agent_type)
        if queue is not None:
            self._discard_from_deque(queue, task_id)
            if not queue:
                self._drop_empty_p1_bucket_locked(agent_type)

    def _drop_empty_p1_bucket_locked(self, agent_type: str) -> None:
        self._p1_by_agent.pop(agent_type, None)
        self._p1_rr = deque(item for item in self._p1_rr if item != agent_type)

    def _discard_from_deque(self, queue: deque[str], task_id: str) -> None:
        try:
            queue.remove(task_id)
        except ValueError:
            pass

    def _detach_running_locked(self, task_id: str) -> None:
        agent_id = self._running_task_to_agent.pop(task_id, None)
        if agent_id is not None:
            self._running_agent_to_task.pop(agent_id, None)

    def _parse_status(self, status: str | None) -> TaskStatus | None:
        if not status:
            return None
        raw = status.strip().lower()
        for member in TaskStatus:
            if member.value == raw:
                return member
        return None

    def _rollover_daily_stats_if_needed(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today == self._stats_day:
            return
        self._stats_day = today
        self._completed_today = 0
        self._failed_today = 0

    async def _on_task_completed(self, event: EventEnvelope) -> None:
        task_id = str(event.payload.get("task_id") or event.source.task_id or "")
        if not task_id:
            return

        task_to_persist: Task | None = None
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if task.status not in {TaskStatus.CANCELLED, TaskStatus.COMPLETED}:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                task.result_data = event.payload.get("results", {})
                self._completed_today += 1
            self._detach_running_locked(task_id)
            task_to_persist = task
        if task_to_persist is not None:
            await self._upsert_task(task_to_persist)

    async def _on_agent_failed(self, event: EventEnvelope) -> None:
        task_id = str(event.source.task_id or "")
        if not task_id:
            return

        task_to_persist: Task | None = None
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if task.status != TaskStatus.CANCELLED:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now(timezone.utc)
                task.result_data = {"error": event.payload.get("error", "")}
                self._failed_today += 1
            self._detach_running_locked(task_id)
            task_to_persist = task
        if task_to_persist is not None:
            await self._upsert_task(task_to_persist)

    async def _on_task_cancelled(self, event: EventEnvelope) -> None:
        task_id = str(event.payload.get("task_id") or event.source.task_id or "")
        if not task_id:
            return

        task_to_persist: Task | None = None
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.status = TaskStatus.CANCELLED
            if task.completed_at is None:
                task.completed_at = datetime.now(timezone.utc)
            self._detach_running_locked(task_id)
            task_to_persist = task
        if task_to_persist is not None:
            await self._upsert_task(task_to_persist)

    async def _initialize_persistence(self) -> None:
        try:
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'"
                )
                row = await cursor.fetchone()
                self._persistence_enabled = row is not None
        except Exception as exc:
            self._persistence_enabled = False
            logger.warning("task_queue_persistence_unavailable", error=str(exc))

        if not self._persistence_enabled:
            logger.warning("task_queue_persistence_disabled", reason="tasks table not found")

    async def _load_persistent_state(self) -> None:
        try:
            async with get_db() as db:
                cursor = await db.execute(
                    """
                    SELECT id, agent_type, status, priority, input_data, result_data, description,
                           requested_by, parent_task_id, current_attempt, max_retries, agent_pid,
                           started_at, completed_at, created_at
                    FROM tasks
                    ORDER BY created_at ASC
                    """
                )
                rows = await cursor.fetchall()
        except Exception as exc:
            logger.warning("task_queue_persistence_load_failed", error=str(exc))
            return

        recovered_requeued = 0
        for row in rows:
            try:
                task = self._task_from_row(row)
            except Exception:
                continue
            self._tasks[task.id] = task

            if task.status in {TaskStatus.CREATED, TaskStatus.QUEUED}:
                task.status = TaskStatus.QUEUED
                self._enqueue_locked(task.id, task.priority, task.agent_type.value)
                continue
            if task.status in {TaskStatus.STARTED, TaskStatus.RUNNING}:
                task.status = TaskStatus.QUEUED
                task.started_at = None
                task.agent_pid = None
                self._enqueue_locked(task.id, task.priority, task.agent_type.value)
                recovered_requeued += 1
                await self._upsert_task(task)

        logger.info(
            "task_queue_state_loaded",
            loaded_tasks=len(rows),
            recovered_requeued=recovered_requeued,
            queued_p0=len(self._p0_queue),
            queued_p1=sum(len(queue) for queue in self._p1_by_agent.values()),
            queued_p2=len(self._p2_queue),
        )

    async def _load_daily_stats(self) -> None:
        today_ts = int(
            datetime.combine(self._stats_day, datetime.min.time(), tzinfo=timezone.utc).timestamp()
        )
        try:
            async with get_db() as db:
                completed_cursor = await db.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE completed_at >= ? AND status = ?
                    """,
                    (today_ts, TaskStatus.COMPLETED.value),
                )
                failed_cursor = await db.execute(
                    """
                    SELECT COUNT(*) FROM tasks
                    WHERE completed_at >= ? AND status = ?
                    """,
                    (today_ts, TaskStatus.FAILED.value),
                )
                completed_row = await completed_cursor.fetchone()
                failed_row = await failed_cursor.fetchone()
                self._completed_today = int(completed_row[0] if completed_row else 0)
                self._failed_today = int(failed_row[0] if failed_row else 0)
        except Exception as exc:
            logger.warning("task_queue_daily_stats_load_failed", error=str(exc))

    async def _upsert_task(self, task: Task | None) -> None:
        if task is None or not self._persistence_enabled:
            return

        try:
            async with get_db() as db:
                await db.execute(
                    """
                    INSERT INTO tasks (
                        id, agent_type, status, priority, input_data, result_data, description,
                        requested_by, parent_task_id, current_attempt, max_retries, agent_pid,
                        started_at, completed_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        agent_type = excluded.agent_type,
                        status = excluded.status,
                        priority = excluded.priority,
                        input_data = excluded.input_data,
                        result_data = excluded.result_data,
                        description = excluded.description,
                        requested_by = excluded.requested_by,
                        parent_task_id = excluded.parent_task_id,
                        current_attempt = excluded.current_attempt,
                        max_retries = excluded.max_retries,
                        agent_pid = excluded.agent_pid,
                        started_at = excluded.started_at,
                        completed_at = excluded.completed_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        task.id,
                        task.agent_type.value,
                        task.status.value,
                        task.priority.value,
                        json.dumps(task.input_data, separators=(",", ":")),
                        json.dumps(task.result_data, separators=(",", ":")),
                        task.description,
                        task.requested_by,
                        task.parent_task_id,
                        task.current_attempt,
                        task.max_retries,
                        task.agent_pid,
                        self._dt_to_ts(task.started_at),
                        self._dt_to_ts(task.completed_at),
                        self._dt_to_ts(task.created_at) or int(datetime.now(timezone.utc).timestamp()),
                        int(datetime.now(timezone.utc).timestamp()),
                    ),
                )
                await db.commit()
        except Exception as exc:
            logger.warning("task_queue_persistence_upsert_failed", task_id=task.id, error=str(exc))

    def _task_from_row(self, row) -> Task:
        input_data = self._safe_json_load(row["input_data"], {})
        result_data = self._safe_json_load(row["result_data"], {})

        created_at = self._ts_to_dt(row["created_at"]) or datetime.now(timezone.utc)
        return Task(
            id=row["id"],
            agent_type=row["agent_type"],
            status=row["status"],
            priority=row["priority"],
            input_data=input_data,
            result_data=result_data,
            description=row["description"] or "",
            requested_by=row["requested_by"] or "",
            parent_task_id=row["parent_task_id"] or "",
            current_attempt=int(row["current_attempt"] or 0),
            max_retries=int(row["max_retries"] or 3),
            agent_pid=row["agent_pid"],
            started_at=self._ts_to_dt(row["started_at"]),
            completed_at=self._ts_to_dt(row["completed_at"]),
            created_at=created_at,
        )

    def _safe_json_load(self, raw: str | None, fallback):
        if not raw:
            return fallback
        try:
            value = json.loads(raw)
            if isinstance(fallback, dict) and isinstance(value, dict):
                return value
            return fallback
        except Exception:
            return fallback

    def _dt_to_ts(self, value: datetime | None) -> int | None:
        if value is None:
            return None
        return int(value.timestamp())

    def _ts_to_dt(self, value: int | None) -> datetime | None:
        if value is None:
            return None
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
