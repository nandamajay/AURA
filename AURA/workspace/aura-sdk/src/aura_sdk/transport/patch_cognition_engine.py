"""Patch cognition and upstream readiness orchestration engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.api_evolution_tracker import (
    ApiEvolutionTraceResult,
    track_api_evolution,
)
from aura_sdk.transport.bisectability_validator import (
    BisectabilityValidationResult,
    validate_bisectability,
)
from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.patch_dependency_graph import (
    PatchDependencyGraphResult,
    build_patch_dependency_graph,
)
from aura_sdk.transport.patch_series_orchestrator import (
    PatchSeriesPlanResult,
    orchestrate_patch_series,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_patch_correlation import (
    RuntimePatchCorrelationResult,
    correlate_runtime_patch_impact,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.subsystem_boundary_reasoner import (
    SubsystemBoundaryResult,
    build_subsystem_boundary_map,
)
from aura_sdk.transport.upstream_governance_gate import (
    UpstreamGovernanceGateResult,
    evaluate_upstream_governance_gate,
)
from aura_sdk.transport.upstream_readiness_classifier import (
    UpstreamReadinessResult,
    classify_upstream_readiness,
)
from aura_sdk.transport.vendor_contamination_detector import (
    VendorContaminationResult,
    detect_vendor_contamination,
)


@dataclass(frozen=True)
class PatchCognitionResult:
    patch_cognition_bundle: dict[str, Any]


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


class PatchCognitionEngine:
    """Target-agnostic patch cognition orchestration with fail-closed governance."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _deterministic_trace(
        self,
        *,
        target_id: str,
        lineage_id: str,
        artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        evidence_references: list[str],
        previous_lineage: list[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        replay = _as_dict(replay_traces)
        governance = _as_dict(governance_state)

        artifact_fingerprints = {
            str(name): str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for name, payload in sorted(_as_dict(artifacts).items())
        }

        lineage_history = [row for row in _as_list(previous_lineage or []) if isinstance(row, dict)]
        lineage_history.append(
            {
                "lineage_id": str(lineage_id),
                "classification": str(_as_dict(_as_dict(artifacts).get("upstream_readiness_report")).get("classification", "UNKNOWN")),
                "readiness_score": float(_as_dict(_as_dict(artifacts).get("upstream_readiness_report")).get("readiness_score", 0.0) or 0.0),
                "artifact_fingerprints": artifact_fingerprints,
            }
        )
        lineage_history = lineage_history[-2000:]

        payload = {
            "schema_version": "1.0",
            "report_name": "deterministic_patch_trace",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(_as_dict(_as_dict(artifacts).get("upstream_readiness_report")).get("classification", "UNKNOWN")),
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
            "lineage_history": lineage_history,
            "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
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
        conversion_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        semantic_cognition: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_patch_lineage: list[Mapping[str, Any]] | None,
    ) -> PatchCognitionResult:
        plugin = self._plugins.load_plugin(target_id)

        subsystem_adapter = _as_dict(
            plugin.subsystem_descriptor_provider(
                {
                    "runtime_evidence": dict(runtime_evidence),
                    "plugin_capability_state": dict(plugin_capability_state),
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
        semantic_adapter = _as_dict(
            plugin.vendor_api_adapter(
                {
                    "driver_context": json.dumps(
                        {
                            "downstream_driver_graph": _as_dict(structural_artifacts.get("downstream_driver_graph")),
                            "semantic_cognition": dict(semantic_cognition),
                        },
                        sort_keys=True,
                    )
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        governance_result: UpstreamGovernanceGateResult = evaluate_upstream_governance_gate(
            target_id=target_id,
            governance_state=governance_state,
            replay_traces=replay_traces,
            evidence_references=evidence,
        )

        contamination_result: VendorContaminationResult = detect_vendor_contamination(
            target_id=target_id,
            downstream_driver_graph=_as_dict(structural_artifacts.get("downstream_driver_graph")),
            downstream_hook_inventory=_as_dict(structural_artifacts.get("downstream_hook_inventory")),
            semantic_cognition=semantic_cognition,
            adapter_payload=semantic_adapter,
            evidence_references=evidence,
        )

        subsystem_result: SubsystemBoundaryResult = build_subsystem_boundary_map(
            target_id=target_id,
            driver_registration_graph=_as_dict(structural_artifacts.get("driver_registration_graph")),
            callback_chain_graph=_as_dict(structural_artifacts.get("callback_chain_graph")),
            topology_runtime_graph=_as_dict(structural_artifacts.get("topology_runtime_graph")),
            subsystem_descriptor=subsystem_adapter,
            evidence_references=evidence,
        )

        api_trace_result: ApiEvolutionTraceResult = track_api_evolution(
            target_id=target_id,
            upstream_equivalence_map=_as_dict(structural_artifacts.get("upstream_equivalence_map")),
            portability_blockers=_as_dict(structural_artifacts.get("portability_blockers")),
            runtime_portability_analysis=_as_dict(conversion_artifacts.get("runtime_portability_analysis")),
            evidence_references=evidence,
        )

        dependency_result: PatchDependencyGraphResult = build_patch_dependency_graph(
            target_id=target_id,
            downstream_driver_graph=_as_dict(structural_artifacts.get("downstream_driver_graph")),
            upstream_equivalence_map=_as_dict(structural_artifacts.get("upstream_equivalence_map")),
            topology_runtime_graph=_as_dict(structural_artifacts.get("topology_runtime_graph")),
            subsystem_boundary_map=subsystem_result.subsystem_boundary_map,
            vendor_contamination_report=contamination_result.vendor_contamination_report,
            api_evolution_trace=api_trace_result.api_evolution_trace,
            evidence_references=evidence,
        )

        runtime_corr_result: RuntimePatchCorrelationResult = correlate_runtime_patch_impact(
            target_id=target_id,
            runtime_evidence={
                **dict(runtime_evidence),
                "expected_sequence": _as_list(runtime_adapter.get("expected_sequence")),
            },
            runtime_source_correlation=_as_dict(structural_artifacts.get("runtime_source_correlation")),
            patch_dependency_graph=dependency_result.patch_dependency_graph,
            topology_runtime_graph=_as_dict(structural_artifacts.get("topology_runtime_graph")),
            evidence_references=evidence,
        )

        bisect_result: BisectabilityValidationResult = validate_bisectability(
            target_id=target_id,
            patch_dependency_graph=dependency_result.patch_dependency_graph,
            runtime_patch_correlation=runtime_corr_result.runtime_patch_correlation,
            vendor_contamination_report=contamination_result.vendor_contamination_report,
            evidence_references=evidence,
        )

        readiness_result: UpstreamReadinessResult = classify_upstream_readiness(
            target_id=target_id,
            upstream_governance_gate=governance_result.upstream_governance_gate,
            vendor_contamination_report=contamination_result.vendor_contamination_report,
            subsystem_boundary_map=subsystem_result.subsystem_boundary_map,
            patch_dependency_graph=dependency_result.patch_dependency_graph,
            runtime_patch_correlation=runtime_corr_result.runtime_patch_correlation,
            bisectability_report=bisect_result.bisectability_report,
            api_evolution_trace=api_trace_result.api_evolution_trace,
            evidence_references=evidence,
        )

        plan_result: PatchSeriesPlanResult = orchestrate_patch_series(
            target_id=target_id,
            upstream_readiness_report=readiness_result.upstream_readiness_report,
            upstream_governance_gate=governance_result.upstream_governance_gate,
            patch_dependency_graph=dependency_result.patch_dependency_graph,
            subsystem_boundary_map=subsystem_result.subsystem_boundary_map,
            runtime_patch_correlation=runtime_corr_result.runtime_patch_correlation,
            bisectability_report=bisect_result.bisectability_report,
            evidence_references=evidence,
        )

        artifacts = {
            "upstream_readiness_report": readiness_result.upstream_readiness_report,
            "patch_dependency_graph": dependency_result.patch_dependency_graph,
            "subsystem_boundary_map": subsystem_result.subsystem_boundary_map,
            "vendor_contamination_report": contamination_result.vendor_contamination_report,
            "runtime_patch_correlation": runtime_corr_result.runtime_patch_correlation,
            "bisectability_report": bisect_result.bisectability_report,
            "api_evolution_trace": api_trace_result.api_evolution_trace,
            "patch_series_plan": plan_result.patch_series_plan,
            "upstream_governance_gate": governance_result.upstream_governance_gate,
        }

        trace = self._deterministic_trace(
            target_id=target_id,
            lineage_id=str(lineage_id),
            artifacts=artifacts,
            replay_traces=replay_traces,
            governance_state=governance_state,
            evidence_references=evidence,
            previous_lineage=previous_patch_lineage,
        )
        artifacts["deterministic_patch_trace"] = trace

        bundle = {
            "schema_version": "1.0",
            "phase": "PATCH_COGNITION_UPSTREAM_READINESS_ENGINE",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": str(readiness_result.upstream_readiness_report.get("classification", "UNKNOWN")),
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["patch_cognition_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": bundle["classification"],
                "artifacts": artifacts,
            }
        )

        return PatchCognitionResult(patch_cognition_bundle=bundle)


class PatchCognitionRegistry:
    """Replay-safe persistence for patch cognition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "upstream_readiness_report": self._output_dir / "upstream_readiness_report.json",
            "patch_dependency_graph": self._output_dir / "patch_dependency_graph.json",
            "subsystem_boundary_map": self._output_dir / "subsystem_boundary_map.json",
            "vendor_contamination_report": self._output_dir / "vendor_contamination_report.json",
            "runtime_patch_correlation": self._output_dir / "runtime_patch_correlation.json",
            "bisectability_report": self._output_dir / "bisectability_report.json",
            "api_evolution_trace": self._output_dir / "api_evolution_trace.json",
            "patch_series_plan": self._output_dir / "patch_series_plan.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("patch_cognition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "patch_cognition_fingerprint": str(payload.get("patch_cognition_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-2000:]

        registry["patch_cognition"] = {
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
                "type": "patch_cognition",
                "recorded_at": _utc_now_iso(),
                "patch_cognition_fingerprint": str(payload.get("patch_cognition_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-9000:]

        registry.setdefault("patch_cognition_lineage", [])
        patch_lineage = [row for row in _as_list(registry.get("patch_cognition_lineage")) if isinstance(row, dict)]
        patch_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "patch_cognition_fingerprint": entry["patch_cognition_fingerprint"],
            }
        )
        registry["patch_cognition_lineage"] = patch_lineage[-3000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "patch_cognition_fingerprint": entry["patch_cognition_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("patch_cognition"))
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
            "replay_type": "patch_cognition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "patch_cognition_fingerprint": str(_as_dict(selected).get("patch_cognition_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "patch_cognition_fingerprint": str(_as_dict(selected).get("patch_cognition_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_patch_replay.json", replay_payload)
        return replay_payload
