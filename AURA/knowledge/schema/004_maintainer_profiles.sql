-- Maintainer intelligence
CREATE TABLE IF NOT EXISTS maintainer_profiles (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT NOT NULL,
    email TEXT,
    subsystem_id TEXT REFERENCES subsystems(id),
    acceptance_rate REAL,
    review_count INTEGER DEFAULT 0,
    common_nak_reasons TEXT DEFAULT '[]',  -- JSON array
    preferred_patterns TEXT DEFAULT '[]',  -- JSON array
    personality_summary TEXT,              -- Text summary
    last_analyzed_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_maintainers_subsystem ON maintainer_profiles(subsystem_id);
