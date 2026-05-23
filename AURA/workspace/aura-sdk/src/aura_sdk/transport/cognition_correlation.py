"""Unified multi-domain cognition correlation engine.

This module fuses runtime/topology/semantic/replay/regression/governance signals
into deterministic, replay-safe, lineage-backed cognition outputs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.causal_lineage import CausalLineageResult, build_causal_lineage
from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.confidence_evolution import ConfidenceEvolutionResult, evolve_confidence
from aura_sdk.transport.evidence_correlation import EvidenceCorrelationResult, correlate_evidence
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint

_ALLOWED_ACTIONS = [
    "correlate",
    "classify",
    "infer",
    "recommend",
    "replay",
    "quarantine",
]

_FORBIDDEN_ACTIONS = [
    "fabricate_evidence",
    "fabricate_causality",
    "auto_patch",
    "auto_modify_runtime",
    "override_governance",
]


@dataclass(frozen=True)
class CognitionCorrelationResult:
    correlation_bundle: dict[str, Any]


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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success"}
    return False


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


class UnifiedCognitionCorrelationEngine:
    """Target-agnostic correlation engine consuming plugin evidence adapters."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _build_unified_graph(
        self,
        *,
        target_id: str,
        evidence_result: EvidenceCorrelationResult,
        causal_result: CausalLineageResult,
        confidence_result: ConfidenceEvolutionResult,
        anomaly_report: Mapping[str, Any],
        plugin_adapters: Mapping[str, Any],
    ) -> dict[str, Any]:
        base_nodes = _as_list(evidence_result.evidence_lineage_graph.get("nodes"))
        base_edges = _as_list(evidence_result.evidence_lineage_graph.get("edges"))
        causal_nodes = _as_list(causal_result.causal_reasoning_graph.get("nodes"))
        causal_edges = _as_list(causal_result.causal_reasoning_graph.get("edges"))

        node_ids = {str(_as_dict(node).get("id", "")) for node in base_nodes if _as_dict(node).get("id")}
        for node in causal_nodes:
            node_id = str(_as_dict(node).get("id", ""))
            if node_id and node_id not in node_ids:
                base_nodes.append(node)
                node_ids.add(node_id)

        base_nodes.extend(
            [
                {"id": "confidence_evolution", "kind": "confidence_state"},
                {"id": "anomaly_correlation", "kind": "anomaly_state"},
                {"id": "plugin_runtime_adapter", "kind": "plugin_adapter"},
                {"id": "plugin_topology_adapter", "kind": "plugin_adapter"},
                {"id": "plugin_semantic_adapter", "kind": "plugin_adapter"},
            ]
        )

        base_edges.extend(causal_edges)
        base_edges.extend(
            [
                {"from": "runtime_evidence", "to": "confidence_evolution", "relation": "propagates"},
                {"from": "semantic_cognition", "to": "confidence_evolution", "relation": "propagates"},
                {"from": "replay_traces", "to": "confidence_evolution", "relation": "propagates"},
                {"from": "regression_history", "to": "confidence_evolution", "relation": "propagates"},
                {"from": "confidence_evolution", "to": "anomaly_correlation", "relation": "checks"},
                {"from": "plugin_runtime_adapter", "to": "runtime_evidence", "relation": "normalizes"},
                {"from": "plugin_topology_adapter", "to": "topology_cognition", "relation": "normalizes"},
                {"from": "plugin_semantic_adapter", "to": "semantic_cognition", "relation": "normalizes"},
            ]
        )

        return {
            "schema_version": "1.0",
            "graph_name": "unified_cognition_graph",
            "target_id": target_id,
            "nodes": base_nodes,
            "edges": base_edges,
            "causal_strength": causal_result.causal_strength,
            "evidence_completeness": evidence_result.evidence_completeness,
            "overall_confidence": _as_dict(confidence_result.confidence_evolution_report.get("current")).get(
                "overall_confidence", 0.0
            ),
            "anomaly_count": len(_as_list(_as_dict(anomaly_report).get("anomalies"))),
            "plugin_adapter_fingerprints": {
                "runtime": stable_fingerprint(_as_dict(plugin_adapters.get("runtime"))),
                "topology": stable_fingerprint(_as_dict(plugin_adapters.get("topology"))),
                "semantic": stable_fingerprint(_as_dict(plugin_adapters.get("semantic"))),
            },
        }

    def _anomaly_correlation(
        self,
        *,
        runtime_evidence: Mapping[str, Any],
        topology_cognition: Mapping[str, Any],
        semantic_cognition: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        governance_decisions: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_result: EvidenceCorrelationResult,
    ) -> dict[str, Any]:
        runtime = _as_dict(runtime_evidence)
        topology = _as_dict(topology_cognition)
        semantic = _as_dict(semantic_cognition)
        replay = _as_dict(replay_traces)
        governance = _as_dict(governance_decisions)
        capabilities = _as_dict(plugin_capability_state)

        anomalies: list[dict[str, Any]] = []

        runtime_success = _to_bool(runtime.get("playback_completion")) or _to_bool(runtime.get("process_success"))
        semantic_primary = str(_as_dict(semantic.get("classification")).get("primary_classification", "UNKNOWN"))

        topology_conf = float(
            _as_dict(topology.get("confidence")).get("topology_confidence", topology.get("topology_confidence", 0.0))
            or 0.0
        )
        replay_stable = _to_bool(replay.get("deterministic_event_ordering")) or bool(replay.get("deterministic_replay_fingerprint"))

        if runtime_success and semantic_primary in {"vendor_coupled", "governance_risky"} and not replay_stable:
            anomalies.append(
                {
                    "code": "semantic_runtime_mismatch",
                    "severity": "MEDIUM",
                    "details": "Runtime success observed while semantic risk is high and replay is unstable.",
                }
            )

        if topology_conf < 0.4:
            anomalies.append(
                {
                    "code": "topology_drift",
                    "severity": "MEDIUM",
                    "details": "Topology confidence below deterministic threshold.",
                }
            )

        if not replay_stable:
            anomalies.append(
                {
                    "code": "replay_instability",
                    "severity": "HIGH",
                    "details": "Replay traces do not show deterministic ordering guarantee.",
                }
            )

        if evidence_result.evidence_gaps:
            anomalies.append(
                {
                    "code": "evidence_gaps",
                    "severity": "MEDIUM",
                    "details": f"Missing domains: {', '.join(evidence_result.evidence_gaps)}",
                }
            )

        if _to_bool(governance.get("autonomous_patching_allowed", False)) or _to_bool(
            governance.get("autonomous_topology_rewrite_allowed", False)
        ):
            anomalies.append(
                {
                    "code": "governance_violations",
                    "severity": "HIGH",
                    "details": "Governance restrictions conflict with autonomous mutation flags.",
                }
            )

        if "supported" in capabilities and not _to_bool(capabilities.get("supported")) and runtime_success:
            anomalies.append(
                {
                    "code": "plugin_capability_inconsistency",
                    "severity": "HIGH",
                    "details": "Runtime success conflicts with plugin capability unsupported state.",
                }
            )

        classification = "PASS"
        if any(str(_as_dict(row).get("severity", "")).upper() == "HIGH" for row in anomalies):
            classification = "FAIL_CLOSED"
        elif anomalies:
            classification = "ADVISORY_ONLY"

        return {
            "schema_version": "1.0",
            "report_name": "anomaly_correlation_report",
            "classification": classification,
            "anomalies": anomalies,
            "deterministic_fingerprint": stable_fingerprint({"classification": classification, "anomalies": anomalies}),
        }

    def correlate(
        self,
        *,
        target_id: str,
        runtime_evidence: Mapping[str, Any],
        pcm_activity: Mapping[str, Any],
        mixer_state: Mapping[str, Any],
        topology_cognition: Mapping[str, Any],
        dts_cognition: Mapping[str, Any],
        semantic_cognition: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        regression_history: list[Mapping[str, Any]],
        plugin_capability_state: Mapping[str, Any],
        governance_decisions: Mapping[str, Any],
        lineage_id: str,
        evidence_references: list[str] | None,
        previous_confidence_state: Mapping[str, Any] | None,
    ) -> CognitionCorrelationResult:
        plugin = self._plugins.load_plugin(target_id)

        runtime_adapter = _as_dict(
            plugin.runtime_evidence_adapter(
                {
                    "runtime_evidence": dict(runtime_evidence),
                    "pcm_activity": dict(pcm_activity),
                    "mixer_state": dict(mixer_state),
                    "replay_traces": dict(replay_traces),
                    "governance_decisions": dict(governance_decisions),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": dict(topology_cognition),
                    "dts_cognition": dict(dts_cognition),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        semantic_adapter = _as_dict(
            plugin.semantic_evidence_adapter(
                {
                    "semantic_cognition": dict(semantic_cognition),
                    "regression_history": list(regression_history),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        adapter_bundle = {
            "runtime": runtime_adapter,
            "topology": topology_adapter,
            "semantic": semantic_adapter,
        }

        evidence_result = correlate_evidence(
            target_id=target_id,
            runtime_evidence=runtime_adapter.get("runtime_evidence", runtime_evidence),
            pcm_activity=runtime_adapter.get("pcm_activity", pcm_activity),
            mixer_state=runtime_adapter.get("mixer_state", mixer_state),
            topology_cognition=topology_adapter.get("topology_cognition", topology_cognition),
            dts_cognition=topology_adapter.get("dts_cognition", dts_cognition),
            semantic_cognition=semantic_adapter.get("semantic_cognition", semantic_cognition),
            replay_traces=runtime_adapter.get("replay_traces", replay_traces),
            regression_history=list(semantic_adapter.get("regression_history", regression_history)),
            plugin_capability_state=semantic_adapter.get("plugin_capability_state", plugin_capability_state),
            governance_decisions=runtime_adapter.get("governance_decisions", governance_decisions),
            adapter_evidence=adapter_bundle,
        )

        causal_result = build_causal_lineage(
            target_id=target_id,
            dts_cognition=topology_adapter.get("dts_cognition", dts_cognition),
            topology_cognition=topology_adapter.get("topology_cognition", topology_cognition),
            runtime_evidence=runtime_adapter.get("runtime_evidence", runtime_evidence),
            pcm_activity=runtime_adapter.get("pcm_activity", pcm_activity),
            regression_history=list(semantic_adapter.get("regression_history", regression_history)),
            semantic_cognition=semantic_adapter.get("semantic_cognition", semantic_cognition),
            replay_traces=runtime_adapter.get("replay_traces", replay_traces),
        )

        anomaly_report = self._anomaly_correlation(
            runtime_evidence=runtime_adapter.get("runtime_evidence", runtime_evidence),
            topology_cognition=topology_adapter.get("topology_cognition", topology_cognition),
            semantic_cognition=semantic_adapter.get("semantic_cognition", semantic_cognition),
            replay_traces=runtime_adapter.get("replay_traces", replay_traces),
            governance_decisions=runtime_adapter.get("governance_decisions", governance_decisions),
            plugin_capability_state=semantic_adapter.get("plugin_capability_state", plugin_capability_state),
            evidence_result=evidence_result,
        )

        confidence_result = evolve_confidence(
            runtime_cognition=runtime_adapter.get("runtime_evidence", runtime_evidence),
            topology_cognition=topology_adapter.get("topology_cognition", topology_cognition),
            semantic_cognition=semantic_adapter.get("semantic_cognition", semantic_cognition),
            replay_traces=runtime_adapter.get("replay_traces", replay_traces),
            regression_history=list(semantic_adapter.get("regression_history", regression_history)),
            evidence_completeness=evidence_result.evidence_completeness,
            mismatch_count=len(evidence_result.mismatches) + len(_as_list(anomaly_report.get("anomalies"))),
            governance_decisions=runtime_adapter.get("governance_decisions", governance_decisions),
            previous_confidence_state=previous_confidence_state,
        )

        unified_graph = self._build_unified_graph(
            target_id=target_id,
            evidence_result=evidence_result,
            causal_result=causal_result,
            confidence_result=confidence_result,
            anomaly_report=anomaly_report,
            plugin_adapters=adapter_bundle,
        )

        fusion_trace = {
            "schema_version": "1.0",
            "trace_name": "cognition_fusion_trace",
            "target_id": target_id,
            "lineage_id": str(lineage_id),
            "domain_fingerprints": evidence_result.domain_snapshot,
            "evidence_correlation_fingerprint": evidence_result.deterministic_fingerprint,
            "causal_lineage_fingerprint": causal_result.deterministic_fingerprint,
            "confidence_fingerprint": confidence_result.deterministic_fingerprint,
            "anomaly_fingerprint": str(anomaly_report.get("deterministic_fingerprint", "")),
            "event_order_preserved": True,
            "plugin_isolation_preserved": True,
        }

        artifacts = {
            "unified_cognition_graph": unified_graph,
            "causal_reasoning_graph": causal_result.causal_reasoning_graph,
            "evidence_lineage_graph": evidence_result.evidence_lineage_graph,
            "confidence_evolution_report": confidence_result.confidence_evolution_report,
            "anomaly_correlation_report": anomaly_report,
            "cognition_fusion_trace": fusion_trace,
        }

        canonical_fingerprint = stable_fingerprint(
            {
                "target_id": target_id,
                "lineage_id": str(lineage_id),
                "artifacts": artifacts,
                "governance_decisions": dict(governance_decisions),
                "adapter_fingerprints": {
                    "runtime": stable_fingerprint(runtime_adapter),
                    "topology": stable_fingerprint(topology_adapter),
                    "semantic": stable_fingerprint(semantic_adapter),
                },
            }
        )

        fusion_trace["deterministic_fusion_fingerprint"] = canonical_fingerprint

        bundle = {
            "schema_version": "1.0",
            "phase": "MULTI_DOMAIN_COGNITION_CORRELATION",
            "created_at": _utc_now_iso(),
            "target_id": target_id,
            "lineage_id": str(lineage_id),
            "governance_boundaries": {
                "allowed_actions": list(_ALLOWED_ACTIONS),
                "forbidden_actions": list(_FORBIDDEN_ACTIONS),
                "fail_closed": True,
            },
            "governance_decisions": dict(governance_decisions),
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
            "plugin_adapters": adapter_bundle,
            "artifacts": artifacts,
            "correlation_fingerprint": canonical_fingerprint,
        }

        return CognitionCorrelationResult(correlation_bundle=bundle)


class CognitionCorrelationRegistry:
    """Replay-safe persistence layer for multi-domain cognition correlation."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "unified_cognition_graph": self._output_dir / "unified_cognition_graph.json",
            "causal_reasoning_graph": self._output_dir / "causal_reasoning_graph.json",
            "evidence_lineage_graph": self._output_dir / "evidence_lineage_graph.json",
            "confidence_evolution_report": self._output_dir / "confidence_evolution_report.json",
            "anomaly_correlation_report": self._output_dir / "anomaly_correlation_report.json",
            "cognition_fusion_trace": self._output_dir / "cognition_fusion_trace.json",
        }

    def persist(self, correlation_bundle: Mapping[str, Any]) -> dict[str, Any]:
        bundle = dict(correlation_bundle)
        artifacts = _as_dict(bundle.get("artifacts"))
        lineage_id = str(bundle.get("lineage_id", "")).strip() or stable_fingerprint(bundle)

        artifact_paths = self._artifact_paths()
        for key, path in artifact_paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        payload = self._registry.load()
        state = _as_dict(payload.get("cognition_correlation"))
        history = _as_list(state.get("history"))

        confidence_report = _as_dict(artifacts.get("confidence_evolution_report"))
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(bundle.get("target_id", "")),
            "correlation_fingerprint": str(bundle.get("correlation_fingerprint", "")),
            "overall_confidence": _as_dict(confidence_report.get("current")).get("overall_confidence", 0.0),
            "evidence_completeness": _as_dict(confidence_report.get("current")).get("evidence_completeness", 0.0),
            "anomaly_classification": _as_dict(artifacts.get("anomaly_correlation_report")).get("classification", "UNKNOWN"),
            "artifact_paths": {key: str(path.resolve()) for key, path in artifact_paths.items()},
            "evidence_references": [str(item) for item in _as_list(bundle.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-1000:]

        payload["cognition_correlation"] = {
            "schema_version": "1.0",
            "latest": dict(bundle),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        payload.setdefault("confidence_evolution", [])
        payload["confidence_evolution"].append(
            {
                "run_id": lineage_id,
                "recorded_at": _utc_now_iso(),
                "runtime_confidence": _as_dict(confidence_report.get("factors")).get("repeated_runtime_validation", 0.0),
                "topology_confidence": _as_dict(confidence_report.get("factors")).get("topology_consistency", 0.0),
                "semantic_confidence": _as_dict(confidence_report.get("factors")).get("semantic_stability", 0.0),
                "evidence_completeness": _as_dict(confidence_report.get("factors")).get("evidence_completeness", 0.0),
                "correlation_confidence": _as_dict(confidence_report.get("current")).get("overall_confidence", 0.0),
            }
        )
        payload["confidence_evolution"] = _as_list(payload.get("confidence_evolution"))[-2000:]

        payload.setdefault("cognition_lineage", [])
        payload["cognition_lineage"].append(
            {
                "lineage_id": lineage_id,
                "type": "multi_domain_correlation",
                "recorded_at": _utc_now_iso(),
                "correlation_fingerprint": str(bundle.get("correlation_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        payload["cognition_lineage"] = _as_list(payload.get("cognition_lineage"))[-3000:]

        payload["updated_at"] = _utc_now_iso()
        self._registry.save(payload)

        return {
            "lineage_id": lineage_id,
            "correlation_fingerprint": str(bundle.get("correlation_fingerprint", "")),
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        payload = self._registry.load()
        state = _as_dict(payload.get("cognition_correlation"))
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
            "replay_type": "multi_domain_correlation",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "correlation_fingerprint": str(_as_dict(selected).get("correlation_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "correlation_fingerprint": str(_as_dict(selected).get("correlation_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "cognition_fusion_trace.json", replay_payload)
        return replay_payload
