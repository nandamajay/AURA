-- Persistent task queue state for S1 orchestrator.
-- Supports restart recovery and 3-tier scheduling bookkeeping.

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_type TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN (
            'created','queued','started','running','completed','failed','cancelled','timed_out'
        )),
    priority TEXT NOT NULL
        CHECK (priority IN ('P0', 'P1', 'P2')),
    input_data TEXT NOT NULL DEFAULT '{}',
    result_data TEXT NOT NULL DEFAULT '{}',
    description TEXT DEFAULT '',
    requested_by TEXT DEFAULT '',
    parent_task_id TEXT DEFAULT '',
    current_attempt INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    agent_pid INTEGER,
    started_at INTEGER,
    completed_at INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_agent_type ON tasks(agent_type);
