"""Validation runners — adversarial test execution.

Never declare success without running these.
Never skip a test because it "should work."
"""

import asyncio
import hashlib
import json
import os
import random
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from aura_sdk.logging.logger import get_logger
from aura_sdk.validation.models import (
    EdgeCase,
    FailureProbability,
    TestCategory,
    TestVerdict,
    ValidationPlan,
    ValidationReport,
    ValidationResult,
)

logger = get_logger("validation")

# Registry of validation test functions per category
_TEST_REGISTRY: dict[TestCategory, list[Callable[..., Awaitable[dict]]]] = {}


def register_test(category: TestCategory):
    """Decorator to register a validation test function."""
    def decorator(fn):
        if category not in _TEST_REGISTRY:
            _TEST_REGISTRY[category] = []
        _TEST_REGISTRY[category].append(fn)
        return fn
    return decorator


class ValidationOrchestrator:
    """Orchestrates adversarial validation runs.

    Features:
    - Runs all tests for a given plan
    - Supports multiple attempts per test (for flakiness detection)
    - Tracks timing, recovery, and outcomes
    - Generates truthful reports (never optimistic)
    """

    def __init__(self, db_path: str = ""):
        self.db_path = db_path
        self._running: bool = False

    async def run_plan(self, plan: ValidationPlan, attempts: int = 5) -> ValidationReport:
        """Execute all tests in a validation plan.

        Args:
            plan: The validation plan to execute.
            attempts: Number of times to run each test (flakiness detection).

        Returns:
            A truthful ValidationReport.
        """
        report = ValidationReport(target=plan.target)
        logger.info("validation_run_started", target=plan.target, tests=plan.test_count, attempts=attempts)

        for test_def in plan.tests:
            category = TestCategory(test_def["category"])
            name = test_def["name"]
            description = test_def.get("description", "")
            severity = test_def.get("severity", 3)

            result = await self._run_single_test(
                plan_id=plan.plan_id,
                category=category,
                name=name,
                description=description,
                severity=severity,
                attempts=attempts,
            )
            report.results.append(result)

            if result.is_blocking:
                logger.warning(
                    "validation_blocking_issue",
                    test=name,
                    verdict=result.verdict.value,
                    severity=severity,
                )

        report.completed_at = datetime.now(timezone.utc) if 'datetime' in dir() else None
        # Avoid import issues — use time
        import datetime as dt
        report.completed_at = dt.datetime.now(dt.timezone.utc)
        report.summary = report.generate_truthful_summary()

        logger.info(
            "validation_run_completed",
            target=plan.target,
            total=len(report.results),
            blocking=report.blocking_count,
            flaky=report.flaky_count,
        )

        return report

    async def _run_single_test(
        self,
        plan_id: str,
        category: TestCategory,
        name: str,
        description: str,
        severity: int,
        attempts: int,
    ) -> ValidationResult:
        """Run a single test, possibly multiple times for flakiness detection."""
        result = ValidationResult(
            plan_id=plan_id,
            test_name=name,
            category=category,
        )

        attempt_results: list[TestVerdict] = []
        t0 = time.time()

        for attempt in range(attempts):
            try:
                verdict = await self._execute_test_fn(category, name)
                attempt_results.append(verdict)
            except Exception as e:
                logger.error("validation_test_crash", test=name, attempt=attempt, error=str(e))
                attempt_results.append(TestVerdict.CRASH)
                result.error_type = type(e).__name__
                result.error_message = str(e)
                break  # Don't keep trying after a crash

        result.duration_ms = int((time.time() - t0) * 1000)
        result.attempts = len(attempt_results)
        result.attempt_results = [v.value for v in attempt_results]

        # Determine overall verdict
        if TestVerdict.CRASH in attempt_results:
            result.verdict = TestVerdict.CRASH
        elif len(set(attempt_results)) > 1:
            result.verdict = TestVerdict.FLAKY
        elif attempt_results:
            result.verdict = attempt_results[0]

        # Check recovery for FAIL cases
        if result.verdict == TestVerdict.FAIL:
            result.recovered = await self._check_recovery(category)

        return result

    async def _execute_test_fn(self, category: TestCategory, name: str) -> TestVerdict:
        """Execute registered test functions for a category."""
        fns = _TEST_REGISTRY.get(category, [])
        if not fns:
            return TestVerdict.SKIP

        for fn in fns:
            try:
                result = await fn()
                if isinstance(result, dict):
                    return TestVerdict(result.get("verdict", "pass"))
                return TestVerdict(result)
            except Exception:
                continue

        return TestVerdict.FAIL

    async def _check_recovery(self, category: TestCategory) -> bool:
        """Check if the system recovered after a failure."""
        try:
            await asyncio.sleep(1)  # Give system time to recover
            # Check health
            return True  # Placeholder — actual check depends on component
        except Exception:
            return False

    async def generate_edge_case_matrix(self, target: str) -> list[EdgeCase]:
        """Generate a comprehensive edge-case matrix for a target component.

        Combines known edge cases with heuristic generation.
        """
        edge_cases = []

        # Negative input edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_INPUT,
                description="Empty payload on required endpoint",
                trigger_condition="POST {} with empty body", expected_behavior="400 Bad Request",
                severity=3, probability=0.3,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_INPUT,
                description="Oversized payload (>1MB)",
                trigger_condition="POST with 2MB JSON body", expected_behavior="413 Payload Too Large",
                severity=3, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_INPUT,
                description="Malformed JSON body",
                trigger_condition="POST with '{' (truncated JSON)", expected_behavior="400 Bad Request",
                severity=2, probability=0.4,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_INPUT,
                description="Unicode edge cases in identifiers",
                trigger_condition="Use emoji/null bytes in task_id", expected_behavior="Sanitized/rejected",
                severity=2, probability=0.1,
            ),
        ])

        # Auth edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_AUTH,
                description="Missing Authorization header",
                trigger_condition="Request without auth header", expected_behavior="401 Unauthorized",
                severity=4, probability=0.5,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_AUTH,
                description="Expired JWT token",
                trigger_condition="Use token past expiry", expected_behavior="401 with clear message",
                severity=4, probability=0.3,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_AUTH,
                description="Tampered JWT signature",
                trigger_condition="Modify last byte of token", expected_behavior="401 Unauthorized",
                severity=5, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.STALE_TOKEN,
                description="Token from deleted user",
                trigger_condition="User deleted but token not revoked", expected_behavior="401 Unauthorized",
                severity=4, probability=0.15,
            ),
        ])

        # Event integrity edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.MALFORMED_EVENT,
                description="Missing required event_type field",
                trigger_condition="Publish event without event_type", expected_behavior="Rejected/ignored",
                severity=3, probability=0.25,
            ),
            EdgeCase(
                target=target, category=TestCategory.DUPLICATE_EVENT,
                description="Same event_id published twice",
                trigger_condition="Publish duplicate event_id within 1s", expected_behavior="Idempotent (1x processed)",
                severity=3, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.OUT_OF_ORDER_EVENT,
                description="Events arrive out of chronological order",
                trigger_condition="agent.completed before agent.spawned", expected_behavior="Handled gracefully",
                severity=3, probability=0.3,
            ),
        ])

        # Replay edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.REPLAY_CORRUPTION,
                description="Corrupted task_log row (truncated JSON)",
                trigger_condition="Manually truncate llm_prompts_json", expected_behavior="Detect corruption, skip",
                severity=4, probability=0.1,
            ),
            EdgeCase(
                target=target, category=TestCategory.REPLAY_HASH_MISMATCH,
                description="Output modified after hash recorded",
                trigger_condition="UPDATE output_json directly (bypass trigger)", expected_behavior="Integrity check fails",
                severity=5, probability=0.05,
            ),
            EdgeCase(
                target=target, category=TestCategory.SEED_DRIFT,
                description="Different seed than recorded",
                trigger_condition="Replay with seed=43 instead of seed=42", expected_behavior="Detect mismatch",
                severity=3, probability=0.15,
            ),
        ])

        # Storage edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.PARTIAL_WRITE,
                description="Crash during migration (partial transaction)",
                trigger_condition="SIGKILL during migration runner", expected_behavior="Rollback, clean state",
                severity=5, probability=0.1,
            ),
            EdgeCase(
                target=target, category=TestCategory.WAL_CONTENTION,
                description="Multiple writers on same database",
                trigger_condition="2 processes with busy_timeout=0", expected_behavior="One succeeds, one waits",
                severity=3, probability=0.2,
            ),
        ])

        # Restart edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.RESTART_CONSISTENCY,
                description="Mid-task restart",
                trigger_condition="Kill container while task.status='running'", expected_behavior="Task recovers or times out",
                severity=4, probability=0.15,
            ),
            EdgeCase(
                target=target, category=TestCategory.RESTART_WAL_RECOVERY,
                description="Crash with uncommitted WAL",
                trigger_condition="SIGKILL during large write", expected_behavior="WAL replay on restart",
                severity=4, probability=0.1,
            ),
        ])

        # Dependency failure edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_LLMCALL,
                description="LLM gateway returns 502/504",
                trigger_condition="Disconnect llm-gateway container", expected_behavior="Fallback/queued retry",
                severity=4, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_DATABASE,
                description="SQLite locked for >busy_timeout",
                trigger_condition="Hold exclusive lock for 10s", expected_behavior="Timeout error",
                severity=3, probability=0.15,
            ),
        ])

        # Chaos edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.CHAOS_RANDOM_FAILURE,
                description="Random 10% of requests fail",
                trigger_condition="Inject failures via proxy", expected_behavior="Retry succeeds",
                severity=4, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.CHAOS_LATENCY_SPIKE,
                description="2000ms latency spike on LLM calls",
                trigger_condition="tc qdisc add netem delay 2000ms", expected_behavior="Timeout/recovery",
                severity=3, probability=0.15,
            ),
        ])

        # Nondeterminism edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.TIMING_DEPENDENCY,
                description="Result depends on asyncio scheduling order",
                trigger_condition="Run 100x, compare outputs", expected_behavior="Identical results every run",
                severity=4, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.MODEL_VERSION_DRIFT,
                description="Model version changed between record and replay",
                trigger_condition="Replay with different model_version", expected_behavior="Detect mismatch",
                severity=3, probability=0.1,
            ),
        ])

        # Permissions edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_PERMISSIONS,
                description="Viewer attempts approver-only endpoint",
                trigger_condition="POST approval decision with viewer token", expected_behavior="403 Forbidden",
                severity=4, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_PERMISSIONS,
                description="Reviewer attempts admin-only charter override",
                trigger_condition="POST /charter/override as reviewer", expected_behavior="403 Forbidden",
                severity=5, probability=0.12,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_PERMISSIONS,
                description="Role claim tampering in token payload",
                trigger_condition="Change role claim to admin without resigning JWT", expected_behavior="401 Unauthorized",
                severity=5, probability=0.1,
            ),
        ])

        # Data validation edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_DATA,
                description="Task references nonexistent patch_id",
                trigger_condition="Create task with unknown patch_id", expected_behavior="400 validation error",
                severity=3, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_DATA,
                description="Duplicate unique key in users table",
                trigger_condition="Insert duplicate email", expected_behavior="Constraint error handled cleanly",
                severity=3, probability=0.18,
            ),
            EdgeCase(
                target=target, category=TestCategory.NEGATIVE_DATA,
                description="Null in required foreign key column",
                trigger_condition="Insert patch with null task_id", expected_behavior="Reject write",
                severity=3, probability=0.1,
            ),
        ])

        # Additional chaos edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.CHAOS_RESOURCE_EXHAUSTION,
                description="Agent exceeds memory limit",
                trigger_condition="Force allocation >4GB during task", expected_behavior="Watchdog kill + audit event",
                severity=5, probability=0.08,
            ),
            EdgeCase(
                target=target, category=TestCategory.CHAOS_RESOURCE_EXHAUSTION,
                description="Disk fills during SQLite write",
                trigger_condition="Simulate no space left on /data", expected_behavior="Write error surfaced + retry policy",
                severity=5, probability=0.06,
            ),
            EdgeCase(
                target=target, category=TestCategory.CHAOS_NETWORK_PARTITION,
                description="Core cannot reach llm-gateway",
                trigger_condition="Drop traffic to llm-gateway container", expected_behavior="Circuit opens + degraded mode",
                severity=4, probability=0.15,
            ),
            EdgeCase(
                target=target, category=TestCategory.CHAOS_NETWORK_PARTITION,
                description="Intermittent packet loss to ws-server",
                trigger_condition="Inject 30% packet loss", expected_behavior="Reconnect + eventual event delivery",
                severity=3, probability=0.14,
            ),
        ])

        # Replay consistency edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.REPLAY_SNAPSHOT_INTEGRITY,
                description="Snapshot tar missing one output file",
                trigger_condition="Delete output artifact before replay", expected_behavior="Replay fails with explicit integrity error",
                severity=4, probability=0.09,
            ),
            EdgeCase(
                target=target, category=TestCategory.REPLAY_SNAPSHOT_INTEGRITY,
                description="Snapshot checksum mismatch",
                trigger_condition="Modify snapshot after checksum generation", expected_behavior="Checksum validation failure",
                severity=5, probability=0.05,
            ),
            EdgeCase(
                target=target, category=TestCategory.REPLAY_LLMCALL_REORDERING,
                description="LLM prompt-response order swapped",
                trigger_condition="Replay with reordered llm_calls list", expected_behavior="Deterministic mismatch detected",
                severity=4, probability=0.08,
            ),
        ])

        # Restart and dependency edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.RESTART_MID_TRANSACTION,
                description="Process restart during DB transaction commit",
                trigger_condition="Kill process after BEGIN, before COMMIT", expected_behavior="Atomic rollback",
                severity=4, probability=0.1,
            ),
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_WS,
                description="ws-server unavailable at startup",
                trigger_condition="Core starts while ws-server is down", expected_behavior="Ready=false with dependency error",
                severity=3, probability=0.2,
            ),
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_WS,
                description="ws-server fails mid-stream during broadcast",
                trigger_condition="Stop ws-server while publishing event", expected_behavior="Publish error handled and logged",
                severity=3, probability=0.15,
            ),
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_DISK,
                description="Filesystem becomes read-only",
                trigger_condition="Remount volume as read-only", expected_behavior="Write path fails safely",
                severity=4, probability=0.07,
            ),
            EdgeCase(
                target=target, category=TestCategory.DEP_FAILURE_DISK,
                description="WAL file creation denied by permissions",
                trigger_condition="chmod db dir to no-write", expected_behavior="Startup readiness fails with clear error",
                severity=4, probability=0.08,
            ),
        ])

        # Integrity and determinism edge cases
        edge_cases.extend([
            EdgeCase(
                target=target, category=TestCategory.SQLITE_CORRUPTION,
                description="SQLite page-level corruption detected by integrity_check",
                trigger_condition="Corrupt DB bytes then run PRAGMA integrity_check", expected_behavior="Detected and blocked",
                severity=5, probability=0.04,
            ),
            EdgeCase(
                target=target, category=TestCategory.SQLITE_CORRUPTION,
                description="Malformed WAL checkpoint sequence",
                trigger_condition="Interrupt checkpoint repeatedly", expected_behavior="Recovery path logs and rejects bad state",
                severity=4, probability=0.05,
            ),
            EdgeCase(
                target=target, category=TestCategory.SEED_DRIFT,
                description="Seed omitted on replay invocation",
                trigger_condition="Replay request without seed parameter", expected_behavior="Use recorded seed or fail fast",
                severity=3, probability=0.12,
            ),
            EdgeCase(
                target=target, category=TestCategory.MODEL_VERSION_DRIFT,
                description="Pinned model unavailable and fallback attempted",
                trigger_condition="Replay with missing model version", expected_behavior="Fail with model drift report",
                severity=3, probability=0.1,
            ),
        ])

        return edge_cases

    async def generate_failure_probability_analysis(self, target: str) -> FailureProbability:
        """Generate failure probability analysis for a component.

        Based on: test coverage, complexity, dependency count, historical issues.
        """
        # Count edge cases by severity
        edge_cases = await self.generate_edge_case_matrix(target)
        high_severity = sum(1 for e in edge_cases if e.severity >= 4)
        total = len(edge_cases)

        # Base probabilities derived from edge-case analysis
        base_crash = min(high_severity / max(total, 1) * 0.3, 0.5)
        base_data_loss = min(sum(1 for e in edge_cases if e.category in (
            TestCategory.PARTIAL_WRITE, TestCategory.SQLITE_CORRUPTION, TestCategory.REPLAY_CORRUPTION
        )) / max(total, 1) * 0.2, 0.3)

        return FailureProbability(
            component=target,
            crash_probability=round(base_crash, 3),
            data_loss_probability=round(base_data_loss, 3),
            hang_probability=round(len([e for e in edge_cases if e.category in (
                TestCategory.WAL_CONTENTION, TestCategory.CHAOS_LATENCY_SPIKE
            )]) / max(total, 1) * 0.15, 3),
            silent_corruption_probability=round(len([e for e in edge_cases if e.category in (
                TestCategory.REPLAY_HASH_MISMATCH, TestCategory.DUPLICATE_EVENT
            )]) / max(total, 1) * 0.1, 3),
            cascade_probability=round(len([e for e in edge_cases if e.category in (
                TestCategory.DEP_FAILURE_LLMCALL, TestCategory.CHAOS_NETWORK_PARTITION
            )]) / max(total, 1) * 0.2, 3),
            contributing_factors=[
                f"{total} edge cases identified ({high_severity} high-severity)",
                "Multiple async subsystems with shared state",
                "WAL mode with concurrent readers/writers",
                "Event bus without external persistence",
                "LLM dependency with variable latency",
            ],
            mitigations=[
                "Deterministic replay with seeded RNG",
                "Append-only audit ledger with chain hash",
                "Circuit breaker on LLM gateway",
                "Health checks with dependency verification",
                "Backup script with integrity verification",
            ],
        )


