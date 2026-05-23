#!/usr/bin/env python3
"""Patch cognition and upstream readiness phase runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.patch_cognition_engine import (
    PatchCognitionEngine,
    PatchCognitionRegistry,
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
        "run_id": str(summary.get("run_id", "patch_cognition_runtime_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(deterministic_alignment.get("playback_runtime_seconds", 25.0) or 25.0),
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": str(_as_dict(topology_cognition.get("runtime_route_graph")).get("route_fingerprint", "")),
        "command_sequence": [str(item) for item in _as_list(lock.get("successful_execution_sequence")) if str(item).strip()],
    }


def _load_structural_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "downstream_driver_graph",
        "driver_registration_graph",
        "callback_chain_graph",
        "topology_runtime_graph",
        "runtime_source_correlation",
        "downstream_hook_inventory",
        "upstream_equivalence_map",
        "portability_blockers",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_conversion_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "runtime_portability_analysis",
        "deterministic_conversion_plan",
        "migration_risk_report",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate patch cognition and upstream readiness artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="patch_cognition_upstream_readiness_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    structural_artifacts = _load_structural_artifacts(output_dir)
    conversion_artifacts = _load_conversion_artifacts(output_dir)

    replay_traces = {
        "deterministic_event_ordering": bool(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("event_ordering_stable", True)
        ),
        "deterministic_replay_fingerprint": str(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("deterministic_fingerprint", "")
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

    semantic_latest = _as_dict(_as_dict(registry_payload.get("semantic_cognition")).get("latest"))

    previous_patch_lineage = [
        row
        for row in _as_list(
            _as_dict(_as_dict(registry_payload.get("patch_cognition")).get("latest", {})).get("artifacts", {}).get(
                "deterministic_patch_trace", {}
            ).get("lineage_history", [])
        )
        if isinstance(row, dict)
    ]

    loader = TargetPluginLoader(registry_path=args.plugin_registry) if str(args.plugin_registry).strip() else TargetPluginLoader()
    engine = PatchCognitionEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_evidence=runtime_evidence,
        structural_artifacts=structural_artifacts,
        conversion_artifacts=conversion_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        semantic_cognition=semantic_latest,
        evidence_references=[
            "registry://runtime_cognition",
            "registry://governance_state",
            "registry://semantic_cognition",
            "artifact://downstream_driver_graph",
            "artifact://upstream_equivalence_map",
            "artifact://runtime_source_correlation",
            "artifact://topology_runtime_graph",
            "artifact://portability_blockers",
            "artifact://runtime_portability_analysis",
        ],
        previous_patch_lineage=previous_patch_lineage,
    )

    store = PatchCognitionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.patch_cognition_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "PATCH_COGNITION_UPSTREAM_READINESS_ENGINE",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "patch_cognition_fingerprint": result.patch_cognition_bundle.get("patch_cognition_fingerprint", ""),
        "classification": result.patch_cognition_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "upstream_readiness_report": str((output_dir / "upstream_readiness_report.json").resolve()),
            "patch_dependency_graph": str((output_dir / "patch_dependency_graph.json").resolve()),
            "subsystem_boundary_map": str((output_dir / "subsystem_boundary_map.json").resolve()),
            "vendor_contamination_report": str((output_dir / "vendor_contamination_report.json").resolve()),
            "runtime_patch_correlation": str((output_dir / "runtime_patch_correlation.json").resolve()),
            "bisectability_report": str((output_dir / "bisectability_report.json").resolve()),
            "api_evolution_trace": str((output_dir / "api_evolution_trace.json").resolve()),
            "patch_series_plan": str((output_dir / "patch_series_plan.json").resolve()),
            "deterministic_patch_replay": str((output_dir / "deterministic_patch_replay.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "patch_cognition_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
