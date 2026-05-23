"""Runtime investigation question resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeQuestionResolutionResult:
    runtime_question_resolution: dict[str, Any]
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


def resolve_runtime_question(
    *,
    target_id: str,
    question: str,
    runtime_artifacts: Mapping[str, Any],
    incident_artifacts: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RuntimeQuestionResolutionResult:
    runtime = _as_dict(runtime_artifacts)
    incident = _as_dict(incident_artifacts)
    lowered = str(question).strip().lower()

    sequence_drift = _as_dict(incident.get("runtime_sequence_drift", runtime.get("runtime_sequence_drift")))
    root_causes = _as_dict(incident.get("root_cause_candidates"))
    lifecycle = _as_dict(incident.get("lifecycle_violation_report", runtime.get("lifecycle_violation_report")))
    dsp = _as_dict(runtime.get("dsp_sync_report", runtime.get("dsp_runtime_trace")))

    drifts = [row for row in _as_list(sequence_drift.get("drifts")) if isinstance(row, dict)]
    violations = [row for row in _as_list(lifecycle.get("violations")) if isinstance(row, dict)]
    candidates = [row for row in _as_list(root_causes.get("candidates")) if isinstance(row, dict)]

    dsp_failure_count = int(_as_dict(dsp.get("summary")).get("sync_failure_count", 0) or 0)
    if dsp_failure_count <= 0:
        dsp_failure_count = len(
            [
                row
                for row in _as_list(dsp.get("events"))
                if "fail" in str(_as_dict(row).get("message", "")).lower()
            ]
        )

    evidence_sources = []
    if drifts:
        evidence_sources.append("artifact://runtime_sequence_drift")
    if violations:
        evidence_sources.append("artifact://lifecycle_violation_report")
    if candidates:
        evidence_sources.append("artifact://root_cause_candidates")
    if _as_dict(dsp):
        evidence_sources.append("artifact://dsp_sync_report")

    answer = "Insufficient runtime evidence to resolve the question."
    causality_chain: list[dict[str, Any]] = []

    if "dsp" in lowered or "mailbox" in lowered or "synchronization" in lowered:
        if dsp_failure_count > 0:
            answer = f"DSP/runtime synchronization reported {dsp_failure_count} failure signal(s), indicating mailbox or DSP acknowledgment instability."
            causality_chain = [
                {"node": "dsp_sync_report", "relation": "observed_sync_failure", "weight": 0.86},
                {"node": "runtime_failure", "relation": "caused_by", "weight": 0.82},
            ]
        else:
            answer = "No explicit DSP synchronization failure was observed in current runtime evidence."
            causality_chain = [
                {"node": "dsp_sync_report", "relation": "no_failure_evidence", "weight": 0.45}
            ]
    elif "lifecycle" in lowered or "drift" in lowered or "sequence" in lowered:
        if drifts or violations:
            answer = (
                f"Lifecycle drift is supported by {len(drifts)} drift signal(s) and "
                f"{len(violations)} lifecycle violation(s) in runtime traces."
            )
            causality_chain = [
                {"node": "runtime_sequence_drift", "relation": "detects", "weight": 0.84},
                {"node": "lifecycle_violation_report", "relation": "confirms", "weight": 0.81},
            ]
    else:
        if candidates:
            top = _as_dict(candidates[0])
            answer = (
                f"Primary runtime failure candidate is '{str(top.get('candidate', 'unknown'))}' "
                f"from {str(top.get('origin', 'runtime_reasoning'))}."
            )
            causality_chain = [
                {"node": "runtime_sequence_drift", "relation": "feeds", "weight": 0.77},
                {"node": "root_cause_candidates", "relation": "selects", "weight": float(top.get("confidence", 0.6) or 0.6)},
                {"node": "runtime_failure", "relation": "explains", "weight": float(top.get("confidence", 0.6) or 0.6)},
            ]
        elif drifts:
            answer = f"Runtime failure aligns with {len(drifts)} sequence drift signal(s), but root-cause evidence is partial."
            causality_chain = [
                {"node": "runtime_sequence_drift", "relation": "signals", "weight": 0.68},
                {"node": "runtime_failure", "relation": "possibly_caused_by", "weight": 0.62},
            ]

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.42 * min(1.0, len(evidence_sources) / 4.0)
                + 0.30 * min(1.0, len(causality_chain) / 3.0)
                + 0.18 * (1.0 if candidates else 0.0)
                + 0.10 * (1.0 if drifts or violations or dsp_failure_count > 0 else 0.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not evidence_sources:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "insufficient_runtime_evidence"
    elif confidence < 0.62:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "runtime_evidence_confidence_below_threshold"

    payload = {
        "schema_version": "1.0",
        "resolver": "runtime_question_resolver",
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

    return RuntimeQuestionResolutionResult(
        runtime_question_resolution=payload,
        confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
