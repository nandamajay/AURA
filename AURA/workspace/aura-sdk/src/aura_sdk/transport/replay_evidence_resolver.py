"""Deterministic replay/evidence resolver for engineering queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class ReplayEvidenceResolutionResult:
    replay_evidence_resolution: dict[str, Any]
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


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "ok",
            "pass",
            "success",
            "supported",
        }
    return False


def resolve_replay_evidence_question(
    *,
    target_id: str,
    question: str,
    replay_artifacts: Mapping[str, Any],
    confidence_artifacts: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> ReplayEvidenceResolutionResult:
    replay = _as_dict(replay_artifacts)
    confidence = _as_dict(confidence_artifacts)
    lowered = str(question).strip().lower()

    replay_objects = {
        name: _as_dict(payload)
        for name, payload in sorted(replay.items())
        if _as_dict(payload)
    }

    replay_scores: list[float] = []
    for payload in replay_objects.values():
        score = payload.get("replay_score")
        if isinstance(score, (int, float)):
            replay_scores.append(float(score))
    mean_replay_score = round(sum(replay_scores) / len(replay_scores), 3) if replay_scores else 0.0

    replay_signal = any(
        _is_true(_as_dict(payload.get("replay_signal")).get("deterministic_event_ordering", False))
        or bool(str(_as_dict(payload.get("replay_signal")).get("deterministic_replay_fingerprint", "")).strip())
        for payload in replay_objects.values()
    )

    runtime_conf = float(_as_dict(confidence.get("runtime_confidence_score")).get("runtime_confidence", 0.0) or 0.0)
    eng_conf = float(_as_dict(confidence.get("engineering_confidence_score")).get("engineering_confidence", 0.0) or 0.0)
    incident_conf = float(_as_dict(confidence.get("engineering_confidence_report")).get("engineering_confidence", 0.0) or 0.0)

    evidence_sources = [
        f"artifact://{name}"
        for name in sorted(replay_objects.keys())
    ]
    if _as_dict(confidence.get("runtime_confidence_score")):
        evidence_sources.append("artifact://runtime_confidence_score")
    if _as_dict(confidence.get("engineering_confidence_score")):
        evidence_sources.append("artifact://engineering_confidence_score")
    if _as_dict(confidence.get("engineering_confidence_report")):
        evidence_sources.append("artifact://engineering_confidence_report")

    answer = "Insufficient deterministic replay evidence to resolve the question."
    causality_chain: list[dict[str, Any]] = []

    if "confidence" in lowered:
        answer = (
            f"Confidence is reduced when replay_score={mean_replay_score}, runtime_confidence={runtime_conf}, "
            f"engineering_confidence={eng_conf}, incident_confidence={incident_conf}, replay_signal={replay_signal}."
        )
        causality_chain = [
            {"node": "deterministic_replay_lineage", "relation": "stability_signal", "weight": mean_replay_score},
            {"node": "confidence_reports", "relation": "reflects_replay_consistency", "weight": round(max(runtime_conf, eng_conf, incident_conf), 3)},
        ]
    elif "replay" in lowered or "lineage" in lowered:
        answer = (
            f"Deterministic replay evidence includes {len(replay_objects)} replay artifact(s) with mean_replay_score={mean_replay_score}."
        )
        causality_chain = [
            {"node": "replay_artifacts", "relation": "provide_lineage", "weight": round(min(1.0, len(replay_objects) / 4.0), 3)},
            {"node": "deterministic_investigation_replay", "relation": "reconstructs_state", "weight": mean_replay_score},
        ]
    else:
        answer = (
            f"Replay lineage quality: artifact_count={len(replay_objects)}, replay_signal={replay_signal}, "
            f"mean_replay_score={mean_replay_score}."
        )
        causality_chain = [
            {"node": "replay_signal", "relation": "supports_determinism", "weight": 1.0 if replay_signal else 0.3}
        ]

    resolver_conf = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * min(1.0, len(replay_objects) / 4.0)
                + 0.25 * (1.0 if replay_signal else 0.0)
                + 0.20 * mean_replay_score
                + 0.10 * min(1.0, max(runtime_conf, eng_conf, incident_conf)),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not replay_objects:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "insufficient_replay_evidence"
    elif resolver_conf < 0.58:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "replay_evidence_confidence_below_threshold"

    payload = {
        "schema_version": "1.0",
        "resolver": "replay_evidence_resolver",
        "target_id": str(target_id),
        "question": str(question).strip(),
        "classification": classification,
        "answer": answer,
        "confidence_score": resolver_conf,
        "evidence_sources": sorted(set(evidence_sources + [str(item) for item in (evidence_references or []) if str(item).strip()])),
        "causality_chain": causality_chain,
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return ReplayEvidenceResolutionResult(
        replay_evidence_resolution=payload,
        confidence=resolver_conf,
        deterministic_fingerprint=fingerprint,
    )
