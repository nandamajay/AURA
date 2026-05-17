-- 3-dimensional approval state
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT NOT NULL REFERENCES patches(id) ON DELETE CASCADE,
    dimension TEXT NOT NULL
        CHECK (dimension IN ('lifecycle','subsystem','quality')),
    stage TEXT NOT NULL,                 -- e.g. "migration", "validation"
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','in_progress','passed','failed','skipped')),
    assigned_to TEXT REFERENCES users(id),
    confidence_threshold REAL DEFAULT 0.7,
    actual_confidence REAL,
    reviewed_by TEXT REFERENCES users(id),
    reviewed_at INTEGER,
    comments TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_approvals_patch ON approvals(patch_id);
CREATE INDEX IF NOT EXISTS idx_approvals_status ON approvals(status);
CREATE INDEX IF NOT EXISTS idx_approvals_assigned ON approvals(assigned_to);
