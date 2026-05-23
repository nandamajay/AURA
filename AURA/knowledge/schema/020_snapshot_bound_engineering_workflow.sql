-- Snapshot-bound engineering workflow runtime.
-- Deterministic, provenance-bound, replay-visible, audit-compatible execution state.

CREATE TABLE IF NOT EXISTS engineering_snapshots (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    intake_id TEXT NOT NULL REFERENCES source_intakes(id) ON DELETE RESTRICT,
    source_snapshot_id TEXT NOT NULL REFERENCES source_replay_snapshots(id) ON DELETE RESTRICT,
    downstream_repo_url TEXT NOT NULL,
    downstream_ref_kind TEXT NOT NULL CHECK (downstream_ref_kind IN ('branch','tag','commit')),
    downstream_ref TEXT NOT NULL,
    downstream_commit_sha TEXT NOT NULL,
    subsystem_name TEXT NOT NULL,
    upstream_target_kernel_version TEXT NOT NULL,
    upstream_target_branch TEXT NOT NULL,
    maintainer_context_json TEXT NOT NULL DEFAULT '[]',
    validation_profile_version TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    validation_tool_versions_json TEXT NOT NULL DEFAULT '{}',
    replay_runtime_version TEXT NOT NULL,
    governance_policy_version TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    snapshot_json TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_engineering_snapshots_intake ON engineering_snapshots(intake_id, created_at);

CREATE TABLE IF NOT EXISTS engineering_workflows (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    intake_id TEXT NOT NULL REFERENCES source_intakes(id) ON DELETE RESTRICT,
    snapshot_id TEXT NOT NULL REFERENCES engineering_snapshots(id) ON DELETE RESTRICT,
    provenance_lineage_hash TEXT NOT NULL,
    task_id TEXT,
    state TEXT NOT NULL
        CHECK (state IN (
            'source_intake',
            'snapshot_frozen',
            'task_created',
            'patch_analysis',
            'transformation_proposal',
            'validation_running',
            'governance_review',
            'replay_persisted',
            'approved',
            'rejected',
            'lineage_finalized'
        )),
    validation_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (validation_status IN ('pending', 'passed', 'failed')),
    replay_trust_valid INTEGER NOT NULL DEFAULT 1 CHECK (replay_trust_valid IN (0, 1)),
    governance_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (governance_state IN ('pending', 'approved', 'rejected')),
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_engineering_workflows_state ON engineering_workflows(state, updated_at);
CREATE INDEX IF NOT EXISTS idx_engineering_workflows_snapshot ON engineering_workflows(snapshot_id);

CREATE TABLE IF NOT EXISTS engineering_workflow_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES engineering_workflows(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'state_transition',
            'task_bound',
            'validation_recorded',
            'governance_requested',
            'governance_decided',
            'replay_verified',
            'reconstruction_failed',
            'lineage_finalized',
            'retry_recorded',
            'evidence_linked'
        )),
    from_state TEXT,
    to_state TEXT,
    event_payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    event_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_engineering_workflow_events_workflow ON engineering_workflow_events(workflow_id, id);

CREATE TABLE IF NOT EXISTS engineering_validation_runs (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    workflow_id TEXT NOT NULL REFERENCES engineering_workflows(id) ON DELETE RESTRICT,
    snapshot_id TEXT NOT NULL REFERENCES engineering_snapshots(id) ON DELETE RESTRICT,
    run_sequence INTEGER NOT NULL,
    tool_name TEXT NOT NULL
        CHECK (tool_name IN ('checkpatch', 'sparse', 'clang_build', 'forbidden_path', 'lineage_integrity')),
    tool_version TEXT NOT NULL,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    findings_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL,
    executed_at INTEGER NOT NULL DEFAULT (unixepoch()),
    output_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE (workflow_id, run_sequence, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_engineering_validation_runs_workflow ON engineering_validation_runs(workflow_id, run_sequence, tool_name);

CREATE TABLE IF NOT EXISTS engineering_governance_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES engineering_workflows(id) ON DELETE RESTRICT,
    operation TEXT NOT NULL
        CHECK (operation IN ('transformation_proposal', 'lineage_finalization')),
    status TEXT NOT NULL CHECK (status IN ('requested', 'approved', 'rejected')),
    reason TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL,
    decided_by TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_engineering_governance_actions_workflow ON engineering_governance_actions(workflow_id, operation, id);

CREATE TABLE IF NOT EXISTS engineering_evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL REFERENCES engineering_workflows(id) ON DELETE RESTRICT,
    evidence_type TEXT NOT NULL,
    evidence_ref TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_engineering_evidence_links_workflow ON engineering_evidence_links(workflow_id, id);

CREATE TRIGGER IF NOT EXISTS engineering_snapshots_no_update
BEFORE UPDATE ON engineering_snapshots
BEGIN
    SELECT RAISE(ABORT, 'engineering_snapshots are immutable: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_snapshots_no_delete
BEFORE DELETE ON engineering_snapshots
BEGIN
    SELECT RAISE(ABORT, 'engineering_snapshots are immutable: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_workflow_events_no_update
BEFORE UPDATE ON engineering_workflow_events
BEGIN
    SELECT RAISE(ABORT, 'engineering_workflow_events are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_workflow_events_no_delete
BEFORE DELETE ON engineering_workflow_events
BEGIN
    SELECT RAISE(ABORT, 'engineering_workflow_events are append-only: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_validation_runs_no_update
BEFORE UPDATE ON engineering_validation_runs
BEGIN
    SELECT RAISE(ABORT, 'engineering_validation_runs are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_validation_runs_no_delete
BEFORE DELETE ON engineering_validation_runs
BEGIN
    SELECT RAISE(ABORT, 'engineering_validation_runs are append-only: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_governance_actions_no_update
BEFORE UPDATE ON engineering_governance_actions
BEGIN
    SELECT RAISE(ABORT, 'engineering_governance_actions are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_governance_actions_no_delete
BEFORE DELETE ON engineering_governance_actions
BEGIN
    SELECT RAISE(ABORT, 'engineering_governance_actions are append-only: deletes forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_evidence_links_no_update
BEFORE UPDATE ON engineering_evidence_links
BEGIN
    SELECT RAISE(ABORT, 'engineering_evidence_links are append-only: updates forbidden');
END;

CREATE TRIGGER IF NOT EXISTS engineering_evidence_links_no_delete
BEFORE DELETE ON engineering_evidence_links
BEGIN
    SELECT RAISE(ABORT, 'engineering_evidence_links are append-only: deletes forbidden');
END;
