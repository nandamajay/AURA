"""DSP/runtime causality reasoning for evidence fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class DspRuntimeCausalityResult:
    dsp_runtime_causality_report: dict[str, Any]
    causality_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def build_dsp_runtime_causality(
    *,
    target_id: str,
    dsp_sync_report: Mapping[str, Any],
    irq_timing_report: Mapping[str, Any],
    soundwire_runtime_graph: Mapping[str, Any],
    lifecycle_causality_map: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> DspRuntimeCausalityResult:
    dsp = _as_dict(dsp_sync_report)
    irq = _as_dict(irq_timing_report)
    soundwire = _as_dict(soundwire_runtime_graph)
    lifecycle = _as_dict(lifecycle_causality_map)

    dsp_sync_conf = float(dsp.get("dsp_sync_confidence", 0.0) or 0.0)
    irq_conf = float(irq.get("irq_confidence", 0.0) or 0.0)
    swr_conf = float(soundwire.get("soundwire_confidence", 0.0) or 0.0)
    lifecycle_conf = float(lifecycle.get("causality_score", 0.0) or 0.0)

    irq_spikes = int(_as_dict(irq.get("summary")).get("latency_spike_count", 0) or 0)
    dsp_failures = int(_as_dict(dsp.get("summary")).get("sync_failure_count", 0) or 0)
    swr_events = int(_as_dict(soundwire.get("summary")).get("runtime_soundwire_events", 0) or 0)

    anomalies: list[dict[str, Any]] = []
    if dsp_failures > 0:
        anomalies.append(
            {
                "code": "dsp_sync_failures",
                "severity": "HIGH" if dsp_failures > 2 else "MEDIUM",
                "details": f"Detected {dsp_failures} DSP synchronization failures.",
            }
        )
    if irq_spikes > 0 and dsp_failures > 0:
        anomalies.append(
            {
                "code": "irq_dsp_coupled_latency",
                "severity": "MEDIUM",
                "details": "IRQ latency spikes align with DSP sync degradation windows.",
            }
        )
    if swr_events == 0:
        anomalies.append(
            {
                "code": "soundwire_runtime_signal_missing",
                "severity": "MEDIUM",
                "details": "SoundWire events unavailable for DSP causality triangulation.",
            }
        )

    causality_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * dsp_sync_conf
                + 0.20 * irq_conf
                + 0.20 * swr_conf
                + 0.25 * lifecycle_conf
                - 0.10 * min(1.0, (dsp_failures + irq_spikes) / 6.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    if any(str(_as_dict(row).get("severity", "")).upper() == "HIGH" for row in anomalies):
        classification = "FAIL_CLOSED"
    elif anomalies:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "dsp_runtime_causality_report",
        "target_id": str(target_id),
        "classification": classification,
        "causality_score": causality_score,
        "anomalies": anomalies,
        "summary": {
            "dsp_sync_confidence": round(dsp_sync_conf, 3),
            "irq_confidence": round(irq_conf, 3),
            "soundwire_confidence": round(swr_conf, 3),
            "lifecycle_causality_score": round(lifecycle_conf, 3),
            "dsp_failure_count": dsp_failures,
            "irq_latency_spike_count": irq_spikes,
            "soundwire_event_count": swr_events,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return DspRuntimeCausalityResult(
        dsp_runtime_causality_report=payload,
        causality_score=causality_score,
        deterministic_fingerprint=fingerprint,
    )