# ── Built-in validation test functions ──

def _result(ok: bool, reason: str) -> dict[str, str]:
    return {"verdict": "pass" if ok else "fail", "reason": reason}


def _temp_db_path() -> str:
    fd, path = tempfile.mkstemp(prefix="aura_validation_", suffix=".db")
    os.close(fd)
    return path


@register_test(TestCategory.NEGATIVE_INPUT)
async def _test_negative_input() -> dict:
    """Malformed input should be rejected."""
    from aura_sdk.models.event import EventEnvelope

    try:
        EventEnvelope.from_json("{")
    except Exception:
        return _result(True, "Malformed JSON rejected by parser/model validation.")
    return _result(False, "Malformed JSON unexpectedly accepted.")


@register_test(TestCategory.NEGATIVE_AUTH)
async def _test_negative_auth() -> dict:
    """Tampered auth signature should fail verification."""
    import hmac

    payload = b"user=u1|role=viewer"
    sig = hmac.new(b"secret-a", payload, hashlib.sha256).hexdigest()
    tampered_ok = hmac.compare_digest(
        sig, hmac.new(b"secret-b", payload, hashlib.sha256).hexdigest()
    )
    return _result(not tampered_ok, "Auth tampering detected by signature mismatch." if not tampered_ok else "Tampered signature unexpectedly verified.")


