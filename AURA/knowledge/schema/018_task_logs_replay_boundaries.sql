-- Enforce replay snapshot boundaries: mutable vs finalized task logs.
-- Finalized snapshots are immutable replay inputs.

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS task_logs_v2 (
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
);

INSERT INTO task_logs_v2 (
    task_id,
    agent_type,
    seed,
    model_version,
    rules_path,
    input_json,
    llm_prompts_json,
    llm_responses_json,
    execution_order_json,
    output_json,
    output_hash,
    recording_state,
    revision,
    finalized_at,
    snapshot_json,
    snapshot_hash,
    created_at
)
SELECT
    task_id,
    agent_type,
    seed,
    model_version,
    rules_path,
    input_json,
    COALESCE(llm_prompts_json, '[]'),
    COALESCE(llm_responses_json, '[]'),
    COALESCE(execution_order_json, '[]'),
    output_json,
    output_hash,
    CASE
        WHEN output_json IS NOT NULL AND output_hash IS NOT NULL THEN 'finalized'
        ELSE 'mutable'
    END AS recording_state,
    0 AS revision,
    CASE
        WHEN output_json IS NOT NULL AND output_hash IS NOT NULL THEN created_at
        ELSE NULL
    END AS finalized_at,
    NULL AS snapshot_json,
    NULL AS snapshot_hash,
    created_at
FROM task_logs;

DROP TABLE task_logs;
ALTER TABLE task_logs_v2 RENAME TO task_logs;

CREATE INDEX IF NOT EXISTS idx_task_logs_agent ON task_logs(agent_type);
CREATE INDEX IF NOT EXISTS idx_task_logs_created ON task_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_task_logs_state ON task_logs(recording_state);

PRAGMA foreign_keys = ON;
