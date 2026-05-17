"""Human Authority & Safe Autonomy Charter — canonical definitions.

This module defines the charter as data structures that can be:
- Stored in the database
- Enforced at runtime
- Audited for compliance
- Displayed in the dashboard
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AutonomyPrinciple(StrEnum):
    """The six core principles of bounded autonomy."""

    BOUNDED = "bounded"           # Autonomy has defined limits
    OBSERVABLE = "observable"     # All actions are visible
    EXPLAINABLE = "explainable"   # All actions have reasoning
    REPLAYABLE = "replayable"     # All actions can be replayed
    INTERRUPTIBLE = "interruptible"  # All actions can be stopped
    REVERSIBLE = "reversible"     # All actions can be undone


class HumanControlRequirement(StrEnum):
    """Eight mandatory human control capabilities."""

    MANUAL_INTERVENTION = "manual_intervention"
    MANUAL_OVERRIDE = "manual_override"
    MANUAL_ROLLBACK = "manual_rollback"
    MANUAL_APPROVAL = "manual_approval"
    MANUAL_REPLAY_INSPECTION = "manual_replay_inspection"
    MANUAL_TASK_CANCELLATION = "manual_task_cancellation"
    MANUAL_AUDIT_INSPECTION = "manual_audit_inspection"
    MANUAL_POLICY_ENFORCEMENT = "manual_policy_enforcement"


class HighRiskAction(StrEnum):
    """Ten categories requiring explicit human approval."""

    GOVERNANCE_MODIFICATION = "governance_modification"
    SECURITY_POLICY_CHANGE = "security_policy_change"
    ARCHITECTURE_CONTRACT_MUTATION = "architecture_contract_mutation"
    PLUGIN_TRUST_ELEVATION = "plugin_trust_elevation"
    DESTRUCTIVE_MIGRATION = "destructive_migration"
    DELETION_OPERATION = "deletion_operation"
    REPLAY_LEDGER_RESET = "replay_ledger_reset"
    AUDIT_LEDGER_MAINTENANCE = "audit_ledger_maintenance"
    INFRASTRUCTURE_ESCALATION = "infrastructure_escalation"
    EXTERNAL_SYSTEM_EXECUTION = "external_system_execution"


class SelfModificationRule(StrEnum):
    """Six prohibitions on uncontrolled self-modification."""

    NO_SILENT_GOVERNANCE_REWRITE = "no_silent_governance_rewrite"
    NO_SILENT_REPLAY_REWRITE = "no_silent_replay_rewrite"
    NO_SILENT_ARCHITECTURE_BYPASS = "no_silent_architecture_bypass"
    NO_SILENT_AUDIT_BYPASS = "no_silent_audit_bypass"
    NO_SILENT_VALIDATION_CHANGE = "no_silent_validation_change"
    NO_SILENT_SECURITY_CHANGE = "no_silent_security_change"


class AutonomousExecutionBound(StrEnum):
    """Five bounds on autonomous execution."""

    RATE_LIMITED = "rate_limited"
    RESOURCE_BOUNDED = "resource_bounded"
    TIMEOUT_BOUNDED = "timeout_bounded"
    SANDBOX_CONSTRAINED = "sandbox_constrained"
    OBSERVABLE_REALTIME = "observable_realtime"


class ExplainabilityRequirement(StrEnum):
    """Six lineage types that must be preserved."""

    REASONING_TRACE = "reasoning_trace"
    EXECUTION_TRACE = "execution_trace"
    EVENT_LINEAGE = "event_lineage"
    DEPENDENCY_LINEAGE = "dependency_lineage"
    REPLAY_LINEAGE = "replay_lineage"
    ROLLBACK_LINEAGE = "rollback_lineage"


class AutonomousModificationRequirement(StrEnum):
    """Five requirements for any autonomous modification."""

    EMIT_AUDIT_EVENT = "emit_audit_event"
    PRESERVE_REPLAYABILITY = "preserve_replayability"
    PRESERVE_DETERMINISTIC_TRACEABILITY = "preserve_deterministic_traceability"
    PRESERVE_ROLLBACK_CAPABILITY = "preserve_rollback_capability"
    PRESERVE_APPROVAL_VISIBILITY = "preserve_approval_visibility"


class CharterViolation(BaseModel):
    """A detected violation of the Human Authority Charter."""

    violation_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    principle: str = ""  # Which principle was violated
    rule: str = ""  # Which specific rule
    action: str = ""  # What action was attempted
    actor: str = ""  # Who/what attempted it
    details: dict[str, Any] = Field(default_factory=dict)
    blocked: bool = True  # Was the action blocked?
    severity: str = "high"  # low, medium, high, critical


class HumanAuthorityCharter(BaseModel):
    """The complete Human Authority & Safe Autonomy Charter.

    This is the single source of truth for governance constraints.
    Stored in the database and loaded at startup.
    """

    charter_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = "1.0.0"
    adopted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Principles
    principles: list[AutonomyPrinciple] = Field(default_factory=lambda: list(AutonomyPrinciple))

    # Human control requirements
    human_controls: list[HumanControlRequirement] = Field(
        default_factory=lambda: list(HumanControlRequirement)
    )

    # High-risk actions requiring approval
    high_risk_actions: list[HighRiskAction] = Field(
        default_factory=lambda: list(HighRiskAction)
    )

    # Self-modification prohibitions
    modification_prohibitions: list[SelfModificationRule] = Field(
        default_factory=lambda: list(SelfModificationRule)
    )

    # Execution bounds
    execution_bounds: list[AutonomousExecutionBound] = Field(
        default_factory=lambda: list(AutonomousExecutionBound)
    )

    # Explainability requirements
    explainability: list[ExplainabilityRequirement] = Field(
        default_factory=lambda: list(ExplainabilityRequirement)
    )

    # Modification requirements
    modification_requirements: list[AutonomousModificationRequirement] = Field(
        default_factory=lambda: list(AutonomousModificationRequirement)
    )

    # Fail-safe configuration
    confidence_threshold: float = 0.7  # Below this, request human review
    auto_rollback_on_failure: bool = True
    preserve_state_on_uncertainty: bool = True

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "principles": [p.value for p in self.principles],
            "human_controls": [c.value for c in self.human_controls],
            "high_risk_actions": [a.value for a in self.high_risk_actions],
            "prohibitions": [r.value for r in self.modification_prohibitions],
            "execution_bounds": [b.value for b in self.execution_bounds],
            "explainability_requirements": [e.value for e in self.explainability],
            "modification_requirements": [r.value for r in self.modification_requirements],
            "confidence_threshold": self.confidence_threshold,
        }

    def check_action_allowed(
        self, action: str, actor: str, confidence: float = 1.0
    ) -> tuple[bool, str]:
        """Check if an action is allowed under the charter.

        Returns:
            (allowed, reason)
        """
        # Check if it's a high-risk action
        for hra in self.high_risk_actions:
            if hra.value in action or action in hra.value:
                if confidence < self.confidence_threshold:
                    return (
                        False,
                        f"HIGH-RISK ACTION BLOCKED: {hra.value} requires human approval "
                        f"(confidence {confidence:.2f} < threshold {self.confidence_threshold:.2f}). "
                        f"Request explicit approval before proceeding.",
                    )
                return (
                    True,
                    f"HIGH-RISK ACTION: {hra.value} allowed but requires audit trail. "
                    f"Ensure all 5 modification requirements are met.",
                )

        return (True, "Action not classified as high-risk. Proceed with standard audit.")