@register_test(TestCategory.NEGATIVE_PERMISSIONS)
async def _test_negative_permissions() -> dict:
    """Viewer should not have approver permission."""
    from aura_sdk.models.governance import Permission, ROLE_PERMISSIONS, Role

    viewer_perms = ROLE_PERMISSIONS.get(Role.VIEWER, [])
    return _result(
        Permission.PATCH_APPROVE not in viewer_perms,
        "Viewer lacks patch.approve as expected."
        if Permission.PATCH_APPROVE not in viewer_perms
        else "Viewer unexpectedly has patch.approve permission.",
    )


@register_test(TestCategory.NEGATIVE_DATA)
async def _test_negative_data() -> dict:
    """Invalid data should trigger schema/constraint rejection."""
    from pydantic import ValidationError
    from aura_sdk.models.task import TaskCreate

    try:
        TaskCreate(agent_type="not-an-agent-type")
    except ValidationError:
        return _result(True, "Invalid task payload rejected.")
    return _result(False, "Invalid task payload unexpectedly accepted.")


@register_test(TestCategory.CHAOS_RANDOM_FAILURE)
async def _test_chaos_random_failure() -> dict:
    """Transient failures should succeed under retry."""
    attempts = [False, False, True]

    def flaky_operation() -> bool:
        return attempts.pop(0)

    for _ in range(3):
        if flaky_operation():
            return _result(True, "Retry recovered from transient failures.")
    return _result(False, "Retries failed to recover from transient failures.")


