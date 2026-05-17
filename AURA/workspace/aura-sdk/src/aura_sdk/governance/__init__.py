"""Human Authority & Safe Autonomy Charter — enforcement layer.

Autonomy must remain: bounded, observable, explainable, replayable,
interruptible, reversible.

Human governance is the final authority.
"""

from aura_sdk.governance.charter import (
    HumanAuthorityCharter,
    AutonomousExecutionBound,
    HighRiskAction,
    HumanControlRequirement,
    SelfModificationRule,
)
from aura_sdk.governance.guard import GovernanceGuard
from aura_sdk.governance.approval_gate import HumanApprovalGate
from aura_sdk.governance.modification_detector import SelfModificationDetector
from aura_sdk.governance.explainability import ExplainabilityTracker
from aura_sdk.governance.failsafe import FailSafeController

__all__ = [
    "HumanAuthorityCharter",
    "AutonomousExecutionBound",
    "HighRiskAction",
    "HumanControlRequirement",
    "SelfModificationRule",
    "GovernanceGuard",
    "HumanApprovalGate",
    "SelfModificationDetector",
    "ExplainabilityTracker",
    "FailSafeController",
]
