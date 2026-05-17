"""BaseAgent ABC — all AURA agents inherit from this.

Every agent is a CLI executable. It receives tasks via stdin,
reports progress via stdout (JSON lines), and exits with canonical codes.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import psutil

from aura_sdk.logging.logger import configure_logging, get_logger
from aura_sdk.protocol.constants import (
    HEARTBEAT_INTERVAL_SECONDS,
    WATCHDOG_TIMEOUT_SECONDS,
    ExitCode,
    MessageType,
)
from aura_sdk.protocol.envelope import (
    AgentHeartbeat,
    AgentProgress,
    AgentResult,
    StdioEnvelope,
)
from aura_sdk.replay.context import DeterministicContext
from aura_sdk.replay.recorder import TaskRecorder


class BaseAgent(ABC):
    """Base class for all AURA CLI agents.

    Subclass and override:
      - AGENT_TYPE: str — unique agent type identifier
      - execute() — main work, returns dict of results
    """

    AGENT_TYPE: str = ""
    DEFAULT_TIMEOUT: int = 300

    def __init__(self):
        self.task_id: str = ""
        self.rules_path: str = ""
        self.output_dir: Path = Path()
        self.llm_gateway_url: str = ""
        self.input_json: str = ""
        self.context: DeterministicContext | None = None
        self.recorder: TaskRecorder | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._start_time: float = 0.0

    @classmethod
    def main(cls):
        """Entry point: python -m aura_agents.{name}"""
        parser = argparse.ArgumentParser(description=f"AURA {cls.AGENT_TYPE} agent")
        parser.add_argument("--task-id", required=True, help="Task identifier")
        parser.add_argument("--rules", required=True, help="Path to rules file/directory")
        parser.add_argument("--output-dir", required=True, help="Output directory")
        parser.add_argument("--llm-gateway", required=True, help="LLM gateway URL")
        parser.add_argument("--input", default="", help="JSON input data")
        parser.add_argument("--timeout", type=int, default=cls.DEFAULT_TIMEOUT)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--model-version", default="gpt-4o-2024-08-06")
        parser.add_argument("--db-path", default="/data/aura.db", help="Path to SQLite DB")
        parser.add_argument("--debug", action="store_true", help="Debug logging")
        args = parser.parse_args()

        if args.debug:
            configure_logging("DEBUG", json_output=False)

        agent = cls()
        try:
            exit_code = asyncio.run(agent.run(args))
            sys.exit(exit_code.value)
        except KeyboardInterrupt:
            print("Interrupted by user", file=sys.stderr)
            sys.exit(ExitCode.UNRECOVERABLE.value)

    async def run(self, args) -> ExitCode:
        """Main execution loop. Subclasses override execute()."""
        self.task_id = args.task_id
        self.rules_path = args.rules
        self.output_dir = Path(args.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.llm_gateway_url = args.llm_gateway
        self.input_json = args.input or ""
        self._start_time = time.time()
        input_data: dict[str, Any] = {}
        if self.input_json:
            try:
                parsed = json.loads(self.input_json)
                if isinstance(parsed, dict):
                    input_data = parsed
            except Exception:
                input_data = {}

        # Initialize deterministic context
        self.context = DeterministicContext(
            seed=args.seed,
            model_version=args.model_version,
        )

        # Initialize recorder
        self.recorder = TaskRecorder(args.db_path)
        self.recorder.start_task(
            task_id=args.task_id,
            agent_type=self.AGENT_TYPE,
            seed=args.seed,
            model_version=args.model_version,
            rules_path=args.rules,
            input_data=input_data,
        )

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            result = await asyncio.wait_for(self.execute(), timeout=args.timeout)
            await self._send_progress(100, "complete", "Task completed successfully")
            await self._send_result(ExitCode.SUCCESS, result)
            self.recorder.finalize(args.task_id, result)
            return ExitCode.SUCCESS

        except asyncio.TimeoutError:
            await self._send_result(
                ExitCode.TIMEOUT, {"error": f"Timed out after {args.timeout}s"}
            )
            return ExitCode.TIMEOUT

        except Exception as e:
            await self._send_result(ExitCode.UNRECOVERABLE, {"error": str(e)})
            return ExitCode.UNRECOVERABLE

        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    @abstractmethod
    async def execute(self) -> dict[str, Any]:
        """Override this. Return dict of results.

        Use self.call_llm() for LLM interactions.
        Use self._send_progress() to report progress.
        """
        raise NotImplementedError

    async def call_llm(self, messages: list[dict[str, str]], max_tokens: int = 4000) -> str:
        """Call LLM via gateway. Records for replay."""
        import httpx

        if self.recorder and self.task_id:
            for msg in messages:
                self.recorder.record_prompt(self.task_id, msg.get("role", "user"), msg.get("content", ""))

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self.llm_gateway_url}/v1/completions",
                json={
                    "agent_type": self.AGENT_TYPE,
                    "task_id": self.task_id,
                    "messages": messages,
                    **(self.context.llm_params() if self.context else {}),
                    "max_tokens": max_tokens,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", "")

            if self.recorder and self.task_id:
                self.recorder.record_response(self.task_id, content)

            return content

    async def _heartbeat_loop(self) -> None:
        """Send heartbeat every HEARTBEAT_INTERVAL_SECONDS."""
        while True:
            try:
                hb = AgentHeartbeat(
                    agent_id=f"{self.AGENT_TYPE}-{self.task_id[:8]}",
                    task_id=self.task_id,
                    timestamp=time.time(),
                    memory_mb=self._get_memory(),
                    cpu_percent=self._get_cpu(),
                )
                print(hb.model_dump_json(), flush=True)
            except Exception:
                pass
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

    async def _send_progress(self, pct: int, status: str, message: str) -> None:
        prog = AgentProgress(
            task_id=self.task_id,
            progress_percent=pct,
            status=status,
            message=message,
        )
        print(prog.model_dump_json(), flush=True)

    async def _send_result(self, exit_code: ExitCode, results: dict[str, Any]) -> None:
        result = AgentResult(
            task_id=self.task_id,
            exit_code=exit_code,
            results=results,
            output_path=str(self.output_dir),
            usage={
                "duration_ms": int((time.time() - self._start_time) * 1000),
                "memory_mb": self._get_memory(),
            },
        )
        print(result.model_dump_json(), flush=True)

    def _get_memory(self) -> int:
        """Get current memory usage in MB."""
        try:
            process = psutil.Process(os.getpid())
            return int(process.memory_info().rss / 1024 / 1024)
        except Exception:
            return 0

    def _get_cpu(self) -> float:
        """Get current CPU usage percentage."""
        try:
            return psutil.Process(os.getpid()).cpu_percent(interval=0.1)
        except Exception:
            return 0.0
