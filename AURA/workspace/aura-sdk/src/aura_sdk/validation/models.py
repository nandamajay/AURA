"""Validation models — adversarial testing framework.

Do NOT declare anything validated without:
- Negative tests passing
- Chaos tests passing
- Replay corruption recovery verified
- Restart consistency confirmed
- All audit invariants holding
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TestCategory(StrEnum):
    """Categories of adversarial validation tests."""

    # Negative testing
    NEGATIVE_INPUT = "negative_input"
    NEGATIVE_AUTH = "negative_auth"
    NEGATIVE_PERMISSIONS = "negative_permissions"
    NEGATIVE_DATA = "negative_data"

    # Chaos testing
    CHAOS_RANDOM_FAILURE = "chaos_random_failure"
    CHAOS_LATENCY_SPIKE = "chaos_latency_spike"
    CHAOS_RESOURCE_EXHAUSTION = "chaos_resource_exhaustion"
    CHAOS_NETWORK_PARTITION = "chaos_network_partition"

    # Replay & determinism
    REPLAY_CORRUPTION = "replay_corruption"
    REPLAY_HASH_MISMATCH = "replay_hash_mismatch"
    REPLAY_SNAPSHOT_INTEGRITY = "replay_snapshot_integrity"
    REPLAY_LLMCALL_REORDERING = "replay_llmcall_reordering"

    # Restart & recovery
    RESTART_CONSISTENCY = "restart_consistency"
    RESTART_WAL_RECOVERY = "restart_wal_recovery"
    RESTART_MID_TRANSACTION = "restart_mid_transaction"

    # Dependency failure
    DEP_FAILURE_LLMCALL = "dep_failure_llmcall"
    DEP_FAILURE_DATABASE = "dep_failure_database"
    DEP_FAILURE_WS = "dep_failure_ws"
    DEP_FAILURE_DISK = "dep_failure_disk"

    # Event integrity
    MALFORMED_EVENT = "malformed_event"
    DUPLICATE_EVENT = "duplicate_event"
    OUT_OF_ORDER_EVENT = "out_of_order_event"
    STALE_TOKEN = "stale_token"

    # Storage integrity
    PARTIAL_WRITE = "partial_write"
    WAL_CONTENTION = "wal_contention"
    SQLITE_CORRUPTION = "sqlite_corruption"

    # Nondeterminism
    SEED_DRIFT = "seed_drift"
    MODEL_VERSION_DRIFT = "model_version_drift"
    TIMING_DEPENDENCY = "timing_dependency"


class TestVerdict(StrEnum):
    """Possible outcomes of a validation test.

    UNKNOWN: Not yet run.
    PASS: Test passed — BUT this does NOT mean the subsystem is "stable".
    FAIL: Test failed — this IS meaningful.
    SKIP: Skipped (dependency unavailable).
    TIMEOUT: Test exceeded time budget.
    CRASH: Test caused a crash — worst outcome.
    FLAKY: Different results across runs — indicates nondeterminism.
    """

    UNKNOWN = "unknown"
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    TIMEOUT = "timeout"
    CRASH = "crash"
    FLAKY = "flaky"


class ValidationPlan(BaseModel):
    """A plan of adversarial tests for a specific subsystem or component.

    Generated automatically from edge-case matrices and failure probability analysis.
    """

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    target: str = ""  # e.g. "aura-sdk.event_bus", "core.auth"
    description: str = ""
    tests: list[dict[str, Any]] = Field(default_factory=list)
    # Each test: {"category": TestCategory, "name": str, "description": str, "severity": int(1-5)}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "system"

    @property
    def test_count(self) -> int:
        return len(self.tests)

    @property
    def critical_tests(self) -> list[dict[str, Any]]:
        return [t for t in self.tests if t.get("severity", 0) >= 4]


class ValidationResult(BaseModel):
    """Result of a single adversarial test execution."""

    result_id: str = Field(default_factory=lambda: str(uuid4()))
    plan_id: str = ""
    test_name: str = ""
    category: TestCategory
    verdict: TestVerdict = TestVerdict.UNKNOWN
    duration_ms: int = 0
    attempts: int = 1
    # For FLAKY verdict: results across attempts
    attempt_results: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)
    # Error info for FAIL/CRASH
    error_type: str = ""
    error_message: str = ""
    stack_trace: str = ""
    # Recovery: did the system recover automatically?
    recovered: bool | None = None
    recovery_time_ms: int | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_blocking(self) -> bool:
        """A FAIL or CRASH is always blocking. FLAKY is blocking too (nondeterminism)."""
        return self.verdict in (TestVerdict.FAIL, TestVerdict.CRASH, TestVerdict.FLAKY)

    @property
    def is_reliable_pass(self) -> bool:
        """Only PASS with multiple consistent attempts counts as reliable."""
        return self.verdict == TestVerdict.PASS and self.attempts >= 3


class ValidationReport(BaseModel):
    """Truthful validation report — NEVER optimistic.

    Reports what was tested, what failed, what was skipped.
    Does NOT declare "stable" or "production-ready".
    """

    report_id: str = Field(default_factory=lambda: str(uuid4()))
    target: str = ""
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    results: list[ValidationResult] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> int | None:
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == TestVerdict.PASS)

    @property
    def fail_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == TestVerdict.FAIL)

    @property
    def crash_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == TestVerdict.CRASH)

    @property
    def flaky_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == TestVerdict.FLAKY)

    @property
    def skip_count(self) -> int:
        return sum(1 for r in self.results if r.verdict == TestVerdict.SKIP)

    @property
    def blocking_count(self) -> int:
        return sum(1 for r in self.results if r.is_blocking)

    @property
    def has_blocking_issues(self) -> bool:
        return self.blocking_count > 0

    def generate_truthful_summary(self) -> dict[str, Any]:
        """Generate a truthful summary — never declares 'stable' or 'production-ready'."""
        total = len(self.results)
        if total == 0:
            return {
                "status": "no_tests_run",
                "message": "No validation tests were executed. System state is UNKNOWN.",
            }

        issues = []
        if self.fail_count > 0:
            issues.append(f"{self.fail_count} test(s) failed")
        if self.crash_count > 0:
            issues.append(f"{self.crash_count} test(s) caused crashes")
        if self.flaky_count > 0:
            issues.append(f"{self.flaky_count} test(s) are flaky (nondeterministic)")
        if self.skip_count > 0:
            issues.append(f"{self.skip_count} test(s) were skipped")

        if not issues:
            if self.pass_count == total:
                return {
                    "status": "all_passed",
                    "message": (
                        f"All {total} validation tests passed. "
                        "This does NOT mean the system is stable — only that these specific "
                        "adversarial conditions did not trigger failures. Continue monitoring."
                    ),
                }

        return {
            "status": "has_issues",
            "message": f"Found {len(issues)} issue(s): {'; '.join(issues)}",
            "details": issues,
            "recommendation": (
                "Do NOT deploy to production. Fix blocking issues before proceeding. "
                "Run validation again after fixes."
            ),
        }


class EdgeCase(BaseModel):
    """A documented edge case with trigger conditions and expected behavior."""

    edge_id: str = Field(default_factory=lambda: str(uuid4()))
    target: str = ""  # subsystem/component
    category: TestCategory
    description: str = ""
    trigger_condition: str = ""  # How to trigger this edge case
    expected_behavior: str = ""  # What should happen
    observed_behavior: str = ""  # What actually happened (filled during testing)
    severity: int = Field(ge=1, le=5, default=3)
    # Probability of occurrence (0.0-1.0)
    probability: float = Field(ge=0.0, le=1.0, default=0.1)
    tested: bool = False
    test_result: TestVerdict = TestVerdict.UNKNOWN
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FailureProbability(BaseModel):
    """Failure probability analysis for a component."""

    component: str = ""
    # Probability of failure modes
    crash_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    data_loss_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    hang_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    silent_corruption_probability: float = Field(ge=0.0, le=1.0, default=0.0)
    cascade_probability: float = Field(ge=0.0, le=1.0, default=0.0)

    # Contributing factors
    contributing_factors: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)

    @property
    def overall_risk(self) -> str:
        """Overall risk level — truthful, not optimistic."""
        max_prob = max(
            self.crash_probability,
            self.data_loss_probability,
            self.hang_probability,
            self.silent_corruption_probability,
            self.cascade_probability,
        )
        if max_prob >= 0.5:
            return "HIGH"
        if max_prob >= 0.2:
            return "MEDIUM"
        if max_prob > 0.0:
            return "LOW"
        return "UNKNOWN"  # Zero probability usually means not tested

    @property
    def requires_action(self) -> bool:
        return self.overall_risk in ("HIGH", "MEDIUM") or self.overall_risk == "UNKNOWN"
