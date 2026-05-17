-- Deterministic replay logs
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
);

CREATE INDEX IF NOT EXISTS idx_task_logs_agent ON task_logs(agent_type);
CREATE INDEX IF NOT EXISTS idx_task_logs_created ON task_logs(created_at);