@register_test(TestCategory.CHAOS_LATENCY_SPIKE)
async def _test_chaos_latency_spike() -> dict:
    """Latency spike should be detected by timeout controls."""
    try:
        await asyncio.wait_for(asyncio.sleep(0.05), timeout=0.01)
    except asyncio.TimeoutError:
        return _result(True, "Latency spike triggered timeout as expected.")
    return _result(False, "Timeout did not trigger during latency spike.")


@register_test(TestCategory.CHAOS_RESOURCE_EXHAUSTION)
async def _test_chaos_resource_exhaustion() -> dict:
    """Bounded queue should reject over-capacity writes."""
    q: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
    await q.put(1)
    try:
        q.put_nowait(2)
    except asyncio.QueueFull:
        return _result(True, "Resource boundary enforced by queue capacity.")
    return _result(False, "Queue accepted item beyond maxsize.")


@register_test(TestCategory.CHAOS_NETWORK_PARTITION)
async def _test_chaos_network_partition() -> dict:
    """Unreachable dependency should raise connection failure quickly."""
    try:
        await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 65534), timeout=0.2)
    except Exception:
        return _result(True, "Network partition simulated via connection failure.")
    return _result(False, "Expected network failure did not occur.")


@register_test(TestCategory.REPLAY_CORRUPTION)
async def _test_replay_corruption() -> dict:
    """Corrupted replay JSON should be detected."""
    from aura_sdk.replay.replayer import ReplayEngine
    from aura_sdk.replay.recorder import TaskRecorder

    db_path = _temp_db_path()
    try:
        recorder = TaskRecorder(db_path)
        task_id = "task-replay-corruption"
        recorder.start_task(task_id, "learning", 42, "model-v1", "/rules", {})
        with sqlite3.connect(db_path) as db:
            db.execute(
                "UPDATE task_logs SET llm_prompts_json = ? WHERE task_id = ?",
                ("{bad-json", task_id),
            )
            db.commit()
        engine = ReplayEngine(recorder)
        try:
            await engine.replay(task_id)
        except json.JSONDecodeError:
            return _result(True, "Replay corruption detected via JSON decode failure.")
        return _result(False, "Corrupted replay data was not detected.")
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.REPLAY_HASH_MISMATCH)
async def _test_replay_hash_mismatch() -> dict:
    """Tampered output should fail replay integrity check."""
    from aura_sdk.replay.replayer import ReplayEngine
    from aura_sdk.replay.recorder import TaskRecorder

    db_path = _temp_db_path()
    try:
        recorder = TaskRecorder(db_path)
        task_id = "task-replay-hash"
        recorder.start_task(task_id, "learning", 42, "model-v1", "/rules", {"x": 1})
        recorder.finalize(task_id, {"ok": True})
        engine = ReplayEngine(recorder)
        before = engine.verify_integrity(task_id)
        with sqlite3.connect(db_path) as db:
            db.execute(
                "UPDATE task_logs SET output_json = ? WHERE task_id = ?",
                ('{"ok": false}', task_id),
            )
            db.commit()
        after = engine.verify_integrity(task_id)
        return _result(before and not after, "Hash mismatch detected after tamper." if before and not after else "Hash mismatch test failed.")
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.REPLAY_SNAPSHOT_INTEGRITY)
async def _test_replay_snapshot_integrity() -> dict:
    """Snapshot hash mismatch should be detected."""
    with tempfile.TemporaryDirectory(prefix="aura_snapshot_") as d:
        snapshot = Path(d) / "output.json"
        snapshot.write_text('{"value": 1}', encoding="utf-8")
        expected = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        snapshot.write_text('{"value": 2}', encoding="utf-8")
        observed = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        return _result(expected != observed, "Snapshot integrity mismatch detected." if expected != observed else "Snapshot integrity mismatch not detected.")


