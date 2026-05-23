-- Engineering source intake + immutable provenance runtime schema.
-- Converts source lineage from documentation-only to executable runtime state.

CREATE TABLE IF NOT EXISTS source_intakes (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    downstream_repo_url TEXT NOT NULL,
    downstream_ref_kind TEXT NOT NULL
        CHECK (downstream_ref_kind IN ('branch','tag','commit')),
    downstream_ref TEXT NOT NULL,
    bsp_lineage TEXT NOT NULL DEFAULT '',
    commit_anchors_json TEXT NOT NULL DEFAULT '[]',
    subsystem_name TEXT NOT NULL,
    subsystem_owner TEXT NOT NULL,
    upstream_repo_url TEXT NOT NULL,
    target_kernel TEXT NOT NULL DEFAULT 'linux',
    target_kernel_version TEXT NOT NULL,
    maintainer_refs_json TEXT NOT NULL DEFAULT '[]',
    patchset_lineage_json TEXT NOT NULL DEFAULT '[]',
    registered_by TEXT NOT NULL,
    registered_at INTEGER NOT NULL DEFAULT (unixepoch()),
    canonical_json TEXT NOT NULL,
    canonical_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_source_intakes_subsystem ON source_intakes(subsystem_name);
CREATE INDEX IF NOT EXISTS idx_source_intakes_registered_at ON source_intakes(registered_at);

CREATE TABLE IF NOT EXISTS source_intake_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intake_id TEXT NOT NULL REFERENCES source_intakes(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'registered',
            'validated',
            'classified',
            'approval_requested',
            'approved',
            'rejected',
            'override',
            'snapshot_created',
            'lineage_recorded',
            'retry_recorded',
            'rebase_recorded'
        )),
    event_payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    event_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_intake_events_intake ON source_intake_events(intake_id, id);

CREATE TABLE IF NOT EXISTS source_replay_snapshots (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    intake_id TEXT NOT NULL REFERENCES source_intakes(id) ON DELETE RESTRICT,
    replay_identifier TEXT NOT NULL UNIQUE,
    snapshot_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_source_replay_snapshots_intake ON source_replay_snapshots(intake_id, created_at);

CREATE TABLE IF NOT EXISTS source_lineage_entries (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    intake_id TEXT NOT NULL REFERENCES source_intakes(id) ON DELETE RESTRICT,
    lineage_stage TEXT NOT NULL
        CHECK (lineage_stage IN (
            'downstream_intake',
            'patch_transform',
            'upstream_prep',
            'validation',
            'approval',
            'replay_evidence',
            'retry',
            'rebase'
        )),
    parent_lineage_hash TEXT,
    lineage_payload TEXT NOT NULL DEFAULT '{}',
    lineage_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    UNIQUE (intake_id, lineage_hash)
);

CREATE INDEX IF NOT EXISTS idx_source_lineage_entries_intake ON source_lineage_entries(intake_id, created_at);

CREATE TRIGGER IF NOT EXISTS source_intakes_no_update
BEFORE UPDATE ON source_intakes
BEGIN
    SELECT RAISE(ABORT, 'source_intakes are immutable: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_intakes_no_delete
BEFORE DELETE ON source_intakes
BEGIN
    SELECT RAISE(ABORT, 'source_intakes are immutable: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_intake_events_no_update
BEFORE UPDATE ON source_intake_events
BEGIN
    SELECT RAISE(ABORT, 'source_intake_events are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_intake_events_no_delete
BEFORE DELETE ON source_intake_events
BEGIN
    SELECT RAISE(ABORT, 'source_intake_events are append-only: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_replay_snapshots_no_update
BEFORE UPDATE ON source_replay_snapshots
BEGIN
    SELECT RAISE(ABORT, 'source_replay_snapshots are immutable: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_replay_snapshots_no_delete
BEFORE DELETE ON source_replay_snapshots
BEGIN
    SELECT RAISE(ABORT, 'source_replay_snapshots are immutable: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_lineage_entries_no_update
BEFORE UPDATE ON source_lineage_entries
BEGIN
    SELECT RAISE(ABORT, 'source_lineage_entries are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS source_lineage_entries_no_delete
BEFORE DELETE ON source_lineage_entries
BEGIN
    SELECT RAISE(ABORT, 'source_lineage_entries are append-only: deletes forbidden');
END;
