"""GovernanceGuard — runtime enforcement of the Human Authority Charter.

Every sensitive operation must pass through the guard.
The guard checks: permissions, high-risk classification, confidence thresholds,
and audit requirements.
"""

from datetime import datetime, timezone
from typing import Any

from aura_sdk.governance.charter import (
    AutonomousModificationRequirement,
    CharterViolation,
    HighRiskAction,
    HumanAuthorityCharter,
    SelfModificationRule,
)
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.governance import Permission, Role, ROLE_PERMISSIONS

logger = get_logger("governance.guard")


class GovernanceGuard:
    """Central enforcement point for the Human Authority Charter.

    Usage:
        guard = GovernanceGuard(charter)
        allowed, reason = guard.check_action(
            action="delete_patch",
            actor=user,
            required_permission=Permission.PATCH_APPROVE,
            confidence=0.95,
        )
        if not allowed:
            raise HTTPException(403, reason)
    """

    def __init__(self, charter: HumanAuthorityCharter | None = None):
        self.charter = charter or HumanAuthorityCharter()
        self._violations: list[CharterViolation] = []

    def check_action(
        self,
        action: str,
        actor: dict[str, Any],
        required_permission: Permission | None = None,
        confidence: float = 1.0,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, str, dict[str, Any]]:
        """Check if an action is allowed.

        Returns:
            (allowed, reason, metadata)
        """
        metadata: dict[str, Any] = {
            "checks_performed": [],
            "violations": [],
            "approval_required": False,
        }

        # 1. RBAC check
        if required_permission:
            metadata["checks_performed"].append("rbac")
            role_str = actor.get("role", "viewer")
            role = Role(role_str) if isinstance(role_str, str) else role_str
            if required_permission not in ROLE_PERMISSIONS.get(role, []):
                violation = CharterViolation(
                    principle="bounded",
                    rule="rbac_enforcement",
                    action=action,
                    actor=actor.get("email", "unknown"),
                    details={
                        "required": required_permission.value,
                        "role": role.value,
                    },
                    blocked=True,
                    severity="high",
                )
                self._violations.append(violation)
                metadata["violations"].append(violation.model_dump(mode="json"))
                return (
                    False,
                    f"RBAC DENIED: Role '{role.value}' lacks permission '{required_permission.value}' "
                    f"for action '{action}'. Human override required.",
                    metadata,
                )

        # 2. High-risk action check
        metadata["checks_performed"].append("high_risk")
        high_risk_match: HighRiskAction | None = None
        for hra in self.charter.high_risk_actions:
            if hra.value in action or action in hra.value:
                high_risk_match = hra
                metadata["approval_required"] = True
                metadata["high_risk_action"] = hra.value
                break

        allowed, reason = self.charter.check_action_allowed(action, actor.get("email", ""), confidence)
        if not allowed:
            metadata["violations"].append({
                "principle": "bounded",
                "rule": "high_risk_approval",
                "action": action,
                "blocked": True,
            })
            return False, reason, metadata

        # High-risk actions always require explicit human approval.
        if high_risk_match and not (context or {}).get("approval_granted", False):
            metadata["violations"].append({
                "principle": "bounded",
                "rule": "high_risk_approval",
                "action": action,
                "blocked": True,
                "required_action": high_risk_match.value,
            })
            return (
                False,
                f"HIGH-RISK ACTION BLOCKED: {high_risk_match.value} requires explicit human approval. "
                "Create an approval request and proceed only after approval_granted=True.",
                metadata,
            )

        if high_risk_match:
            metadata["checks_performed"].append("audit_requirements")
            # Verify modification requirements
            missing = self._check_modification_requirements(context)
            if missing:
                return (
                    False,
                    f"HIGH-RISK ACTION BLOCKED: Missing modification requirements: {', '.join(missing)}. "
                    f"All autonomous modifications must: emit audit events, preserve replayability, "
                    f"preserve deterministic traceability, preserve rollback capability, "
                    f"and preserve approval visibility.",
                    metadata,
                )

        # 3. Self-modification prohibition check
        metadata["checks_performed"].append("self_modification")
        violation = self._check_self_modification(action, actor, context)
        if violation:
            self._violations.append(violation)
            metadata["violations"].append(violation.model_dump(mode="json"))
            return (
                False,
                f"CHARTER VIOLATION: {violation.rule}. {violation.principle} principle violated. "
                f"Action '{action}' blocked. Audit event created.",
                metadata,
            )

        # 4. Fail-safe: confidence check
        metadata["checks_performed"].append("confidence")
        if confidence < self.charter.confidence_threshold:
            metadata["confidence_below_threshold"] = True
            if self.charter.preserve_state_on_uncertainty:
                return (
                    False,
                    f"FAIL-SAFE: Confidence {confidence:.2f} below threshold "
                    f"{self.charter.confidence_threshold:.2f}. "
                    f"State preserved. Human review required before proceeding.",
                    metadata,
                )

        metadata["checks_performed"].append("passed")
        return True, f"Action '{action}' allowed. {len(metadata['checks_performed'])} checks passed.", metadata

    def _check_modification_requirements(
        self, context: dict[str, Any] | None
    ) -> list[str]:
        """Check if all 5 modification requirements are met."""
        if context is None:
            return ["No context provided — cannot verify modification requirements"]

        missing = []
        requirements = [
            (AutonomousModificationRequirement.EMIT_AUDIT_EVENT, "audit_event_emitted"),
            (AutonomousModificationRequirement.PRESERVE_REPLAYABILITY, "replayability_preserved"),
            (AutonomousModificationRequirement.PRESERVE_DETERMINISTIC_TRACEABILITY, "determinism_preserved"),
            (AutonomousModificationRequirement.PRESERVE_ROLLBACK_CAPABILITY, "rollback_preserved"),
            (AutonomousModificationRequirement.PRESERVE_APPROVAL_VISIBILITY, "approval_visible"),
        ]

        for req, key in requirements:
            if not context.get(key, False):
                missing.append(req.value)

        return missing

    def _check_self_modification(
        self, action: str, actor: dict[str, Any], context: dict[str, Any] | None
    ) -> CharterViolation | None:
        """Check for prohibited self-modification patterns."""
        action_lower = action.lower()
        ctx = context or {}

        # Check each prohibition
        prohibition_checks = [
            (
                SelfModificationRule.NO_SILENT_GOVERNANCE_REWRITE,
                ["governance", "rule_change", "policy_update", "permission_change"],
                "governance",
            ),
            (
                SelfModificationRule.NO_SILENT_REPLAY_REWRITE,
                ["replay", "snapshot", "task_log", "output_hash"],
                "replay",
            ),
            (
                SelfModificationRule.NO_SILENT_ARCHITECTURE_BYPASS,
                ["architecture", "constitution", "contract", "subsystem"],
                "architecture",
            ),
            (
                SelfModificationRule.NO_SILENT_AUDIT_BYPASS,
                ["audit", "ledger", "audit_log", "tamper"],
                "audit",
            ),
            (
                SelfModificationRule.NO_SILENT_VALIDATION_CHANGE,
                ["validation", "test", "check", "verify"],
                "validation",
            ),
            (
                SelfModificationRule.NO_SILENT_SECURITY_CHANGE,
                ["security", "auth", "jwt", "password", "secret", "rbac"],
                "security",
            ),
        ]

        for rule, keywords, category in prohibition_checks:
            matches = any(kw in action_lower for kw in keywords)
            if matches:
                # Check if this was silent (no explicit approval recorded)
                if not ctx.get("explicitly_approved", False):
                    return CharterViolation(
                        principle="bounded",
                        rule=rule.value,
                        action=action,
                        actor=actor.get("email", "unknown"),
                        details={
                            "category": category,
                            "silent": True,
                            "keywords_matched": [k for k in keywords if k in action_lower],
                        },
                        blocked=True,
                        severity="critical",
                    )

        return None

    @property
    def violations(self) -> list[CharterViolation]:
        return list(self._violations)

    @property
    def violation_count(self) -> int:
        return len(self._violations)

    def get_violations_by_severity(self, severity: str) -> list[CharterViolation]:
        return [v for v in self._violations if v.severity == severity]
