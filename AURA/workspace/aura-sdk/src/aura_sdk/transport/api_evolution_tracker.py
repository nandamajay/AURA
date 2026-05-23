"""API evolution compatibility tracking for upstream patch planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class ApiEvolutionTraceResult:
    api_evolution_trace: dict[str, Any]
    compatibility_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def track_api_evolution(
    *,
    target_id: str,
    upstream_equivalence_map: Mapping[str, Any],
    portability_blockers: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> ApiEvolutionTraceResult:
    equivalence = _as_dict(upstream_equivalence_map)
    blockers = _as_dict(portability_blockers)
    runtime = _as_dict(runtime_portability_analysis)

    entries = [row for row in _as_list(equivalence.get("entries")) if isinstance(row, dict)]

    exact = 0
    partial = 0
    unresolved = 0

    trace_rows: list[dict[str, Any]] = []
    for row in entries[:1200]:
        status = str(row.get("equivalence_status", "UNKNOWN")).strip().upper()
        if status == "EXACT":
            exact += 1
        elif status == "PARTIAL":
            partial += 1
        elif status == "UNRESOLVED":
            unresolved += 1

        confidence = _to_float(row.get("equivalence_confidence", 0.0), 0.0)
        compatibility_window = "OPEN"
        if status == "UNRESOLVED" or confidence < 0.4:
            compatibility_window = "NARROW"
        if status == "UNRESOLVED" and confidence < 0.2:
            compatibility_window = "BLOCKED"

        trace_rows.append(
            {
                "downstream_construct": str(row.get("downstream_construct", "")),
                "upstream_equivalent": str(row.get("upstream_equivalent", "")),
                "equivalence_status": status,
                "equivalence_confidence": round(confidence, 3),
                "compatibility_window": compatibility_window,
            }
        )

    blocker_penalty = int(_as_dict(blockers.get("summary", {})).get("blocked_unsafe_count", 0) or 0)
    runtime_penalty = len(_as_list(runtime.get("unsupported_runtime_dependencies")))
    total = max(1, exact + partial + unresolved)

    compatibility_score = round(
        max(
            0.0,
            min(
                1.0,
                0.65 * (exact / total)
                + 0.25 * (partial / total)
                - 0.05 * blocker_penalty
                - 0.01 * runtime_penalty,
            ),
        ),
        3,
    )

    classification = "PASS"
    if unresolved > 40 or blocker_penalty > 0:
        classification = "FAIL_CLOSED"
    elif unresolved > 0 or partial > 0:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "api_evolution_trace",
        "target_id": str(target_id),
        "classification": classification,
        "compatibility_score": compatibility_score,
        "summary": {
            "exact_count": exact,
            "partial_count": partial,
            "unresolved_count": unresolved,
            "api_drift_count": unresolved + partial,
            "blocked_unsafe_count": blocker_penalty,
            "runtime_dependency_count": runtime_penalty,
        },
        "trace_entries": trace_rows,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return ApiEvolutionTraceResult(
        api_evolution_trace=payload,
        compatibility_score=compatibility_score,
        deterministic_fingerprint=fingerprint,
    )
