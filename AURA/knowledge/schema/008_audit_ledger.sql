-- Audit ledger (append-only, tamper-evident)
CREATE TABLE IF NOT EXISTS audit_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL DEFAULT (unixepoch()),
    user_id TEXT REFERENCES users(id),
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'user.login','user.logout','user.created',
            'task.created','task.started','task.completed','task.failed',
            'agent.spawned','agent.completed','agent.failed','agent.timeout',
            'patch.created','patch.updated','patch.approved','patch.rejected',
            'approval.submitted','approval.granted','approval.rejected','approval.escalated',
            'config.changed','system.bootstrap'
        )),
    target_type TEXT NOT NULL,           -- patch, task, agent, user, config
    target_id TEXT NOT NULL,
    before_state TEXT,                   -- JSON snapshot
    after_state TEXT,                    -- JSON snapshot
    evidence_hash TEXT,                  -- SHA256 of evidence JSON
    chain_hash TEXT                      -- Hash chain for tamper evidence
);

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_ledger(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_ledger(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_ledger(event_type);

-- Append-only enforcement triggers
DROP TRIGGER IF EXISTS audit_no_update;
CREATE TRIGGER audit_no_update
BEFORE UPDATE ON audit_ledger
WHEN NOT (
    OLD.id = NEW.id
    AND OLD.chain_hash IS NULL
    AND NEW.chain_hash IS NOT NULL
    AND OLD.timestamp = NEW.timestamp
    AND COALESCE(OLD.user_id, '') = COALESCE(NEW.user_id, '')
    AND OLD.session_id = NEW.session_id
    AND OLD.event_type = NEW.event_type
    AND OLD.target_type = NEW.target_type
    AND OLD.target_id = NEW.target_id
    AND COALESCE(OLD.before_state, '') = COALESCE(NEW.before_state, '')
    AND COALESCE(OLD.after_state, '') = COALESCE(NEW.after_state, '')
    AND COALESCE(OLD.evidence_hash, '') = COALESCE(NEW.evidence_hash, '')
)
BEGIN
    SELECT RAISE(ABORT, 'audit_ledger is append-only: updates forbidden');
END;

DROP TRIGGER IF EXISTS audit_no_delete;
CREATE TRIGGER audit_no_delete
BEFORE DELETE ON audit_ledger
BEGIN
    SELECT RAISE(ABORT, 'audit_ledger is append-only: deletes forbidden');
END;

-- Chain hash trigger: auto-compute on insert
DROP TRIGGER IF EXISTS audit_chain_hash;
CREATE TRIGGER audit_chain_hash
AFTER INSERT ON audit_ledger
BEGIN
    -- Portable deterministic chain fingerprint (no SQLite hash extension required).
    UPDATE audit_ledger SET chain_hash = (
        SELECT substr(lower(hex(
            COALESCE(
                (SELECT chain_hash FROM audit_ledger WHERE id = NEW.id - 1),
                '0000000000000000000000000000000000000000000000000000000000000000'
            )
            || '|'
            || CAST(NEW.timestamp AS TEXT)
            || '|'
            || NEW.event_type
            || '|'
            || NEW.target_type
            || '|'
            || NEW.target_id
            || '|'
            || COALESCE(NEW.user_id, '')
        )), 1, 64)
    ) WHERE id = NEW.id;
END;
