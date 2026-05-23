#!/usr/bin/env python3
"""Engineering Investigation and Query Reasoning runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.engineering_query_engine import EngineeringQueryEngine
from aura_sdk.transport.investigation_session_registry import InvestigationSessionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _load_artifacts(output_dir: Path, names: list[str]) -> dict[str, Any]:
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate engineering investigation reasoning artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="engineering_investigation_session_v1")
    parser.add_argument("--lineage-id", default="engineering_investigation_v1")
    parser.add_argument(
        "--question",
        default="What caused this runtime failure?",
    )
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_artifacts = _load_artifacts(
        output_dir,
        [
            "runtime_truth_graph",
            "dapm_transition_trace",
            "pcm_lifecycle_trace",
            "soundwire_runtime_graph",
            "irq_timing_report",
            "dsp_sync_report",
            "runtime_drift_report",
            "runtime_confidence_score",
            "pcm_runtime_state",
            "subsystem_runtime_state",
        ],
    )
    topology_artifacts = _load_artifacts(
        output_dir,
        [
            "topology_runtime_graph",
            "runtime_topology_correlation",
            "dts_topology_graph",
            "topology_runtime_causality",
        ],
    )
    migration_artifacts = _load_artifacts(
        output_dir,
        [
            "portability_blockers",
            "migration_phase_plan",
            "migration_runtime_alignment",
            "upstream_equivalence_map",
            "migration_dependency_graph",
            "staged_migration_plan",
        ],
    )
    patch_artifacts = _load_artifacts(
        output_dir,
        [
            "runtime_patch_correlation",
            "patch_series_plan",
            "upstream_readiness_report",
            "vendor_contamination_report",
            "regression_causality_report",
        ],
    )
    semantic_artifacts = _load_artifacts(
        output_dir,
        [
            "semantic_confidence_report",
            "semantic_ontology",
            "dts_topology_graph",
            "semantic_entity_graph",
        ],
    )
    structural_artifacts = _load_artifacts(
        output_dir,
        ["structural_graph", "topology_structure_graph", "runtime_source_correlation"],
    )
    incident_artifacts = _load_artifacts(
        output_dir,
        [
            "runtime_incident_graph",
            "root_cause_candidates",
            "lifecycle_violation_report",
            "runtime_sequence_drift",
            "topology_runtime_causality",
            "regression_causality_report",
            "engineering_confidence_report",
        ],
    )
    fusion_artifacts = _load_artifacts(
        output_dir,
        [
            "unified_engineering_truth_graph",
            "regression_rootcause_report",
            "engineering_confidence_score",
        ],
    )
    replay_artifacts = _load_artifacts(
        output_dir,
        [
            "deterministic_runtime_session_replay",
            "deterministic_fusion_replay",
            "deterministic_incident_replay",
            "deterministic_runtime_replay",
            "deterministic_runtime_session_replay",
        ],
    )
    confidence_artifacts = {
        "runtime_confidence_score": _read_json(output_dir / "runtime_confidence_score.json"),
        "engineering_confidence_score": _read_json(output_dir / "engineering_confidence_score.json"),
        "engineering_confidence_report": _read_json(output_dir / "engineering_confidence_report.json"),
    }

    replay_det = _read_json(output_dir / "aura_replay_determinism_report.json")
    replay_traces = {
        "deterministic_event_ordering": bool(_as_dict(replay_det).get("event_ordering_stable", True)),
        "deterministic_replay_fingerprint": str(_as_dict(replay_det).get("deterministic_fingerprint", "")),
    }

    governance_state = _as_dict(registry_payload.get("governance_state"))
    if not governance_state:
        governance_state = {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        }

    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }

    previous_query_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("engineering_query_history")).get("history"))
        if isinstance(row, dict)
    ]

    latest_investigation = _as_dict(_as_dict(registry_payload.get("engineering_investigation")).get("latest"))
    latest_artifacts = _as_dict(latest_investigation.get("artifacts"))
    latest_lineage = _as_dict(latest_artifacts.get("runtime_question_lineage"))
    previous_reasoning_lineage = [
        row
        for row in _as_list(latest_lineage.get("lineage"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = EngineeringQueryEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        question=str(args.question),
        runtime_artifacts=runtime_artifacts,
        topology_artifacts=topology_artifacts,
        migration_artifacts=migration_artifacts,
        patch_artifacts=patch_artifacts,
        semantic_artifacts=semantic_artifacts,
        structural_artifacts=structural_artifacts,
        incident_artifacts=incident_artifacts,
        fusion_artifacts=fusion_artifacts,
        replay_artifacts=replay_artifacts,
        confidence_artifacts=confidence_artifacts,
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://engineering_investigation",
            "artifact://runtime_incident_graph",
            "artifact://root_cause_candidates",
            "artifact://runtime_sequence_drift",
            "artifact://topology_runtime_causality",
            "artifact://portability_blockers",
            "artifact://runtime_patch_correlation",
            "artifact://deterministic_incident_replay",
            "artifact://deterministic_fusion_replay",
            "artifact://deterministic_runtime_session_replay",
        ],
        previous_query_history=previous_query_history,
        previous_reasoning_lineage=previous_reasoning_lineage,
    )

    store = InvestigationSessionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.investigation_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "ENGINEERING_INVESTIGATION_QUERY_REASONING_LAYER",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "question": str(args.question),
        "engineering_investigation_fingerprint": result.investigation_bundle.get(
            "engineering_investigation_fingerprint", ""
        ),
        "classification": result.investigation_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "investigation_reasoning_graph": str((output_dir / "investigation_reasoning_graph.json").resolve()),
            "engineering_answer_trace": str((output_dir / "engineering_answer_trace.json").resolve()),
            "causality_resolution_report": str((output_dir / "causality_resolution_report.json").resolve()),
            "migration_blocker_reasoning": str((output_dir / "migration_blocker_reasoning.json").resolve()),
            "runtime_question_lineage": str((output_dir / "runtime_question_lineage.json").resolve()),
            "deterministic_investigation_replay": str(
                (output_dir / "deterministic_investigation_replay.json").resolve()
            ),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "engineering_investigation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