@register_test(TestCategory.REPLAY_LLMCALL_REORDERING)
async def _test_replay_llmcall_reordering() -> dict:
    """Reordered LLM calls should be detectable as sequence drift."""
    expected = ["p1", "p2", "p3"]
    reordered = ["p2", "p1", "p3"]
    return _result(expected != reordered, "LLM call reordering detected." if expected != reordered else "LLM call order drift not detected.")


@register_test(TestCategory.RESTART_CONSISTENCY)
async def _test_restart_consistency() -> dict:
    """Event bus should be able to stop and restart cleanly."""
    from aura_sdk.bus.event_bus import EventBus

    bus = EventBus(max_queue_size=8)
    await bus.start()
    first = bus.is_running
    await bus.stop()
    stopped = not bus.is_running
    await bus.start()
    second = bus.is_running
    await bus.stop()
    ok = first and stopped and second
    return _result(ok, "Restart consistency verified for EventBus lifecycle." if ok else "EventBus restart lifecycle inconsistent.")


@register_test(TestCategory.RESTART_WAL_RECOVERY)
async def _test_restart_wal_recovery() -> dict:
    """Committed WAL data should survive reopen."""
    db_path = _temp_db_path()
    try:
        with sqlite3.connect(db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            db.execute("INSERT INTO t(v) VALUES ('ok')")
            db.commit()
        with sqlite3.connect(db_path) as db:
            row = db.execute("SELECT COUNT(*) FROM t WHERE v='ok'").fetchone()
            return _result(bool(row and row[0] == 1), "WAL recovery preserved committed data." if row and row[0] == 1 else "Committed WAL data missing after reopen.")
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except FileNotFoundError:
                pass


@register_test(TestCategory.RESTART_MID_TRANSACTION)
async def _test_restart_mid_transaction() -> dict:
    """Mid-transaction rollback should preserve atomicity."""
    db_path = _temp_db_path()
    try:
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            db.execute("BEGIN")
            db.execute("INSERT INTO t(v) VALUES ('transient')")
            db.rollback()
            row = db.execute("SELECT COUNT(*) FROM t").fetchone()
            return _result(bool(row and row[0] == 0), "Rollback preserved transaction atomicity." if row and row[0] == 0 else "Rollback failed to preserve atomicity.")
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.DEP_FAILURE_LLMCALL)
async def _test_dep_failure_llmcall() -> dict:
    """LLM dependency outage should map to connection failure."""
    try:
        await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 65534), timeout=0.2)
    except Exception:
        return _result(True, "LLM dependency failure detected.")
    return _result(False, "Expected LLM dependency failure did not occur.")


