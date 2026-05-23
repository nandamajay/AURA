"""Deterministic engineering runtime session replay payload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class EngineeringSessionReplayResult:
    deterministic_runtime_session_replay: dict[str, Any]
    replay_score: float
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


def build_engineering_session_replay(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    runtime_capture_fingerprint: Mapping[str, Any],
    artifact_fingerprints: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    previous_history: list[Mapping[str, Any]] | None,
    evidence_references: list[str] | None,
) -> EngineeringSessionReplayResult:
    capture = _as_dict(runtime_capture_fingerprint)
    replay = _as_dict(replay_traces)

    replay_signal = _is_true(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    history = [row for row in _as_list(previous_history or []) if isinstance(row, dict)]
    history.append(
        {
            "lineage_id": str(lineage_id),
            "session_id": str(session_id),
            "classification": str(capture.get("classification", "UNKNOWN")),
            "runtime_capture_fingerprint": str(capture.get("deterministic_fingerprint", "")),
        }
    )
    history = history[-5000:]

    replay_score = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * (1.0 if replay_signal else 0.0)
                + 0.35 * (1.0 if bool(str(capture.get("deterministic_fingerprint", "")).strip()) else 0.0)
                + 0.20 * min(1.0, len(_as_dict(artifact_fingerprints)) / 10.0),
            ),
        ),
        3,
    )

    classification = "PASS" if replay_score >= 0.75 else "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "deterministic_runtime_session_replay",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "replay_score": replay_score,
        "runtime_capture_fingerprint": str(capture.get("deterministic_fingerprint", "")),
        "artifact_fingerprints": {
            str(name): str(value)
            for name, value in sorted(_as_dict(artifact_fingerprints).items())
        },
        "replay_signal": {
            "deterministic_event_ordering": _is_true(replay.get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": history,
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return EngineeringSessionReplayResult(
        deterministic_runtime_session_replay=payload,
        replay_score=replay_score,
        deterministic_fingerprint=fingerprint,
    )
