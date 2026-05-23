"""Governance-safe upstream conversion planner.

Planner produces deterministic, evidence-backed conversion cognition artifacts
without autonomous code or topology mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.downstream_upstream_mapping import (
    DownstreamUpstreamMappingResult,
    build_downstream_upstream_mapping,
)
from aura_sdk.transport.migration_lineage import (
    MigrationLineageResult,
    build_migration_lineage,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_conversion_reasoning import (
    RuntimeConversionReasoningResult,
    analyze_runtime_conversion,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.topology_translation_cognition import (
    TopologyTranslationResult,
    build_topology_translation_report,
)

_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "plan",
    "recommend",
    "replay",
]

_FORBIDDEN_ACTIONS = [
    "autonomous_code_rewrite",
    "autonomous_dts_mutation",
    "autonomous_driver_mutation",
    "unsafe_topology_mutation",
]


@dataclass(frozen=True)
class UpstreamConversionPlannerResult:
    conversion_bundle: dict[str, Any]


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


class UpstreamConversionPlanner:
    """Target-agnostic conversion cognition planner using plugin adapters."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _governance_ok(self, governance_state: Mapping[str, Any]) -> bool:
        gov = _as_dict(governance_state)
        violations = [
            _to_bool(gov.get("autonomous_patching_allowed", False)),
            _to_bool(gov.get("autonomous_topology_rewrite_allowed", False)),
            _to_bool(gov.get("autonomous_upstream_generation_allowed", False)),
        ]
        return not any(violations)

    def _build_reasoning_graph(
        self,
        *,
        target_id: str,
        mapping_result: DownstreamUpstreamMappingResult,
        topology_result: TopologyTranslationResult,
        runtime_result: RuntimeConversionReasoningResult,
        migration_result: MigrationLineageResult,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "graph_name": "upstream_conversion_reasoning_graph",
            "target_id": target_id,
            "nodes": [
                {"id": f"target:{target_id}", "kind": "target"},
                {"id": "semantic_mapping", "kind": "semantic_mapping"},
                {"id": "topology_translation", "kind": "topology_translation"},
                {"id": "runtime_portability", "kind": "runtime_portability"},
                {"id": "migration_lineage", "kind": "migration_lineage"},
                {"id": "upstream_conversion_plan", "kind": "conversion_plan"},
            ],
            "edges": [
                {"from": f"target:{target_id}", "to": "semantic_mapping", "relation": "informs"},
                {"from": "semantic_mapping", "to": "topology_translation", "relation": "constrains"},
                {"from": "topology_translation", "to": "runtime_portability", "relation": "validates"},
                {"from": "runtime_portability", "to": "migration_lineage", "relation": "tracked_by"},
                {"from": "migration_lineage", "to": "upstream_conversion_plan", "relation": "gates"},
            ],
            "fingerprints": {
                "semantic_mapping": mapping_result.deterministic_fingerprint,
                "topology_translation": topology_result.deterministic_fingerprint,
                "runtime_portability": runtime_result.deterministic_fingerprint,
                "migration_lineage": migration_result.deterministic_fingerprint,
            },
        }

    def _build_confidence(
        self,
        *,
        mapping_result: DownstreamUpstreamMappingResult,
        topology_result: TopologyTranslationResult,
        runtime_result: RuntimeConversionReasoningResult,
        migration_result: MigrationLineageResult,
        replay_traces: Mapping[str, Any],
        governance_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        replay = _as_dict(replay_traces)
        replay_ok = _to_bool(replay.get("deterministic_event_ordering")) or bool(replay.get("deterministic_replay_fingerprint", ""))
        governance_ok = self._governance_ok(governance_state)

        factors = {
            "semantic_equivalence": mapping_result.semantic_equivalence_confidence,
            "topology_translation": topology_result.translation_confidence,
            "runtime_portability": runtime_result.portability_score,
            "migration_stability": round(max(0.0, 1.0 - migration_result.drift_score), 3),
            "replay_compatibility": 1.0 if replay_ok else 0.2,
            "governance_safety": 1.0 if governance_ok else 0.0,
        }

        score = round(
            0.22 * factors["semantic_equivalence"]
            + 0.20 * factors["topology_translation"]
            + 0.20 * factors["runtime_portability"]
            + 0.18 * factors["migration_stability"]
            + 0.10 * factors["replay_compatibility"]
            + 0.10 * factors["governance_safety"],
            3,
        )

        classification = "PASS"
        if not governance_ok:
            classification = "FAIL_CLOSED"
        elif str(runtime_result.runtime_portability_analysis.get("governance_classification", "")) == "FAIL_CLOSED":
            classification = "FAIL_CLOSED"
        elif score < 0.45:
            classification = "ADVISORY_ONLY"

        payload = {
            "schema_version": "1.0",
            "report_name": "upstream_conversion_confidence",
            "factors": factors,
            "overall_confidence_score": score,
            "classification": classification,
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def analyze(
        self,
        *,
        target_id: str,
        runtime_evidence: Mapping[str, Any],
        topology_cognition: Mapping[str, Any],
        dts_cognition: Mapping[str, Any],
        semantic_cognition: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        regression_history: list[Mapping[str, Any]],
        plugin_capability_state: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        lineage_id: str,
        evidence_references: list[str] | None,
        previous_migration_lineage: list[Mapping[str, Any]] | None,
    ) -> UpstreamConversionPlannerResult:
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
        topology_adapter = _as_dict(
            plugin.topology_translation_adapter(
                {
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

        mapping_result = build_downstream_upstream_mapping(
            target_id=target_id,
            semantic_cognition=semantic_cognition,
            topology_cognition=topology_cognition,
            adapter_payload=mapping_adapter,
            evidence_references=evidence_references,
        )

        topology_result = build_topology_translation_report(
            target_id=target_id,
            topology_cognition=topology_cognition,
            dts_cognition=dts_cognition,
            adapter_payload=topology_adapter,
        )

        runtime_result = analyze_runtime_conversion(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            plugin_capability_state=plugin_capability_state,
            governance_state=governance_state,
            replay_traces=replay_traces,
            adapter_payload=runtime_adapter,
        )

        translated_model = {
            "expected_runtime_seconds": _as_dict(runtime_adapter).get("expected_runtime_seconds", runtime_evidence.get("playback_runtime_seconds", 0.0)),
            "route_fingerprint": _as_dict(topology_adapter).get("route_fingerprint", runtime_evidence.get("route_fingerprint", "")),
            "required_capabilities": _as_dict(runtime_adapter).get("required_capabilities", _as_dict(plugin_capability_state.get("capabilities"))),
            "expected_sequence": _as_list(runtime_adapter.get("expected_sequence")),
        }

        migration_result = build_migration_lineage(
            target_id=target_id,
            lineage_id=lineage_id,
            runtime_evidence=runtime_evidence,
            translated_model=translated_model,
            regression_history=list(regression_history),
            previous_lineage=list(previous_migration_lineage or []),
        )

        confidence_report = self._build_confidence(
            mapping_result=mapping_result,
            topology_result=topology_result,
            runtime_result=runtime_result,
            migration_result=migration_result,
            replay_traces=replay_traces,
            governance_state=governance_state,
        )

        reasoning_graph = self._build_reasoning_graph(
            target_id=target_id,
            mapping_result=mapping_result,
            topology_result=topology_result,
            runtime_result=runtime_result,
            migration_result=migration_result,
        )

        replay_compatibility = {
            "schema_version": "1.0",
            "report_name": "translation_replay_compatibility",
            "deterministic_replay_supported": _to_bool(replay_traces.get("deterministic_event_ordering"))
            or bool(replay_traces.get("deterministic_replay_fingerprint", "")),
            "mapping_fingerprint": mapping_result.deterministic_fingerprint,
            "topology_fingerprint": topology_result.deterministic_fingerprint,
            "runtime_portability_fingerprint": runtime_result.deterministic_fingerprint,
            "migration_lineage_fingerprint": migration_result.deterministic_fingerprint,
        }

        suggested_mappings = [
            {
                "downstream_construct": row.get("downstream_construct", ""),
                "upstream_equivalent": row.get("upstream_equivalent", ""),
                "confidence": row.get("equivalence_confidence", 0.0),
            }
            for row in _as_list(mapping_result.mapping_graph.get("entries"))
        ]

        artifacts = {
            "downstream_upstream_mapping_graph": mapping_result.mapping_graph,
            "topology_translation_report": topology_result.topology_translation_report,
            "runtime_portability_analysis": runtime_result.runtime_portability_analysis,
            "migration_lineage": migration_result.migration_lineage,
            "upstream_conversion_confidence": confidence_report,
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "TRANSLATION_INTELLIGENCE_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": target_id,
            "lineage_id": str(lineage_id),
            "governance_boundaries": {
                "allowed_actions": list(_ALLOWED_ACTIONS),
                "forbidden_actions": list(_FORBIDDEN_ACTIONS),
                "fail_closed": True,
            },
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
            "plugin_adapters": {
                "mapping": mapping_adapter,
                "topology_translation": topology_adapter,
                "runtime_conversion": runtime_adapter,
            },
            "suggested_upstream_mappings": suggested_mappings,
            "reasoning_graph": reasoning_graph,
            "replay_compatibility_report": replay_compatibility,
            "artifacts": artifacts,
        }

        bundle["translation_fingerprint"] = stable_fingerprint(
            {
                "target_id": target_id,
                "lineage_id": str(lineage_id),
                "artifacts": artifacts,
                "reasoning_graph": reasoning_graph,
                "replay_compatibility_report": replay_compatibility,
                "governance_boundaries": bundle["governance_boundaries"],
            }
        )

        return UpstreamConversionPlannerResult(conversion_bundle=bundle)


class TranslationIntelligenceRegistry:
    """Replay-safe persistence for translation intelligence artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "downstream_upstream_mapping_graph": self._output_dir / "downstream_upstream_mapping_graph.json",
            "topology_translation_report": self._output_dir / "topology_translation_report.json",
            "runtime_portability_analysis": self._output_dir / "runtime_portability_analysis.json",
            "migration_lineage": self._output_dir / "migration_lineage.json",
            "upstream_conversion_confidence": self._output_dir / "upstream_conversion_confidence.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("translation_intelligence"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "translation_fingerprint": str(payload.get("translation_fingerprint", "")),
            "artifact_paths": {key: str(path.resolve()) for key, path in paths.items()},
            "confidence": _as_dict(artifacts.get("upstream_conversion_confidence")).get("overall_confidence_score", 0.0),
            "classification": _as_dict(artifacts.get("upstream_conversion_confidence")).get("classification", "UNKNOWN"),
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-1000:]

        registry["translation_intelligence"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        registry["cognition_lineage"].append(
            {
                "lineage_id": lineage_id,
                "type": "translation_intelligence",
                "recorded_at": _utc_now_iso(),
                "translation_fingerprint": str(payload.get("translation_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = _as_list(registry.get("cognition_lineage"))[-4000:]

        registry.setdefault("migration_lineage", [])
        registry["migration_lineage"].append(_as_dict(artifacts.get("migration_lineage")))
        registry["migration_lineage"] = _as_list(registry.get("migration_lineage"))[-1000:]

        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "translation_fingerprint": str(payload.get("translation_fingerprint", "")),
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("translation_intelligence"))
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
            "replay_type": "translation_intelligence",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "translation_fingerprint": str(_as_dict(selected).get("translation_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "translation_fingerprint": str(_as_dict(selected).get("translation_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        _save_json(self._output_dir / "deterministic_translation_replay.json", replay_payload)
        return replay_payload