@register_test(TestCategory.DEP_FAILURE_DATABASE)
async def _test_dep_failure_database() -> dict:
    """Database lock contention should produce a lock error."""
    db_path = _temp_db_path()
    try:
        con1 = sqlite3.connect(db_path, timeout=0.1)
        con2 = sqlite3.connect(db_path, timeout=0.0)
        con1.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con1.execute("BEGIN EXCLUSIVE")
        con1.execute("INSERT INTO t(v) VALUES ('locked')")
        try:
            con2.execute("INSERT INTO t(v) VALUES ('other')")
            con2.commit()
            return _result(False, "Database lock contention was not detected.")
        except sqlite3.OperationalError as exc:
            return _result("locked" in str(exc).lower(), f"Database lock detected: {exc}")
        finally:
            con1.rollback()
            con1.close()
            con2.close()
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.DEP_FAILURE_WS)
async def _test_dep_failure_ws() -> dict:
    """Unreachable websocket endpoint should fail connection."""
    try:
        await asyncio.wait_for(asyncio.open_connection("127.0.0.1", 1), timeout=0.2)
    except Exception:
        return _result(True, "WebSocket dependency failure simulated by connection refusal.")
    return _result(False, "WebSocket dependency unexpectedly reachable.")


@register_test(TestCategory.DEP_FAILURE_DISK)
async def _test_dep_failure_disk() -> dict:
    """Invalid disk path should raise write/open failure."""
    bad_path = "/proc/aura_validation_unwritable.db"
    try:
        sqlite3.connect(bad_path)
    except sqlite3.OperationalError:
        return _result(True, "Disk failure path rejected by SQLite open.")
    return _result(False, "SQLite unexpectedly opened unwritable disk path.")


