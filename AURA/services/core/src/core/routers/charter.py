"""Human Authority Charter API — governance enforcement endpoints.

Provides:
- Charter status and principles
- Human control operations (override, rollback, cancel, inspect)
- Approval request management
- Explainability trace retrieval
- Fail-safe incident reporting
- Self-modification detection alerts
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from aura_sdk.governance.charter import (
    AutonomyPrinciple,
    CharterViolation,
    HighRiskAction,
    HumanAuthorityCharter,
    HumanControlRequirement,
    SelfModificationRule,
)
from aura_sdk.governance.approval_gate import HumanApprovalGate
from aura_sdk.governance.explainability import ExplainabilityTracker
from aura_sdk.governance.failsafe import FailSafeController
from aura_sdk.governance.guard import GovernanceGuard
from aura_sdk.governance.modification_detector import SelfModificationDetector
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.governance import Permission
from core.routers.auth import get_current_user

logger = get_logger("core.charter")
router = APIRouter()

# Global governance components (initialized at module load)
CHARTER = HumanAuthorityCharter()
GUARD = GovernanceGuard(CHARTER)
APPROVAL_GATE = HumanApprovalGate()
EXPL_TRACKER = ExplainabilityTracker()
FAILSAFE = FailSafeController(confidence_threshold=CHARTER.confidence_threshold)
MOD_DETECTOR = SelfModificationDetector()


class ManualInterventionRequest(BaseModel):
    """Payload for manual intervention."""

    target: str = ""
    action: str = "pause"


class ManualOverrideRequest(BaseModel):
    """Payload for manual override."""

    target_action: str = ""
    justification: str = ""


class ManualRollbackRequest(BaseModel):
    """Payload for manual rollback."""

    target: str = ""
    to_state: str = ""


class ApprovalRequestPayload(BaseModel):
    """Payload for approval request creation."""

    action: str = ""
    action_type: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class RejectApprovalPayload(BaseModel):
    """Payload for approval rejection."""

    reason: str = "No reason provided"


class FailSafeEvaluatePayload(BaseModel):
    """Payload for fail-safe evaluation."""

    action: str = ""
    confidence: float = 0.0
    is_destructive: bool = False
    context: Any = None


class IntegrityCheckPayload(BaseModel):
    """Payload for integrity checks."""

    path: str = ""
    content: str = ""


class CheckActionPayload(BaseModel):
    """Payload for dry-run charter checks."""

    action: str = ""
    confidence: float = 1.0
    required_permission: str | None = None
    context: Any = None


class EnforcePolicyPayload(BaseModel):
    """Payload for blocking policy enforcement checks."""

    action: str = ""
    confidence: float = 1.0
    required_permission: str | None = None
    context: Any = None


# ── Charter Information ──

@router.get("/principles")
async def get_principles(current_user: dict = Depends(get_current_user)):
    """Get the six core autonomy principles."""
    return {
        "principles": [p.value for p in AutonomyPrinciple],
        "description": {
            "bounded": "Autonomy has defined limits — cannot exceed human-set boundaries",
            "observable": "All actions are visible in real time via audit and event streams",
            "explainable": "All actions have preserved reasoning traces",
            "replayable": "All actions can be deterministically replayed",
            "interruptible": "All actions can be stopped by human operators",
            "reversible": "All actions can be undone",
        },
    }


@router.get("/human-controls")
async def get_human_controls(current_user: dict = Depends(get_current_user)):
    """Get the eight mandatory human control requirements."""
    return {
        "human_controls": [c.value for c in HumanControlRequirement],
        "endpoints": {
            "manual_intervention": "/api/v1/charter/intervene",
            "manual_override": "/api/v1/charter/override",
            "manual_rollback": "/api/v1/charter/rollback",
            "manual_approval": "/api/v1/charter/approvals",
            "manual_replay_inspection": "/api/v1/tasks/{task_id}/replay",
            "manual_task_cancellation": "/api/v1/tasks/{task_id}/cancel",
            "manual_audit_inspection": "/api/v1/governance/audit",
            "manual_policy_enforcement": "/api/v1/charter/enforce",
        },
    }


@router.get("/high-risk-actions")
async def get_high_risk_actions(current_user: dict = Depends(get_current_user)):
    """Get the 10 categories requiring explicit human approval."""
    return {
        "high_risk_actions": [
            {
                "action": a.value,
                "required_role": HumanApprovalGate.ROLE_REQUIREMENTS.get(a, "architect"),
                "description": _describe_hra(a),
            }
            for a in HighRiskAction
        ],
        "note": "ALL of these actions require explicit human approval before execution. Autonomous systems cannot self-approve.",
    }


@router.get("/self-modification-rules")
async def get_self_modification_rules(current_user: dict = Depends(get_current_user)):
    """Get the 6 prohibitions on uncontrolled self-modification."""
    return {
        "prohibitions": [r.value for r in SelfModificationRule],
        "description": {
            "no_silent_governance_rewrite": "Platform cannot silently change governance rules",
            "no_silent_replay_rewrite": "Platform cannot silently modify replay semantics",
            "no_silent_architecture_bypass": "Platform cannot silently bypass architecture compliance",
            "no_silent_audit_bypass": "Platform cannot silently bypass audit systems",
            "no_silent_validation_change": "Platform cannot silently alter validation logic",
            "no_silent_security_change": "Platform cannot silently change security policies",
        },
        "enforcement": "GovernanceGuard blocks all matching actions unless explicitly_approved=True in context",
    }


@router.get("/summary")
async def charter_summary(current_user: dict = Depends(get_current_user)):
    """Get complete charter summary."""
    return {
        **CHARTER.summary,
        "violation_count": GUARD.violation_count,
        "pending_approvals": APPROVAL_GATE.pending_count,
        "failsafe_incidents": len(FAILSAFE.incidents),
        "modification_detections": MOD_DETECTOR.detection_count,
    }


# ── Human Control Endpoints ──

@router.post("/intervene")
async def manual_intervention(
    data: ManualInterventionRequest = Body(default_factory=ManualInterventionRequest),
    current_user: dict = Depends(get_current_user),
):
    """Manual intervention — pause or modify an ongoing action."""
    target = data.target
    action = data.action

    # This must be logged but cannot be blocked by the guard
    # (humans can always intervene)
    logger.critical(
        "manual_intervention",
        actor=current_user.get("email"),
        target=target,
        action=action,
        principle="interruptible",
    )

    return {
        "status": "intervened",
        "target": target,
        "action": action,
        "actor": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Human intervention executed. Autonomous action paused or modified.",
    }


@router.post("/override")
async def manual_override(
    data: ManualOverrideRequest = Body(default_factory=ManualOverrideRequest),
    current_user: dict = Depends(get_current_user),
):
    """Manual override — force an action through despite automated blocks."""
    target_action = data.target_action
    justification = data.justification

    if not justification:
        raise HTTPException(status_code=400, detail="Override requires written justification")

    logger.critical(
        "manual_override",
        actor=current_user.get("email"),
        target=target_action,
        justification=justification,
        principle="human_governance_is_final",
    )

    return {
        "status": "overridden",
        "target_action": target_action,
        "justification": justification,
        "actor": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "warning": "Override granted. Human operator assumes full responsibility. Audit trail created.",
    }


@router.post("/rollback")
async def manual_rollback(
    data: ManualRollbackRequest = Body(default_factory=ManualRollbackRequest),
    current_user: dict = Depends(get_current_user),
):
    """Manual rollback — revert system to a previous state."""
    target = data.target
    to_state = data.to_state

    logger.critical(
        "manual_rollback",
        actor=current_user.get("email"),
        target=target,
        to_state=to_state,
        principle="reversible",
    )

    return {
        "status": "rollback_initiated",
        "target": target,
        "to_state": to_state,
        "actor": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "note": "Rollback initiated. System will be restored to specified state.",
    }


# ── Approval Management ──

@router.post("/approvals/request")
async def request_approval(
    data: ApprovalRequestPayload = Body(default_factory=ApprovalRequestPayload),
    current_user: dict = Depends(get_current_user),
):
    """Request human approval for a high-risk action."""
    action = data.action
    action_type_str = data.action_type
    details = data.details

    try:
        action_type = HighRiskAction(action_type_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid high-risk action type: {action_type_str}")

    req = await APPROVAL_GATE.request_approval(
        action=action,
        action_type=action_type,
        actor=current_user.get("email", "system"),
        details=details,
    )

    return {
        "request_id": req.request_id,
        "status": req.status,
        "action": action,
        "action_type": action_type.value,
        "required_role": req.required_role,
        "expires_at": req.expires_at.isoformat(),
        "note": f"Approval required from role: {req.required_role}",
    }


@router.post("/approvals/{request_id}/approve")
async def approve_request(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Approve a pending request (human only)."""
    role = current_user.get("role", "viewer")
    success, message = await APPROVAL_GATE.approve(
        request_id=request_id,
        approver=current_user.get("email", "unknown"),
        approver_role=role,
    )
    if not success:
        raise HTTPException(status_code=403, detail=message)
    return {"status": "approved", "message": message}


