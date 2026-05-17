"""Replay regression tests."""

import asyncio
import sqlite3

from aura_sdk.replay.recorder import TaskRecorder
from aura_sdk.replay.replayer import ReplayEngine, ReplayFidelity


def test_replay_handles_null_output_json(tmp_path):
    """Replay must not fail when a task log exists but output_json is NULL."""
    db_path = tmp_path / "replay.db"
    recorder = TaskRecorder(str(db_path))
    task_id = "task-null-output"

    recorder.start_task(
        task_id=task_id,
        agent_type="learning",
        seed=42,
        model_version="gpt-4o-2024-08-06",
        rules_path="/rules/learning.yaml",
        input_data={"goal": "validate null output handling"},
    )
    recorder.record_prompt(task_id, "user", "hello")
    recorder.record_response(task_id, "world")

    # Ensure explicit NULL to cover migration/legacy rows.
    with sqlite3.connect(str(db_path)) as db:
        db.execute("UPDATE task_logs SET output_json = NULL WHERE task_id = ?", (task_id,))
        db.commit()

    engine = ReplayEngine(recorder)
    result = asyncio.run(engine.replay(task_id))

    assert result["success"] is True
    assert result["fidelity"] == ReplayFidelity.PERFECT
    assert result["output"] == {}
    assert result["output_keys"] == []
    assert result["prompt_count"] == 1
    assert result["response_count"] == 1
