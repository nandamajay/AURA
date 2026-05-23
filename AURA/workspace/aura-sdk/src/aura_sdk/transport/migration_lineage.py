"""Regression-aware migration lineage for downstream to upstream conversion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationLineageResult:
    migration_lineage: dict[str, Any]
    drift_score: float
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


def _sequence_drift(expected: list[str], observed: list[str]) -> tuple[bool, dict[str, Any]]:
    expected_norm = [str(item).strip() for item in expected if str(item).strip()]
    observed_norm = [str(item).strip() for item in observed if str(item).strip()]

    missing = [item for item in expected_norm if item not in observed_norm]
    extra = [item for item in observed_norm if item not in expected_norm]
    drift = bool(missing or extra)
    return drift, {
        "missing_expected_steps": missing,
        "unexpected_steps": extra,
    }


def build_migration_lineage(
    *,
    target_id: str,
    lineage_id: str,
    runtime_evidence: Mapping[str, Any],
    translated_model: Mapping[str, Any],
    regression_history: list[Mapping[str, Any]],
    previous_lineage: list[Mapping[str, Any]] | None,
) -> MigrationLineageResult:
    runtime = _as_dict(runtime_evidence)
    translated = _as_dict(translated_model)

    drifts: list[dict[str, Any]] = []

    runtime_duration = _to_float(runtime.get("playback_runtime_seconds", runtime.get("runtime_seconds", 0.0)))
    translated_duration = _to_float(translated.get("expected_runtime_seconds", 0.0))
    timing_delta = abs(runtime_duration - translated_duration)
    if translated_duration > 0.0 and timing_delta > 1.0:
        drifts.append(
            {
                "type": "timing_drift",
                "severity": "MEDIUM",
                "runtime_seconds": runtime_duration,
                "translated_seconds": translated_duration,
                "delta_seconds": round(timing_delta, 3),
            }
        )

    runtime_route = str(runtime.get("route_fingerprint", "")).strip()
    translated_route = str(translated.get("route_fingerprint", "")).strip()
    if runtime_route and translated_route and runtime_route != translated_route:
        drifts.append(
            {
                "type": "route_drift",
                "severity": "HIGH",
                "runtime_route_fingerprint": runtime_route,
                "translated_route_fingerprint": translated_route,
            }
        )

    runtime_caps = _as_dict(runtime.get("capabilities"))
    required_caps = _as_dict(translated.get("required_capabilities"))
    capability_changes: list[dict[str, Any]] = []
    for key in sorted(set(runtime_caps.keys()).union(required_caps.keys())):
        observed = str(runtime_caps.get(key, "UNKNOWN"))
        required = str(required_caps.get(key, "UNKNOWN"))
        if observed != required:
            capability_changes.append(
                {
                    "capability": key,
                    "runtime": observed,
                    "translated": required,
                }
            )
    if capability_changes:
        drifts.append(
            {
                "type": "capability_drift",
                "severity": "MEDIUM",
                "changes": capability_changes,
            }
        )

    expected_sequence = [str(item) for item in _as_list(translated.get("expected_sequence")) if str(item).strip()]
    observed_sequence = [str(item) for item in _as_list(runtime.get("command_sequence")) if str(item).strip()]
    seq_drift, seq_details = _sequence_drift(expected_sequence, observed_sequence)
    if seq_drift:
        drifts.append(
            {
                "type": "sequencing_drift",
                "severity": "MEDIUM",
                "details": seq_details,
            }
        )

    for entry in regression_history:
        row = _as_dict(entry)
        for deviation in _as_list(row.get("deviations")):
            dev = _as_dict(deviation)
            code = str(dev.get("code", "")).strip().lower()
            if code in {"runtime_latency_drift", "route_drift", "capability_drift", "sequencing_drift"}:
                drifts.append(
                    {
                        "type": code,
                        "severity": str(dev.get("severity", row.get("severity", "MEDIUM"))).upper(),
                        "source": "regression_history",
                        "details": str(dev.get("details", "")),
                    }
                )

    drift_score = round(min(1.0, 0.2 * len(drifts)), 3)
    migration_confidence = round(max(0.0, 1.0 - drift_score), 3)

    lineage_history = [row for row in _as_list(previous_lineage) if isinstance(row, dict)]
    lineage_entry = {
        "lineage_id": str(lineage_id),
        "target_id": str(target_id),
        "drifts": drifts,
        "drift_score": drift_score,
        "migration_confidence": migration_confidence,
    }
    lineage_history.append(lineage_entry)
    lineage_history = lineage_history[-1000:]

    payload = {
        "schema_version": "1.0",
        "report_name": "migration_lineage",
        "target_id": target_id,
        "lineage_id": str(lineage_id),
        "migration_confidence": migration_confidence,
        "drift_score": drift_score,
        "drifts": drifts,
        "history": lineage_history,
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "lineage_id": str(lineage_id),
            "drifts": drifts,
            "drift_score": drift_score,
            "migration_confidence": migration_confidence,
        }
    )
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationLineageResult(
        migration_lineage=payload,
        drift_score=drift_score,
        deterministic_fingerprint=fingerprint,
    )
