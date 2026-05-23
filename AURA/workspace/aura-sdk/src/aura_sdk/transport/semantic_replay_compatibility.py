"""Replay compatibility validator for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class SemanticReplayCompatibilityResult:
    semantic_replay_compatibility: dict[str, Any]
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_semantic_replay_compatibility(
    *,
    source_id: str,
    source_version: str,
    artifacts: Mapping[str, Any],
    governance_boundary: Mapping[str, Any],
) -> SemanticReplayCompatibilityResult:
    artifact_rows = []
    for name, payload in sorted(_as_dict(artifacts).items()):
        row = _as_dict(payload)
        fingerprint = str(row.get("deterministic_fingerprint", "")).strip()
        artifact_rows.append(
            {
                "artifact": str(name),
                "has_fingerprint": bool(fingerprint),
                "deterministic_fingerprint": fingerprint,
                "classification": str(row.get("classification", row.get("report_name", row.get("graph_name", "UNKNOWN")))),
            }
        )

    missing = [row["artifact"] for row in artifact_rows if not bool(row["has_fingerprint"])]
    ordering = [row["artifact"] for row in artifact_rows]

    governance = _as_dict(governance_boundary)
    governance_ok = str(governance.get("classification", "PASS")) != "FAIL_CLOSED"

    classification = "PASS"
    if missing:
        classification = "FAIL_CLOSED"
    elif not governance_ok:
        classification = "FAIL_CLOSED"

    replay_payload = {
        "schema_version": "1.0",
        "report_name": "semantic_replay_compatibility",
        "source_id": str(source_id),
        "source_version": str(source_version),
        "classification": classification,
        "deterministic_outputs_only": True,
        "artifact_ordering": ordering,
        "artifact_checks": artifact_rows,
        "missing_fingerprints": missing,
        "governance_classification": str(governance.get("classification", "UNKNOWN")),
        "replay_supported": classification == "PASS",
    }
    fingerprint = stable_fingerprint(replay_payload)
    replay_payload["deterministic_fingerprint"] = fingerprint

    return SemanticReplayCompatibilityResult(
        semantic_replay_compatibility=replay_payload,
        deterministic_fingerprint=fingerprint,
    )
