"""Governed Conversion Reasoning Engine.

Reasons about why downstream implementations cannot directly map upstream while
preserving advisory-only governance, deterministic replay, runtime-truth
precedence, and plugin isolation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.abstraction_gap_reasoner import (
    AbstractionGapReasoningResult,
    reason_abstraction_gaps,
)
from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.lifecycle_incompatibility_detector import (
    LifecycleIncompatibilityResult,
    detect_lifecycle_incompatibilities,
)
from aura_sdk.transport.migration_phase_planner import (
    MigrationPhasePlanResult,
    build_migration_phase_plan,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.portability_blocker_classifier import (
    GovernedPortabilityBlockerReportResult,
    classify_governed_portability_blockers,
)
from aura_sdk.transport.runtime_portability_reasoner import (
    RuntimePortabilityReasoningResult,
    reason_runtime_portability,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.upstream_equivalence_confidence import (
    UpstreamEquivalenceConfidenceResult,
    score_upstream_equivalence_confidence,
)
from aura_sdk.transport.vendor_dependency_classifier import (
    VendorDependencyGraphResult,
    classify_vendor_dependencies,
)


@dataclass(frozen=True)
class GovernedConversionReasoningResult:
    conversion_reasoning_bundle: dict[str, Any]


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


class GovernedConversionReasoningEngine:
    """Target-agnostic governed conversion reasoning orchestrator."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _reasoning_graph(
        self,
        *,
        target_id: str,
        lineage_id: str,
        vendor_result: VendorDependencyGraphResult,
        lifecycle_result: LifecycleIncompatibilityResult,
        abstraction_result: AbstractionGapReasoningResult,
        runtime_result: RuntimePortabilityReasoningResult,
        confidence_result: UpstreamEquivalenceConfidenceResult,
        blocker_result: GovernedPortabilityBlockerReportResult,
        phase_plan_result: MigrationPhasePlanResult,
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        replay = _as_dict(replay_traces)
        governance = _as_dict(governance_state)

        nodes = [
            {"id": f"target:{target_id}", "kind": "target"},
            {"id": f"lineage:{lineage_id}", "kind": "lineage"},
            {"id": "vendor_dependency_graph", "kind": "reasoning_artifact"},
            {"id": "lifecycle_incompatibility_report", "kind": "reasoning_artifact"},
            {"id": "abstraction_gap_report", "kind": "reasoning_artifact"},
            {"id": "runtime_portability_analysis", "kind": "reasoning_artifact"},
            {"id": "upstream_equivalence_confidence", "kind": "reasoning_artifact"},
            {"id": "portability_blocker_report", "kind": "reasoning_artifact"},
            {"id": "migration_phase_plan", "kind": "reasoning_artifact"},
            {"id": "deterministic_conversion_reasoning_trace", "kind": "reasoning_artifact"},
        ]

        edges = [
            {"from": f"target:{target_id}", "to": f"lineage:{lineage_id}", "relation": "reasoned_as"},
            {"from": f"lineage:{lineage_id}", "to": "vendor_dependency_graph", "relation": "depends_on"},
            {"from": f"lineage:{lineage_id}", "to": "lifecycle_incompatibility_report", "relation": "depends_on"},
            {"from": f"lineage:{lineage_id}", "to": "abstraction_gap_report", "relation": "depends_on"},
            {"from": f"lineage:{lineage_id}", "to": "runtime_portability_analysis", "relation": "depends_on"},
            {"from": "vendor_dependency_graph", "to": "portability_blocker_report", "relation": "contributes"},
            {"from": "lifecycle_incompatibility_report", "to": "portability_blocker_report", "relation": "contributes"},
            {"from": "abstraction_gap_report", "to": "portability_blocker_report", "relation": "contributes"},
            {"from": "runtime_portability_analysis", "to": "portability_blocker_report", "relation": "contributes"},
            {"from": "upstream_equivalence_confidence", "to": "portability_blocker_report", "relation": "constrains"},
            {"from": "portability_blocker_report", "to": "migration_phase_plan", "relation": "gates"},
            {"from": "migration_phase_plan", "to": "deterministic_conversion_reasoning_trace", "relation": "materializes"},
        ]

        payload = {
            "schema_version": "1.0",
            "graph_name": "conversion_reasoning_graph",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(blocker_result.portability_blocker_report.get("classification", "UNKNOWN")),
            "nodes": nodes,
            "edges": edges,
            "scores": {
                "vendor_dependency_risk": vendor_result.dependency_risk_score,
                "lifecycle_risk": lifecycle_result.lifecycle_risk_score,
                "abstraction_gap_score": abstraction_result.abstraction_gap_score,
                "runtime_portability_score": runtime_result.runtime_portability_score,
                "equivalence_confidence": confidence_result.overall_confidence,
                "portability_risk_score": blocker_result.risk_score,
                "phase_plan_confidence": phase_plan_result.plan_confidence,
            },
            "governance_state": {
                "fail_closed_posture": bool(governance.get("fail_closed_posture", True)),
                "autonomous_patching_allowed": _is_true(governance.get("autonomous_patching_allowed", False)),
                "autonomous_topology_rewrite_allowed": _is_true(
                    governance.get("autonomous_topology_rewrite_allowed", False)
                ),
                "autonomous_runtime_mutation_allowed": _is_true(
                    governance.get("autonomous_runtime_mutation_allowed", False)
                ),
                "autonomous_upstream_generation_allowed": _is_true(
                    governance.get("autonomous_upstream_generation_allowed", False)
                ),
            },
            "replay_state": {
                "deterministic_event_ordering": _is_true(replay.get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
            },
            "runtime_truth_precedence": True,
            "advisory_only_reasoning": True,
            "plugin_isolation": True,
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def _deterministic_trace(
        self,
        *,
        target_id: str,
        lineage_id: str,
        artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        evidence_references: list[str],
        governance_state: Mapping[str, Any],
        regression_history: list[Mapping[str, Any]],
        previous_lineage: list[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        replay = _as_dict(replay_traces)
        governance = _as_dict(governance_state)

        artifact_fingerprints = {
            str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for name, payload in sorted(_as_dict(artifacts).items())
        }

        history = [row for row in _as_list(previous_lineage or []) if isinstance(row, dict)]
        history.append(
            {
                "lineage_id": str(lineage_id),
                "artifact_fingerprints": artifact_fingerprints,
                "classification": str(
                    _as_dict(_as_dict(artifacts).get("portability_blocker_report")).get(
                        "classification", "UNKNOWN"
                    )
                ),
                "risk_classification": str(
                    _as_dict(_as_dict(artifacts).get("portability_blocker_report")).get(
                        "risk_classification", "UNKNOWN"
                    )
                ),
            }
        )
        history = history[-1500:]

        trace = {
            "schema_version": "1.0",
            "report_name": "deterministic_conversion_reasoning_trace",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(
                _as_dict(_as_dict(artifacts).get("portability_blocker_report")).get(
                    "classification", "UNKNOWN"
                )
            ),
            "risk_classification": str(
                _as_dict(_as_dict(artifacts).get("portability_blocker_report")).get(
                    "risk_classification", "UNKNOWN"
                )
            ),
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
            "regression_context": {
                "regression_history_entries": len([row for row in regression_history if isinstance(row, dict)]),
            },
            "lineage_history": history,
            "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
            "runtime_truth_precedence": True,
            "advisory_only_reasoning": True,
            "plugin_isolation": True,
        }
        trace["deterministic_fingerprint"] = stable_fingerprint(trace)
        return trace

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        runtime_evidence: Mapping[str, Any],
        structural_artifacts: Mapping[str, Any],
        semantic_cognition: Mapping[str, Any],
        topology_cognition: Mapping[str, Any],
        dts_cognition: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        regression_history: list[Mapping[str, Any]],
        previous_reasoning_lineage: list[Mapping[str, Any]] | None,
    ) -> GovernedConversionReasoningResult:
        plugin = self._plugins.load_plugin(target_id)

        mapping_adapter = _as_dict(
            plugin.downstream_upstream_adapter(
                {
                    "semantic_cognition": dict(semantic_cognition),
                    "topology_cognition": dict(topology_cognition),
                    "dts_cognition": dict(dts_cognition),
                    "runtime_evidence": dict(runtime_evidence),
                }
            )
        )
        runtime_adapter = _as_dict(
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

        downstream_hook_inventory = _as_dict(structural_artifacts.get("downstream_hook_inventory"))
        callback_chain_graph = _as_dict(structural_artifacts.get("callback_chain_graph"))
        driver_registration_graph = _as_dict(structural_artifacts.get("driver_registration_graph"))
        topology_structure_graph = _as_dict(structural_artifacts.get("topology_structure_graph"))
        upstream_equivalence_trace = _as_dict(structural_artifacts.get("upstream_equivalence_trace"))
        runtime_source_correlation = _as_dict(structural_artifacts.get("runtime_source_correlation"))

        vendor_result = classify_vendor_dependencies(
            target_id=target_id,
            downstream_hook_inventory=downstream_hook_inventory,
            callback_chain_graph=callback_chain_graph,
            semantic_cognition=semantic_cognition,
            adapter_payload=mapping_adapter,
            evidence_references=evidence,
        )

        lifecycle_result = detect_lifecycle_incompatibilities(
            target_id=target_id,
            driver_registration_graph=driver_registration_graph,
            callback_chain_graph=callback_chain_graph,
            upstream_equivalence_trace=upstream_equivalence_trace,
            evidence_references=evidence,
        )

        abstraction_result = reason_abstraction_gaps(
            target_id=target_id,
            topology_structure_graph=topology_structure_graph,
            upstream_equivalence_trace=upstream_equivalence_trace,
            vendor_dependency_graph=vendor_result.vendor_dependency_graph,
            lifecycle_incompatibility_report=lifecycle_result.lifecycle_incompatibility_report,
            evidence_references=evidence,
        )

        runtime_result = reason_runtime_portability(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            runtime_source_correlation=runtime_source_correlation,
            plugin_capability_state=plugin_capability_state,
            governance_state=governance_state,
            adapter_payload=runtime_adapter,
            evidence_references=evidence,
        )

        confidence_result = score_upstream_equivalence_confidence(
            target_id=target_id,
            upstream_equivalence_trace=upstream_equivalence_trace,
            abstraction_gap_report=abstraction_result.abstraction_gap_report,
            runtime_portability_analysis=runtime_result.runtime_portability_analysis,
            vendor_dependency_graph=vendor_result.vendor_dependency_graph,
            lifecycle_incompatibility_report=lifecycle_result.lifecycle_incompatibility_report,
            evidence_references=evidence,
        )

        blocker_result = classify_governed_portability_blockers(
            target_id=target_id,
            vendor_dependency_graph=vendor_result.vendor_dependency_graph,
            lifecycle_incompatibility_report=lifecycle_result.lifecycle_incompatibility_report,
            abstraction_gap_report=abstraction_result.abstraction_gap_report,
            runtime_portability_analysis=runtime_result.runtime_portability_analysis,
            upstream_equivalence_confidence=confidence_result.upstream_equivalence_confidence,
            governance_state=governance_state,
            evidence_references=evidence,
        )

        phase_plan_result = build_migration_phase_plan(
            target_id=target_id,
            portability_blocker_report=blocker_result.portability_blocker_report,
            abstraction_gap_report=abstraction_result.abstraction_gap_report,
            upstream_equivalence_confidence=confidence_result.upstream_equivalence_confidence,
            runtime_portability_analysis=runtime_result.runtime_portability_analysis,
            governance_state=governance_state,
            evidence_references=evidence,
        )

        conversion_reasoning_graph = self._reasoning_graph(
            target_id=target_id,
            lineage_id=str(lineage_id),
            vendor_result=vendor_result,
            lifecycle_result=lifecycle_result,
            abstraction_result=abstraction_result,
            runtime_result=runtime_result,
            confidence_result=confidence_result,
            blocker_result=blocker_result,
            phase_plan_result=phase_plan_result,
            replay_traces=replay_traces,
            governance_state=governance_state,
        )

        artifacts = {
            "conversion_reasoning_graph": conversion_reasoning_graph,
            "portability_blocker_report": blocker_result.portability_blocker_report,
            "migration_phase_plan": phase_plan_result.migration_phase_plan,
            "abstraction_gap_report": abstraction_result.abstraction_gap_report,
            "upstream_equivalence_confidence": confidence_result.upstream_equivalence_confidence,
            "lifecycle_incompatibility_report": lifecycle_result.lifecycle_incompatibility_report,
            "vendor_dependency_graph": vendor_result.vendor_dependency_graph,
            "runtime_portability_analysis": runtime_result.runtime_portability_analysis,
        }

        trace = self._deterministic_trace(
            target_id=target_id,
            lineage_id=str(lineage_id),
            artifacts=artifacts,
            replay_traces=replay_traces,
            evidence_references=evidence,
            governance_state=governance_state,
            regression_history=list(regression_history),
            previous_lineage=previous_reasoning_lineage,
        )
        artifacts["deterministic_conversion_reasoning_trace"] = trace

        bundle = {
            "schema_version": "1.0",
            "phase": "GOVERNED_CONVERSION_REASONING_ENGINE",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(blocker_result.portability_blocker_report.get("classification", "UNKNOWN")),
            "risk_classification": str(blocker_result.portability_blocker_report.get("risk_classification", "UNKNOWN")),
            "advisory_only_reasoning": True,
            "runtime_truth_precedence": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "downstream_upstream": mapping_adapter,
                "runtime_conversion": runtime_adapter,
            },
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["conversion_reasoning_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": bundle["classification"],
                "risk_classification": bundle["risk_classification"],
                "artifacts": artifacts,
            }
        )

        return GovernedConversionReasoningResult(conversion_reasoning_bundle=bundle)


class GovernedConversionReasoningRegistry:
    """Replay-safe persistence for governed conversion reasoning artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "conversion_reasoning_graph": self._output_dir / "conversion_reasoning_graph.json",
            "portability_blocker_report": self._output_dir / "portability_blocker_report.json",
            "migration_phase_plan": self._output_dir / "migration_phase_plan.json",
            "abstraction_gap_report": self._output_dir / "abstraction_gap_report.json",
            "upstream_equivalence_confidence": self._output_dir / "upstream_equivalence_confidence.json",
            "lifecycle_incompatibility_report": self._output_dir / "lifecycle_incompatibility_report.json",
            "vendor_dependency_graph": self._output_dir / "vendor_dependency_graph.json",
            "runtime_portability_analysis": self._output_dir / "runtime_portability_analysis.json",
            "deterministic_conversion_reasoning_trace": self._output_dir / "deterministic_conversion_reasoning_trace.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("governed_conversion_reasoning"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "risk_classification": str(payload.get("risk_classification", "UNKNOWN")),
            "conversion_reasoning_fingerprint": str(payload.get("conversion_reasoning_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-1500:]

        registry["governed_conversion_reasoning"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineage = _as_list(registry.get("cognition_lineage"))
        lineage.append(
            {
                "lineage_id": lineage_id,
                "type": "governed_conversion_reasoning",
                "recorded_at": _utc_now_iso(),
                "conversion_reasoning_fingerprint": str(
                    payload.get("conversion_reasoning_fingerprint", "")
                ),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineage[-8000:]

        registry.setdefault("conversion_reasoning_lineage", [])
        reason_lineage = _as_list(registry.get("conversion_reasoning_lineage"))
        reason_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "risk_classification": entry["risk_classification"],
                "conversion_reasoning_fingerprint": entry["conversion_reasoning_fingerprint"],
            }
        )
        registry["conversion_reasoning_lineage"] = reason_lineage[-2000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "risk_classification": entry["risk_classification"],
            "conversion_reasoning_fingerprint": entry["conversion_reasoning_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("governed_conversion_reasoning"))
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
            "replay_type": "governed_conversion_reasoning",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "risk_classification": str(_as_dict(selected).get("risk_classification", "UNKNOWN")),
            "conversion_reasoning_fingerprint": str(
                _as_dict(selected).get("conversion_reasoning_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "risk_classification": str(_as_dict(selected).get("risk_classification", "UNKNOWN")),
                    "conversion_reasoning_fingerprint": str(
                        _as_dict(selected).get("conversion_reasoning_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_conversion_reasoning_replay.json", replay_payload)
        return replay_payload
