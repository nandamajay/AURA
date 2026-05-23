"""Real downstream kernel ingestion and governed conversion planning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.downstream_driver_ingestion import (
    DownstreamDriverIngestionResult,
    ingest_downstream_driver_tree,
)
from aura_sdk.transport.migration_lineage import (
    MigrationLineageResult,
    build_migration_lineage,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.portability_blocker_classifier import (
    PortabilityBlockerResult,
    classify_portability_blockers,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.topology_reconstruction_cognition import (
    TopologyReconstructionResult,
    reconstruct_topology_runtime_graph,
)
from aura_sdk.transport.upstream_semantic_matcher import (
    UpstreamSemanticMatcherResult,
    match_upstream_semantics,
)


_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "fingerprint",
    "plan",
    "recommend",
    "replay",
]

_FORBIDDEN_ACTIONS = [
    "autonomous_patch_generation",
    "autonomous_topology_mutation",
    "unsafe_runtime_rewrite",
    "unsupported_semantic_assumption",
]


@dataclass(frozen=True)
class RealDownstreamConversionPlannerResult:
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


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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


class RealDownstreamConversionPlanner:
    """Plugin-driven real downstream ingestion and governed conversion reasoning."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def _governance_boundaries(self, governance_state: Mapping[str, Any]) -> dict[str, Any]:
        gov = _as_dict(governance_state)
        violations = {
            "autonomous_patch_generation": _is_true(gov.get("autonomous_patching_allowed", False)),
            "autonomous_topology_mutation": _is_true(gov.get("autonomous_topology_rewrite_allowed", False))
            or _is_true(gov.get("autonomous_mixer_mutation_allowed", False)),
            "unsafe_runtime_rewrite": _is_true(gov.get("autonomous_runtime_mutation_allowed", False)),
            "autonomous_upstream_generation": _is_true(gov.get("autonomous_upstream_generation_allowed", False)),
        }
        blocked = [key for key, value in violations.items() if value]
        classification = "FAIL_CLOSED" if blocked else "PASS"
        payload = {
            "schema_version": "1.0",
            "report_name": "governance_conversion_boundaries",
            "classification": classification,
            "fail_closed_posture": bool(gov.get("fail_closed_posture", True)),
            "allowed_actions": list(_ALLOWED_ACTIONS),
            "forbidden_actions": list(_FORBIDDEN_ACTIONS),
            "blocked_by_state": blocked,
            "governance_state": dict(gov),
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def _build_migration_risk_report(
        self,
        *,
        target_id: str,
        upstream_match: UpstreamSemanticMatcherResult,
        topology: TopologyReconstructionResult,
        blockers: PortabilityBlockerResult,
        migration_lineage: MigrationLineageResult,
    ) -> dict[str, Any]:
        unresolved = int(_as_dict(upstream_match.upstream_equivalence_map.get("summary")).get("unresolved", 0))
        blocker_payload = _as_dict(blockers.portability_blockers)
        blocked_count = int(_as_dict(blocker_payload.get("summary")).get("blocked_unsafe_count", 0))
        advisory_count = int(_as_dict(blocker_payload.get("summary")).get("advisory_count", 0))

        risk_score = round(
            min(
                1.0,
                0.35 * (1.0 - float(upstream_match.semantic_equivalence_confidence))
                + 0.20 * (1.0 - float(topology.topology_reconstruction_confidence))
                + 0.25 * float(migration_lineage.drift_score)
                + 0.15 * (0.2 * blocked_count + 0.05 * advisory_count)
                + 0.05 * min(1.0, unresolved / 20.0),
            ),
            3,
        )

        if risk_score >= 0.7 or blocked_count > 0:
            classification = "HIGH_RISK_FAIL_CLOSED"
        elif risk_score >= 0.45:
            classification = "MEDIUM_RISK_ADVISORY"
        else:
            classification = "LOW_RISK_ADVISORY"

        payload = {
            "schema_version": "1.0",
            "report_name": "migration_risk_report",
            "target_id": str(target_id),
            "risk_score": risk_score,
            "classification": classification,
            "drivers": {
                "semantic_equivalence_confidence": upstream_match.semantic_equivalence_confidence,
                "topology_reconstruction_confidence": topology.topology_reconstruction_confidence,
                "migration_drift_score": migration_lineage.drift_score,
                "blocked_unsafe_count": blocked_count,
                "advisory_count": advisory_count,
                "unresolved_equivalence_count": unresolved,
            },
            "drift_details": _as_list(_as_dict(migration_lineage.migration_lineage).get("drifts")),
            "blocker_summary": _as_dict(blocker_payload.get("summary")),
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def _build_deterministic_plan(
        self,
        *,
        target_id: str,
        lineage_id: str,
        upstream_match: UpstreamSemanticMatcherResult,
        topology: TopologyReconstructionResult,
        blockers: PortabilityBlockerResult,
        risk_report: Mapping[str, Any],
        governance_boundaries: Mapping[str, Any],
        replay_compatibility: Mapping[str, Any],
    ) -> dict[str, Any]:
        match_entries = [
            row
            for row in _as_list(_as_dict(upstream_match.upstream_equivalence_map).get("entries"))
            if isinstance(row, dict)
        ]

        suggested_mappings = [
            {
                "downstream_construct": str(row.get("downstream_construct", "")),
                "upstream_equivalent": str(row.get("upstream_equivalent", "")),
                "status": str(row.get("equivalence_status", "")),
                "confidence": _to_float(row.get("equivalence_confidence", 0.0)),
            }
            for row in match_entries[:400]
        ]

        transformations = _as_dict(_as_dict(blockers.portability_blockers).get("transformation_classes"))
        blocked_count = int(_as_dict(_as_dict(blockers.portability_blockers).get("summary")).get("blocked_unsafe_count", 0))

        plan_classification = "PASS"
        if blocked_count > 0 or str(_as_dict(governance_boundaries).get("classification", "")) == "FAIL_CLOSED":
            plan_classification = "FAIL_CLOSED"
        elif str(_as_dict(risk_report).get("classification", "")).startswith("MEDIUM"):
            plan_classification = "ADVISORY_ONLY"

        phases = [
            {
                "phase": "phase_1_real_ingestion",
                "goal": "extract downstream driver cognition graph",
                "deterministic_gate": "downstream_driver_graph.deterministic_fingerprint_stable",
            },
            {
                "phase": "phase_2_topology_normalization",
                "goal": "reconstruct FE/BE + PCM/DPCM portable runtime graph",
                "deterministic_gate": "topology_runtime_graph.deterministic_fingerprint_stable",
            },
            {
                "phase": "phase_3_semantic_equivalence_mapping",
                "goal": "map downstream vendor constructs to upstream abstractions",
                "deterministic_gate": "upstream_equivalence_map.semantic_equivalence_confidence_non_degrading",
            },
            {
                "phase": "phase_4_governed_migration_advisory",
                "goal": "produce governed migration advisory plan with replay checks",
                "deterministic_gate": "replay_compatibility.compatibility_level_not_incompatible",
            },
        ]

        payload = {
            "schema_version": "1.0",
            "report_name": "deterministic_conversion_plan",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": plan_classification,
            "phases": phases,
            "suggested_upstream_mappings": suggested_mappings,
            "topology_equivalence_reasoning": {
                "topology_fingerprint": topology.deterministic_fingerprint,
                "topology_confidence": topology.topology_reconstruction_confidence,
                "runtime_activation_order": _as_list(
                    _as_dict(_as_dict(topology.topology_runtime_graph).get("normalized_portable_audio_graph")).get(
                        "runtime_activation_order"
                    )
                ),
            },
            "replay_compatibility_analysis": dict(replay_compatibility),
            "regression_risk_analysis": dict(risk_report),
            "transformation_policy": {
                "replay_safe": _as_list(transformations.get("replay_safe")),
                "advisory_only": _as_list(transformations.get("advisory_only")),
                "forbidden_autonomous_transformations": _as_list(transformations.get("forbidden_autonomous_transformations")),
            },
            "governance_conversion_boundaries": dict(governance_boundaries),
        }
        payload["deterministic_fingerprint"] = stable_fingerprint(payload)
        return payload

    def analyze(
        self,
        *,
        target_id: str,
        downstream_root: str | Path,
        upstream_root: str | Path,
        runtime_evidence: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_contract: Mapping[str, Any],
        lineage_id: str,
        evidence_references: list[str] | None,
        regression_history: list[Mapping[str, Any]],
        previous_migration_lineage: list[Mapping[str, Any]] | None,
    ) -> RealDownstreamConversionPlannerResult:
        plugin = self._plugins.load_plugin(target_id)

        ingestion_adapter = _as_dict(
            plugin.downstream_ingestion_adapter(
                {
                    "target_id": str(target_id),
                    "downstream_root": str(downstream_root),
                    "governance_state": dict(governance_state),
                }
            )
        )

        ingestion = ingest_downstream_driver_tree(
            target_id=target_id,
            downstream_root=downstream_root,
            adapter_payload=ingestion_adapter,
            evidence_references=evidence_references,
        )

        topology_adapter = _as_dict(
            plugin.topology_reconstruction_adapter(
                {
                    "target_id": str(target_id),
                    "downstream_driver_graph": dict(ingestion.downstream_driver_graph),
                    "runtime_evidence": dict(runtime_evidence),
                }
            )
        )

        topology = reconstruct_topology_runtime_graph(
            target_id=target_id,
            downstream_driver_graph=ingestion.downstream_driver_graph,
            runtime_evidence=runtime_evidence,
            adapter_payload=topology_adapter,
        )

        upstream_match_adapter = _as_dict(
            plugin.upstream_match_adapter(
                {
                    "target_id": str(target_id),
                    "downstream_driver_graph": dict(ingestion.downstream_driver_graph),
                    "topology_runtime_graph": dict(topology.topology_runtime_graph),
                    "upstream_root": str(upstream_root),
                }
            )
        )

        upstream_match = match_upstream_semantics(
            target_id=target_id,
            upstream_root=upstream_root,
            downstream_driver_graph=ingestion.downstream_driver_graph,
            adapter_payload=upstream_match_adapter,
            evidence_references=evidence_references,
        )

        blockers = classify_portability_blockers(
            target_id=target_id,
            downstream_driver_graph=ingestion.downstream_driver_graph,
            upstream_equivalence_map=upstream_match.upstream_equivalence_map,
            runtime_evidence=runtime_evidence,
            governance_state=governance_state,
            adapter_payload=upstream_match_adapter,
        )

        translated_model = {
            "expected_runtime_seconds": _to_float(runtime_evidence.get("expected_runtime_seconds", 25.0)),
            "route_fingerprint": str(
                _as_dict(topology.topology_runtime_graph).get("deterministic_fingerprint", "")
            ),
            "required_capabilities": _as_dict(runtime_evidence.get("capabilities")),
            "expected_sequence": _as_list(
                _as_dict(_as_dict(topology.topology_runtime_graph).get("normalized_portable_audio_graph")).get(
                    "runtime_activation_order"
                )
            ),
        }

        migration_lineage = build_migration_lineage(
            target_id=target_id,
            lineage_id=str(lineage_id),
            runtime_evidence=runtime_evidence,
            translated_model=translated_model,
            regression_history=list(regression_history),
            previous_lineage=list(previous_migration_lineage or []),
        )

        governance_boundaries = self._governance_boundaries(governance_state)
        replay_compatibility = _as_dict(
            plugin.validation_provider(
                {
                    "mode": "replay_compatibility",
                    "replay_contract": dict(replay_contract),
                }
            )
        )

        risk_report = self._build_migration_risk_report(
            target_id=target_id,
            upstream_match=upstream_match,
            topology=topology,
            blockers=blockers,
            migration_lineage=migration_lineage,
        )

        deterministic_plan = self._build_deterministic_plan(
            target_id=target_id,
            lineage_id=str(lineage_id),
            upstream_match=upstream_match,
            topology=topology,
            blockers=blockers,
            risk_report=risk_report,
            governance_boundaries=governance_boundaries,
            replay_compatibility=replay_compatibility,
        )

        artifacts = {
            "downstream_driver_graph": ingestion.downstream_driver_graph,
            "topology_runtime_graph": topology.topology_runtime_graph,
            "upstream_equivalence_map": upstream_match.upstream_equivalence_map,
            "portability_blockers": blockers.portability_blockers,
            "migration_risk_report": risk_report,
            "deterministic_conversion_plan": deterministic_plan,
            "governance_conversion_boundaries": governance_boundaries,
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "REAL_DOWNSTREAM_INGESTION_COGNITION",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "downstream_root": str(Path(downstream_root).resolve()),
            "upstream_root": str(Path(upstream_root).resolve()),
            "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
            "governance_boundaries": governance_boundaries,
            "artifacts": artifacts,
        }
        bundle["conversion_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "artifacts": artifacts,
                "governance_boundaries": governance_boundaries,
            }
        )

        return RealDownstreamConversionPlannerResult(conversion_bundle=bundle)


class RealDownstreamConversionRegistry:
    """Replay-safe persistence for real downstream ingestion cognition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "downstream_driver_graph": self._output_dir / "downstream_driver_graph.json",
            "topology_runtime_graph": self._output_dir / "topology_runtime_graph.json",
            "upstream_equivalence_map": self._output_dir / "upstream_equivalence_map.json",
            "portability_blockers": self._output_dir / "portability_blockers.json",
            "migration_risk_report": self._output_dir / "migration_risk_report.json",
            "deterministic_conversion_plan": self._output_dir / "deterministic_conversion_plan.json",
            "governance_conversion_boundaries": self._output_dir / "governance_conversion_boundaries.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            _save_json(path, _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("real_downstream_ingestion"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "conversion_fingerprint": str(payload.get("conversion_fingerprint", "")),
            "artifact_paths": {key: str(path.resolve()) for key, path in paths.items()},
            "classification": str(_as_dict(artifacts.get("deterministic_conversion_plan")).get("classification", "UNKNOWN")),
            "risk_classification": str(_as_dict(artifacts.get("migration_risk_report")).get("classification", "UNKNOWN")),
            "evidence_references": [str(item) for item in _as_list(payload.get("evidence_references")) if str(item).strip()],
        }
        history.append(entry)
        history = history[-1000:]

        registry["real_downstream_ingestion"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        registry["cognition_lineage"].append(
            {
                "lineage_id": lineage_id,
                "type": "real_downstream_ingestion",
                "recorded_at": _utc_now_iso(),
                "conversion_fingerprint": str(payload.get("conversion_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = _as_list(registry.get("cognition_lineage"))[-5000:]

        registry.setdefault("migration_lineage", [])
        registry["migration_lineage"].append(_as_dict(artifacts.get("migration_risk_report")))
        registry["migration_lineage"] = _as_list(registry.get("migration_lineage"))[-2000:]

        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "conversion_fingerprint": str(payload.get("conversion_fingerprint", "")),
            "artifact_paths": entry["artifact_paths"],
            "classification": entry["classification"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("real_downstream_ingestion"))
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
            "replay_type": "real_downstream_ingestion",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "conversion_fingerprint": str(_as_dict(selected).get("conversion_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "conversion_fingerprint": str(_as_dict(selected).get("conversion_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "deterministic_conversion_replay.json", replay_payload)
        return replay_payload
