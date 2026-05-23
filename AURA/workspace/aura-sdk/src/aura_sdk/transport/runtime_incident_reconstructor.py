"""Runtime Incident Reconstruction and Root-Cause Reasoning Layer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.evidence_confidence_engine import (
    EngineeringConfidenceReportResult,
    build_engineering_confidence_report,
)
from aura_sdk.transport.lifecycle_violation_detector import (
    LifecycleViolationReportResult,
    detect_lifecycle_violations,
)
from aura_sdk.transport.patch_runtime_causality_engine import (
    RegressionCausalityReportResult,
    build_patch_runtime_causality,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.root_cause_reasoner import (
    RootCauseCandidatesResult,
    build_root_cause_candidates,
)
from aura_sdk.transport.runtime_sequence_drift_engine import (
    RuntimeSequenceDriftResult,
    reconstruct_runtime_sequence_drift,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.topology_runtime_failure_mapper import (
    TopologyRuntimeCausalityResult,
    map_topology_runtime_failures,
)


@dataclass(frozen=True)
class RuntimeIncidentReconstructionResult:
    incident_bundle: dict[str, Any]


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


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _build_runtime_incident_graph(
    *,
    target_id: str,
    sequence_result: RuntimeSequenceDriftResult,
    lifecycle_result: LifecycleViolationReportResult,
    topology_result: TopologyRuntimeCausalityResult,
    regression_result: RegressionCausalityReportResult,
    root_result: RootCauseCandidatesResult,
    confidence_result: EngineeringConfidenceReportResult,
    evidence_references: list[str],
) -> dict[str, Any]:
    timeline = _as_list(sequence_result.runtime_sequence_drift.get("ordered_runtime_timeline"))
    subsystem_order = _as_list(sequence_result.runtime_sequence_drift.get("subsystem_activation_ordering"))

    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": "runtime_sequence_drift", "kind": "incident_domain"},
        {"id": "lifecycle_violation_report", "kind": "incident_domain"},
        {"id": "topology_runtime_causality", "kind": "incident_domain"},
        {"id": "regression_causality_report", "kind": "incident_domain"},
        {"id": "root_cause_candidates", "kind": "incident_domain"},
        {"id": "engineering_confidence_report", "kind": "incident_domain"},
    ]

    edges = [
        {"from": f"target:{target_id}", "to": "runtime_sequence_drift", "relation": "observed_runtime"},
        {"from": "runtime_sequence_drift", "to": "lifecycle_violation_report", "relation": "constrains"},
        {"from": "runtime_sequence_drift", "to": "topology_runtime_causality", "relation": "maps_to_topology"},
        {"from": "topology_runtime_causality", "to": "regression_causality_report", "relation": "contributes"},
        {"from": "lifecycle_violation_report", "to": "root_cause_candidates", "relation": "contributes"},
        {"from": "regression_causality_report", "to": "root_cause_candidates", "relation": "explains"},
        {"from": "root_cause_candidates", "to": "engineering_confidence_report", "relation": "confidence_input"},
    ]

    payload = {
        "schema_version": "1.0",
        "graph_name": "runtime_incident_graph",
        "target_id": str(target_id),
        "classification": str(confidence_result.engineering_confidence_report.get("classification", "UNKNOWN")),
        "nodes": nodes,
        "edges": edges,
        "timeline": timeline,
        "subsystem_activation_ordering": subsystem_order,
        "domain_fingerprints": {
            "runtime_sequence_drift": sequence_result.deterministic_fingerprint,
            "lifecycle_violation_report": lifecycle_result.deterministic_fingerprint,
            "topology_runtime_causality": topology_result.deterministic_fingerprint,
            "regression_causality_report": regression_result.deterministic_fingerprint,
            "root_cause_candidates": root_result.deterministic_fingerprint,
            "engineering_confidence_report": confidence_result.deterministic_fingerprint,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_deterministic_incident_replay(
    *,
    target_id: str,
    lineage_id: str,
    runtime_incident_graph: Mapping[str, Any],
    artifacts: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    evidence_references: list[str],
    previous_lineage: list[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    replay = _as_dict(replay_traces)
    graph = _as_dict(runtime_incident_graph)

    artifact_fingerprints = {
        str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
        for name, payload in sorted(_as_dict(artifacts).items())
    }

    history = [row for row in _as_list(previous_lineage or []) if isinstance(row, dict)]
    history.append(
        {
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(artifacts.get("engineering_confidence_report")).get("classification", "UNKNOWN")),
            "incident_graph_fingerprint": str(graph.get("deterministic_fingerprint", "")),
            "artifact_fingerprints": artifact_fingerprints,
        }
    )
    history = history[-3000:]

    replay_score = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * (1.0 if _is_true(replay.get("deterministic_event_ordering", False)) else 0.0)
                + 0.35 * (1.0 if bool(str(graph.get("deterministic_fingerprint", "")).strip()) else 0.0)
                + 0.20 * min(1.0, len(artifact_fingerprints) / 8.0),
            ),
        ),
        3,
    )

    classification = "PASS" if replay_score >= 0.75 else "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "deterministic_incident_replay",
        "target_id": str(target_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "replay_score": replay_score,
        "runtime_incident_graph_fingerprint": str(graph.get("deterministic_fingerprint", "")),
        "artifact_fingerprints": artifact_fingerprints,
        "replay_signal": {
            "deterministic_event_ordering": _is_true(replay.get("deterministic_event_ordering", False)),
            "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
        },
        "lineage_history": history,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class RuntimeIncidentReconstructor:
    """Runtime incident reconstruction orchestrator."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        runtime_sources: Mapping[str, Any],
        runtime_artifacts: Mapping[str, Any],
        topology_artifacts: Mapping[str, Any],
        patch_artifacts: Mapping[str, Any],
        migration_artifacts: Mapping[str, Any],
        semantic_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_incident_lineage: list[Mapping[str, Any]] | None,
    ) -> RuntimeIncidentReconstructionResult:
        plugin = self._plugins.load_plugin(target_id)

        runtime_adapter = _as_dict(
            plugin.runtime_evidence_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                    "pcm_activity": _as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
                    "mixer_state": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                    "replay_traces": dict(replay_traces),
                    "governance_decisions": dict(governance_state),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": _as_dict(topology_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": _as_dict(semantic_artifacts.get("dts_topology_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        semantic_adapter = _as_dict(
            plugin.semantic_evidence_adapter(
                {
                    "semantic_cognition": _as_dict(semantic_artifacts.get("semantic_confidence_report")),
                    "regression_history": _as_list(previous_incident_lineage or []),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        expected_sequence = [
            str(item).strip().upper()
            for item in _as_list(_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")).get("summary", {}).get("observed_stages", []))
            if str(item).strip()
        ]
        if not expected_sequence:
            expected_sequence = ["OPEN", "PREPARE", "START", "CLOSE"]

        sequence_result = reconstruct_runtime_sequence_drift(
            target_id=target_id,
            runtime_sources=runtime_sources,
            pcm_lifecycle_trace=_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
            dapm_transition_trace=_as_dict(runtime_artifacts.get("dapm_transition_trace")),
            soundwire_runtime_graph=_as_dict(runtime_artifacts.get("soundwire_runtime_graph")),
            irq_timing_report=_as_dict(runtime_artifacts.get("irq_timing_report")),
            dsp_sync_report=_as_dict(runtime_artifacts.get("dsp_sync_report")),
            expected_sequence=expected_sequence,
            evidence_references=evidence,
        )

        topology_result = map_topology_runtime_failures(
            target_id=target_id,
            topology_runtime_graph=_as_dict(topology_artifacts.get("topology_runtime_graph")),
            runtime_truth_graph=_as_dict(runtime_artifacts.get("runtime_truth_graph")),
            pcm_lifecycle_trace=_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
            dapm_transition_trace=_as_dict(runtime_artifacts.get("dapm_transition_trace")),
            soundwire_runtime_graph=_as_dict(runtime_artifacts.get("soundwire_runtime_graph")),
            runtime_sequence_drift=sequence_result.runtime_sequence_drift,
            evidence_references=evidence,
        )

        lifecycle_result = detect_lifecycle_violations(
            target_id=target_id,
            pcm_lifecycle_trace=_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
            dapm_transition_trace=_as_dict(runtime_artifacts.get("dapm_transition_trace")),
            runtime_sequence_drift=sequence_result.runtime_sequence_drift,
            dsp_sync_report=_as_dict(runtime_artifacts.get("dsp_sync_report")),
            evidence_references=evidence,
        )

        regression_result = build_patch_runtime_causality(
            target_id=target_id,
            patch_series_plan=_as_dict(patch_artifacts.get("patch_series_plan")),
            runtime_patch_correlation=_as_dict(patch_artifacts.get("runtime_patch_correlation")),
            runtime_drift_report=_as_dict(runtime_artifacts.get("runtime_drift_report")),
            migration_runtime_alignment=_as_dict(migration_artifacts.get("migration_runtime_alignment")),
            portability_blockers=_as_dict(migration_artifacts.get("portability_blockers")),
            upstream_equivalence_map=_as_dict(migration_artifacts.get("upstream_equivalence_map")),
            vendor_contamination_report=_as_dict(patch_artifacts.get("vendor_contamination_report")),
            evidence_references=evidence,
        )

        root_result = build_root_cause_candidates(
            target_id=target_id,
            runtime_sequence_drift=sequence_result.runtime_sequence_drift,
            lifecycle_violation_report=lifecycle_result.lifecycle_violation_report,
            topology_runtime_causality=topology_result.topology_runtime_causality,
            regression_causality_report=regression_result.regression_causality_report,
            fusion_rootcause_report=_as_dict(runtime_artifacts.get("fusion_rootcause_report")),
            upstream_equivalence_map=_as_dict(migration_artifacts.get("upstream_equivalence_map")),
            evidence_references=evidence,
        )

        confidence_result = build_engineering_confidence_report(
            target_id=target_id,
            governance_state=governance_state,
            replay_traces=replay_traces,
            runtime_sequence_drift=sequence_result.runtime_sequence_drift,
            lifecycle_violation_report=lifecycle_result.lifecycle_violation_report,
            topology_runtime_causality=topology_result.topology_runtime_causality,
            regression_causality_report=regression_result.regression_causality_report,
            root_cause_candidates=root_result.root_cause_candidates,
            evidence_references=evidence,
        )

        runtime_incident_graph = _build_runtime_incident_graph(
            target_id=target_id,
            sequence_result=sequence_result,
            lifecycle_result=lifecycle_result,
            topology_result=topology_result,
            regression_result=regression_result,
            root_result=root_result,
            confidence_result=confidence_result,
            evidence_references=evidence,
        )

        artifacts: dict[str, Any] = {
            "runtime_incident_graph": runtime_incident_graph,
            "root_cause_candidates": root_result.root_cause_candidates,
            "lifecycle_violation_report": lifecycle_result.lifecycle_violation_report,
            "runtime_sequence_drift": sequence_result.runtime_sequence_drift,
            "topology_runtime_causality": topology_result.topology_runtime_causality,
            "regression_causality_report": regression_result.regression_causality_report,
            "engineering_confidence_report": confidence_result.engineering_confidence_report,
        }

        deterministic_replay = _build_deterministic_incident_replay(
            target_id=target_id,
            lineage_id=str(lineage_id),
            runtime_incident_graph=runtime_incident_graph,
            artifacts=artifacts,
            replay_traces=replay_traces,
            evidence_references=evidence,
            previous_lineage=previous_incident_lineage,
        )
        artifacts["deterministic_incident_replay"] = deterministic_replay

        classification = str(confidence_result.engineering_confidence_report.get("classification", "UNKNOWN"))

        bundle = {
            "schema_version": "1.0",
            "phase": "RUNTIME_INCIDENT_RECONSTRUCTION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime": runtime_adapter,
                "topology": topology_adapter,
                "semantic": semantic_adapter,
            },
            "replay_traces": dict(replay_traces),
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["runtime_incident_reconstruction_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "artifacts": artifacts,
                "adapter_fingerprints": {
                    "runtime": str(runtime_adapter.get("fingerprint", "")),
                    "topology": str(topology_adapter.get("fingerprint", "")),
                    "semantic": str(semantic_adapter.get("fingerprint", "")),
                },
            }
        )

        return RuntimeIncidentReconstructionResult(incident_bundle=bundle)


class RuntimeIncidentReconstructionRegistry:
    """Replay-safe persistence for runtime incident reasoning artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "runtime_incident_graph": self._output_dir / "runtime_incident_graph.json",
            "root_cause_candidates": self._output_dir / "root_cause_candidates.json",
            "lifecycle_violation_report": self._output_dir / "lifecycle_violation_report.json",
            "runtime_sequence_drift": self._output_dir / "runtime_sequence_drift.json",
            "topology_runtime_causality": self._output_dir / "topology_runtime_causality.json",
            "regression_causality_report": self._output_dir / "regression_causality_report.json",
            "deterministic_incident_replay": self._output_dir / "deterministic_incident_replay.json",
            "engineering_confidence_report": self._output_dir / "engineering_confidence_report.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_incident_reasoning"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "runtime_incident_reconstruction_fingerprint": str(
                payload.get("runtime_incident_reconstruction_fingerprint", "")
            ),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-3000:]

        registry["runtime_incident_reasoning"] = {
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
                "type": "runtime_incident_reasoning",
                "recorded_at": _utc_now_iso(),
                "runtime_incident_reconstruction_fingerprint": str(
                    payload.get("runtime_incident_reconstruction_fingerprint", "")
                ),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-12000:]

        registry.setdefault("runtime_incident_lineage", [])
        incident_lineage = [
            row
            for row in _as_list(registry.get("runtime_incident_lineage"))
            if isinstance(row, dict)
        ]
        incident_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "runtime_incident_reconstruction_fingerprint": entry[
                    "runtime_incident_reconstruction_fingerprint"
                ],
            }
        )
        registry["runtime_incident_lineage"] = incident_lineage[-5000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "runtime_incident_reconstruction_fingerprint": entry[
                "runtime_incident_reconstruction_fingerprint"
            ],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_incident_reasoning"))
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
            "replay_type": "runtime_incident_reasoning",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "runtime_incident_reconstruction_fingerprint": str(
                _as_dict(selected).get("runtime_incident_reconstruction_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "runtime_incident_reconstruction_fingerprint": str(
                        _as_dict(selected).get("runtime_incident_reconstruction_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_incident_replay.json", replay_payload)
        return replay_payload
