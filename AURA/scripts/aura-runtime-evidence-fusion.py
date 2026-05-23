#!/usr/bin/env python3
"""Runtime Evidence Fusion Layer runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_evidence_fusion_engine import (
    RuntimeEvidenceFusionEngine,
    RuntimeEvidenceFusionRegistry,
)


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


def _load_runtime_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "runtime_truth_graph",
        "dapm_transition_trace",
        "pcm_lifecycle_trace",
        "soundwire_runtime_graph",
        "irq_timing_report",
        "dsp_sync_report",
        "runtime_drift_report",
        "runtime_confidence_score",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_topology_artifacts(output_dir: Path) -> dict[str, Any]:
    names = ["topology_runtime_graph"]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_semantic_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "semantic_entity_graph",
        "semantic_relationship_map",
        "semantic_confidence_report",
        "dts_topology_graph",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_migration_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "migration_dependency_graph",
        "portability_transition_state",
        "migration_checkpoint_registry",
        "migration_lineage",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_patch_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "patch_series_plan",
        "runtime_patch_correlation",
        "upstream_readiness_report",
        "subsystem_boundary_map",
        "api_evolution_trace",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime evidence fusion artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="runtime_evidence_fusion_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_artifacts = _load_runtime_artifacts(output_dir)
    topology_artifacts = _load_topology_artifacts(output_dir)
    semantic_artifacts = _load_semantic_artifacts(output_dir)
    migration_artifacts = _load_migration_artifacts(output_dir)
    patch_artifacts = _load_patch_artifacts(output_dir)

    replay_det = _read_json(output_dir / "aura_replay_determinism_report.json")
    replay_traces = {
        "deterministic_event_ordering": bool(
            _as_dict(replay_det).get("event_ordering_stable", True)
        ),
        "deterministic_replay_fingerprint": str(
            _as_dict(replay_det).get("deterministic_fingerprint", "")
        ),
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

    previous_fusion_lineage = [
        row
        for row in _as_list(registry_payload.get("runtime_evidence_fusion_lineage"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = RuntimeEvidenceFusionEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_artifacts=runtime_artifacts,
        topology_artifacts=topology_artifacts,
        semantic_artifacts=semantic_artifacts,
        migration_artifacts=migration_artifacts,
        patch_artifacts=patch_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://runtime_truth_cognition",
            "registry://semantic_cognition",
            "registry://patch_cognition",
            "artifact://runtime_truth_graph",
            "artifact://topology_runtime_graph",
            "artifact://semantic_entity_graph",
            "artifact://migration_dependency_graph",
            "artifact://patch_series_plan",
            "artifact://runtime_patch_correlation",
            "artifact://subsystem_boundary_map",
        ],
        previous_fusion_lineage=previous_fusion_lineage,
    )

    store = RuntimeEvidenceFusionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.fusion_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_EVIDENCE_FUSION_LAYER",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "runtime_evidence_fusion_fingerprint": result.fusion_bundle.get(
            "runtime_evidence_fusion_fingerprint", ""
        ),
        "classification": result.fusion_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "unified_engineering_truth_graph": str(
                (output_dir / "unified_engineering_truth_graph.json").resolve()
            ),
            "runtime_topology_correlation": str(
                (output_dir / "runtime_topology_correlation.json").resolve()
            ),
            "lifecycle_causality_map": str(
                (output_dir / "lifecycle_causality_map.json").resolve()
            ),
            "migration_runtime_alignment": str(
                (output_dir / "migration_runtime_alignment.json").resolve()
            ),
            "patch_runtime_lineage": str(
                (output_dir / "patch_runtime_lineage.json").resolve()
            ),
            "dsp_runtime_causality_report": str(
                (output_dir / "dsp_runtime_causality_report.json").resolve()
            ),
            "regression_rootcause_report": str(
                (output_dir / "regression_rootcause_report.json").resolve()
            ),
            "deterministic_fusion_replay": str(
                (output_dir / "deterministic_fusion_replay.json").resolve()
            ),
            "engineering_confidence_score": str(
                (output_dir / "engineering_confidence_score.json").resolve()
            ),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "runtime_evidence_fusion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
