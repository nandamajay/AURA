"""Deterministic runtime trace correlation for offline runtime truth cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class TraceCorrelationResult:
    trace_correlation: dict[str, Any]
    correlation_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def correlate_runtime_traces(
    *,
    target_id: str,
    runtime_event_ingestion: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    topology_runtime_graph: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> TraceCorrelationResult:
    ingestion = _as_dict(runtime_event_ingestion)
    runtime = _as_dict(runtime_evidence)
    topology = _as_dict(topology_runtime_graph)

    events = [row for row in _as_list(ingestion.get("events")) if isinstance(row, dict)]
    categories = [str(row.get("category", "")) for row in events]

    observed = {
        "pcm_lifecycle": categories.count("pcm_lifecycle"),
        "dapm_transition": categories.count("dapm_transition"),
        "soundwire": categories.count("soundwire"),
        "irq": categories.count("irq"),
        "dsp_sync": categories.count("dsp_sync"),
        "power_transition": categories.count("power_transition"),
    }

    ordering_warnings: list[dict[str, Any]] = []

    def _first_index(category: str) -> int | None:
        for idx, row in enumerate(events):
            if str(row.get("category", "")) == category:
                return idx
        return None

    pcm_idx = _first_index("pcm_lifecycle")
    dapm_idx = _first_index("dapm_transition")
    dsp_idx = _first_index("dsp_sync")

    if dapm_idx is not None and pcm_idx is not None and dapm_idx > pcm_idx:
        ordering_warnings.append(
            {
                "code": "dapm_after_pcm_start",
                "severity": "MEDIUM",
                "details": "DAPM transition appears after PCM lifecycle start event.",
            }
        )

    if dsp_idx is not None and pcm_idx is not None and dsp_idx > pcm_idx:
        ordering_warnings.append(
            {
                "code": "dsp_sync_after_pcm",
                "severity": "MEDIUM",
                "details": "DSP synchronization event appears after PCM started.",
            }
        )

    runtime_success = bool(runtime.get("process_success", False)) and bool(runtime.get("playback_completion", False))
    topology_edges = len(_as_list(topology.get("edges")))

    coverage_score = sum(1 for _, count in observed.items() if count > 0) / max(1, len(observed))
    warning_penalty = min(0.5, 0.15 * len(ordering_warnings))

    correlation_score = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * coverage_score
                + 0.25 * (1.0 if runtime_success else 0.0)
                + 0.20 * min(1.0, topology_edges / 20.0)
                + 0.10 * float(_as_dict(ingestion.get("summary")).get("total_events", 0) > 0)
                - warning_penalty,
            ),
        ),
        3,
    )

    classification = "PASS"
    if correlation_score < 0.40:
        classification = "FAIL_CLOSED"
    elif ordering_warnings:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "trace_correlation",
        "target_id": str(target_id),
        "classification": classification,
        "correlation_score": correlation_score,
        "observed_category_counts": observed,
        "ordering_warnings": ordering_warnings,
        "runtime_state": {
            "process_success": bool(runtime.get("process_success", False)),
            "playback_completion": bool(runtime.get("playback_completion", False)),
            "route_fingerprint": str(runtime.get("route_fingerprint", "")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return TraceCorrelationResult(
        trace_correlation=payload,
        correlation_score=correlation_score,
        deterministic_fingerprint=fingerprint,
    )