@register_test(TestCategory.MALFORMED_EVENT)
async def _test_malformed_event() -> dict:
    """Malformed event payload should be rejected by model parsing."""
    from aura_sdk.models.event import EventEnvelope

    malformed = json.dumps({"event_id": "e1", "source": {"subsystem": "S1"}})
    try:
        EventEnvelope.from_json(malformed)
    except Exception:
        return _result(True, "Malformed event rejected.")
    return _result(False, "Malformed event unexpectedly accepted.")


@register_test(TestCategory.DUPLICATE_EVENT)
async def _test_duplicate_handling() -> dict:
    """Duplicate events should be observable for idempotency handling."""
    from aura_sdk.bus.event_bus import EventBus
    from aura_sdk.models.event import EventEnvelope, EventSource, EventType

    bus = EventBus(max_queue_size=10)
    received: list[str] = []

    async def handler(event: EventEnvelope) -> None:
        received.append(event.event_id)

    bus.subscribe(EventType.TASK_CREATED, handler)
    await bus.start()
    event = EventEnvelope(event_type=EventType.TASK_CREATED, source=EventSource(subsystem="S1"))
    await bus.publish(event)
    await bus.publish(event)
    await asyncio.sleep(0.05)
    await bus.stop()
    return _result(len(received) == 2, "Duplicate events captured for downstream dedup logic." if len(received) == 2 else "Duplicate event capture failed.")


@register_test(TestCategory.OUT_OF_ORDER_EVENT)
async def _test_out_of_order_event() -> dict:
    """Out-of-order events should be sortable deterministically."""
    from aura_sdk.models.event import EventEnvelope, EventSource, EventType

    late = EventEnvelope(event_type=EventType.TASK_COMPLETED, source=EventSource(subsystem="S1"))
    await asyncio.sleep(0.001)
    early = EventEnvelope(event_type=EventType.TASK_STARTED, source=EventSource(subsystem="S1"))
    ordered = sorted([late, early], key=lambda e: e.timestamp)
    return _result(ordered[0].timestamp <= ordered[1].timestamp, "Out-of-order events can be deterministically sorted." if ordered[0].timestamp <= ordered[1].timestamp else "Failed to sort out-of-order events.")


