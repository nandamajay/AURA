-- Learning events (4-tier learning system)
CREATE TABLE IF NOT EXISTS learning_events (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tier INTEGER NOT NULL
        CHECK (tier IN (1,2,3,4)),
    tier_name TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('discovered','validated','invalidated','refined')),
    pattern_description TEXT NOT NULL,
    source_refs TEXT DEFAULT '[]',
    confidence_before REAL,
    confidence_after REAL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_learning_tier ON learning_events(tier, created_at);
