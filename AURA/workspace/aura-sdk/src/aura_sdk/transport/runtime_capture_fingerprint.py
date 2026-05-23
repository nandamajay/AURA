"""Deterministic runtime capture fingerprint model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeCaptureFingerprintResult:
    runtime_capture_fingerprint: dict[str, Any]
    fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_runtime_capture_fingerprint(
    *,
    target_id: str,
    session_id: str,
    normalized_runtime_evidence: Mapping[str, Any],
    source_fingerprints: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> RuntimeCaptureFingerprintResult:
    evidence = _as_dict(normalized_runtime_evidence)

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_capture_fingerprint",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "classification": str(evidence.get("classification", "UNKNOWN")),
        "source_fingerprints": {
            str(name): str(value)
            for name, value in sorted(_as_dict(source_fingerprints).items())
        },
        "evidence_summary": {
            "normalized_event_count": len(_as_list(evidence.get("normalized_events"))),
            "subsystem_count": len(_as_list(_as_dict(evidence.get("subsystem_runtime_state")).get("subsystems"))),
            "missing_required_source_count": len(_as_list(_as_dict(evidence.get("summary")).get("missing_required_sources"))),
        },
        "runtime_truth_precedence": True,
        "read_only_ingestion": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimeCaptureFingerprintResult(
        runtime_capture_fingerprint=payload,
        fingerprint=fingerprint,
    )
