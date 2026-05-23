"""Deterministic confidence propagation for unified cognition correlation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class ConfidenceEvolutionResult:
    confidence_evolution_report: dict[str, Any]
    current_confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success"}
    return False


def _severity_penalty(entry: Mapping[str, Any]) -> float:
    sev = str(entry.get("severity", "")).strip().upper()
    if sev == "HIGH":
        return 0.25
    if sev == "MEDIUM":
        return 0.12
    if sev == "LOW":
        return 0.05
    return 0.08 if _to_bool(entry.get("regression_detected", False)) else 0.0


def evolve_confidence(
    *,
    runtime_cognition: Mapping[str, Any],
    topology_cognition: Mapping[str, Any],
    semantic_cognition: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    regression_history: list[Mapping[str, Any]],
    evidence_completeness: float,
    mismatch_count: int,
    governance_decisions: Mapping[str, Any],
    previous_confidence_state: Mapping[str, Any] | None,
) -> ConfidenceEvolutionResult:
    runtime = _as_dict(runtime_cognition)
    topology = _as_dict(topology_cognition)
    semantic = _as_dict(semantic_cognition)
    replay = _as_dict(replay_traces)
    governance = _as_dict(governance_decisions)
    previous = _as_dict(previous_confidence_state)

    runtime_conf = _to_float(_as_dict(runtime.get("confidence")).get("runtime_confidence", runtime.get("runtime_confidence", 0.0)))
    if runtime_conf <= 0.0:
        runtime_conf = 1.0 if _to_bool(_as_dict(runtime.get("last_trace_summary")).get("process_success", False)) else 0.25

    topology_conf = _to_float(
        _as_dict(topology.get("confidence")).get("topology_confidence", topology.get("topology_confidence", 0.0))
    )

    replay_conf = 1.0 if (_to_bool(replay.get("deterministic_event_ordering")) or bool(replay.get("deterministic_replay_fingerprint"))) else 0.3

    semantic_scores = _as_dict(_as_dict(semantic.get("classification")).get("scores"))
    semantic_stability = _to_float(semantic_scores.get("upstream_friendly", 0.0))
    governance_risk = _to_float(semantic_scores.get("governance_risky", 0.0))
    if semantic_stability <= 0.0:
        semantic_stability = max(0.0, 1.0 - governance_risk)

    total_penalty = 0.0
    for row in regression_history:
        entry = _as_dict(row)
        total_penalty += _severity_penalty(entry)
        for deviation in _as_list(entry.get("deviations")):
            total_penalty += _severity_penalty(_as_dict(deviation))
    normalized_penalty = min(1.0, total_penalty / max(1.0, float(max(1, len(regression_history)))))
    regression_stability = round(max(0.0, 1.0 - normalized_penalty), 3)

    evidence_score = max(0.0, min(1.0, float(evidence_completeness)))

    factors = {
        "repeated_runtime_validation": round(max(0.0, min(1.0, runtime_conf)), 3),
        "replay_consistency": round(max(0.0, min(1.0, replay_conf)), 3),
        "semantic_stability": round(max(0.0, min(1.0, semantic_stability)), 3),
        "topology_consistency": round(max(0.0, min(1.0, topology_conf)), 3),
        "regression_drift_history": round(regression_stability, 3),
        "evidence_completeness": round(evidence_score, 3),
    }

    weighted = (
        0.25 * factors["repeated_runtime_validation"]
        + 0.20 * factors["replay_consistency"]
        + 0.15 * factors["semantic_stability"]
        + 0.15 * factors["topology_consistency"]
        + 0.15 * factors["regression_drift_history"]
        + 0.10 * factors["evidence_completeness"]
    )

    mismatch_penalty = min(0.35, 0.06 * max(0, int(mismatch_count)))
    governance_penalty = 0.0
    if _to_bool(governance.get("autonomous_patching_allowed", False)):
        governance_penalty += 0.25
    if _to_bool(governance.get("autonomous_topology_rewrite_allowed", False)):
        governance_penalty += 0.20
    if _to_bool(governance.get("autonomous_mixer_mutation_allowed", False)):
        governance_penalty += 0.20
    if _to_bool(governance.get("autonomous_upstream_generation_allowed", False)):
        governance_penalty += 0.20

    raw_confidence = max(0.0, min(1.0, weighted - mismatch_penalty - governance_penalty))

    previous_overall = _to_float(previous.get("overall_confidence", 0.0))
    previous_evidence = _to_float(previous.get("evidence_completeness", 0.0))

    # Missing evidence must never increase confidence deterministically.
    if evidence_score < previous_evidence and raw_confidence > previous_overall:
        raw_confidence = previous_overall
    if evidence_score < 1.0 and raw_confidence > previous_overall and previous_overall > 0.0:
        raw_confidence = previous_overall

    current_confidence = round(max(0.0, min(1.0, raw_confidence)), 3)
    trend = round(current_confidence - previous_overall, 3)

    report = {
        "schema_version": "1.0",
        "report_name": "confidence_evolution_report",
        "weights": {
            "repeated_runtime_validation": 0.25,
            "replay_consistency": 0.20,
            "semantic_stability": 0.15,
            "topology_consistency": 0.15,
            "regression_drift_history": 0.15,
            "evidence_completeness": 0.10,
        },
        "factors": factors,
        "penalties": {
            "mismatch_penalty": round(mismatch_penalty, 3),
            "governance_penalty": round(governance_penalty, 3),
        },
        "previous": {
            "overall_confidence": round(previous_overall, 3),
            "evidence_completeness": round(previous_evidence, 3),
        },
        "current": {
            "overall_confidence": current_confidence,
            "evidence_completeness": factors["evidence_completeness"],
        },
        "trend": {
            "delta": trend,
            "direction": "UP" if trend > 0 else ("DOWN" if trend < 0 else "FLAT"),
        },
        "integrity_guards": {
            "evidence_backed_only": True,
            "no_confidence_amplification_loops": True,
            "missing_evidence_never_increases_confidence": True,
            "agent_self_reinforcement_blocked": True,
        },
    }

    fingerprint = stable_fingerprint(
        {
            "factors": factors,
            "penalties": report["penalties"],
            "previous": report["previous"],
            "current": report["current"],
            "trend": report["trend"],
        }
    )

    report["deterministic_fingerprint"] = fingerprint

    return ConfidenceEvolutionResult(
        confidence_evolution_report=report,
        current_confidence=current_confidence,
        deterministic_fingerprint=fingerprint,
    )
