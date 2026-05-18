"""Replay hook enforcement tests for BaseAgent lifecycle."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from aura_agents.base import BaseAgent
from aura_sdk.protocol.constants import ExitCode
from aura_sdk.replay.recorder import TaskRecorder
from aura_sdk.replay.replayer import ReplayEngine


class _FailingAgent(BaseAgent):
    AGENT_TYPE = "failing-probe"

    async def execute(self) -> dict:
        raise RuntimeError("intentional-failure")


class _TimeoutAgent(BaseAgent):
    AGENT_TYPE = "timeout-probe"

    async def execute(self) -> dict:
        await asyncio.sleep(0.1)
        return {"ok": True}


def _args(tmp_path: Path, *, task_id: str, timeout: float) -> argparse.Namespace:
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    return argparse.Namespace(
        task_id=task_id,
        rules=str(tmp_path / "rules"),
        output_dir=str(out_dir),
        llm_gateway="http://localhost:65535",
        input="{}",
        timeout=timeout,
        seed=42,
        model_version="gpt-4o-2024-08-06",
        db_path=str(tmp_path / "replay.db"),
        debug=False,
    )


def _run_agent(agent: BaseAgent, args: argparse.Namespace) -> ExitCode:
    return asyncio.run(agent.run(args))


def _load_execution_steps(log: dict) -> list[dict]:
    raw = log.get("execution_order_json") or "[]"
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, list) else []


def test_unrecoverable_failure_finalizes_replay_and_persists_steps(tmp_path):
    args = _args(tmp_path, task_id="task-fail", timeout=5)
    exit_code = _run_agent(_FailingAgent(), args)
    assert exit_code == ExitCode.UNRECOVERABLE

    recorder = TaskRecorder(args.db_path)
    log = recorder.get_log(args.task_id)
    assert log is not None
    assert log["recording_state"] == "finalized"

    output = json.loads(log["output_json"])
    assert output["status"] == "unrecoverable"
    assert output["exit_code"] == int(ExitCode.UNRECOVERABLE)
    assert "intentional-failure" in output["results"]["error"]

    steps = _load_execution_steps(log)
    step_names = [step["step"] for step in steps]
    assert "task_started" in step_names
    assert "execute_exception" in step_names
    assert "task_result" in step_names
    assert "task_finished" in step_names
    assert [step["seq"] for step in steps] == list(range(1, len(steps) + 1))

    replay = asyncio.run(ReplayEngine(recorder).replay(args.task_id))
    assert replay["success"] is True
    assert replay["recording_state"] == "finalized"
    assert replay["output"]["status"] == "unrecoverable"


def test_timeout_finalizes_replay(tmp_path):
    args = _args(tmp_path, task_id="task-timeout", timeout=0.01)
    exit_code = _run_agent(_TimeoutAgent(), args)
    assert exit_code == ExitCode.TIMEOUT

    recorder = TaskRecorder(args.db_path)
    log = recorder.get_log(args.task_id)
    assert log is not None
    assert log["recording_state"] == "finalized"

    output = json.loads(log["output_json"])
    assert output["status"] == "timeout"
    assert output["exit_code"] == int(ExitCode.TIMEOUT)

    replay = asyncio.run(ReplayEngine(recorder).replay(args.task_id))
    assert replay["success"] is True
    assert replay["output"]["status"] == "timeout"
