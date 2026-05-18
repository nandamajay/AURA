"""TaskRecorder — records all inputs + LLM responses for deterministic replay."""

import hashlib
import json
import sqlite3
import time
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
            db.execute(
                """
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
                    recording_state TEXT NOT NULL DEFAULT 'mutable'
                        CHECK (recording_state IN ('mutable','finalized')),
                    revision INTEGER NOT NULL DEFAULT 0,
                    finalized_at INTEGER,
                    snapshot_json TEXT,
                    snapshot_hash TEXT,
                    created_at INTEGER NOT NULL DEFAULT (unixepoch())
                )
                """
            )
            db.commit()
            self._ensure_columns(db)

    def _ensure_columns(self, db: sqlite3.Connection) -> None:
        """Ensure replay-boundary columns exist for pre-migration databases."""
        rows = db.execute("PRAGMA table_info(task_logs)").fetchall()
        columns = {str(row[1]) for row in rows}
        additions: list[tuple[str, str]] = [
            (
                "recording_state",
                "TEXT NOT NULL DEFAULT 'mutable' CHECK (recording_state IN ('mutable','finalized'))",
            ),
            ("revision", "INTEGER NOT NULL DEFAULT 0"),
            ("finalized_at", "INTEGER"),
            ("snapshot_json", "TEXT"),
            ("snapshot_hash", "TEXT"),
        ]
        for name, definition in additions:
            if name in columns:
                continue
            db.execute(f"ALTER TABLE task_logs ADD COLUMN {name} {definition}")
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
                INSERT INTO task_logs
                (task_id, agent_type, seed, model_version, rules_path, input_json,
                 llm_prompts_json, llm_responses_json, execution_order_json,
                 output_json, output_hash, recording_state, revision,
                 finalized_at, snapshot_json, snapshot_hash)
                VALUES (?, ?, ?, ?, ?, ?, '[]', '[]', '[]', NULL, NULL, 'mutable', 0, NULL, NULL, NULL)
                ON CONFLICT(task_id) DO UPDATE SET
                    agent_type = excluded.agent_type,
                    seed = excluded.seed,
                    model_version = excluded.model_version,
                    rules_path = excluded.rules_path,
                    input_json = excluded.input_json,
                    llm_prompts_json = '[]',
                    llm_responses_json = '[]',
                    execution_order_json = '[]',
                    output_json = NULL,
                    output_hash = NULL,
                    recording_state = 'mutable',
                    revision = 0,
                    finalized_at = NULL,
                    snapshot_json = NULL,
                    snapshot_hash = NULL
                """,
                (
                    task_id,
                    agent_type,
                    seed,
                    model_version,
                    rules_path,
                    json.dumps(input_data, separators=(",", ":")),
                ),
            )
            db.commit()

    def record_prompt(self, task_id: str, role: str, content: str) -> bool:
        """Record an LLM prompt."""
        prompt = {"role": role, "content": content}
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                UPDATE task_logs SET llm_prompts_json = json_insert(
                    COALESCE(llm_prompts_json, '[]'), '$[#]', json(?)
                ), revision = revision + 1
                WHERE task_id = ? AND recording_state = 'mutable'
                """,
                (json.dumps(prompt, separators=(",", ":")), task_id),
            )
            db.commit()
            return cursor.rowcount == 1

    def record_response(self, task_id: str, response: str) -> bool:
        """Record an LLM response."""
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                UPDATE task_logs SET llm_responses_json = json_insert(
                    COALESCE(llm_responses_json, '[]'), '$[#]', ?
                ), revision = revision + 1
                WHERE task_id = ? AND recording_state = 'mutable'
                """,
                (response, task_id),
            )
            db.commit()
            return cursor.rowcount == 1

    def record_execution_step(self, task_id: str, step: dict[str, Any]) -> bool:
        """Record an execution step (tool call, file operation, etc.)."""
        with sqlite3.connect(self.db_path) as db:
            cursor = db.execute(
                """
                UPDATE task_logs SET execution_order_json = json_insert(
                    COALESCE(execution_order_json, '[]'), '$[#]', json(?)
                ), revision = revision + 1
                WHERE task_id = ? AND recording_state = 'mutable'
                """,
                (json.dumps(step, separators=(",", ":")), task_id),
            )
            db.commit()
            return cursor.rowcount == 1

    def _safe_list(self, raw: str | None) -> list[Any]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []

    def _safe_dict(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def finalize(self, task_id: str, output: dict[str, Any]) -> bool:
        """Finalize the task recording with immutable replay snapshot."""
        with sqlite3.connect(self.db_path) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT task_id, agent_type, seed, model_version, rules_path, input_json,
                       llm_prompts_json, llm_responses_json, execution_order_json,
                       recording_state
                FROM task_logs
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                db.rollback()
                return False

            if str(row["recording_state"] or "") == "finalized":
                db.commit()
                return True

            prompts = self._safe_list(row["llm_prompts_json"])
            responses = self._safe_list(row["llm_responses_json"])
            execution = self._safe_list(row["execution_order_json"])
            input_data = self._safe_dict(row["input_json"])
            normalized_output = output if isinstance(output, dict) else {"result": output}
            output_json = json.dumps(normalized_output, separators=(",", ":"), sort_keys=True)
            output_hash = hashlib.sha256(output_json.encode()).hexdigest()
            finalized_at = int(time.time())

            snapshot = {
                "task_id": task_id,
                "agent_type": row["agent_type"],
                "seed": int(row["seed"]),
                "model_version": row["model_version"],
                "rules_path": row["rules_path"],
                "input": input_data,
                "prompts": prompts,
                "responses": responses,
                "execution": execution,
                "output": normalized_output,
                "output_hash": output_hash,
                "finalized_at": finalized_at,
            }
            snapshot_json = json.dumps(snapshot, separators=(",", ":"), sort_keys=True)
            snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()

            cursor = db.execute(
                """
                UPDATE task_logs
                SET output_json = ?,
                    output_hash = ?,
                    recording_state = 'finalized',
                    revision = revision + 1,
                    finalized_at = ?,
                    snapshot_json = ?,
                    snapshot_hash = ?
                WHERE task_id = ? AND recording_state = 'mutable'
                """,
                (output_json, output_hash, finalized_at, snapshot_json, snapshot_hash, task_id),
            )
            if cursor.rowcount != 1:
                db.rollback()
                return False
            db.commit()
            return True

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
