"""Incremental migration orchestration layer.

Builds governed staged migration orchestration artifacts with deterministic
replay, rollback-aware reasoning, and partial state tracking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.incremental_equivalence_engine import (
    IncrementalEquivalenceResult,
    evaluate_incremental_equivalence,
)
from aura_sdk.transport.migration_checkpoint_registry import (
    MigrationCheckpointRegistryResult,
    build_migration_checkpoint_registry,
)
from aura_sdk.transport.migration_dependency_graph import (
    MigrationDependencyGraphResult,
    build_migration_dependency_graph,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.portability_transition_tracker import (
    PortabilityTransitionStateResult,
    track_portability_transitions,
)
from aura_sdk.transport.rollback_boundary_engine import (
    RollbackBoundaryReportResult,
    build_rollback_boundary_report,
)
from aura_sdk.transport.runtime_stability_gate import (
    RuntimeStabilityGateResult,
    evaluate_runtime_stability_gate,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.staged_conversion_planner import (
    StagedMigrationPlanResult,
    build_staged_migration_plan,
)


@dataclass(frozen=True)
class IncrementalMigrationOrchestrationResult:
    orchestration_bundle: dict[str, Any]


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


class IncrementalMigrationOrchestrator:
    """Target-agnostic orchestrator for staged migration reasoning."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _build_trace(
        self,
        *,
        target_id: str,
        lineage_id: str,
        artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        evidence_references: list[str],
        previous_trace_history: list[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        replay = _as_dict(replay_traces)
        governance = _as_dict(governance_state)

        artifact_fingerprints = {
            str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for name, payload in sorted(_as_dict(artifacts).items())
        }

        history = [row for row in _as_list(previous_trace_history or []) if isinstance(row, dict)]
        history.append(
            {
                "lineage_id": str(lineage_id),
                "classification": str(_as_dict(_as_dict(artifacts).get("staged_migration_plan")).get("classification", "UNKNOWN")),
                "progress": float(_as_dict(_as_dict(artifacts).get("portability_transition_state")).get("summary", {}).get("progress", 0.0) or 0.0),
                "artifact_fingerprints": artifact_fingerprints,
            }
        )
        history = history[-2000:]

        payload = {
            "schema_version": "1.0",
            "report_name": "deterministic_migration_orchestration_trace",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(_as_dict(artifacts).get("staged_migration_plan")).get("classification", "UNKNOWN")),
            "artifact_fingerprints": artifact_fingerprints,
            "replay": {
                "deterministic_event_ordering": _is_true(replay.get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
            },
            "governance": {
                "fail_closed_posture": bool(governance.get("fail_closed_posture", True)),
                "autonomous_mutation_allowed": any(
                    [
                        _is_true(governance.get("autonomous_patching_allowed", False)),
                        _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
                        _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
                        _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
                    ]
                ),
            },
            "lineage_history": history,
            "runtime_truth_precedence": True,
            "advisory_only_orchestration": True,
            "plugin_isolation": True,
            "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        runtime_evidence: Mapping[str, Any],
        structural_artifacts: Mapping[str, Any],
        conversion_reasoning_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        previous_transition_state: Mapping[str, Any] | None,
        previous_checkpoint_history: list[Mapping[str, Any]] | None,
        previous_trace_history: list[Mapping[str, Any]] | None,
        evidence_references: list[str] | None,
    ) -> IncrementalMigrationOrchestrationResult:
        plugin = self._plugins.load_plugin(target_id)

        topology_translation_adapter = _as_dict(
            plugin.topology_translation_adapter(
                {
                    "topology_cognition": _as_dict(structural_artifacts.get("topology_structure_graph")),
                    "dts_cognition": _as_dict(structural_artifacts.get("topology_structure_graph")),
                    "runtime_evidence": dict(runtime_evidence),
                }
            )
        )
        runtime_conversion_adapter = _as_dict(
            plugin.runtime_conversion_adapter(
                {
                    "runtime_evidence": dict(runtime_evidence),
                    "plugin_capability_state": {},
                    "governance_state": dict(governance_state),
                    "replay_traces": dict(replay_traces),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        dependency_result = build_migration_dependency_graph(
            target_id=target_id,
            structural_artifacts=structural_artifacts,
            conversion_reasoning_artifacts=conversion_reasoning_artifacts,
            adapter_payload={
                "topology_translation": topology_translation_adapter,
                "runtime_conversion": runtime_conversion_adapter,
            },
            evidence_references=evidence,
        )

        runtime_gate_result = evaluate_runtime_stability_gate(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            runtime_portability_analysis=_as_dict(conversion_reasoning_artifacts.get("runtime_portability_analysis")),
            migration_dependency_graph=dependency_result.migration_dependency_graph,
            replay_traces=replay_traces,
            governance_state=governance_state,
            evidence_references=evidence,
        )

        transition_result = track_portability_transitions(
            target_id=target_id,
            migration_dependency_graph=dependency_result.migration_dependency_graph,
            runtime_stability_gate_report=runtime_gate_result.runtime_stability_gate_report,
            portability_blocker_report=_as_dict(conversion_reasoning_artifacts.get("portability_blocker_report")),
            previous_transition_state=previous_transition_state,
            evidence_references=evidence,
        )

        incremental_equivalence_result = evaluate_incremental_equivalence(
            target_id=target_id,
            upstream_equivalence_confidence=_as_dict(conversion_reasoning_artifacts.get("upstream_equivalence_confidence")),
            migration_dependency_graph=dependency_result.migration_dependency_graph,
            portability_transition_state=transition_result.portability_transition_state,
            runtime_stability_gate_report=runtime_gate_result.runtime_stability_gate_report,
            evidence_references=evidence,
        )

        staged_plan_result = build_staged_migration_plan(
            target_id=target_id,
            migration_dependency_graph=dependency_result.migration_dependency_graph,
            runtime_stability_gate_report=runtime_gate_result.runtime_stability_gate_report,
            portability_transition_state=transition_result.portability_transition_state,
            portability_blocker_report=_as_dict(conversion_reasoning_artifacts.get("portability_blocker_report")),
            incremental_equivalence_report=incremental_equivalence_result.incremental_equivalence_report,
            evidence_references=evidence,
        )

        rollback_result = build_rollback_boundary_report(
            target_id=target_id,
            staged_migration_plan=staged_plan_result.staged_migration_plan,
            portability_transition_state=transition_result.portability_transition_state,
            runtime_stability_gate_report=runtime_gate_result.runtime_stability_gate_report,
            portability_blocker_report=_as_dict(conversion_reasoning_artifacts.get("portability_blocker_report")),
            evidence_references=evidence,
        )

        checkpoint_result = build_migration_checkpoint_registry(
            target_id=target_id,
            lineage_id=str(lineage_id),
            staged_migration_plan=staged_plan_result.staged_migration_plan,
            portability_transition_state=transition_result.portability_transition_state,
            rollback_boundary_report=rollback_result.rollback_boundary_report,
            runtime_stability_gate_report=runtime_gate_result.runtime_stability_gate_report,
            incremental_equivalence_report=incremental_equivalence_result.incremental_equivalence_report,
            previous_checkpoints=previous_checkpoint_history,
            evidence_references=evidence,
        )

        artifacts = {
            "staged_migration_plan": staged_plan_result.staged_migration_plan,
            "migration_dependency_graph": dependency_result.migration_dependency_graph,
            "rollback_boundary_report": rollback_result.rollback_boundary_report,
            "runtime_stability_gate_report": runtime_gate_result.runtime_stability_gate_report,
            "portability_transition_state": transition_result.portability_transition_state,
            "incremental_equivalence_report": incremental_equivalence_result.incremental_equivalence_report,
            "migration_checkpoint_registry": checkpoint_result.migration_checkpoint_registry,
        }

        trace = self._build_trace(
            target_id=target_id,
            lineage_id=str(lineage_id),
            artifacts=artifacts,
            replay_traces=replay_traces,
            governance_state=governance_state,
            evidence_references=evidence,
            previous_trace_history=previous_trace_history,
        )
        artifacts["deterministic_migration_orchestration_trace"] = trace

        bundle = {
            "schema_version": "1.0",
            "phase": "INCREMENTAL_MIGRATION_ORCHESTRATION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(staged_plan_result.staged_migration_plan.get("classification", "UNKNOWN")),
            "risk_classification": str(_as_dict(conversion_reasoning_artifacts.get("portability_blocker_report", {})).get("risk_classification", "UNKNOWN")),
            "runtime_truth_precedence": True,
            "advisory_only_orchestration": True,
            "plugin_isolation": True,
            "plugin_adapters": {
                "topology_translation": topology_translation_adapter,
                "runtime_conversion": runtime_conversion_adapter,
            },
            "governance_state": dict(governance_state),
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["migration_orchestration_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": bundle["classification"],
                "artifacts": artifacts,
            }
        )

        return IncrementalMigrationOrchestrationResult(orchestration_bundle=bundle)


class MigrationOrchestrationRegistry:
    """Replay-safe persistence for incremental migration orchestration artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "staged_migration_plan": self._output_dir / "staged_migration_plan.json",
            "migration_dependency_graph": self._output_dir / "migration_dependency_graph.json",
            "rollback_boundary_report": self._output_dir / "rollback_boundary_report.json",
            "runtime_stability_gate_report": self._output_dir / "runtime_stability_gate_report.json",
            "portability_transition_state": self._output_dir / "portability_transition_state.json",
            "incremental_equivalence_report": self._output_dir / "incremental_equivalence_report.json",
            "migration_checkpoint_registry": self._output_dir / "migration_checkpoint_registry.json",
            "deterministic_migration_orchestration_trace": self._output_dir / "deterministic_migration_orchestration_trace.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("incremental_migration_orchestration"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "risk_classification": str(payload.get("risk_classification", "UNKNOWN")),
            "migration_orchestration_fingerprint": str(payload.get("migration_orchestration_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-2000:]

        registry["incremental_migration_orchestration"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineages = _as_list(registry.get("cognition_lineage"))
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "incremental_migration_orchestration",
                "recorded_at": _utc_now_iso(),
                "migration_orchestration_fingerprint": str(payload.get("migration_orchestration_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-9000:]

        registry.setdefault("migration_orchestration_lineage", [])
        orchestration_lineage = _as_list(registry.get("migration_orchestration_lineage"))
        orchestration_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "risk_classification": entry["risk_classification"],
                "migration_orchestration_fingerprint": entry["migration_orchestration_fingerprint"],
            }
        )
        registry["migration_orchestration_lineage"] = orchestration_lineage[-3000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "risk_classification": entry["risk_classification"],
            "migration_orchestration_fingerprint": entry["migration_orchestration_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("incremental_migration_orchestration"))
        history = _as_list(state.get("history"))

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
            "replay_type": "incremental_migration_orchestration",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "risk_classification": str(_as_dict(selected).get("risk_classification", "UNKNOWN")),
            "migration_orchestration_fingerprint": str(_as_dict(selected).get("migration_orchestration_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "risk_classification": str(_as_dict(selected).get("risk_classification", "UNKNOWN")),
                    "migration_orchestration_fingerprint": str(_as_dict(selected).get("migration_orchestration_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_migration_orchestration_replay.json", replay_payload)
        return replay_payload
