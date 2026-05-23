#!/usr/bin/env python3
"""Incremental Migration Orchestration Layer runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.migration_orchestrator import (
    IncrementalMigrationOrchestrator,
    MigrationOrchestrationRegistry,
)
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


def _derive_runtime_evidence(registry_payload: dict[str, Any]) -> dict[str, Any]:
    runtime_cognition = _as_dict(registry_payload.get("runtime_cognition"))
    topology_cognition = _as_dict(registry_payload.get("topology_cognition"))
    summary = _as_dict(runtime_cognition.get("last_trace_summary"))
    lock = _as_dict(runtime_cognition.get("procedural_lock"))

    deterministic_alignment = _as_dict(_as_dict(topology_cognition.get("confidence")).get("deterministic_alignment"))

    return {
        "run_id": str(summary.get("run_id", "incremental_orchestration_runtime_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(deterministic_alignment.get("playback_runtime_seconds", 25.0) or 25.0),
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": str(_as_dict(topology_cognition.get("runtime_route_graph")).get("route_fingerprint", "")),
        "command_sequence": [str(item) for item in _as_list(lock.get("successful_execution_sequence")) if str(item).strip()],
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": str(_as_dict(registry_payload.get("translation_intelligence", {})).get("latest", {}).get("translation_fingerprint", "")),
    }


def _load_structural_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "structural_graph",
        "driver_registration_graph",
        "topology_structure_graph",
        "runtime_source_correlation",
        "downstream_hook_inventory",
        "upstream_equivalence_trace",
        "portability_blocker_graph",
        "callback_chain_graph",
        "deterministic_structural_fingerprint",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_conversion_reasoning_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "conversion_reasoning_graph",
        "portability_blocker_report",
        "migration_phase_plan",
        "abstraction_gap_report",
        "upstream_equivalence_confidence",
        "lifecycle_incompatibility_report",
        "vendor_dependency_graph",
        "runtime_portability_analysis",
        "deterministic_conversion_reasoning_trace",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate incremental migration orchestration artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="incremental_migration_orchestration_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    structural_artifacts = _load_structural_artifacts(output_dir)
    conversion_reasoning_artifacts = _load_conversion_reasoning_artifacts(output_dir)

    replay_traces = {
        "deterministic_event_ordering": bool(_as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("event_ordering_stable", True)),
        "deterministic_replay_fingerprint": str(_as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("deterministic_fingerprint", "")),
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

    previous_orchestration = _as_dict(registry_payload.get("incremental_migration_orchestration"))
    previous_latest = _as_dict(previous_orchestration.get("latest"))
    previous_artifacts = _as_dict(previous_latest.get("artifacts"))
    previous_transition_state = _as_dict(previous_artifacts.get("portability_transition_state"))
    previous_checkpoint_history = _as_list(_as_dict(previous_artifacts.get("migration_checkpoint_registry")).get("history"))
    previous_trace_history = _as_list(_as_dict(previous_artifacts.get("deterministic_migration_orchestration_trace")).get("lineage_history"))

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    orchestrator = IncrementalMigrationOrchestrator(plugin_loader=loader)

    result = orchestrator.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_evidence=runtime_evidence,
        structural_artifacts=structural_artifacts,
        conversion_reasoning_artifacts=conversion_reasoning_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        previous_transition_state=previous_transition_state,
        previous_checkpoint_history=previous_checkpoint_history,
        previous_trace_history=previous_trace_history,
        evidence_references=[
            "registry://runtime_cognition",
            "registry://governance_state",
            "artifact://structural_graph",
            "artifact://driver_registration_graph",
            "artifact://topology_structure_graph",
            "artifact://runtime_source_correlation",
            "artifact://conversion_reasoning_graph",
            "artifact://portability_blocker_report",
            "artifact://runtime_portability_analysis",
            "artifact://upstream_equivalence_confidence",
        ],
    )

    store = MigrationOrchestrationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.orchestration_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "INCREMENTAL_MIGRATION_ORCHESTRATION_LAYER",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "migration_orchestration_fingerprint": result.orchestration_bundle.get("migration_orchestration_fingerprint", ""),
        "classification": result.orchestration_bundle.get("classification", "UNKNOWN"),
        "risk_classification": result.orchestration_bundle.get("risk_classification", "UNKNOWN"),
        "artifact_files": {
            "staged_migration_plan": str((output_dir / "staged_migration_plan.json").resolve()),
            "migration_dependency_graph": str((output_dir / "migration_dependency_graph.json").resolve()),
            "rollback_boundary_report": str((output_dir / "rollback_boundary_report.json").resolve()),
            "runtime_stability_gate_report": str((output_dir / "runtime_stability_gate_report.json").resolve()),
            "portability_transition_state": str((output_dir / "portability_transition_state.json").resolve()),
            "incremental_equivalence_report": str((output_dir / "incremental_equivalence_report.json").resolve()),
            "migration_checkpoint_registry": str((output_dir / "migration_checkpoint_registry.json").resolve()),
            "deterministic_migration_orchestration_trace": str((output_dir / "deterministic_migration_orchestration_trace.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "incremental_migration_orchestration_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
