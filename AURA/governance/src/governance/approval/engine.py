"""Approval engine — 3-dimensional approval state machine."""

from aura_sdk.models.governance import Approval, ApprovalDimension


class ApprovalEngine:
    """Manages the 3-dimensional approval matrix.

    Dimensions:
    - Lifecycle: migration → validation → simulation → review
    - Subsystem: audio-qualcomm, etc.
    - Quality: checkpatch, sparse, build, regression
    """

    STAGES = {
        ApprovalDimension.LIFECYCLE: ["migration", "validation", "simulation", "review"],
        ApprovalDimension.SUBSYSTEM: ["audio-qualcomm"],
        ApprovalDimension.QUALITY: ["checkpatch", "sparse", "build", "regression"],
    }

    @classmethod
    def get_required_approvals(cls, patch_id: str, subsystem: str) -> list[Approval]:
        """Generate required approvals for a patch."""
        approvals = []

        # Lifecycle approvals
        for stage in cls.STAGES[ApprovalDimension.LIFECYCLE]:
            approvals.append(Approval(
                patch_id=patch_id,
                dimension=ApprovalDimension.LIFECYCLE,
                stage=stage,
            ))

        # Subsystem approval
        approvals.append(Approval(
            patch_id=patch_id,
            dimension=ApprovalDimension.SUBSYSTEM,
            stage=subsystem,
        ))

        # Quality approvals
        for stage in cls.STAGES[ApprovalDimension.QUALITY]:
            approvals.append(Approval(
                patch_id=patch_id,
                dimension=ApprovalDimension.QUALITY,
                stage=stage,
            ))

        return approvals

    @classmethod
    def check_complete(cls, approvals: list[Approval]) -> bool:
        """Check if all required approvals are passed."""
        return all(
            a.status in ("passed", "skipped") for a in approvals
        )