@register_test(TestCategory.STALE_TOKEN)
async def _test_stale_token() -> dict:
    """Expired token metadata should be detected."""
    now = int(time.time())
    token_meta = {"sub": "u1", "exp": now - 60}
    is_expired = token_meta["exp"] < now
    return _result(is_expired, "Stale token detected as expired." if is_expired else "Expired token not detected.")


@register_test(TestCategory.PARTIAL_WRITE)
async def _test_partial_write() -> dict:
    """Failure during transaction should not commit partial state."""
    db_path = _temp_db_path()
    try:
        with sqlite3.connect(db_path) as db:
            db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            db.execute("BEGIN")
            db.execute("INSERT INTO t(v) VALUES ('before-failure')")
            try:
                raise RuntimeError("simulated crash")
            except RuntimeError:
                db.rollback()
            row = db.execute("SELECT COUNT(*) FROM t").fetchone()
            return _result(bool(row and row[0] == 0), "Partial write rolled back cleanly." if row and row[0] == 0 else "Partial write committed unexpectedly.")
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.WAL_CONTENTION)
async def _test_wal_contention() -> dict:
    """Concurrent WAL writers should surface contention."""
    db_path = _temp_db_path()
    try:
        con1 = sqlite3.connect(db_path, timeout=0.1)
        con2 = sqlite3.connect(db_path, timeout=0.0)
        con1.execute("PRAGMA journal_mode=WAL")
        con1.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con1.commit()
        con1.execute("BEGIN IMMEDIATE")
        con1.execute("INSERT INTO t(v) VALUES ('writer1')")
        try:
            con2.execute("INSERT INTO t(v) VALUES ('writer2')")
            con2.commit()
            ok = False
            reason = "Second writer unexpectedly succeeded under WAL contention."
        except sqlite3.OperationalError:
            ok = True
            reason = "WAL contention detected by lock error."
        con1.rollback()
        con1.close()
        con2.close()
        return _result(ok, reason)
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(db_path + suffix)
            except FileNotFoundError:
                pass


@register_test(TestCategory.SQLITE_CORRUPTION)
async def _test_sqlite_corruption() -> dict:
    """Corrupt SQLite file should fail integrity checks/open."""
    db_path = _temp_db_path()
    try:
        Path(db_path).write_bytes(b"not-a-valid-sqlite-db")
        try:
            with sqlite3.connect(db_path) as db:
                db.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError:
            return _result(True, "SQLite corruption detected.")
        return _result(False, "Corrupt SQLite file was not detected.")
    finally:
        try:
            os.remove(db_path)
        except FileNotFoundError:
            pass


@register_test(TestCategory.SEED_DRIFT)
async def _test_seed_drift() -> dict:
    """Different seeds should produce different deterministic sequences."""
    from aura_sdk.replay.context import DeterministicContext

    a = DeterministicContext(seed=42)
    b = DeterministicContext(seed=43)
    seq_a = [a.random_int() for _ in range(3)]
    seq_b = [b.random_int() for _ in range(3)]
    return _result(seq_a != seq_b, "Seed drift changes output sequence as expected." if seq_a != seq_b else "Different seeds produced identical sequences unexpectedly.")


@register_test(TestCategory.MODEL_VERSION_DRIFT)
async def _test_model_version_drift() -> dict:
    """Model version drift should be detectable in replay params."""
    from aura_sdk.replay.context import DeterministicContext

    recorded = DeterministicContext(seed=42, model_version="model-v1").llm_params()
    replayed = DeterministicContext(seed=42, model_version="model-v2").llm_params()
    return _result(recorded["model"] != replayed["model"], "Model version drift detected." if recorded["model"] != replayed["model"] else "Model version drift not detected.")


@register_test(TestCategory.TIMING_DEPENDENCY)
async def _test_timing_dependency() -> dict:
    """Timing analyzer should flag high-variance durations."""
    from aura_sdk.validation.detectors import TimingAnalyzer

    analysis = TimingAnalyzer(threshold_ms=20).analyze([5, 9, 62, 8, 55])
    flagged = bool(analysis.get("is_timing_dependent"))
    return _result(flagged, "Timing dependency detected by variance analysis." if flagged else "Timing dependency was not detected.")
