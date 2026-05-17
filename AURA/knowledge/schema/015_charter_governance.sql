-- Human Authority & Safe Autonomy Charter — pre-seeded governance rules
-- These rules are the foundational constraints that AURA cannot violate.

-- ── Charter Configuration ──
CREATE TABLE IF NOT EXISTS charter_config (
    charter_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    version TEXT NOT NULL DEFAULT '1.0.0',
    adopted_at INTEGER NOT NULL DEFAULT (unixepoch()),
    confidence_threshold REAL NOT NULL DEFAULT 0.7,
    auto_rollback_on_failure INTEGER NOT NULL DEFAULT 1,
    preserve_state_on_uncertainty INTEGER NOT NULL DEFAULT 1,
    human_governance_final INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Seed the charter config
INSERT OR IGNORE INTO charter_config (charter_id, version, confidence_threshold)
VALUES ('charter-v1', '1.0.0', 0.7);

-- ── Charter Violations Log ──
CREATE TABLE IF NOT EXISTS charter_violations (
    violation_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    timestamp INTEGER NOT NULL DEFAULT (unixepoch()),
    principle TEXT NOT NULL,     -- bounded, observable, explainable, replayable, interruptible, reversible
    rule TEXT NOT NULL,          -- which specific rule
    action TEXT NOT NULL,        -- what action was attempted
    actor TEXT NOT NULL,         -- who/what attempted it
    details TEXT DEFAULT '{}',   -- JSON
    blocked INTEGER NOT NULL DEFAULT 1,
    severity TEXT NOT NULL DEFAULT 'high'
        CHECK (severity IN ('critical','high','medium','low')),
    resolution TEXT,             -- how it was resolved
    resolved_at INTEGER,
    resolved_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_violations_timestamp ON charter_violations(timestamp);
CREATE INDEX IF NOT EXISTS idx_violations_severity ON charter_violations(severity);
CREATE INDEX IF NOT EXISTS idx_violations_actor ON charter_violations(actor);

-- ── Approval Requests ──
CREATE TABLE IF NOT EXISTS approval_requests (
    request_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    action_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    details TEXT DEFAULT '{}',   -- JSON
    required_role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','rejected','expired')),
    approved_by TEXT,
    approved_at INTEGER,
    rejection_reason TEXT,
    audit_trail TEXT DEFAULT '[]',  -- JSON array
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    expires_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_approvals_status ON approval_requests(status);
CREATE INDEX IF NOT EXISTS idx_approvals_actor ON approval_requests(actor);
CREATE INDEX IF NOT EXISTS idx_approvals_expires ON approval_requests(expires_at);

-- ── Explainability Traces ──
CREATE TABLE IF NOT EXISTS explainability_traces (
    trace_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    started_at INTEGER NOT NULL,
    completed_at INTEGER,
    final_status TEXT,
    reasoning_trace TEXT DEFAULT '{}',
    execution_trace TEXT DEFAULT '{}',
    event_lineage TEXT DEFAULT '{}',
    dependency_lineage TEXT DEFAULT '{}',
    replay_lineage TEXT DEFAULT '{}',
    rollback_lineage TEXT DEFAULT '{}',
    completeness_score REAL,
    is_complete INTEGER DEFAULT 0,
    missing_lineage TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_traces_action ON explainability_traces(action);
CREATE INDEX IF NOT EXISTS idx_traces_actor ON explainability_traces(actor);

-- ── Fail-Safe Incidents ──
CREATE TABLE IF NOT EXISTS failsafe_incidents (
    incident_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    incident_type TEXT NOT NULL,  -- destructive_action_blocked, low_confidence_degraded
    action TEXT NOT NULL,
    confidence REAL,
    threshold REAL,
    is_destructive INTEGER DEFAULT 0,
    reason TEXT NOT NULL,
    proceeded INTEGER DEFAULT 0,
    degraded INTEGER DEFAULT 0,
    human_review_required INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_failsafe_type ON failsafe_incidents(incident_type);
CREATE INDEX IF NOT EXISTS idx_failsafe_action ON failsafe_incidents(action);

-- ── Self-Modification Detections ──
CREATE TABLE IF NOT EXISTS modification_detections (
    detection_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    timestamp INTEGER NOT NULL DEFAULT (unixepoch()),
    rule_violated TEXT NOT NULL,  -- which SelfModificationRule
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    actor TEXT NOT NULL,
    keywords_matched TEXT DEFAULT '[]',
    explicitly_approved INTEGER DEFAULT 0,
    blocked INTEGER DEFAULT 1,
    severity TEXT NOT NULL DEFAULT 'critical'
);

CREATE INDEX IF NOT EXISTS idx_moddetect_rule ON modification_detections(rule_violated);
CREATE INDEX IF NOT EXISTS idx_moddetect_actor ON modification_detections(actor);

-- ── Integrity Registry ──
CREATE TABLE IF NOT EXISTS integrity_registry (
    path TEXT PRIMARY KEY,
    known_hash TEXT NOT NULL,
    registered_at INTEGER NOT NULL DEFAULT (unixepoch()),
    last_verified_at INTEGER,
    current_hash TEXT,
    is_valid INTEGER
);

-- ── Pre-seeded Engineering Decisions: Charter-specific ──
INSERT INTO engineering_decisions
(decision_id, title, subsystem, decision_made, reasoning, context,
 constraints, alternatives_considered, rejected_alternatives,
 operational_impact, scalability_impact, determinism_impact,
 observability_impact, security_impact,
 decided_by, reversible, reversal_conditions)
VALUES
('dec-charter-001', 'Human Authority as Final Governance', 'S6_Governance',
 'Human operators have final authority over all autonomous actions',
 'Autonomous systems must augment, not replace, engineering authority. Bounded autonomy with human override prevents runaway automation.',
 'Third architectural injection. Core governance philosophy for the entire platform.',
 '["human oversight", "bounded autonomy", "accountability"]' ,
 '[{"option":"Full autonomy with human notification only","reason_rejected":"Unacceptable risk for production engineering platform. Violates safety principles."},{"option":"Human-in-the-loop for every action","reason_rejected":"Would negate efficiency benefits of automation. Creates bottlenecks."}]',
 '["Full autonomy (unacceptable risk)", "Human-in-loop-every-action (inefficient)"]',
 'All high-risk actions require explicit approval. 8 manual control endpoints always available. Override capability for emergencies.',
 'Approval system scales with team size. No single point of failure for governance.',
 'Deterministic: same charter rules applied consistently. Reproducible: all decisions auditable.',
 'Every charter enforcement event is observable. Violations logged in real-time. Explainability traces mandatory.',
 'Prevents unauthorized autonomous actions. Self-modification detection. Integrity monitoring.',
 'system', 0,
 'Not reversible. Human authority is a foundational invariant of the platform.'
),
('dec-charter-002', 'Confidence-Threshold Fail-Safe', 'S6_Governance',
 'Actions below confidence threshold trigger human review; destructive actions below threshold are always blocked',
 'When AI uncertainty is high, the safe choice is to stop and ask. Destructive actions carry irreversible consequences and must never proceed on low confidence.',
 'Fail-safe principle from Human Authority Charter. Prevents destructive actions from executing autonomously when uncertain.',
 '["destructive actions", "confidence threshold", "human review"]' ,
 '[{"option":"Allow destructive actions with logging only","reason_rejected":"Irreversible data loss possible. Logging is not prevention."},{"option":"Use Bayesian confidence with dynamic thresholds","reason_rejected":"Over-engineered for P2. Simple threshold is auditable and predictable."}]',
 '["Logging-only (insufficient)", "Dynamic thresholds (over-engineered)"]',
 'Destructive actions blocked at 0.7 confidence threshold. Human review requested automatically. State preserved.',
 'Threshold can be adjusted per-deployment. Per-action thresholds at P3.',
 'Fixed threshold is deterministic. Same confidence → same outcome every time.',
 'All fail-safe activations logged. Incident table tracks patterns. Review report available via API.',
 'Prevents accidental data destruction. Blocks actions when AI is uncertain.',
 'system', 1,
 'Threshold can be raised (more restrictive) or lowered (more permissive) by admin'
),
('dec-charter-003', 'Six Self-Modification Prohibitions', 'S6_Governance',
 'Platform cannot silently modify governance, replay, architecture, audit, validation, or security systems',
 'An autonomous system that can silently change its own rules is fundamentally unsafe. These 6 prohibitions create immutable guardrails.',
 'Charter injection. Prevents the platform from becoming an uncontrollable autonomous entity.',
 '["safety", "immutability", "audit integrity"]' ,
 '[{"option":"Allow self-modification with audit logging","reason_rejected":"Audit log can be tampered with. Prevention is stronger than detection."},{"option":"Use formal verification for self-modification","reason_rejected":"Over-engineered. Static detection + human approval is sufficient for P2."}]',
 '["Audit-only (insufficient)", "Formal verification (over-engineered)"]',
 'GovernanceGuard checks every action against 6 prohibition patterns. ModificationDetector verifies file integrity.',
 'Pattern matching is O(n) in keywords. Negligible performance impact.',
 'Deterministic: same action → same prohibition check → same outcome.',
 'Every detection logged. Integrity registry tracks known-good hashes. Dashboard shows violation count.',
 'Critical safety boundary. Prevents autonomous bypass of security controls.',
 'system', 0,
 'Not reversible. These prohibitions are platform invariants.'
);

-- ── Pre-seeded Known Risks: Charter-specific ──
INSERT INTO known_risks
(risk_id, title, description, probability, impact,
 risk_score, affected_subsystems, affected_users,
 mitigation_plan, contingency_plan, residual_risk,
 status, severity, owner)
VALUES
('risk-charter-001', 'Autonomous bypass of human approval',
 'A bug or adversarial input could cause the platform to execute a high-risk action without human approval.',
 'low', 'critical', 'medium',
 '["S6_Governance","S1_Orchestrator"]',
 'All users, all data',
 'GovernanceGuard with mandatory high-risk classification. ApprovalGate requires human explicit approval. Self-modification detection.',
 'Emergency shutdown via /charter/intervene. Audit review of all actions in incident window.',
 'Low: Multiple independent enforcement layers.',
 'open', 'critical', 'system'
),
('risk-charter-002', 'Over-confident autonomous action',
 'The platform may report high confidence for an action that is actually wrong, bypassing fail-safe.',
 'medium', 'high', 'high',
 '["S6_Governance","S2_AgentRuntime"]',
 'Task requesters',
 'Fail-safe with conservative threshold (0.7). Degraded mode for uncertain actions. Human review requests.',
 'Manual rollback via /charter/rollback. State preserved before uncertain actions.',
 'Medium: Threshold is conservative. Multiple checks before destructive actions.',
 'open', 'high', 'system'
),
('risk-charter-003', 'Silent integrity violation undetected',
 'A file or rule could be modified without the SelfModificationDetector noticing.',
 'low', 'critical', 'medium',
 '["S6_Governance","S3_KnowledgeSystem"]',
 'All users',
 'Hash-based integrity monitoring for all critical files. Periodic verification.',
 'Restore from backup. Re-register known-good hashes. Investigate how bypass occurred.',
 'Low: SHA-256 collision resistance. Multiple files monitored.',
 'open', 'medium', 'system'
),
('risk-charter-004', 'Charter configuration tampering',
 'The charter_config table could be modified to weaken governance (e.g., lower confidence threshold).',
 'low', 'critical', 'medium',
 '["S6_Governance"]',
 'All users',
 'Charter config changes are high-risk actions requiring admin approval. Audit trigger on any update.',
 'Restore charter_config from seed SQL. Investigate who/why.',
 'Low: Admin approval required. All changes auditable.',
 'open', 'medium', 'system'
);
