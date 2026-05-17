-- Patch lifecycle
CREATE TABLE IF NOT EXISTS patches (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subsystem_id TEXT REFERENCES subsystems(id),
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN (
            'draft','migrating','validating','simulating',
            'reviewing','approved','rejected','upstreamed'
        )),
    title TEXT,
    description TEXT,
    confidence_score REAL,
    generated_by TEXT,                   -- agent type
    approved_by TEXT REFERENCES users(id),
    diff_path TEXT,                      -- path to diff file on disk
    cover_letter_path TEXT,
    changelog_path TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_patches_status ON patches(status);
CREATE INDEX IF NOT EXISTS idx_patches_subsystem ON patches(subsystem_id);
CREATE INDEX IF NOT EXISTS idx_patches_created ON patches(created_at);
