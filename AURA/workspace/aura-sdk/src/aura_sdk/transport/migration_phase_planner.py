"""Migration phase planner for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationPhasePlanResult:
    migration_phase_plan: dict[str, Any]
    plan_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success", "supported"}
    return False


def build_migration_phase_plan(
    *,
    target_id: str,
    portability_blocker_report: Mapping[str, Any],
    abstraction_gap_report: Mapping[str, Any],
    upstream_equivalence_confidence: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> MigrationPhasePlanResult:
    blockers = _as_dict(portability_blocker_report)
    gaps = _as_dict(abstraction_gap_report)
    confidence = _as_dict(upstream_equivalence_confidence)
    runtime = _as_dict(runtime_portability_analysis)
    governance = _as_dict(governance_state)

    blocked_count = int(_as_dict(blockers.get("summary", {})).get("blocked_unsafe_count", 0) or 0)
    gap_score = float(gaps.get("abstraction_gap_score", 0.0) or 0.0)
    overall_conf = float(_as_dict(confidence.get("scores", {})).get("overall_confidence", 0.0) or 0.0)
    runtime_score = float(runtime.get("runtime_portability_score", 0.0) or 0.0)

    governance_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )

    phases = [
        {
            "phase": "phase_1_blocker_isolation",
            "goal": "stabilize vendor/runtime blocker inventory and fail-closed gating",
            "entry_criteria": ["runtime_truth_precedence_enabled", "governance_fail_closed_enabled"],
            "exit_criteria": ["blocked_unsafe_count_non_increasing", "deterministic_trace_stable"],
            "autonomy": "ADVISORY_ONLY",
        },
        {
            "phase": "phase_2_lifecycle_and_topology_alignment",
            "goal": "reduce lifecycle mismatch and DPCM/FE-BE abstraction gaps",
            "entry_criteria": ["phase_1_completed"],
            "exit_criteria": ["lifecycle_mismatch_reduced", "topology_conversion_confidence_improved"],
            "autonomy": "ADVISORY_ONLY",
        },
        {
            "phase": "phase_3_equivalence_hardening",
            "goal": "increase upstream equivalence coverage under replay constraints",
            "entry_criteria": ["phase_2_completed"],
            "exit_criteria": ["equivalence_confidence_threshold_met", "replay_determinism_preserved"],
            "autonomy": "GOVERNED_ONLY",
        },
        {
            "phase": "phase_4_governed_conversion_readiness",
            "goal": "produce governed migration recommendations with bounded risk",
            "entry_criteria": ["phase_3_completed"],
            "exit_criteria": ["risk_classification_within_threshold", "no_autonomous_mutation_paths"],
            "autonomy": "GOVERNED_ONLY",
        },
    ]

    if governance_violation or blocked_count > 0:
        classification = "FAIL_CLOSED"
    elif gap_score >= 0.5 or overall_conf < 0.45 or runtime_score < 0.45:
        classification = "ADVISORY_ONLY"
    else:
        classification = "PASS"

    plan_confidence = round(max(0.0, min(1.0, 0.45 * overall_conf + 0.3 * runtime_score + 0.25 * max(0.0, 1.0 - gap_score))), 3)

    payload = {
        "schema_version": "1.0",
        "report_name": "migration_phase_plan",
        "target_id": str(target_id),
        "classification": classification,
        "plan_confidence": plan_confidence,
        "phases": phases,
        "risk_inputs": {
            "blocked_unsafe_count": blocked_count,
            "abstraction_gap_score": round(gap_score, 3),
            "overall_equivalence_confidence": round(overall_conf, 3),
            "runtime_portability_score": round(runtime_score, 3),
            "governance_violation": governance_violation,
        },
        "governance_rules": {
            "advisory_only_reasoning": True,
            "autonomous_rewrite_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationPhasePlanResult(
        migration_phase_plan=payload,
        plan_confidence=plan_confidence,
        deterministic_fingerprint=fingerprint,
    )
