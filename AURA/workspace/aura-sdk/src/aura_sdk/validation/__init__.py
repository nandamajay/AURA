"""Adversarial Validation Framework — "No Fake Success" validation layer.

Every subsystem must be validated adversarially.
No optimistic reporting. No shallow checks. Engineering truthfulness only.
"""

from aura_sdk.validation.models import (
    TestCategory,
    TestVerdict,
    ValidationPlan,
    ValidationResult,
    ValidationReport,
    EdgeCase,
    FailureProbability,
)
from aura_sdk.validation.runners import ValidationOrchestrator
from aura_sdk.validation.detectors import NondeterminismDetector, FlakyTestDetector

__all__ = [
    "TestCategory",
    "TestVerdict",
    "ValidationPlan",
    "ValidationResult",
    "ValidationReport",
    "EdgeCase",
    "FailureProbability",
    "ValidationOrchestrator",
    "NondeterminismDetector",
    "FlakyTestDetector",
]
