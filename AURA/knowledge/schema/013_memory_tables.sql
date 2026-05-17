-- Engineering Memory System — 10 ledgers and registers
-- Append-only by design. No UPDATE/DELETE triggers.

-- ── 1. Engineering Decision Ledger ──
CREATE TABLE IF NOT EXISTS engineering_decisions (
    decision_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    decision_made TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    context TEXT,
    constraints TEXT DEFAULT '[]',             -- JSON array
    alternatives_considered TEXT DEFAULT '[]', -- JSON array
    rejected_alternatives TEXT DEFAULT '[]',   -- JSON array
    operational_impact TEXT,
    scalability_impact TEXT,
    determinism_impact TEXT,
    observability_impact TEXT,
    security_impact TEXT,
    cost_impact TEXT,
    decided_by TEXT REFERENCES users(id),
    approved_by TEXT REFERENCES users(id),
    related_decisions TEXT DEFAULT '[]',       -- JSON array of decision_ids
    reversible INTEGER NOT NULL DEFAULT 1,
    reversal_conditions TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch()),
    updated_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_decisions_subsystem ON engineering_decisions(subsystem);
CREATE INDEX IF NOT EXISTS idx_decisions_created ON engineering_decisions(created_at);

-- ── 2. Failure Investigation Ledger ──
CREATE TABLE IF NOT EXISTS failure_investigations (
    failure_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    description TEXT,
    root_cause TEXT,
    root_cause_category TEXT,
    impact_scope TEXT,
    impact_severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (impact_severity IN ('critical','high','medium','low','info')),
    affected_components TEXT DEFAULT '[]',     -- JSON array
    first_observed_at INTEGER,
    resolved_at INTEGER,
    detection_latency_ms INTEGER,
    recovery_method TEXT,
    prevention_strategy TEXT,
    replay_affected INTEGER NOT NULL DEFAULT 0,
    replay_recovery TEXT,
    approval_required_after_fix INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical','high','medium','low','info')),
    related_failures TEXT DEFAULT '[]',        -- JSON array
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_failures_status ON failure_investigations(status);
CREATE INDEX IF NOT EXISTS idx_failures_subsystem ON failure_investigations(subsystem);

-- ── 3. Replay Incident Ledger ──
CREATE TABLE IF NOT EXISTS replay_incidents (
    incident_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    description TEXT,
    expected_fidelity TEXT,
    actual_fidelity TEXT,
    divergence_cause TEXT,
    divergence_point TEXT,
    seed_used INTEGER NOT NULL,
    model_version_used TEXT,
    original_llm_calls INTEGER DEFAULT 0,
    replay_llm_calls INTEGER DEFAULT 0,
    mismatched_llm_responses INTEGER DEFAULT 0,
    original_output_hash TEXT,
    replay_output_hash TEXT,
    hash_match INTEGER DEFAULT 0,
    resolution TEXT,
    replay_recovered INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical','high','medium','low','info')),
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_replay_task ON replay_incidents(task_id);
CREATE INDEX IF NOT EXISTS idx_replay_status ON replay_incidents(status);

-- ── 4. Architecture Drift Ledger ──
CREATE TABLE IF NOT EXISTS architecture_drift (
    drift_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    intended_design TEXT NOT NULL,
    actual_implementation TEXT NOT NULL,
    drift_description TEXT NOT NULL,
    drift_type TEXT NOT NULL
        CHECK (drift_type IN ('intentional','accidental','necessary','technical_debt')),
    functional_impact TEXT,
    maintainability_impact TEXT,
    scalability_impact TEXT,
    compliance_impact TEXT,
    remediation_plan TEXT,
    remediation_priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (remediation_priority IN ('critical','high','medium','low','info')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    subsystem TEXT NOT NULL,
    introduced_at INTEGER NOT NULL DEFAULT (unixepoch()),
    detected_at INTEGER NOT NULL DEFAULT (unixepoch()),
    resolved_at INTEGER,
    detected_by TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_drift_status ON architecture_drift(status);
CREATE INDEX IF NOT EXISTS idx_drift_subsystem ON architecture_drift(subsystem);

-- ── 5. Operational Incident Ledger ──
CREATE TABLE IF NOT EXISTS operational_incidents (
    incident_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL
        CHECK (category IN ('deployment','scaling','outage','performance','security')),
    started_at INTEGER,
    detected_at INTEGER,
    resolved_at INTEGER,
    duration_minutes INTEGER,
    affected_services TEXT DEFAULT '[]',       -- JSON array
    affected_users INTEGER DEFAULT 0,
    detection_method TEXT,
    response_actions TEXT DEFAULT '[]',        -- JSON array
    postmortem TEXT,
    action_items TEXT DEFAULT '[]',            -- JSON array
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical','high','medium','low','info')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_ops_status ON operational_incidents(status);
CREATE INDEX IF NOT EXISTS idx_ops_category ON operational_incidents(category);

-- ── 6. Stabilization Timeline ──
CREATE TABLE IF NOT EXISTS stabilization_timeline (
    entry_id TEXT PRIMARY KEY,
    milestone TEXT NOT NULL,
    description TEXT,
    failures_before TEXT DEFAULT '[]',         -- JSON array of failure_ids
    known_issues_before TEXT DEFAULT '[]',     -- JSON array
    changes TEXT DEFAULT '[]',                 -- JSON array
    tests_added TEXT DEFAULT '[]',             -- JSON array
    tests_passing INTEGER DEFAULT 0,
    tests_total INTEGER DEFAULT 0,
    stability_duration_hours REAL DEFAULT 0,
    metrics_after TEXT DEFAULT '{}',           -- JSON object
    subsystem TEXT,
    achieved_by TEXT,
    achieved_at INTEGER NOT NULL DEFAULT (unixepoch()),
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_stabilization_subsystem ON stabilization_timeline(subsystem);

-- ── 7. Technical Debt Register ──
CREATE TABLE IF NOT EXISTS technical_debt (
    debt_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    subsystem TEXT,
    debt_type TEXT NOT NULL
        CHECK (debt_type IN ('design','code','test','documentation','infrastructure')),
    interest_rate TEXT
        CHECK (interest_rate IN ('low','medium','high','critical')),
    current_impact TEXT,
    future_impact TEXT,
    estimated_fix_effort TEXT,
    estimated_fix_complexity TEXT,
    payoff_if_fixed TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical','high','medium','low','info')),
    introduced_at INTEGER NOT NULL DEFAULT (unixepoch()),
    target_resolution INTEGER,
    resolved_at INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_debt_status ON technical_debt(status);
CREATE INDEX IF NOT EXISTS idx_debt_subsystem ON technical_debt(subsystem);

-- ── 8. Deferred Scalability Register ──
CREATE TABLE IF NOT EXISTS deferred_scalability (
    item_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    current_approach TEXT,
    target_approach TEXT,
    trigger_condition TEXT,
    trigger_metric TEXT,
    trigger_threshold TEXT,
    current_value TEXT,
    estimated_effort TEXT,
    estimated_phase TEXT,
    status TEXT NOT NULL DEFAULT 'deferred'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('critical','high','medium','low','info')),
    subsystem TEXT,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- ── 9. Known Risk Register ──
CREATE TABLE IF NOT EXISTS known_risks (
    risk_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    probability TEXT
        CHECK (probability IN ('low','medium','high','certain')),
    impact TEXT
        CHECK (impact IN ('low','medium','high','critical')),
    risk_score TEXT
        CHECK (risk_score IN ('low','medium','high','critical')),
    affected_subsystems TEXT DEFAULT '[]',     -- JSON array
    affected_users TEXT,
    mitigation_plan TEXT,
    contingency_plan TEXT,
    residual_risk TEXT,
    monitoring_metric TEXT,
    alert_threshold TEXT,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    severity TEXT NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('critical','high','medium','low','info')),
    owner TEXT,
    reviewed_at INTEGER,
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_risks_status ON known_risks(status);
CREATE INDEX IF NOT EXISTS idx_risks_owner ON known_risks(owner);

-- ── 10. Future Migration Register ──
CREATE TABLE IF NOT EXISTS future_migrations (
    migration_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    trigger_phase TEXT,
    trigger_condition TEXT,
    prerequisites TEXT DEFAULT '[]',           -- JSON array
    estimated_duration TEXT,
    estimated_team_size INTEGER DEFAULT 1,
    rollback_plan TEXT,
    risk_level TEXT
        CHECK (risk_level IN ('low','medium','high')),
    risk_factors TEXT DEFAULT '[]',            -- JSON array
    status TEXT NOT NULL DEFAULT 'deferred'
        CHECK (status IN ('open','in_progress','resolved','deferred','wontfix')),
    priority TEXT NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('critical','high','medium','low','info')),
    created_at INTEGER NOT NULL DEFAULT (unixepoch())
);
