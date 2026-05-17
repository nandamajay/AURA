"""Engineering Memory models — 10 ledgers and registers.

Every major implementation decision must record:
- reasoning
- tradeoffs
- rejected alternatives
- operational implications
- scalability implications
- determinism implications
- observability implications
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Severity(StrEnum):
    """Severity levels for memory entries."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Status(StrEnum):
    """Status for memory entries."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    WONTFIX = "wontfix"


# ── 1. Engineering Decision Ledger ──

class DecisionRecord(BaseModel):
    """Records WHY a major engineering decision was made.

    Without this, future evolution becomes painful —
    people change code without understanding original reasoning.
    """

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    subsystem: str = ""  # e.g. "S2_AgentRuntime", "core.auth"
    decision_made: str = ""  # What was decided
    # Reasoning
    reasoning: str = ""  # Why this decision was made
    context: str = ""  # What situation led to this decision
    constraints: list[str] = Field(default_factory=list)
    # Alternatives
    alternatives_considered: list[dict[str, str]] = Field(default_factory=list)
    # [{"option": "PostgreSQL", "reason_rejected": "Overkill for P2"}]
    rejected_alternatives: list[str] = Field(default_factory=list)
    # Implications
    operational_impact: str = ""
    scalability_impact: str = ""
    determinism_impact: str = ""
    observability_impact: str = ""
    security_impact: str = ""
    cost_impact: str = ""
    # Governance
    decided_by: str = ""  # user_id
    approved_by: str = ""  # user_id (for significant decisions)
    related_decisions: list[str] = Field(default_factory=list)  # decision_ids
    # Metadata
    reversible: bool = True
    reversal_conditions: str = ""  # When/how this decision could be reversed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ── 2. Failure Investigation Ledger ──

class FailureRecord(BaseModel):
    """Records root cause analysis for every significant failure.

    Not just what broke — WHY it broke, and how to prevent it.
    """

    failure_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    subsystem: str = ""
    # Incident
    description: str = ""
    root_cause: str = ""
    root_cause_category: str = ""  # race_condition, resource_exhaustion, logic_bug, etc.
    # Impact
    impact_scope: str = ""  # Which subsystems were affected
    impact_severity: Severity = Severity.MEDIUM
    affected_components: list[str] = Field(default_factory=list)
    # Timeline
    first_observed_at: datetime | None = None
    resolved_at: datetime | None = None
    detection_latency_ms: int | None = None  # Time from failure to detection
    # Resolution
    recovery_method: str = ""  # How was it fixed
    prevention_strategy: str = ""  # How to prevent recurrence
    # Replay implications
    replay_affected: bool = False
    replay_recovery: str = ""  # How replay handles this scenario
    # Governance implications
    approval_required_after_fix: bool = False
    audit_entry_ids: list[str] = Field(default_factory=list)
    # Metadata
    status: Status = Status.OPEN
    severity: Severity = Severity.MEDIUM
    related_failures: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 3. Replay Incident Ledger ──

class ReplayIncident(BaseModel):
    """Records incidents specifically related to replay/determinism.

    Critical for maintaining trust in the deterministic execution system.
    """

    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    agent_type: str = ""
    description: str = ""
    # Fidelity
    expected_fidelity: str = ""  # PERFECT, PARTIAL, etc.
    actual_fidelity: str = ""
    # Cause
    divergence_cause: str = ""  # Why replay diverged from original
    divergence_point: str = ""  # Where in the execution it diverged
    # Seeded RNG
    seed_used: int = 0
    model_version_used: str = ""
    # LLM call comparison
    original_llm_calls: int = 0
    replay_llm_calls: int = 0
    mismatched_llm_responses: int = 0
    # Hash verification
    original_output_hash: str = ""
    replay_output_hash: str = ""
    hash_match: bool = False
    # Resolution
    resolution: str = ""
    replay_recovered: bool = False
    # Metadata
    status: Status = Status.OPEN
    severity: Severity = Severity.MEDIUM
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 4. Architecture Drift Ledger ──

class ArchitectureDrift(BaseModel):
    """Records deviations from the intended architecture.

    Helps track when the implementation has drifted from the spec.
    """

    drift_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    # Spec vs. Reality
    intended_design: str = ""  # What the architecture says
    actual_implementation: str = ""  # What was actually built
    drift_description: str = ""  # How they differ
    # Classification
    drift_type: str = ""  # intentional, accidental, necessary, technical_debt
    # Impact
    functional_impact: str = ""
    maintainability_impact: str = ""
    scalability_impact: str = ""
    compliance_impact: str = ""  # Does it violate the Constitution?
    # Resolution
    remediation_plan: str = ""
    remediation_priority: Severity = Severity.MEDIUM
    # Metadata
    status: Status = Status.OPEN
    subsystem: str = ""
    introduced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    detected_by: str = ""  # How was this detected (review, audit, test)


# ── 5. Operational Incident Ledger ──

class OperationalIncident(BaseModel):
    """Records production/operational incidents.

    Distinguishes from FailureRecord — this is about operations
    (deployment, scaling, outages), not code bugs.
    """

    incident_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    # Incident
    description: str = ""
    category: str = ""  # deployment, scaling, outage, performance, security
    # Timeline
    started_at: datetime | None = None
    detected_at: datetime | None = None
    resolved_at: datetime | None = None
    duration_minutes: int | None = None
    # Impact
    affected_services: list[str] = Field(default_factory=list)
    affected_users: int = 0
    # Response
    detection_method: str = ""  # How was it detected
    response_actions: list[str] = Field(default_factory=list)
    # Post-incident
    postmortem: str = ""
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    # [{"action": "Add alert", "owner": "team", "due": "2024-01-15", "status": "open"}]
    # Metadata
    severity: Severity = Severity.MEDIUM
    status: Status = Status.OPEN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 6. Stabilization Timeline ──

class StabilizationEntry(BaseModel):
    """Records stabilization milestones and the conditions that achieved them.

    What was fixed, in what order, and what the system looked like after.
    """

    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    milestone: str = ""  # e.g. "First stable overnight run"
    description: str = ""
    # Pre-conditions
    failures_before: list[str] = Field(default_factory=list)  # failure_ids
    known_issues_before: list[str] = Field(default_factory=list)
    # Changes made
    changes: list[dict[str, Any]] = Field(default_factory=list)
    # [{"change": "Added WAL recovery", "subsystem": "db", "commit": "abc123"}]
    # Validation
    tests_added: list[str] = Field(default_factory=list)
    tests_passing: int = 0
    tests_total: int = 0
    # Post-conditions
    stability_duration_hours: float = 0.0
    metrics_after: dict[str, Any] = Field(default_factory=dict)
    # [{"metric": "error_rate", "value": "0.01%"}]
    # Metadata
    subsystem: str = ""
    achieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    achieved_by: str = ""


# ── 7. Technical Debt Register ──

class TechnicalDebt(BaseModel):
    """Records known technical debt.

    Not all debt is bad — but all debt must be visible.
    """

    debt_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    subsystem: str = ""
    # Classification
    debt_type: str = ""  # design, code, test, documentation, infrastructure
    # Impact
    interest_rate: str = ""  # How fast this debt grows: "low", "medium", "high", "critical"
    current_impact: str = ""  # How it hurts today
    future_impact: str = ""  # How it will hurt if not addressed
    # Cost
    estimated_fix_effort: str = ""  # e.g. "2 days", "1 week"
    estimated_fix_complexity: str = ""  # low, medium, high
    # Payoff
    payoff_if_fixed: str = ""  # What we gain by fixing
    # Metadata
    status: Status = Status.OPEN
    severity: Severity = Severity.MEDIUM
    introduced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    target_resolution: datetime | None = None  # When we plan to fix
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 8. Deferred Scalability Register ──

class DeferredScalability(BaseModel):
    """Records scalability work that was deferred.

    Links to the Constitution's Phase Boundaries (Article VII).
    """

    item_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    # What was deferred
    current_approach: str = ""  # What we do now
    target_approach: str = ""  # What we should do at scale
    # Trigger
    trigger_condition: str = ""  # When to implement: "when agents > 50", "when users > 20"
    trigger_metric: str = ""  # Which metric to watch
    trigger_threshold: str = ""  # Threshold value
    current_value: str = ""  # Current value of the metric
    # Estimate
    estimated_effort: str = ""
    estimated_phase: str = ""  # Which Phase this belongs to (P3, P4, etc.)
    # Metadata
    status: Status = Status.DEFERRED
    priority: Severity = Severity.MEDIUM
    subsystem: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 9. Known Risk Register ──

class KnownRisk(BaseModel):
    """Records known risks with probability and impact.

    Kept visible so they are not forgotten.
    """

    risk_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    # Risk assessment
    probability: str = ""  # "low", "medium", "high", "certain"
    impact: str = ""  # "low", "medium", "high", "critical"
    risk_score: str = ""  # probability x impact: "medium", "high", etc.
    # Affected areas
    affected_subsystems: list[str] = Field(default_factory=list)
    affected_users: str = ""  # Who is affected
    # Mitigation
    mitigation_plan: str = ""  # What we're doing to reduce risk
    contingency_plan: str = ""  # What we do if it happens
    residual_risk: str = ""  # Risk after mitigation
    # Monitoring
    monitoring_metric: str = ""  # What to watch
    alert_threshold: str = ""  # When to escalate
    # Metadata
    status: Status = Status.OPEN
    severity: Severity = Severity.MEDIUM
    owner: str = ""  # Who owns this risk
    reviewed_at: datetime | None = None  # Last review date
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── 10. Future Migration Register ──

class FutureMigration(BaseModel):
    """Records planned future migrations (cross-phase transitions).

    Links to the Constitution's Article VII (Phase Boundaries)
    and Article V (Anti-Overengineering).
    """

    migration_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = ""
    description: str = ""
    # Migration details
    from_state: str = ""  # e.g. "SQLite single-node"
    to_state: str = ""  # e.g. "PostgreSQL with read replicas"
    # Trigger
    trigger_phase: str = ""  # e.g. "P3", "P4"
    trigger_condition: str = ""  # What triggers this migration
    # Dependencies
    prerequisites: list[str] = Field(default_factory=list)
    # e.g. ["Kubernetes cluster operational", "Multi-region networking"]
    # Effort
    estimated_duration: str = ""  # e.g. "2-4 weeks"
    estimated_team_size: int = 1
    rollback_plan: str = ""  # How to roll back if needed
    # Risk
    risk_level: str = ""  # "low", "medium", "high"
    risk_factors: list[str] = Field(default_factory=list)
    # Metadata
    status: Status = Status.DEFERRED
    priority: Severity = Severity.MEDIUM
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
