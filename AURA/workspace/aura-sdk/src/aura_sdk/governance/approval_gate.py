"""HumanApprovalGate — explicit human approval for high-risk actions.

Every high-risk action creates an approval request that must be
explicitly approved by a human with sufficient privileges.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from aura_sdk.governance.charter import HighRiskAction
from aura_sdk.logging.logger import get_logger

logger = get_logger("governance.approval_gate")


class ApprovalRequest:
    """A pending approval request for a high-risk action."""

    def __init__(
        self,
        action: str,
        action_type: HighRiskAction,
        actor: str,
        details: dict[str, Any],
        required_role: str = "architect",
        timeout_minutes: int = 60,
    ):
        self.request_id = str(uuid4())
        self.action = action
        self.action_type = action_type
        self.actor = actor
        self.details = details
        self.required_role = required_role
        self.status = "pending"  # pending, approved, rejected, expired
        self.approved_by: str | None = None
        self.approved_at: datetime | None = None
        self.rejection_reason: str = ""
        self.created_at = datetime.now(timezone.utc)
        self.expires_at = self.created_at + timedelta(minutes=timeout_minutes)
        self.audit_trail: list[dict[str, Any]] = []

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_resolved(self) -> bool:
        return self.status in ("approved", "rejected", "expired")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "action_type": self.action_type.value,
            "actor": self.actor,
            "details": self.details,
            "required_role": self.required_role,
            "status": self.status,
            "approved_by": self.approved_by,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired,
            "audit_trail": self.audit_trail,
        }


class HumanApprovalGate:
    """Manages approval requests for high-risk actions.

    All high-risk actions create a pending approval.
    Actions execute ONLY after explicit human approval.
    """

    # Role requirements per high-risk action type
    ROLE_REQUIREMENTS: dict[HighRiskAction, str] = {
        HighRiskAction.GOVERNANCE_MODIFICATION: "admin",
        HighRiskAction.SECURITY_POLICY_CHANGE: "admin",
        HighRiskAction.ARCHITECTURE_CONTRACT_MUTATION: "architect",
        HighRiskAction.PLUGIN_TRUST_ELEVATION: "architect",
        HighRiskAction.DESTRUCTIVE_MIGRATION: "architect",
        HighRiskAction.DELETION_OPERATION: "approver",
        HighRiskAction.REPLAY_LEDGER_RESET: "admin",
        HighRiskAction.AUDIT_LEDGER_MAINTENANCE: "admin",
        HighRiskAction.INFRASTRUCTURE_ESCALATION: "architect",
        HighRiskAction.EXTERNAL_SYSTEM_EXECUTION: "approver",
    }

    def __init__(self):
        self._requests: dict[str, ApprovalRequest] = {}

    async def request_approval(
        self,
        action: str,
        action_type: HighRiskAction,
        actor: str,
        details: dict[str, Any],
    ) -> ApprovalRequest:
        """Create an approval request for a high-risk action."""
        required_role = self.ROLE_REQUIREMENTS.get(action_type, "architect")
        req = ApprovalRequest(
            action=action,
            action_type=action_type,
            actor=actor,
            details=details,
            required_role=required_role,
        )
        self._requests[req.request_id] = req

        logger.warning(
            "approval_requested",
            request_id=req.request_id,
            action=action,
            action_type=action_type.value,
            actor=actor,
            required_role=required_role,
        )

        return req

    async def approve(
        self, request_id: str, approver: str, approver_role: str
    ) -> tuple[bool, str]:
        """Approve a pending request."""
        req = self._requests.get(request_id)
        if req is None:
            return False, f"Approval request {request_id} not found."

        if req.is_resolved:
            return False, f"Request already {req.status}."

        if req.is_expired:
            req.status = "expired"
            return False, "Approval request has expired. Create a new request."

        # Check approver role
        role_hierarchy = {"viewer": 0, "reviewer": 1, "approver": 2, "architect": 3, "admin": 4}
        required_level = role_hierarchy.get(req.required_role, 3)
        approver_level = role_hierarchy.get(approver_role, 0)

        if approver_level < required_level:
            return (
                False,
                f"INSUFFICIENT PRIVILEGE: Role '{approver_role}' (level {approver_level}) "
                f"cannot approve {req.action_type.value}. Required: '{req.required_role}' "
                f"(level {required_level}).",
            )

        req.status = "approved"
        req.approved_by = approver
        req.approved_at = datetime.now(timezone.utc)
        req.audit_trail.append({
            "event": "approved",
            "by": approver,
            "role": approver_role,
            "at": req.approved_at.isoformat(),
        })

        logger.warning(
            "approval_granted",
            request_id=request_id,
            action=req.action,
            approved_by=approver,
            role=approver_role,
        )

        return True, f"Approved. Request {request_id} for '{req.action}' granted by {approver}."

    async def reject(
        self, request_id: str, rejecter: str, reason: str
    ) -> tuple[bool, str]:
        """Reject a pending request."""
        req = self._requests.get(request_id)
        if req is None:
            return False, f"Approval request {request_id} not found."

        if req.is_resolved:
            return False, f"Request already {req.status}."

        req.status = "rejected"
        req.rejection_reason = reason
        req.audit_trail.append({
            "event": "rejected",
            "by": rejecter,
            "reason": reason,
            "at": datetime.now(timezone.utc).isoformat(),
        })

        logger.warning(
            "approval_rejected",
            request_id=request_id,
            action=req.action,
            rejected_by=rejecter,
            reason=reason,
        )

        return True, f"Rejected. Request {request_id} for '{req.action}' denied: {reason}."

    async def check_approved(self, request_id: str) -> tuple[bool, str]:
        """Check if a request has been approved."""
        req = self._requests.get(request_id)
        if req is None:
            return False, "Request not found."
        if req.status == "approved":
            return True, f"Approved by {req.approved_by}."
        if req.status == "rejected":
            return False, f"Rejected: {req.rejection_reason}"
        if req.is_expired:
            return False, "Request expired."
        return False, f"Status: {req.status}. Awaiting human approval."

    def get_pending(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        return [r for r in self._requests.values() if r.status == "pending" and not r.is_expired]

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    @property
    def pending_count(self) -> int:
        return len(self.get_pending())