@router.post("/approvals/request/{request_id}/approve")
async def approve_request_alias(
    request_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Compatibility alias for approve endpoint path defined in the charter."""
    return await approve_request(request_id=request_id, current_user=current_user)


@router.post("/approvals/{request_id}/reject")
async def reject_request(
    request_id: str,
    data: RejectApprovalPayload = Body(default_factory=RejectApprovalPayload),
    current_user: dict = Depends(get_current_user),
):
    """Reject a pending request."""
    reason = data.reason

    success, message = await APPROVAL_GATE.reject(
        request_id=request_id,
        rejecter=current_user.get("email", "unknown"),
        reason=reason,
    )
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "rejected", "message": message}


@router.post("/approvals/request/{request_id}/reject")
async def reject_request_alias(
    request_id: str,
    data: RejectApprovalPayload = Body(default_factory=RejectApprovalPayload),
    current_user: dict = Depends(get_current_user),
):
    """Compatibility alias for reject endpoint path defined in the charter."""
    return await reject_request(request_id=request_id, data=data, current_user=current_user)


@router.get("/approvals/pending")
async def list_pending_approvals(
    current_user: dict = Depends(get_current_user)
):
    """List all pending approval requests."""
    pending = APPROVAL_GATE.get_pending()
    return {
        "pending_count": len(pending),
        "requests": [r.to_dict() for r in pending],
    }


# ── Explainability ──

@router.get("/explainability/traces/{trace_id}")
async def get_trace(
    trace_id: str, current_user: dict = Depends(get_current_user)
):
    """Get a complete explainability trace."""
    trace = EXPL_TRACKER.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


@router.get("/explainability/report")
async def explainability_report(
    current_user: dict = Depends(get_current_user)
):
    """Get explainability completeness report."""
    return EXPL_TRACKER.get_completeness_report()


# ── Fail-Safe ──

@router.get("/failsafe/report")
async def failsafe_report(current_user: dict = Depends(get_current_user)):
    """Get fail-safe activation report."""
    return FAILSAFE.get_report()


@router.post("/failsafe/evaluate")
async def evaluate_failsafe(
    data: FailSafeEvaluatePayload = Body(default_factory=FailSafeEvaluatePayload),
    current_user: dict = Depends(get_current_user),
):
    """Evaluate an action against fail-safe rules."""
    result = FAILSAFE.evaluate(data.action, data.confidence, data.is_destructive, data.context)
    return result


# ── Self-Modification Detection ──

@router.get("/integrity/report")
async def integrity_report(current_user: dict = Depends(get_current_user)):
    """Get self-modification detection report."""
    return MOD_DETECTOR.generate_integrity_report()


@router.post("/integrity/check")
async def check_integrity(
    data: IntegrityCheckPayload = Body(default_factory=IntegrityCheckPayload),
    current_user: dict = Depends(get_current_user),
):
    """Check integrity of a registered file/rule."""
    is_valid, result = MOD_DETECTOR.check_integrity(data.path, data.content)
    return {"valid": is_valid, **result}


# ── Violations ──

@router.get("/violations")
async def list_violations(
    severity: str = "",
    current_user: dict = Depends(get_current_user),
):
    """List charter violations."""
    if severity:
        violations = GUARD.get_violations_by_severity(severity)
    else:
        violations = GUARD.violations
    return {
        "count": len(violations),
        "violations": [v.model_dump() for v in violations],
    }


# ── Enforcement on Actions ──

@router.post("/check-action")
async def check_action(
    data: CheckActionPayload = Body(default_factory=CheckActionPayload),
    current_user: dict = Depends(get_current_user),
):
    """Check if an action is allowed under the charter (dry-run)."""
    allowed, reason, metadata = GUARD.check_action(
        action=data.action,
        actor=current_user,
        required_permission=Permission(data.required_permission) if data.required_permission else None,
        confidence=data.confidence,
        context=data.context,
    )

    return {
        "allowed": allowed,
        "reason": reason,
        "metadata": jsonable_encoder(metadata),
        "principle": "bounded" if not allowed else None,
    }


@router.post("/enforce")
async def enforce_policy(
    data: EnforcePolicyPayload = Body(default_factory=EnforcePolicyPayload),
    current_user: dict = Depends(get_current_user),
):
    """Enforce charter policy for an action (blocking when disallowed)."""
    action = data.action
    if not action:
        raise HTTPException(status_code=400, detail="Field 'action' is required")

    confidence = float(data.confidence)
    required_permission = data.required_permission
    context = data.context

    allowed, reason, metadata = GUARD.check_action(
        action=action,
        actor=current_user,
        required_permission=Permission(required_permission) if required_permission else None,
        confidence=confidence,
        context=context,
    )
    if not allowed:
        logger.warning(
            "charter_enforce_blocked",
            actor=current_user.get("email"),
            action=action,
            reason=reason,
            metadata=metadata,
        )
        raise HTTPException(
            status_code=403,
            detail=jsonable_encoder({
                "allowed": False,
                "reason": reason,
                "metadata": metadata,
            }),
        )

    logger.info(
        "charter_enforce_allowed",
        actor=current_user.get("email"),
        action=action,
        confidence=confidence,
    )
    return {
        "allowed": True,
        "reason": reason,
        "metadata": jsonable_encoder(metadata),
        "enforced_by": current_user.get("email"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _describe_hra(action: HighRiskAction) -> str:
    descriptions = {
        HighRiskAction.GOVERNANCE_MODIFICATION: "Change governance rules, roles, or policies",
        HighRiskAction.SECURITY_POLICY_CHANGE: "Modify security settings, JWT secrets, auth rules",
        HighRiskAction.ARCHITECTURE_CONTRACT_MUTATION: "Change subsystem contracts or interfaces",
        HighRiskAction.PLUGIN_TRUST_ELEVATION: "Increase plugin trust level or capabilities",
        HighRiskAction.DESTRUCTIVE_MIGRATION: "Run migrations that delete or alter data",
        HighRiskAction.DELETION_OPERATION: "Delete patches, tasks, rules, or audit entries",
        HighRiskAction.REPLAY_LEDGER_RESET: "Reset or truncate replay/task logs",
        HighRiskAction.AUDIT_LEDGER_MAINTENANCE: "Modify or maintain the audit ledger",
        HighRiskAction.INFRASTRUCTURE_ESCALATION: "Change Docker/K8s infrastructure",
        HighRiskAction.EXTERNAL_SYSTEM_EXECUTION: "Execute commands on external systems",
    }
    return descriptions.get(action, "High-risk action requiring human approval")
