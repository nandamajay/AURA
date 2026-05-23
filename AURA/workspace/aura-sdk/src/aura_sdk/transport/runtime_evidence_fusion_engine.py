"""Runtime Evidence Fusion Layer orchestration.

Fuses runtime/topology/semantic/migration/patch cognition into a unified,
replay-safe engineering truth model while preserving governance and plugin
isolation boundaries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.cross_domain_reasoning_engine import (
    CrossDomainReasoningResult,
    build_cross_domain_reasoning,
)
from aura_sdk.transport.deterministic_fusion_replay import (
    DeterministicFusionReplayResult,
    build_deterministic_fusion_replay,
)
from aura_sdk.transport.dsp_runtime_causality import (
    DspRuntimeCausalityResult,
    build_dsp_runtime_causality,
)
from aura_sdk.transport.lifecycle_causality_mapper import (
    LifecycleCausalityMapResult,
    build_lifecycle_causality_map,
)
from aura_sdk.transport.migration_runtime_alignment import (
    MigrationRuntimeAlignmentResult,
    build_migration_runtime_alignment,
)
from aura_sdk.transport.patch_runtime_lineage import (
    PatchRuntimeLineageResult,
    build_patch_runtime_lineage,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.regression_rootcause_reasoner import (
    RegressionRootcauseResult,
    reason_regression_rootcause,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.topology_runtime_correlator import (
    RuntimeTopologyCorrelationResult,
    correlate_topology_runtime,
)
from aura_sdk.transport.unified_engineering_truth_graph import (
    UnifiedEngineeringTruthGraphResult,
    build_unified_engineering_truth_graph,
)


@dataclass(frozen=True)
class RuntimeEvidenceFusionResult:
    fusion_bundle: dict[str, Any]


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


def _compute_engineering_confidence(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    runtime_topology_result: RuntimeTopologyCorrelationResult,
    lifecycle_result: LifecycleCausalityMapResult,
    migration_result: MigrationRuntimeAlignmentResult,
    patch_result: PatchRuntimeLineageResult,
    dsp_result: DspRuntimeCausalityResult,
    cross_domain_result: CrossDomainReasoningResult,
    rootcause_result: RegressionRootcauseResult,
    truth_graph_result: UnifiedEngineeringTruthGraphResult,
    replay_result: DeterministicFusionReplayResult,
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

    replay_signal = bool(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    rootcause_summary = _as_dict(rootcause_result.regression_rootcause_report.get("summary"))
    high = int(rootcause_summary.get("high_severity_count", 0) or 0)
    medium = int(rootcause_summary.get("medium_severity_count", 0) or 0)
    rootcause_safety = round(max(0.0, 1.0 - min(1.0, (high * 2 + medium) / 10.0)), 3)

    factors = {
        "runtime_topology_correlation": runtime_topology_result.correlation_score,
        "lifecycle_causality": lifecycle_result.causality_score,
        "migration_runtime_alignment": migration_result.alignment_score,
        "patch_runtime_lineage": patch_result.lineage_score,
        "dsp_runtime_causality": dsp_result.causality_score,
        "cross_domain_reasoning": cross_domain_result.reasoning_score,
        "rootcause_safety": rootcause_safety,
        "unified_truth_graph_confidence": truth_graph_result.graph_confidence,
        "deterministic_fusion_replay": replay_result.replay_score,
        "governance_safety": 1.0 if governance_ok else 0.0,
        "replay_signal": 1.0 if replay_signal else 0.0,
    }

    engineering_confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.10 * factors["runtime_topology_correlation"]
                + 0.09 * factors["lifecycle_causality"]
                + 0.09 * factors["migration_runtime_alignment"]
                + 0.09 * factors["patch_runtime_lineage"]
                + 0.09 * factors["dsp_runtime_causality"]
                + 0.11 * factors["cross_domain_reasoning"]
                + 0.09 * factors["rootcause_safety"]
                + 0.11 * factors["unified_truth_graph_confidence"]
                + 0.10 * factors["deterministic_fusion_replay"]
                + 0.08 * factors["governance_safety"]
                + 0.05 * factors["replay_signal"],
            ),
        ),
        3,
    )

    classifications = {
        str(runtime_topology_result.runtime_topology_correlation.get("classification", "")),
        str(lifecycle_result.lifecycle_causality_map.get("classification", "")),
        str(migration_result.migration_runtime_alignment.get("classification", "")),
        str(patch_result.patch_runtime_lineage.get("classification", "")),
        str(dsp_result.dsp_runtime_causality_report.get("classification", "")),
        str(cross_domain_result.cross_domain_reasoning.get("classification", "")),
        str(rootcause_result.regression_rootcause_report.get("classification", "")),
        str(truth_graph_result.unified_engineering_truth_graph.get("classification", "")),
    }

    classification = "PASS"
    if not governance_ok or "FAIL_CLOSED" in classifications:
        classification = "FAIL_CLOSED"
    elif engineering_confidence < 0.68:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "engineering_confidence_score",
        "target_id": str(target_id),
        "classification": classification,
        "engineering_confidence": engineering_confidence,
        "factors": factors,
        "summary": {
            "governance_ok": governance_ok,
            "replay_signal_present": replay_signal,
            "fail_closed_domain_count": len(
                [item for item in classifications if str(item).strip() == "FAIL_CLOSED"]
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "preserve_migration_governance_rules": True,
        "evidence_references": [str(item) for item in evidence_references if str(item).strip()],
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class RuntimeEvidenceFusionEngine:
    """Unified runtime evidence fusion orchestrator."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        lineage_id: str,
        runtime_artifacts: Mapping[str, Any],
        topology_artifacts: Mapping[str, Any],
        semantic_artifacts: Mapping[str, Any],
        migration_artifacts: Mapping[str, Any],
        patch_artifacts: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_fusion_lineage: list[Mapping[str, Any]] | None,
    ) -> RuntimeEvidenceFusionResult:
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
                    "regression_history": _as_list(previous_fusion_lineage or []),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        runtime_truth_graph = _as_dict(runtime_artifacts.get("runtime_truth_graph"))
        topology_runtime_graph = _as_dict(topology_artifacts.get("topology_runtime_graph"))

        topology_runtime_result = correlate_topology_runtime(
            target_id=target_id,
            topology_runtime_graph=topology_runtime_graph,
            runtime_truth_graph=runtime_truth_graph,
            pcm_lifecycle_trace=_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
            dapm_transition_trace=_as_dict(runtime_artifacts.get("dapm_transition_trace")),
            soundwire_runtime_graph=_as_dict(runtime_artifacts.get("soundwire_runtime_graph")),
            evidence_references=evidence,
        )

        lifecycle_result = build_lifecycle_causality_map(
            target_id=target_id,
            pcm_lifecycle_trace=_as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
            dapm_transition_trace=_as_dict(runtime_artifacts.get("dapm_transition_trace")),
            irq_timing_report=_as_dict(runtime_artifacts.get("irq_timing_report")),
            dsp_sync_report=_as_dict(runtime_artifacts.get("dsp_sync_report")),
            runtime_topology_correlation=topology_runtime_result.runtime_topology_correlation,
            evidence_references=evidence,
        )

        migration_result = build_migration_runtime_alignment(
            target_id=target_id,
            migration_dependency_graph=_as_dict(migration_artifacts.get("migration_dependency_graph")),
            portability_transition_state=_as_dict(migration_artifacts.get("portability_transition_state")),
            migration_checkpoint_registry=_as_dict(
                migration_artifacts.get("migration_checkpoint_registry")
            ),
            runtime_drift_report=_as_dict(runtime_artifacts.get("runtime_drift_report")),
            runtime_confidence_score=_as_dict(runtime_artifacts.get("runtime_confidence_score")),
            evidence_references=evidence,
        )

        patch_result = build_patch_runtime_lineage(
            target_id=target_id,
            patch_series_plan=_as_dict(patch_artifacts.get("patch_series_plan")),
            runtime_patch_correlation=_as_dict(patch_artifacts.get("runtime_patch_correlation")),
            runtime_drift_report=_as_dict(runtime_artifacts.get("runtime_drift_report")),
            upstream_readiness_report=_as_dict(patch_artifacts.get("upstream_readiness_report")),
            evidence_references=evidence,
        )

        dsp_result = build_dsp_runtime_causality(
            target_id=target_id,
            dsp_sync_report=_as_dict(runtime_artifacts.get("dsp_sync_report")),
            irq_timing_report=_as_dict(runtime_artifacts.get("irq_timing_report")),
            soundwire_runtime_graph=_as_dict(runtime_artifacts.get("soundwire_runtime_graph")),
            lifecycle_causality_map=lifecycle_result.lifecycle_causality_map,
            evidence_references=evidence,
        )

        cross_domain_result = build_cross_domain_reasoning(
            target_id=target_id,
            runtime_topology_correlation=topology_runtime_result.runtime_topology_correlation,
            lifecycle_causality_map=lifecycle_result.lifecycle_causality_map,
            migration_runtime_alignment=migration_result.migration_runtime_alignment,
            patch_runtime_lineage=patch_result.patch_runtime_lineage,
            dsp_runtime_causality_report=dsp_result.dsp_runtime_causality_report,
            upstream_readiness_report=_as_dict(patch_artifacts.get("upstream_readiness_report")),
            runtime_confidence_score=_as_dict(runtime_artifacts.get("runtime_confidence_score")),
            evidence_references=evidence,
        )

        rootcause_result = reason_regression_rootcause(
            target_id=target_id,
            runtime_drift_report=_as_dict(runtime_artifacts.get("runtime_drift_report")),
            lifecycle_causality_map=lifecycle_result.lifecycle_causality_map,
            migration_runtime_alignment=migration_result.migration_runtime_alignment,
            patch_runtime_lineage=patch_result.patch_runtime_lineage,
            dsp_runtime_causality_report=dsp_result.dsp_runtime_causality_report,
            cross_domain_reasoning=cross_domain_result.cross_domain_reasoning,
            evidence_references=evidence,
        )

        truth_graph_result = build_unified_engineering_truth_graph(
            target_id=target_id,
            runtime_topology_correlation=topology_runtime_result.runtime_topology_correlation,
            lifecycle_causality_map=lifecycle_result.lifecycle_causality_map,
            migration_runtime_alignment=migration_result.migration_runtime_alignment,
            patch_runtime_lineage=patch_result.patch_runtime_lineage,
            dsp_runtime_causality_report=dsp_result.dsp_runtime_causality_report,
            regression_rootcause_report=rootcause_result.regression_rootcause_report,
            cross_domain_reasoning=cross_domain_result.cross_domain_reasoning,
            evidence_references=evidence,
        )

        # Augment unified graph with explicit semantic/structural/migration/patch domains.
        truth_graph_payload = dict(truth_graph_result.unified_engineering_truth_graph)
        truth_nodes = [row for row in _as_list(truth_graph_payload.get("nodes")) if isinstance(row, dict)]
        truth_edges = [row for row in _as_list(truth_graph_payload.get("edges")) if isinstance(row, dict)]

        truth_nodes.extend(
            [
                {"id": "semantic_entity_graph", "kind": "domain_context"},
                {"id": "subsystem_boundary_map", "kind": "domain_context"},
                {"id": "migration_lineage", "kind": "domain_context"},
                {"id": "patch_series_plan", "kind": "domain_context"},
            ]
        )
        truth_edges.extend(
            [
                {
                    "from": "semantic_entity_graph",
                    "to": "cross_domain_reasoning",
                    "relation": "contextualizes",
                },
                {
                    "from": "subsystem_boundary_map",
                    "to": "patch_runtime_lineage",
                    "relation": "constrains",
                },
                {
                    "from": "migration_lineage",
                    "to": "migration_runtime_alignment",
                    "relation": "lineage_context",
                },
                {
                    "from": "patch_series_plan",
                    "to": "patch_runtime_lineage",
                    "relation": "sequencing_context",
                },
            ]
        )

        truth_graph_payload["nodes"] = truth_nodes
        truth_graph_payload["edges"] = truth_edges
        truth_graph_payload["domain_context"] = {
            "semantic_entity_graph_fingerprint": str(
                _as_dict(semantic_artifacts.get("semantic_entity_graph")).get(
                    "deterministic_fingerprint", ""
                )
            ),
            "subsystem_boundary_map_fingerprint": str(
                _as_dict(patch_artifacts.get("subsystem_boundary_map")).get(
                    "deterministic_fingerprint", ""
                )
            ),
            "migration_lineage_fingerprint": str(
                _as_dict(migration_artifacts.get("migration_lineage")).get(
                    "deterministic_fingerprint", ""
                )
            ),
            "patch_series_plan_fingerprint": str(
                _as_dict(patch_artifacts.get("patch_series_plan")).get(
                    "deterministic_fingerprint", ""
                )
            ),
        }
        truth_graph_payload["deterministic_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "graph_name": "unified_engineering_truth_graph",
                "nodes": truth_nodes,
                "edges": truth_edges,
                "domain_context": truth_graph_payload["domain_context"],
                "domain_fingerprints": _as_dict(truth_graph_payload.get("domain_fingerprints")),
                "classification": str(truth_graph_payload.get("classification", "UNKNOWN")),
                "graph_confidence": float(truth_graph_payload.get("graph_confidence", 0.0) or 0.0),
            }
        )

        artifacts: dict[str, Any] = {
            "unified_engineering_truth_graph": truth_graph_payload,
            "runtime_topology_correlation": topology_runtime_result.runtime_topology_correlation,
            "lifecycle_causality_map": lifecycle_result.lifecycle_causality_map,
            "migration_runtime_alignment": migration_result.migration_runtime_alignment,
            "patch_runtime_lineage": patch_result.patch_runtime_lineage,
            "dsp_runtime_causality_report": dsp_result.dsp_runtime_causality_report,
            "regression_rootcause_report": rootcause_result.regression_rootcause_report,
        }

        replay_result = build_deterministic_fusion_replay(
            target_id=target_id,
            lineage_id=str(lineage_id),
            unified_engineering_truth_graph=truth_graph_payload,
            artifacts=artifacts,
            replay_traces=replay_traces,
            evidence_references=evidence,
        )
        artifacts["deterministic_fusion_replay"] = replay_result.deterministic_fusion_replay

        engineering_confidence = _compute_engineering_confidence(
            target_id=target_id,
            governance_state=governance_state,
            replay_traces=replay_traces,
            runtime_topology_result=topology_runtime_result,
            lifecycle_result=lifecycle_result,
            migration_result=migration_result,
            patch_result=patch_result,
            dsp_result=dsp_result,
            cross_domain_result=cross_domain_result,
            rootcause_result=rootcause_result,
            truth_graph_result=truth_graph_result,
            replay_result=replay_result,
            evidence_references=evidence,
        )
        artifacts["engineering_confidence_score"] = engineering_confidence

        classifications = {
            str(_as_dict(value).get("classification", "")) for value in artifacts.values()
        }
        fusion_classification = "PASS"
        if str(engineering_confidence.get("classification", "")) == "FAIL_CLOSED" or "FAIL_CLOSED" in classifications:
            fusion_classification = "FAIL_CLOSED"
        elif str(engineering_confidence.get("classification", "")) == "ADVISORY_ONLY" or "ADVISORY_ONLY" in classifications:
            fusion_classification = "ADVISORY_ONLY"

        lineage_history = [
            row for row in _as_list(previous_fusion_lineage or []) if isinstance(row, dict)
        ]
        lineage_history.append(
            {
                "lineage_id": str(lineage_id),
                "recorded_at": _utc_now_iso(),
                "classification": fusion_classification,
                "engineering_confidence": float(
                    engineering_confidence.get("engineering_confidence", 0.0) or 0.0
                ),
                "fusion_fingerprint": str(
                    _as_dict(artifacts.get("unified_engineering_truth_graph")).get(
                        "deterministic_fingerprint", ""
                    )
                ),
            }
        )
        lineage_history = lineage_history[-2500:]

        bundle = {
            "schema_version": "1.0",
            "phase": "RUNTIME_EVIDENCE_FUSION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": fusion_classification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "preserve_migration_governance_rules": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime": runtime_adapter,
                "topology": topology_adapter,
                "semantic": semantic_adapter,
            },
            "replay_traces": dict(replay_traces),
            "evidence_references": evidence,
            "artifacts": artifacts,
            "fusion_lineage_history": lineage_history,
        }
        bundle["runtime_evidence_fusion_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "classification": fusion_classification,
                "artifacts": artifacts,
                "adapter_fingerprints": {
                    "runtime": str(runtime_adapter.get("fingerprint", "")),
                    "topology": str(topology_adapter.get("fingerprint", "")),
                    "semantic": str(semantic_adapter.get("fingerprint", "")),
                },
            }
        )

        return RuntimeEvidenceFusionResult(fusion_bundle=bundle)


