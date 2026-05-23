#!/usr/bin/env python3
"""Governed Conversion Reasoning Engine runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.conversion_reasoning_engine import (
    GovernedConversionReasoningEngine,
    GovernedConversionReasoningRegistry,
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
        "run_id": str(summary.get("run_id", "governed_conversion_runtime_unknown")),
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


def _derive_dts_cognition(registry_payload: dict[str, Any]) -> dict[str, Any]:
    semantic_state = _as_dict(registry_payload.get("semantic_cognition"))
    latest = _as_dict(semantic_state.get("latest"))
    adapters = _as_dict(latest.get("adapters"))
    dts_adapter = _as_dict(adapters.get("dts"))
    dts_semantic = _as_dict(dts_adapter.get("semantic_dts"))

    return {
        "overlay_inheritance": {
            "overlay_candidates": _as_list(dts_semantic.get("overlay_candidates")),
        },
        "backend_frontend_mappings": _as_list(dts_semantic.get("fe_be_route_topology")),
        "qcom_audio_routing": _as_list(dts_semantic.get("fe_be_route_topology")),
        "soundwire_topology_markers": _as_list(_as_dict(_as_dict(latest.get("adapters", {})).get("topology", {})).get("topology_graph", {}).get("soundwire_markers", [])),
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate governed conversion reasoning artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="governed_conversion_reasoning_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    structural_artifacts = _load_structural_artifacts(output_dir)

    topology_cognition = _as_dict(registry_payload.get("topology_cognition"))
    semantic_cognition = _as_dict(_as_dict(registry_payload.get("semantic_cognition")).get("latest"))
    dts_cognition = _derive_dts_cognition(registry_payload)

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

    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }

    regression_history = [row for row in _as_list(registry_payload.get("regression_lineage")) if isinstance(row, dict)]
    previous_reasoning_lineage = [
        row for row in _as_list(registry_payload.get("conversion_reasoning_lineage")) if isinstance(row, dict)
    ]

    loader = TargetPluginLoader(registry_path=args.plugin_registry) if str(args.plugin_registry).strip() else TargetPluginLoader()
    engine = GovernedConversionReasoningEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_evidence=runtime_evidence,
        structural_artifacts=structural_artifacts,
        semantic_cognition=semantic_cognition,
        topology_cognition=topology_cognition,
        dts_cognition=dts_cognition,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        governance_state=governance_state,
        evidence_references=[
            "registry://runtime_cognition",
            "registry://topology_cognition",
            "registry://semantic_cognition",
            "registry://governance_state",
            "artifact://structural_graph",
            "artifact://driver_registration_graph",
            "artifact://topology_structure_graph",
            "artifact://runtime_source_correlation",
            "artifact://downstream_hook_inventory",
            "artifact://upstream_equivalence_trace",
            "artifact://callback_chain_graph",
        ],
        regression_history=regression_history,
        previous_reasoning_lineage=previous_reasoning_lineage,
    )

    store = GovernedConversionReasoningRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.conversion_reasoning_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "GOVERNED_CONVERSION_REASONING_ENGINE",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "conversion_reasoning_fingerprint": result.conversion_reasoning_bundle.get(
            "conversion_reasoning_fingerprint", ""
        ),
        "classification": result.conversion_reasoning_bundle.get("classification", "UNKNOWN"),
        "risk_classification": result.conversion_reasoning_bundle.get("risk_classification", "UNKNOWN"),
        "artifact_files": {
            "conversion_reasoning_graph": str((output_dir / "conversion_reasoning_graph.json").resolve()),
            "portability_blocker_report": str((output_dir / "portability_blocker_report.json").resolve()),
            "migration_phase_plan": str((output_dir / "migration_phase_plan.json").resolve()),
            "abstraction_gap_report": str((output_dir / "abstraction_gap_report.json").resolve()),
            "upstream_equivalence_confidence": str((output_dir / "upstream_equivalence_confidence.json").resolve()),
            "lifecycle_incompatibility_report": str((output_dir / "lifecycle_incompatibility_report.json").resolve()),
            "vendor_dependency_graph": str((output_dir / "vendor_dependency_graph.json").resolve()),
            "runtime_portability_analysis": str((output_dir / "runtime_portability_analysis.json").resolve()),
            "deterministic_conversion_reasoning_trace": str(
                (output_dir / "deterministic_conversion_reasoning_trace.json").resolve()
            ),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "governed_conversion_reasoning_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
