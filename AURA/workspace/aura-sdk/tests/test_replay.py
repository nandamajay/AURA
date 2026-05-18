"""Replay regression tests."""

import asyncio

from aura_sdk.replay.recorder import TaskRecorder
from aura_sdk.replay.replayer import ReplayEngine, ReplayFidelity


def test_replay_rejects_mutable_log_until_finalized(tmp_path):
    db_path = tmp_path / "replay.db"
    recorder = TaskRecorder(str(db_path))
    task_id = "task-mutable"

    recorder.start_task(
        task_id=task_id,
        agent_type="learning",
        seed=42,
        model_version="gpt-4o-2024-08-06",
        rules_path="/rules/learning.yaml",
        input_data={"goal": "boundary-check"},
    )
    recorder.record_prompt(task_id, "user", "hello")
    recorder.record_response(task_id, "world")

    engine = ReplayEngine(recorder)
    result = asyncio.run(engine.replay(task_id))

    assert result["success"] is False
    assert result["fidelity"] == ReplayFidelity.INCOMPLETE
    assert "not finalized" in result["error"]
    assert result["recording_state"] == "mutable"


def test_replay_uses_immutable_snapshot_after_finalize(tmp_path):
    db_path = tmp_path / "replay.db"
    recorder = TaskRecorder(str(db_path))
    task_id = "task-finalized"

    recorder.start_task(
        task_id=task_id,
        agent_type="learning",
        seed=99,
        model_version="gpt-4o-2024-08-06",
        rules_path="/rules/learning.yaml",
        input_data={"goal": "snapshot-check"},
    )
    recorder.record_prompt(task_id, "user", "p0")
    recorder.record_response(task_id, "r0")
    assert recorder.finalize(task_id, {"status": "ok"}) is True

    # Late writes must be rejected for finalized logs.
    assert recorder.record_prompt(task_id, "user", "late") is False
    assert recorder.record_response(task_id, "late") is False

    engine = ReplayEngine(recorder)
    first = asyncio.run(engine.replay(task_id))
    second = asyncio.run(engine.replay(task_id))

    assert first["success"] is True
    assert first["fidelity"] == ReplayFidelity.PERFECT
    assert first["recording_state"] == "finalized"
    assert first["prompt_count"] == 1
    assert first["response_count"] == 1
    assert first["snapshot_hash"]
    assert second["snapshot_hash"] == first["snapshot_hash"]
    assert second["output_hash"] == first["output_hash"]
    assert engine.verify_integrity(task_id) is True


def test_replay_integrity_fails_for_mutable_log(tmp_path):
    db_path = tmp_path / "replay.db"
    recorder = TaskRecorder(str(db_path))
    task_id = "task-integrity-mutable"

    recorder.start_task(
        task_id=task_id,
        agent_type="learning",
        seed=7,
        model_version="gpt-4o-2024-08-06",
        rules_path="/rules/learning.yaml",
        input_data={"goal": "integrity-check"},
    )
    recorder.record_prompt(task_id, "user", "hello")

    engine = ReplayEngine(recorder)
    assert engine.verify_integrity(task_id) is False
