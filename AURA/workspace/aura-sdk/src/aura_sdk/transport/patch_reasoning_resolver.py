"""Patch causality investigation resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PatchReasoningResolutionResult:
    patch_reasoning_resolution: dict[str, Any]
    confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def resolve_patch_reasoning_question(
    *,
    target_id: str,
    question: str,
    patch_artifacts: Mapping[str, Any],
    incident_artifacts: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> PatchReasoningResolutionResult:
    patch = _as_dict(patch_artifacts)
    incident = _as_dict(incident_artifacts)
    lowered = str(question).strip().lower()

    corr = _as_dict(patch.get("runtime_patch_correlation"))
    readiness = _as_dict(patch.get("upstream_readiness_report"))
    series_plan = _as_dict(patch.get("patch_series_plan"))
    regression = _as_dict(incident.get("regression_causality_report", patch.get("regression_causality_report")))

    mappings = [row for row in _as_list(corr.get("command_patch_mappings")) if isinstance(row, dict)]
    causes = [row for row in _as_list(regression.get("causes")) if isinstance(row, dict)]
    series = [row for row in _as_list(series_plan.get("series")) if isinstance(row, dict)]

    evidence_sources = []
    if _as_dict(corr):
        evidence_sources.append("artifact://runtime_patch_correlation")
    if _as_dict(readiness):
        evidence_sources.append("artifact://upstream_readiness_report")
    if _as_dict(series_plan):
        evidence_sources.append("artifact://patch_series_plan")
    if _as_dict(regression):
        evidence_sources.append("artifact://regression_causality_report")

    top_patch = ""
    top_patch_conf = 0.0
    if mappings:
        ranked = sorted(
            mappings,
            key=lambda row: float(_as_dict(row).get("correlation_confidence", 0.0) or 0.0),
            reverse=True,
        )
        top = _as_dict(ranked[0])
        impacted = _as_list(top.get("impacted_patch_nodes"))
        top_patch = str(impacted[0]) if impacted else "unknown_patch"
        top_patch_conf = float(top.get("correlation_confidence", 0.0) or 0.0)

    answer = "Insufficient patch evidence to resolve regression causality."
    causality_chain: list[dict[str, Any]] = []

    if "which patch" in lowered or "introduced" in lowered or "regression" in lowered:
        if top_patch:
            answer = (
                f"Most likely patch introducing regression is '{top_patch}' with correlation_confidence="
                f"{round(top_patch_conf, 3)}."
            )
            causality_chain = [
                {"node": "runtime_patch_correlation", "relation": "maps_runtime_to_patch", "weight": round(top_patch_conf, 3)},
                {"node": top_patch, "relation": "candidate_regression_introducer", "weight": round(top_patch_conf, 3)},
            ]
    elif "upstream readiness" in lowered or "readiness" in lowered:
        answer = (
            f"Upstream readiness classification is {str(readiness.get('classification', 'UNKNOWN'))} "
            f"with patch_series_count={len(series)}."
        )
        causality_chain = [
            {"node": "upstream_readiness_report", "relation": "classifies_readiness", "weight": 0.76},
            {"node": "patch_series_plan", "relation": "provides_sequence_context", "weight": 0.71},
        ]
    else:
        answer = (
            f"Patch causality currently has mapping_count={len(mappings)} and regression_cause_count={len(causes)}."
        )
        causality_chain = [
            {"node": "runtime_patch_correlation", "relation": "provides_correlation", "weight": 0.73},
            {"node": "regression_causality_report", "relation": "provides_cause_candidates", "weight": 0.77},
        ]

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.43 * min(1.0, len(evidence_sources) / 4.0)
                + 0.22 * min(1.0, len(causality_chain) / 2.0)
                + 0.20 * min(1.0, len(mappings) / 6.0)
                + 0.15 * min(1.0, len(causes) / 5.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not evidence_sources:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "insufficient_patch_evidence"
    elif confidence < 0.58:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "patch_evidence_confidence_below_threshold"

    payload = {
        "schema_version": "1.0",
        "resolver": "patch_reasoning_resolver",
        "target_id": str(target_id),
        "question": str(question).strip(),
        "classification": classification,
        "answer": answer,
        "confidence_score": confidence,
        "evidence_sources": sorted(set(evidence_sources + [str(item) for item in (evidence_references or []) if str(item).strip()])),
        "causality_chain": causality_chain,
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return PatchReasoningResolutionResult(
        patch_reasoning_resolution=payload,
        confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
