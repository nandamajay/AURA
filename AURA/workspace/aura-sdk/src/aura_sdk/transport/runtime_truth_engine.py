"""Runtime Truth Cognition Layer orchestration (offline foundation)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.dapm_runtime_reasoner import (
    DapmTransitionTraceResult,
    build_dapm_transition_trace,
)
from aura_sdk.transport.deterministic_runtime_replay import (
    DeterministicRuntimeReplayResult,
    build_deterministic_runtime_replay,
)
from aura_sdk.transport.dsp_sync_reasoner import (
    DspSyncReportResult,
    analyze_dsp_sync,
)
from aura_sdk.transport.irq_timing_analyzer import (
    IrqTimingReportResult,
    analyze_irq_timing,
)
from aura_sdk.transport.pcm_lifecycle_tracker import (
    PcmLifecycleTraceResult,
    build_pcm_lifecycle_trace,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_drift_detector import (
    RuntimeDriftReportResult,
    detect_runtime_drift,
)
from aura_sdk.transport.runtime_event_ingestion import (
    RuntimeEventIngestionResult,
    ingest_runtime_events,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.soundwire_runtime_graph import (
    SoundwireRuntimeGraphResult,
    build_soundwire_runtime_graph,
)
from aura_sdk.transport.trace_correlation_engine import (
    TraceCorrelationResult,
    correlate_runtime_traces,
)


@dataclass(frozen=True)
class RuntimeTruthResult:
    runtime_truth_bundle: dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _build_runtime_truth_graph(
    *,
    target_id: str,
    ingestion_result: RuntimeEventIngestionResult,
    correlation_result: TraceCorrelationResult,
    dapm_result: DapmTransitionTraceResult,
    pcm_result: PcmLifecycleTraceResult,
    soundwire_result: SoundwireRuntimeGraphResult,
    irq_result: IrqTimingReportResult,
    dsp_result: DspSyncReportResult,
    drift_result: RuntimeDriftReportResult,
) -> dict[str, Any]:
    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": "runtime_event_ingestion", "kind": "ingestion"},
        {"id": "trace_correlation", "kind": "correlation"},
        {"id": "dapm_transition_trace", "kind": "runtime_domain"},
        {"id": "pcm_lifecycle_trace", "kind": "runtime_domain"},
        {"id": "soundwire_runtime_graph", "kind": "runtime_domain"},
        {"id": "irq_timing_report", "kind": "runtime_domain"},
        {"id": "dsp_sync_report", "kind": "runtime_domain"},
        {"id": "runtime_drift_report", "kind": "runtime_domain"},
    ]

    edges = [
        {"from": f"target:{target_id}", "to": "runtime_event_ingestion", "relation": "observed_by"},
        {"from": "runtime_event_ingestion", "to": "trace_correlation", "relation": "correlates"},
        {"from": "runtime_event_ingestion", "to": "dapm_transition_trace", "relation": "extracts"},
        {"from": "runtime_event_ingestion", "to": "pcm_lifecycle_trace", "relation": "extracts"},
        {"from": "runtime_event_ingestion", "to": "soundwire_runtime_graph", "relation": "extracts"},
        {"from": "runtime_event_ingestion", "to": "irq_timing_report", "relation": "extracts"},
        {"from": "runtime_event_ingestion", "to": "dsp_sync_report", "relation": "extracts"},
        {"from": "trace_correlation", "to": "runtime_drift_report", "relation": "detects_drift"},
    ]

    payload = {
        "schema_version": "1.0",
        "graph_name": "runtime_truth_graph",
        "target_id": str(target_id),
        "classification": str(correlation_result.trace_correlation.get("classification", "UNKNOWN")),
        "nodes": nodes,
        "edges": edges,
        "domain_fingerprints": {
            "runtime_event_ingestion": ingestion_result.deterministic_fingerprint,
            "trace_correlation": correlation_result.deterministic_fingerprint,
            "dapm": dapm_result.deterministic_fingerprint,
            "pcm": pcm_result.deterministic_fingerprint,
            "soundwire": soundwire_result.deterministic_fingerprint,
            "irq": irq_result.deterministic_fingerprint,
            "dsp": dsp_result.deterministic_fingerprint,
            "drift": drift_result.deterministic_fingerprint,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_runtime_confidence(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    ingestion_result: RuntimeEventIngestionResult,
    correlation_result: TraceCorrelationResult,
    dapm_result: DapmTransitionTraceResult,
    pcm_result: PcmLifecycleTraceResult,
    soundwire_result: SoundwireRuntimeGraphResult,
    irq_result: IrqTimingReportResult,
    dsp_result: DspSyncReportResult,
    drift_result: RuntimeDriftReportResult,
    deterministic_replay_result: DeterministicRuntimeReplayResult,
    evidence_references: list[str],
) -> dict[str, Any]:
    governance = _as_dict(governance_state)
    replay = _as_dict(replay_traces)

    governance_ok = not any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    ) and bool(governance.get("fail_closed_posture", True))

    replay_ok = bool(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    factors = {
        "ingestion_confidence": ingestion_result.ingestion_confidence,
        "trace_correlation": correlation_result.correlation_score,
        "dapm_confidence": dapm_result.dapm_confidence,
        "pcm_confidence": pcm_result.pcm_confidence,
        "soundwire_confidence": soundwire_result.soundwire_confidence,
        "irq_confidence": irq_result.irq_confidence,
        "dsp_sync_confidence": dsp_result.dsp_sync_confidence,
        "drift_safety": round(max(0.0, 1.0 - drift_result.drift_score), 3),
        "replay_confidence": deterministic_replay_result.replay_score,
        "governance_safety": 1.0 if governance_ok else 0.0,
        "replay_signal": 1.0 if replay_ok else 0.0,
    }

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.11 * factors["ingestion_confidence"]
                + 0.10 * factors["trace_correlation"]
                + 0.09 * factors["dapm_confidence"]
                + 0.11 * factors["pcm_confidence"]
                + 0.08 * factors["soundwire_confidence"]
                + 0.08 * factors["irq_confidence"]
                + 0.09 * factors["dsp_sync_confidence"]
                + 0.11 * factors["drift_safety"]
                + 0.11 * factors["replay_confidence"]
                + 0.07 * factors["governance_safety"]
                + 0.05 * factors["replay_signal"],
            ),
        ),
        3,
    )

    classification = "PASS"
    if not governance_ok or str(drift_result.runtime_drift_report.get("classification", "")) == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
    elif confidence < 0.65:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_confidence_score",
        "target_id": str(target_id),
        "classification": classification,
        "runtime_confidence": confidence,
        "factors": factors,
        "summary": {
            "governance_ok": governance_ok,
            "replay_signal_present": replay_ok,
            "drift_classification": str(drift_result.runtime_drift_report.get("classification", "UNKNOWN")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "offline_foundation_mode": True,
        "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class RuntimeTruthEngine:
    """Offline-first runtime truth cognition orchestrator."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        runtime_evidence: Mapping[str, Any],
        source_payloads: Mapping[str, Any],
        structural_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        dts_cognition: Mapping[str, Any],
        archived_runtime_lineage: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> RuntimeTruthResult:
        plugin = self._plugins.load_plugin(target_id)

        runtime_adapter = _as_dict(
            plugin.runtime_evidence_adapter(
                {
                    "runtime_evidence": dict(runtime_evidence),
                    "pcm_activity": _as_dict(runtime_evidence.get("pcm_activity")),
                    "mixer_state": _as_dict(runtime_evidence.get("mixer_state")),
                    "replay_traces": dict(replay_traces),
                    "governance_decisions": dict(governance_state),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": _as_dict(structural_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": dict(dts_cognition),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        conversion_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": dict(runtime_evidence),
                    "plugin_capability_state": dict(plugin_capability_state),
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        normalized_runtime = _as_dict(runtime_adapter.get("runtime_evidence"))
        if conversion_adapter.get("expected_runtime_seconds") is not None:
            normalized_runtime["expected_runtime_seconds"] = float(conversion_adapter.get("expected_runtime_seconds", 25.0) or 25.0)
        normalized_runtime["expected_sequence"] = [
            str(item) for item in _as_list(conversion_adapter.get("expected_sequence")) if str(item).strip()
        ]
        normalized_runtime["process_success"] = bool(runtime_evidence.get("process_success", normalized_runtime.get("process_success", False)))
        normalized_runtime["playback_completion"] = bool(runtime_evidence.get("playback_completion", normalized_runtime.get("playback_completion", False)))
        normalized_runtime["playback_runtime_seconds"] = float(runtime_evidence.get("playback_runtime_seconds", runtime_evidence.get("expected_runtime_seconds", 25.0)) or 25.0)
        normalized_runtime["route_fingerprint"] = str(runtime_evidence.get("route_fingerprint", normalized_runtime.get("route_fingerprint", "")))

        ingestion_result = ingest_runtime_events(
            target_id=target_id,
            source_payloads=source_payloads,
            adapter_payload=conversion_adapter,
            archived_runtime_lineage=archived_runtime_lineage,
            evidence_references=evidence,
        )

        correlation_result = correlate_runtime_traces(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            runtime_evidence=normalized_runtime,
            topology_runtime_graph=_as_dict(structural_artifacts.get("topology_runtime_graph")),
            evidence_references=evidence,
        )

        dapm_result = build_dapm_transition_trace(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            evidence_references=evidence,
        )

        pcm_result = build_pcm_lifecycle_trace(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            runtime_evidence=normalized_runtime,
            evidence_references=evidence,
        )

        soundwire_result = build_soundwire_runtime_graph(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            topology_runtime_graph=_as_dict(structural_artifacts.get("topology_runtime_graph")),
            evidence_references=evidence,
        )

        irq_result = analyze_irq_timing(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            evidence_references=evidence,
        )

        dsp_result = analyze_dsp_sync(
            target_id=target_id,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            evidence_references=evidence,
        )

        drift_result = detect_runtime_drift(
            target_id=target_id,
            runtime_evidence=normalized_runtime,
            runtime_event_ingestion=ingestion_result.runtime_event_ingestion,
            trace_correlation=correlation_result.trace_correlation,
            expected_lineage=archived_runtime_lineage,
            evidence_references=evidence,
        )

        runtime_truth_graph = _build_runtime_truth_graph(
            target_id=target_id,
            ingestion_result=ingestion_result,
            correlation_result=correlation_result,
            dapm_result=dapm_result,
            pcm_result=pcm_result,
            soundwire_result=soundwire_result,
            irq_result=irq_result,
            dsp_result=dsp_result,
            drift_result=drift_result,
        )

        artifacts = {
            "runtime_truth_graph": runtime_truth_graph,
            "dapm_transition_trace": dapm_result.dapm_transition_trace,
            "pcm_lifecycle_trace": pcm_result.pcm_lifecycle_trace,
            "soundwire_runtime_graph": soundwire_result.soundwire_runtime_graph,
            "irq_timing_report": irq_result.irq_timing_report,
            "dsp_sync_report": dsp_result.dsp_sync_report,
            "runtime_drift_report": drift_result.runtime_drift_report,
        }

        deterministic_replay_result = build_deterministic_runtime_replay(
            target_id=target_id,
            lineage_id=lineage_id,
            runtime_truth_graph=runtime_truth_graph,
            artifacts=artifacts,
            replay_traces=replay_traces,
            evidence_references=evidence,
        )

        runtime_confidence = _build_runtime_confidence(
            target_id=target_id,
            governance_state=governance_state,
            replay_traces=replay_traces,
            ingestion_result=ingestion_result,
            correlation_result=correlation_result,
            dapm_result=dapm_result,
            pcm_result=pcm_result,
            soundwire_result=soundwire_result,
            irq_result=irq_result,
            dsp_result=dsp_result,
            drift_result=drift_result,
            deterministic_replay_result=deterministic_replay_result,
            evidence_references=evidence,
        )

        artifacts["deterministic_runtime_replay"] = deterministic_replay_result.deterministic_runtime_replay
        artifacts["runtime_confidence_score"] = runtime_confidence

        bundle = {
            "schema_version": "1.0",
            "phase": "RUNTIME_TRUTH_COGNITION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(runtime_confidence.get("classification", "UNKNOWN")),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "offline_foundation_mode": True,
            "governance_state": dict(governance_state),
            "adapter_fingerprints": {
                "runtime": str(runtime_adapter.get("fingerprint", "")),
                "topology": str(topology_adapter.get("fingerprint", "")),
                "conversion": str(conversion_adapter.get("fingerprint", "")),
            },
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["runtime_truth_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": bundle["classification"],
                "artifacts": artifacts,
            }
        )

        return RuntimeTruthResult(runtime_truth_bundle=bundle)


class RuntimeTruthRegistry:
    """Replay-safe persistence for runtime truth cognition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "runtime_truth_graph": self._output_dir / "runtime_truth_graph.json",
            "dapm_transition_trace": self._output_dir / "dapm_transition_trace.json",
            "pcm_lifecycle_trace": self._output_dir / "pcm_lifecycle_trace.json",
            "soundwire_runtime_graph": self._output_dir / "soundwire_runtime_graph.json",
            "irq_timing_report": self._output_dir / "irq_timing_report.json",
            "dsp_sync_report": self._output_dir / "dsp_sync_report.json",
            "runtime_drift_report": self._output_dir / "runtime_drift_report.json",
            "deterministic_runtime_replay": self._output_dir / "deterministic_runtime_replay.json",
            "runtime_confidence_score": self._output_dir / "runtime_confidence_score.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_truth_cognition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "runtime_truth_fingerprint": str(payload.get("runtime_truth_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-2000:]

        registry["runtime_truth_cognition"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineages = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "runtime_truth_cognition",
                "recorded_at": _utc_now_iso(),
                "runtime_truth_fingerprint": str(payload.get("runtime_truth_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-9000:]

        registry.setdefault("runtime_truth_lineage", [])
        runtime_lineage = [row for row in _as_list(registry.get("runtime_truth_lineage")) if isinstance(row, dict)]
        runtime_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "runtime_truth_fingerprint": entry["runtime_truth_fingerprint"],
            }
        )
        registry["runtime_truth_lineage"] = runtime_lineage[-3000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "runtime_truth_fingerprint": entry["runtime_truth_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_truth_cognition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "runtime_truth_cognition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "runtime_truth_fingerprint": str(_as_dict(selected).get("runtime_truth_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "runtime_truth_fingerprint": str(_as_dict(selected).get("runtime_truth_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "offline_foundation_mode": True,
        }

        _save_json(self._output_dir / "deterministic_runtime_replay.json", replay_payload)
        return replay_payload