class RuntimeEvidenceFusionRegistry:
    """Replay-safe persistence for runtime evidence fusion artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "unified_engineering_truth_graph": self._output_dir
            / "unified_engineering_truth_graph.json",
            "runtime_topology_correlation": self._output_dir
            / "runtime_topology_correlation.json",
            "lifecycle_causality_map": self._output_dir / "lifecycle_causality_map.json",
            "migration_runtime_alignment": self._output_dir
            / "migration_runtime_alignment.json",
            "patch_runtime_lineage": self._output_dir / "patch_runtime_lineage.json",
            "dsp_runtime_causality_report": self._output_dir
            / "dsp_runtime_causality_report.json",
            "regression_rootcause_report": self._output_dir
            / "regression_rootcause_report.json",
            "deterministic_fusion_replay": self._output_dir
            / "deterministic_fusion_replay.json",
            "engineering_confidence_score": self._output_dir
            / "engineering_confidence_score.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_fusion"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "runtime_evidence_fusion_fingerprint": str(
                payload.get("runtime_evidence_fusion_fingerprint", "")
            ),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }
        history.append(entry)
        history = history[-2500:]

        registry["runtime_evidence_fusion"] = {
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
                "type": "runtime_evidence_fusion",
                "recorded_at": _utc_now_iso(),
                "runtime_evidence_fusion_fingerprint": str(
                    payload.get("runtime_evidence_fusion_fingerprint", "")
                ),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineages[-10000:]

        registry.setdefault("runtime_evidence_fusion_lineage", [])
        fusion_lineage = [
            row
            for row in _as_list(registry.get("runtime_evidence_fusion_lineage"))
            if isinstance(row, dict)
        ]
        fusion_lineage.append(
            {
                "lineage_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "classification": entry["classification"],
                "runtime_evidence_fusion_fingerprint": entry[
                    "runtime_evidence_fusion_fingerprint"
                ],
            }
        )
        registry["runtime_evidence_fusion_lineage"] = fusion_lineage[-4000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "classification": entry["classification"],
            "runtime_evidence_fusion_fingerprint": entry[
                "runtime_evidence_fusion_fingerprint"
            ],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("runtime_evidence_fusion"))
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
            "replay_type": "runtime_evidence_fusion",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "runtime_evidence_fusion_fingerprint": str(
                _as_dict(selected).get("runtime_evidence_fusion_fingerprint", "")
            ),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(
                _as_dict(selected).get("evidence_references", [])
            ),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "classification": str(
                        _as_dict(selected).get("classification", "UNKNOWN")
                    ),
                    "runtime_evidence_fusion_fingerprint": str(
                        _as_dict(selected).get("runtime_evidence_fusion_fingerprint", "")
                    ),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_fusion_replay.json", replay_payload)
        return replay_payload
