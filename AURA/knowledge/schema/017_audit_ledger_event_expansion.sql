-- Expand audit_ledger event_type constraint to include runtime lifecycle events
-- emitted by core EventBus persistence.

PRAGMA foreign_keys = OFF;

DROP TRIGGER IF EXISTS audit_no_update;
DROP TRIGGER IF EXISTS audit_no_delete;
DROP TRIGGER IF EXISTS audit_chain_hash;

CREATE TABLE IF NOT EXISTS audit_ledger_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL DEFAULT (unixepoch()),
    user_id TEXT REFERENCES users(id),
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN (
            'user.login','user.logout','user.created',
            'task.created','task.queued','task.started','task.progress','task.completed','task.failed','task.cancelled',
            'agent.registered','agent.spawned','agent.heartbeat','agent.completed','agent.failed','agent.timeout','agent.killed',
            'sim.started','sim.progress','sim.completed','sim.failed',
            'governance.approval_required','governance.approval_granted','governance.approval_rejected','governance.escalation_triggered',
            'llm.request','llm.response','llm.error','llm.cache_hit',
            'patch.created','patch.updated','patch.approved','patch.rejected',
            'approval.submitted','approval.granted','approval.rejected','approval.escalated',
            'service.started','service.stopped','system.bootstrap','system.circuit_breaker_state',
            'config.changed'
        )),
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    before_state TEXT,
    after_state TEXT,
    evidence_hash TEXT,
    chain_hash TEXT
);

INSERT INTO audit_ledger_v2 (
    id, timestamp, user_id, session_id, event_type, target_type, target_id, before_state, after_state, evidence_hash, chain_hash
)
SELECT
    id, timestamp, user_id, session_id, event_type, target_type, target_id, before_state, after_state, evidence_hash, chain_hash
FROM audit_ledger;

DROP TABLE audit_ledger;
ALTER TABLE audit_ledger_v2 RENAME TO audit_ledger;

CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_ledger(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_ledger(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_ledger(event_type);

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

CREATE TRIGGER audit_no_delete
BEFORE DELETE ON audit_ledger
BEGIN
    SELECT RAISE(ABORT, 'audit_ledger is append-only: deletes forbidden');
END;

CREATE TRIGGER audit_chain_hash
AFTER INSERT ON audit_ledger
BEGIN
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

PRAGMA foreign_keys = ON;
