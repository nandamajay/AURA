-- Evidence & traceability
CREATE TABLE IF NOT EXISTS evidence_links (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    patch_id TEXT REFERENCES patches(id) ON DELETE CASCADE,
    rule_id TEXT REFERENCES migration_rules(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL
        CHECK (evidence_type IN ('reference','justification','warning','correction')),
    source_ref TEXT NOT NULL,            -- git commit hash or URL
    source_file TEXT,                    -- file path in kernel tree
    source_lines TEXT,                   -- line range "120-145"
    source_excerpt TEXT,                 -- relevant code excerpt
    confidence REAL NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_evidence_patch ON evidence_links(patch_id);
CREATE INDEX IF NOT EXISTS idx_evidence_rule ON evidence_links(rule_id);
CREATE INDEX IF NOT EXISTS idx_evidence_type ON evidence_links(evidence_type);
