"""Nondeterminism and flaky-behavior detection engines.

Detects hidden sources of nondeterminism that can break replay
and cause unpredictable behavior.
"""

import hashlib
import json
import time
from collections import Counter
from typing import Any

from aura_sdk.logging.logger import get_logger
from aura_sdk.validation.models import TestVerdict

logger = get_logger("validation.detectors")


class NondeterminismDetector:
    """Detects sources of nondeterminism in code execution.

    Checks for:
    - Unseeded random usage
    - Set/dict iteration order
    - Timing-dependent logic
    - Async scheduling effects
    """

    def __init__(self, trials: int = 10):
        self.trials = trials

    async def detect_in_function(
        self, fn, *args, **kwargs
    ) -> dict[str, Any]:
        """Run a function multiple times and compare outputs.

        Returns:
            Dict with: is_deterministic, variance, sample_outputs
        """
        import asyncio

        outputs = []
        durations = []

        for trial in range(self.trials):
            start = time.time()
            try:
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(*args, **kwargs)
                else:
                    result = fn(*args, **kwargs)
                outputs.append(self._normalize_output(result))
            except Exception as e:
                outputs.append(f"EXCEPTION:{type(e).__name__}:{e}")
            durations.append(int((time.time() - start) * 1000))

        # Compare outputs
        counter = Counter(outputs)
        most_common = counter.most_common(1)[0]
        is_deterministic = most_common[1] == self.trials
        unique_outputs = len(counter)

        result = {
            "is_deterministic": is_deterministic,
            "unique_outputs": unique_outputs,
            "majority_count": most_common[1],
            "trials": self.trials,
            "variance_ms": max(durations) - min(durations) if durations else 0,
            "duration_samples": durations,
            "distinct_hashes": list(counter.keys())[:5],
        }

        if not is_deterministic:
            logger.warning(
                "nondeterminism_detected",
                function=fn.__name__,
                unique=unique_outputs,
                trials=self.trials,
            )

        return result

    def check_code_for_nondeterminism(self, source_code: str) -> list[dict[str, Any]]:
        """Static analysis: scan code for common nondeterminism sources.

        Returns list of findings with line numbers.
        """
        findings = []
        lines = source_code.split('\n')

        risky_patterns = [
            ("random.random()", "Unseeded random — use DeterministicContext"),
            ("random.choice(", "Unseeded random — use DeterministicContext"),
            ("random.randint(", "Unseeded random — use DeterministicContext"),
            ("random.shuffle(", "Unseeded random — use DeterministicContext"),
            ("set(", "Set iteration order — convert to sorted list"),
            ("dict(", "Dict iteration order — use OrderedDict or sort"),
            (".keys()", "Dict keys iteration — wrap in sorted()"),
            (".values()", "Dict values iteration — wrap in sorted()"),
            ("time.time()", "Timing dependency — use deterministic timestamp"),
            ("datetime.now()", "Timing dependency — use injected clock"),
            ("asyncio.gather(", "Concurrent execution — order may vary"),
            ("hash(", "Built-in hash non-deterministic across runs"),
            ("id(", "Object ID non-deterministic across runs"),
        ]

        for lineno, line in enumerate(lines, 1):
            for pattern, reason in risky_patterns:
                if pattern in line and '#' not in line.split(pattern)[0]:
                    findings.append({
                        "line": lineno,
                        "code": line.strip(),
                        "pattern": pattern,
                        "reason": reason,
                        "severity": "warning",
                    })

        return findings

    def _normalize_output(self, output: Any) -> str:
        """Normalize output for comparison."""
        if isinstance(output, (dict, list)):
            return hashlib.sha256(
                json.dumps(output, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
        return str(output)


class FlakyTestDetector:
    """Detects flaky tests by running them multiple times.

    A test is flaky if:
    - It produces different results across runs
    - It has timing-dependent behavior
    - It depends on system state
    """

    def __init__(self, min_pass_rate: float = 0.9, max_runs: int = 20):
        self.min_pass_rate = min_pass_rate
        self.max_runs = max_runs

    async def analyze_test(
        self, test_fn, *args, **kwargs
    ) -> dict[str, Any]:
        """Run a test multiple times and analyze flakiness.

        Returns:
            Dict with: is_flaky, pass_rate, run_count, results_distribution
        """
        import asyncio

        results = []

        for run in range(self.max_runs):
            try:
                if asyncio.iscoroutinefunction(test_fn):
                    result = await test_fn(*args, **kwargs)
                else:
                    result = test_fn(*args, **kwargs)
                results.append("pass" if result else "fail")
            except Exception as e:
                results.append(f"error:{type(e).__name__}")

        pass_count = results.count("pass")
        pass_rate = pass_count / len(results) if results else 0
        is_flaky = pass_rate > 0 and pass_rate < 1.0
        is_consistently_failing = pass_rate == 0 and len(results) > 0

        distribution = Counter(results)

        result = {
            "is_flaky": is_flaky,
            "is_consistently_failing": is_consistently_failing,
            "pass_rate": round(pass_rate, 3),
            "run_count": len(results),
            "pass_count": pass_count,
            "distribution": dict(distribution),
            "recommendation": self._recommendation(is_flaky, is_consistently_failing, pass_rate),
        }

        if is_flaky:
            logger.warning(
                "flaky_test_detected",
                test=test_fn.__name__,
                pass_rate=pass_rate,
                distribution=dict(distribution),
            )

        return result

    def _recommendation(self, is_flaky: bool, consistently_failing: bool, pass_rate: float) -> str:
        if consistently_failing:
            return "Test is consistently failing — fix the underlying bug before anything else."
        if is_flaky:
            if pass_rate < 0.5:
                return "Highly flaky (<50% pass) — likely race condition or timing dependency."
            return f"Moderately flaky ({pass_rate*100:.0f}% pass) — investigate nondeterminism sources."
        if pass_rate == 1.0:
            return "Test is stable across all runs — BUT this doesn't prove correctness."
        return "Analysis inconclusive."


class TimingAnalyzer:
    """Analyzes timing variance to detect timing-dependent behavior."""

    def __init__(self, threshold_ms: int = 50):
        self.threshold_ms = threshold_ms

    def analyze(self, durations_ms: list[int]) -> dict[str, Any]:
        """Analyze a list of execution durations.

        Returns:
            Dict with timing statistics and timing-dependent verdict.
        """
        if not durations_ms:
            return {"error": "No timing data"}

        n = len(durations_ms)
        mean = sum(durations_ms) / n
        variance = sum((d - mean) ** 2 for d in durations_ms) / n
        std_dev = variance ** 0.5
        cv = std_dev / mean if mean > 0 else 0  # Coefficient of variation

        return {
            "samples": n,
            "mean_ms": round(mean, 1),
            "std_dev_ms": round(std_dev, 1),
            "min_ms": min(durations_ms),
            "max_ms": max(durations_ms),
            "range_ms": max(durations_ms) - min(durations_ms),
            "cv": round(cv, 3),
            "is_timing_dependent": (max(durations_ms) - min(durations_ms)) > self.threshold_ms,
            "threshold_ms": self.threshold_ms,
        }
