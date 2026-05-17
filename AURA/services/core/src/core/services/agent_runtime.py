"""Agent runtime manager: spawn and monitor CLI agent subprocesses."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventSource, EventType
from aura_sdk.protocol.constants import ExitCode
from aura_sdk.protocol.envelope import AgentHeartbeat, AgentProgress, AgentResult
from core.services.watchdog import AgentWatch, WatchdogManager

logger = get_logger("core.agent_runtime")


def _discover_agent_registry() -> tuple[set[str], dict[str, int]]:
    """Best-effort discovery of available CLI agent types and default timeouts."""
    try:
        from aura_agents.cli import AGENT_TYPES
    except Exception:
        return {"learning"}, {}

    if not AGENT_TYPES:
        return {"learning"}, {}

    default_timeouts: dict[str, int] = {}
    for agent_name, agent_cls in AGENT_TYPES.items():
        timeout = getattr(agent_cls, "DEFAULT_TIMEOUT", None)
        if isinstance(timeout, int) and timeout > 0:
            default_timeouts[agent_name] = timeout

    return set(AGENT_TYPES.keys()), default_timeouts


def _resolve_spawn_timeout(
    *,
    requested_timeout: int | None,
    agent_type: str,
    runtime_default_timeout: int,
    agent_default_timeouts: dict[str, int],
) -> int:
    """Resolve timeout with explicit request first, then agent default, then runtime default."""
    if isinstance(requested_timeout, int) and requested_timeout > 0:
        return requested_timeout

    agent_timeout = agent_default_timeouts.get(agent_type)
    if isinstance(agent_timeout, int) and agent_timeout > 0:
        return agent_timeout

    return runtime_default_timeout


@dataclass(slots=True)
class RunningAgent:
    """In-memory state for a running CLI agent subprocess."""

    agent_id: str
    task_id: str
    agent_type: str
    requested_by: str
    process: asyncio.subprocess.Process
    output_dir: str
    created_at: float = field(default_factory=time.time)
    status: str = "running"
    progress_percent: int = 0
    last_message: str = ""
    last_heartbeat: float = 0.0
    exit_code: int | None = None
    final_result: dict[str, Any] = field(default_factory=dict)
    stdout_task: asyncio.Task[None] | None = None
    stderr_task: asyncio.Task[None] | None = None
    wait_task: asyncio.Task[None] | None = None
    final_event_emitted: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "requested_by": self.requested_by,
            "pid": self.process.pid,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "last_message": self.last_message,
            "last_heartbeat": self.last_heartbeat,
            "exit_code": self.exit_code,
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "runtime_seconds": round(max(0.0, time.time() - self.created_at), 3),
        }


class AgentRuntimeManager:
    """Launches agent CLI subprocesses and bridges their stdio protocol to events."""

    def __init__(
        self,
        *,
        watchdog: WatchdogManager,
        event_bus: EventBus | None,
        llm_gateway_url: str,
        rules_path: str,
        default_timeout_seconds: int,
        output_root: str = "/data/outputs",
        python_executable: str | None = None,
    ):
        self._watchdog = watchdog
        self._event_bus = event_bus
        self._llm_gateway_url = llm_gateway_url
        self._rules_path = rules_path
        self._default_timeout_seconds = default_timeout_seconds
        self._output_root = output_root
        self._python_executable = python_executable or sys.executable
        self._agents: dict[str, RunningAgent] = {}
        self._supported_agent_types, self._agent_default_timeouts = _discover_agent_registry()

    @property
    def supported_agent_types(self) -> set[str]:
        return set(self._supported_agent_types)

    def list_running(self) -> list[dict[str, Any]]:
        return [agent.to_public() for agent in self._agents.values()]

    async def spawn(
        self,
        *,
        agent_type: str,
        requested_by: str,
        task_id: str | None = None,
        input_data: dict[str, Any] | None = None,
        seed: int = 42,
        model_version: str = "gpt-4o-2024-08-06",
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        if agent_type not in self._supported_agent_types:
            raise ValueError(f"agent_type_not_supported:{agent_type}")

        task_id = task_id or str(uuid4())
        timeout = _resolve_spawn_timeout(
            requested_timeout=timeout_seconds,
            agent_type=agent_type,
            runtime_default_timeout=self._default_timeout_seconds,
            agent_default_timeouts=self._agent_default_timeouts,
        )
        agent_id = f"{agent_type}-{task_id[:8]}"
        output_dir = os.path.join(self._output_root, agent_type, task_id)
        os.makedirs(output_dir, exist_ok=True)

        input_json = json.dumps(input_data or {}, separators=(",", ":"))
        cmd = [
            self._python_executable,
            "-m",
            "aura_agents",
            agent_type,
            "--task-id",
            task_id,
            "--rules",
            self._rules_path,
            "--output-dir",
            output_dir,
            "--llm-gateway",
            self._llm_gateway_url,
            "--input",
            input_json,
            "--timeout",
            str(timeout),
            "--seed",
            str(seed),
            "--model-version",
            model_version,
            "--db-path",
            "/data/aura.db",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        running = RunningAgent(
            agent_id=agent_id,
            task_id=task_id,
            agent_type=agent_type,
            requested_by=requested_by,
            process=process,
            output_dir=output_dir,
            status="running",
        )
        try:
            self._watchdog.register(
                AgentWatch(
                    agent_id=agent_id,
                    task_id=task_id,
                    agent_type=agent_type,
                    process=process,
                    last_heartbeat=time.time(),
                )
            )
        except Exception:
            process.kill()
            await process.wait()
            raise

        self._agents[agent_id] = running

        await self._publish(
            EventType.AGENT_REGISTERED,
            running,
            payload={"requested_by": requested_by, "pid": process.pid},
            trace_id=task_id,
        )
        await self._publish(
            EventType.AGENT_SPAWNED,
            running,
            payload={"requested_by": requested_by, "pid": process.pid, "status": "running"},
            trace_id=task_id,
        )
        await self._publish(
            EventType.TASK_STARTED,
            running,
            payload={
                "task_id": task_id,
                "agent_type": agent_type,
                "requested_by": requested_by,
                "status": "running",
            },
            trace_id=task_id,
        )

        running.stdout_task = asyncio.create_task(self._consume_stdout(running))
        running.stderr_task = asyncio.create_task(self._consume_stderr(running))
        running.wait_task = asyncio.create_task(self._wait_for_exit(running))
        return running.to_public()

    async def terminate(self, agent_id: str, *, reason: str, requested_by: str) -> bool:
        running = self._agents.get(agent_id)
        if running is None:
            return False

        if running.process.returncode is None:
            running.status = "stopping"
            try:
                running.process.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass

            try:
                await asyncio.wait_for(running.process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                running.process.kill()
                await running.process.wait()

        running.status = "killed"
        running.exit_code = running.process.returncode
        running.final_event_emitted = True
        self._watchdog.unregister(agent_id)
        await self._publish(
            EventType.AGENT_KILLED,
            running,
            payload={
                "reason": reason,
                "requested_by": requested_by,
                "exit_code": running.exit_code,
            },
            trace_id=running.task_id,
        )
        await self._publish(
            EventType.TASK_CANCELLED,
            running,
            payload={
                "task_id": running.task_id,
                "agent_type": running.agent_type,
                "cancelled_by": requested_by,
                "reason": reason,
            },
            trace_id=running.task_id,
        )
        self._agents.pop(agent_id, None)
        return True

    async def stop(self) -> None:
        for agent_id in list(self._agents):
            await self.terminate(
                agent_id,
                reason="runtime_shutdown",
                requested_by="system",
            )

    async def _consume_stdout(self, running: RunningAgent) -> None:
        if running.process.stdout is None:
            return

        while True:
            line = await running.process.stdout.readline()
            if not line:
                break

            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            await self._handle_stdout_line(running, raw)

    async def _consume_stderr(self, running: RunningAgent) -> None:
        if running.process.stderr is None:
            return

        while True:
            line = await running.process.stderr.readline()
            if not line:
                break
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue
            logger.warning(
                "agent_stderr",
                agent_id=running.agent_id,
                task_id=running.task_id,
                agent_type=running.agent_type,
                message=raw,
            )

    async def _handle_stdout_line(self, running: RunningAgent, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "agent_stdout_non_json",
                agent_id=running.agent_id,
                task_id=running.task_id,
                line=raw[:300],
            )
            return

        message_type = payload.get("message_type", "")

        if message_type == "heartbeat":
            heartbeat = AgentHeartbeat.model_validate(payload)
            running.last_heartbeat = heartbeat.timestamp or time.time()
            self._watchdog.on_heartbeat(running.agent_id, heartbeat)
            await self._publish(
                EventType.AGENT_HEARTBEAT,
                running,
                payload={
                    "memory_mb": heartbeat.memory_mb,
                    "cpu_percent": heartbeat.cpu_percent,
                    "timestamp": heartbeat.timestamp,
                },
                trace_id=running.task_id,
            )
            return

        if message_type == "progress":
            progress = AgentProgress.model_validate(payload)
            running.progress_percent = progress.progress_percent
            running.last_message = progress.message
            await self._publish(
                EventType.TASK_PROGRESS,
                running,
                payload={
                    "task_id": running.task_id,
                    "progress_percent": progress.progress_percent,
                    "status": progress.status,
                    "message": progress.message,
                },
                trace_id=running.task_id,
            )
            return

        if message_type == "task.complete":
            result = AgentResult.model_validate(payload)
            running.final_result = {
                "results": result.results,
                "evidence": result.evidence,
                "confidence": result.confidence,
                "usage": result.usage,
                "output_path": result.output_path,
            }
            running.exit_code = int(result.exit_code)
            if int(result.exit_code) == ExitCode.SUCCESS.value:
                running.status = "completed"
                await self._publish(
                    EventType.AGENT_COMPLETED,
                    running,
                    payload={
                        "exit_code": int(result.exit_code),
                        "usage": result.usage,
                        "confidence": result.confidence,
                    },
                    trace_id=running.task_id,
                )
                await self._publish(
                    EventType.TASK_COMPLETED,
                    running,
                    payload={
                        "task_id": running.task_id,
                        "agent_type": running.agent_type,
                        "status": "completed",
                        "results": result.results,
                    },
                    trace_id=running.task_id,
                )
            else:
                running.status = "failed"
                await self._publish(
                    EventType.AGENT_FAILED,
                    running,
                    payload={
                        "exit_code": int(result.exit_code),
                        "usage": result.usage,
                        "error": result.results.get("error", ""),
                    },
                    trace_id=running.task_id,
                )
            running.final_event_emitted = True
            return

        logger.warning(
            "agent_stdout_unknown_message_type",
            agent_id=running.agent_id,
            task_id=running.task_id,
            message_type=message_type,
        )

    async def _wait_for_exit(self, running: RunningAgent) -> None:
        return_code = await running.process.wait()
        running.exit_code = return_code
        self._watchdog.unregister(running.agent_id)

        if not running.final_event_emitted:
            if return_code == 0:
                running.status = "completed"
                await self._publish(
                    EventType.AGENT_COMPLETED,
                    running,
                    payload={"exit_code": return_code},
                    trace_id=running.task_id,
                )
                await self._publish(
                    EventType.TASK_COMPLETED,
                    running,
                    payload={
                        "task_id": running.task_id,
                        "agent_type": running.agent_type,
                        "status": "completed",
                        "results": running.final_result.get("results", {}),
                    },
                    trace_id=running.task_id,
                )
            else:
                running.status = "failed"
                await self._publish(
                    EventType.AGENT_FAILED,
                    running,
                    payload={"exit_code": return_code},
                    trace_id=running.task_id,
                )

        self._agents.pop(running.agent_id, None)
        logger.info(
            "agent_process_exited",
            agent_id=running.agent_id,
            task_id=running.task_id,
            agent_type=running.agent_type,
            exit_code=return_code,
        )

    async def _publish(
        self,
        event_type: EventType,
        running: RunningAgent,
        *,
        payload: dict[str, Any],
        trace_id: str = "",
    ) -> None:
        if self._event_bus is None:
            return
        event = EventEnvelope(
            event_type=event_type,
            source=EventSource(
                subsystem="S1",
                service="core",
                task_id=running.task_id,
                agent_type=running.agent_type,
                agent_id=running.agent_id,
            ),
            payload=payload,
            trace_id=trace_id,
        )
        await self._event_bus.publish(event)
