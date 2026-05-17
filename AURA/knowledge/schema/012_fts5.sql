-- FTS5 full-text search over migration rules
CREATE VIRTUAL TABLE IF NOT EXISTS rules_fts USING fts5(
    downstream_pattern,
    upstream_equivalent,
    description,
    content = 'migration_rules',
    content_rowid = 'rowid'
);

-- Auto-sync triggers
DROP TRIGGER IF EXISTS rules_fts_insert;
CREATE TRIGGER rules_fts_insert AFTER INSERT ON migration_rules
BEGIN
    INSERT INTO rules_fts(rowid, downstream_pattern, upstream_equivalent, description)
    VALUES (NEW.rowid, NEW.downstream_pattern, NEW.upstream_equivalent, NEW.description);
END;

DROP TRIGGER IF EXISTS rules_fts_delete;
CREATE TRIGGER rules_fts_delete AFTER DELETE ON migration_rules
BEGIN
    INSERT INTO rules_fts(rules_fts, rowid, downstream_pattern, upstream_equivalent, description)
    VALUES ('delete', OLD.rowid, OLD.downstream_pattern, OLD.upstream_equivalent, OLD.description);
END;

DROP TRIGGER IF EXISTS rules_fts_update;
CREATE TRIGGER rules_fts_update AFTER UPDATE ON migration_rules
BEGIN
    INSERT INTO rules_fts(rules_fts, rowid, downstream_pattern, upstream_equivalent, description)
    VALUES ('delete', OLD.rowid, OLD.downstream_pattern, OLD.upstream_equivalent, OLD.description);
    INSERT INTO rules_fts(rowid, downstream_pattern, upstream_equivalent, description)
    VALUES (NEW.rowid, NEW.downstream_pattern, NEW.upstream_equivalent, NEW.description);
END;
