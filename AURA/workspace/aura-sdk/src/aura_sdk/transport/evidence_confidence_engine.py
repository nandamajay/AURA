"""Engineering confidence scoring for runtime incident reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class EngineeringConfidenceReportResult:
    engineering_confidence_report: dict[str, Any]
    engineering_confidence: float
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


def build_engineering_confidence_report(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    runtime_sequence_drift: Mapping[str, Any],
    lifecycle_violation_report: Mapping[str, Any],
    topology_runtime_causality: Mapping[str, Any],
    regression_causality_report: Mapping[str, Any],
    root_cause_candidates: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> EngineeringConfidenceReportResult:
    governance = _as_dict(governance_state)
    replay = _as_dict(replay_traces)
    drift = _as_dict(runtime_sequence_drift)
    lifecycle = _as_dict(lifecycle_violation_report)
    topology = _as_dict(topology_runtime_causality)
    regression = _as_dict(regression_causality_report)
    rootcause = _as_dict(root_cause_candidates)

    governance_ok = not any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    ) and bool(governance.get("fail_closed_posture", True))

    replay_ok = bool(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    timeline_count = len(_as_list(drift.get("ordered_runtime_timeline")))
    drift_count = len(_as_list(drift.get("drifts")))
    violation_count = len(_as_list(lifecycle.get("violations")))
    topology_inconsistency_count = len(_as_list(topology.get("inconsistencies")))
    regression_cause_count = len(_as_list(regression.get("causes")))
    root_candidates_count = len(_as_list(rootcause.get("candidates")))

    root_conf = float(rootcause.get("root_cause_confidence", 0.0) or 0.0)
    drift_score = float(drift.get("drift_score", 0.0) or 0.0)
    lifecycle_score = float(lifecycle.get("violation_score", 0.0) or 0.0)
    topology_score = float(topology.get("causality_score", 0.0) or 0.0)
    regression_score = float(regression.get("causality_confidence", 0.0) or 0.0)

    evidence_coverage = round(
        max(0.0, min(1.0, timeline_count / 60.0 + root_candidates_count / 12.0)),
        3,
    )

    factors = {
        "evidence_coverage": evidence_coverage,
        "timeline_stability": round(max(0.0, 1.0 - drift_score), 3),
        "lifecycle_stability": round(max(0.0, 1.0 - lifecycle_score), 3),
        "topology_runtime_alignment": topology_score,
        "regression_causality_strength": regression_score,
        "root_cause_confidence": root_conf,
        "governance_safety": 1.0 if governance_ok else 0.0,
        "replay_safety": 1.0 if replay_ok else 0.0,
    }

    engineering_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.14 * factors["evidence_coverage"]
                + 0.13 * factors["timeline_stability"]
                + 0.12 * factors["lifecycle_stability"]
                + 0.14 * factors["topology_runtime_alignment"]
                + 0.14 * factors["regression_causality_strength"]
                + 0.15 * factors["root_cause_confidence"]
                + 0.10 * factors["governance_safety"]
                + 0.08 * factors["replay_safety"],
            ),
        ),
        3,
    )

    uncertain = root_candidates_count == 0 or root_conf < 0.62 or evidence_coverage < 0.35

    classification = "PASS"
    if not governance_ok or uncertain:
        classification = "FAIL_CLOSED"
    elif any(
        item in {"FAIL_CLOSED"}
        for item in {
            str(drift.get("classification", "")),
            str(lifecycle.get("classification", "")),
            str(topology.get("classification", "")),
            str(regression.get("classification", "")),
            str(rootcause.get("classification", "")),
        }
    ):
        classification = "FAIL_CLOSED"
    elif engineering_confidence < 0.7:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "engineering_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "engineering_confidence": engineering_confidence,
        "factors": factors,
        "summary": {
            "timeline_event_count": timeline_count,
            "drift_count": drift_count,
            "lifecycle_violation_count": violation_count,
            "topology_inconsistency_count": topology_inconsistency_count,
            "regression_cause_count": regression_cause_count,
            "root_cause_candidate_count": root_candidates_count,
            "uncertain_classification": uncertain,
            "governance_ok": governance_ok,
            "replay_ok": replay_ok,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return EngineeringConfidenceReportResult(
        engineering_confidence_report=payload,
        engineering_confidence=engineering_confidence,
        deterministic_fingerprint=fingerprint,
    )
