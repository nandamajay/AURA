-- Core knowledge: learned migration rules
CREATE TABLE IF NOT EXISTS migration_rules (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    subsystem_id TEXT REFERENCES subsystems(id) ON DELETE CASCADE,
    category TEXT NOT NULL
        CHECK (category IN ('api_mapping','macro','pattern','style','philosophy')),
    downstream_pattern TEXT NOT NULL,
    upstream_equivalent TEXT,
    description TEXT,
    confidence REAL NOT NULL DEFAULT 0.5
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    source_refs TEXT DEFAULT '[]',       -- JSON array of {commit, file, line}
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    last_applied_at INTEGER,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rules_subsystem ON migration_rules(subsystem_id);
CREATE INDEX IF NOT EXISTS idx_rules_category ON migration_rules(category);
CREATE INDEX IF NOT EXISTS idx_rules_confidence ON migration_rules(confidence);
CREATE INDEX IF NOT EXISTS idx_rules_pattern ON migration_rules(downstream_pattern);
