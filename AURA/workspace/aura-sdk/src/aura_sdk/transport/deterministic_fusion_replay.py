"""Deterministic replay payload builder for runtime evidence fusion layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DeterministicFusionReplayResult:
    deterministic_fusion_replay: dict[str, Any]
    replay_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def build_deterministic_fusion_replay(
    *,
    target_id: str,
    lineage_id: str,
    unified_engineering_truth_graph: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> DeterministicFusionReplayResult:
    truth_graph = _as_dict(unified_engineering_truth_graph)
    replay = _as_dict(replay_traces)
    artifact_map = _as_dict(artifacts)

    artifact_fingerprints = {
        str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
        for name, payload in sorted(artifact_map.items())
    }

    replay_signal = bool(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    replay_score = round(
        max(
            0.0,
            min(
                1.0,
                0.42 * (1.0 if replay_signal else 0.0)
                + 0.33
                * (
                    1.0
                    if bool(
                        str(truth_graph.get("deterministic_fingerprint", "")).strip()
                    )
                    else 0.0
                )
                + 0.25 * min(1.0, len(artifact_fingerprints) / 9.0),
            ),
        ),
        3,
    )

    classification = "PASS" if replay_score >= 0.75 else "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "deterministic_fusion_replay",
        "target_id": str(target_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "replay_score": replay_score,
        "unified_engineering_truth_graph_fingerprint": str(
            truth_graph.get("deterministic_fingerprint", "")
        ),
        "artifact_fingerprints": artifact_fingerprints,
        "replay_signal": {
            "deterministic_event_ordering": bool(
                replay.get("deterministic_event_ordering", False)
            ),
            "deterministic_replay_fingerprint": str(
                replay.get("deterministic_replay_fingerprint", "")
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [
            str(item) for item in (evidence_references or []) if str(item).strip()
        ],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return DeterministicFusionReplayResult(
        deterministic_fusion_replay=payload,
        replay_score=replay_score,
        deterministic_fingerprint=fingerprint,
    )
