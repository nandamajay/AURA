"""TaskRecorder — records all inputs + LLM responses for deterministic replay."""

import hashlib
import json
import sqlite3
from typing import Any


class TaskRecorder:
    """Records all inputs + LLM responses for deterministic replay.

    Stores in SQLite for durability. Each task gets one row in task_logs.
    LLM prompts and responses appended as JSON arrays.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Create the task_logs table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS task_logs (
                    task_id TEXT PRIMARY KEY,
                    agent_type TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    model_version TEXT NOT NULL,
                    rules_path TEXT,
                    input_json TEXT NOT NULL,
                    llm_prompts_json TEXT DEFAULT '[]',
                    llm_responses_json TEXT DEFAULT '[]',
                    execution_order_json TEXT DEFAULT '[]',
                    output_json TEXT,
                    output_hash TEXT,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
            """)
            db.commit()

    def start_task(
        self,
        task_id: str,
        agent_type: str,
        seed: int,
        model_version: str,
        rules_path: str,
        input_data: dict[str, Any],
    ) -> None:
        """Record the start of a task."""
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                INSERT OR REPLACE INTO task_logs
                (task_id, agent_type, seed, model_version, rules_path, input_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    agent_type,
                    seed,
                    model_version,
                    rules_path,
                    json.dumps(input_data),
                ),
            )
            db.commit()

    def record_prompt(self, task_id: str, role: str, content: str) -> None:
        """Record an LLM prompt."""
        prompt = {"role": role, "content": content}
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE task_logs SET llm_prompts_json = json_insert(
                    COALESCE(llm_prompts_json, '[]'), '$[#]', json(?)
                ) WHERE task_id = ?
                """,
                (json.dumps(prompt), task_id),
            )
            db.commit()

    def record_response(self, task_id: str, response: str) -> None:
        """Record an LLM response."""
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE task_logs SET llm_responses_json = json_insert(
                    COALESCE(llm_responses_json, '[]'), '$[#]', ?
                ) WHERE task_id = ?
                """,
                (response, task_id),
            )
            db.commit()

    def record_execution_step(self, task_id: str, step: dict[str, Any]) -> None:
        """Record an execution step (tool call, file operation, etc.)."""
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE task_logs SET execution_order_json = json_insert(
                    COALESCE(execution_order_json, '[]'), '$[#]', json(?)
                ) WHERE task_id = ?
                """,
                (json.dumps(step), task_id),
            )
            db.commit()

    def finalize(self, task_id: str, output: dict[str, Any]) -> None:
        """Finalize the task recording with output."""
        output_json = json.dumps(output)
        output_hash = hashlib.sha256(output_json.encode()).hexdigest()
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                """
                UPDATE task_logs SET output_json = ?, output_hash = ?
                WHERE task_id = ?
                """,
                (output_json, output_hash, task_id),
            )
            db.commit()

    def get_log(self, task_id: str) -> dict[str, Any] | None:
        """Retrieve a task log by ID."""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            row = db.execute(
                "SELECT * FROM task_logs WHERE task_id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            return dict(row)
