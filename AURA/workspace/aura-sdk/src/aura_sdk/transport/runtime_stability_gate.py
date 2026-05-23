"""Runtime stability gating for incremental migration orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeStabilityGateResult:
    runtime_stability_gate_report: dict[str, Any]
    stability_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success", "supported"}
    return False


def evaluate_runtime_stability_gate(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    migration_dependency_graph: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RuntimeStabilityGateResult:
    runtime = _as_dict(runtime_evidence)
    portability = _as_dict(runtime_portability_analysis)
    dependency_graph = _as_dict(migration_dependency_graph)
    replay = _as_dict(replay_traces)
    governance = _as_dict(governance_state)

    process_success = _is_true(runtime.get("process_success", runtime.get("playback_completion", False)))
    playback_completion = _is_true(runtime.get("playback_completion", False))
    runtime_seconds = _to_float(runtime.get("playback_runtime_seconds", 0.0))
    expected_seconds = _to_float(runtime.get("expected_runtime_seconds", 25.0), 25.0)

    timing_delta = abs(runtime_seconds - expected_seconds)
    timing_ok = expected_seconds <= 0.0 or timing_delta <= 2.5

    replay_ok = _is_true(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    blocked_unsafe = len([node for node in _as_list(_as_dict(portability).get("runtime_portability_blockers")) if isinstance(node, dict) and str(node.get("severity", "")).upper() == "HIGH"])

    dependency_high_risk = len(
        [
            row
            for row in _as_list(dependency_graph.get("nodes"))
            if isinstance(row, dict) and str(row.get("risk", "")).upper() == "HIGH"
        ]
    )

    governance_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )

    gates = [
        {
            "gate": "runtime_execution_success",
            "passed": process_success and playback_completion,
            "severity": "HIGH",
            "details": {
                "process_success": process_success,
                "playback_completion": playback_completion,
            },
        },
        {
            "gate": "runtime_timing_window",
            "passed": timing_ok,
            "severity": "MEDIUM",
            "details": {
                "observed_seconds": runtime_seconds,
                "expected_seconds": expected_seconds,
                "delta_seconds": round(timing_delta, 3),
            },
        },
        {
            "gate": "runtime_portability_blockers",
            "passed": blocked_unsafe == 0,
            "severity": "HIGH",
            "details": {
                "blocked_unsafe_count": blocked_unsafe,
            },
        },
        {
            "gate": "replay_determinism",
            "passed": replay_ok,
            "severity": "HIGH",
            "details": {
                "deterministic_event_ordering": _is_true(replay.get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
            },
        },
        {
            "gate": "governance_boundary",
            "passed": not governance_violation,
            "severity": "HIGH",
            "details": {
                "governance_violation": governance_violation,
            },
        },
        {
            "gate": "dependency_risk_containment",
            "passed": dependency_high_risk <= 6,
            "severity": "MEDIUM",
            "details": {
                "dependency_high_risk_count": dependency_high_risk,
            },
        },
    ]

    failed_high = len([g for g in gates if not bool(g.get("passed")) and str(g.get("severity", "")).upper() == "HIGH"])
    failed_medium = len([g for g in gates if not bool(g.get("passed")) and str(g.get("severity", "")).upper() == "MEDIUM"])

    stability_score = round(max(0.0, min(1.0, 1.0 - 0.22 * failed_high - 0.08 * failed_medium)), 3)

    classification = "PASS"
    if failed_high > 0:
        classification = "FAIL_CLOSED"
    elif failed_medium > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_stability_gate_report",
        "target_id": str(target_id),
        "classification": classification,
        "stability_score": stability_score,
        "gates": gates,
        "summary": {
            "failed_high": failed_high,
            "failed_medium": failed_medium,
            "total_gates": len(gates),
        },
        "runtime_truth_precedence": True,
        "advisory_only_orchestration": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimeStabilityGateResult(
        runtime_stability_gate_report=payload,
        stability_score=stability_score,
        deterministic_fingerprint=fingerprint,
    )
