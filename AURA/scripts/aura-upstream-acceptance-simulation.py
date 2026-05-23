#!/usr/bin/env python3
"""Upstream Acceptance Simulation and Patch Validation runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.upstream_acceptance_simulation import (
    UpstreamAcceptanceSimulationEngine,
    UpstreamAcceptanceSimulationRegistry,
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


def _load(output_dir: Path, names: list[str]) -> dict[str, Any]:
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_generated_patch(output_dir: Path) -> dict[str, Any]:
    patch_path = output_dir / "generated_upstream_patch.diff"
    if not patch_path.exists():
        return {}
    return {
        "patch_text": patch_path.read_text(encoding="utf-8", errors="ignore"),
        "path": str(patch_path.resolve()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate upstream acceptance simulation artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="upstream_acceptance_session_v1")
    parser.add_argument("--lineage-id", default="upstream_acceptance_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

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

    previous_submission_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("upstream_acceptance_simulation")).get("history"))
        if isinstance(row, dict)
    ]

    translation_artifacts = _load(
        output_dir,
        [
            "upstream_translation_plan",
            "api_replacement_map",
            "runtime_equivalence_validation",
            "unsupported_vendor_constructs",
        ],
    )
    execution_artifacts = _load(
        output_dir,
        [
            "translation_execution_report",
            "transformation_lineage",
        ],
    )
    execution_artifacts["generated_upstream_patch"] = _load_generated_patch(output_dir)

    patch_artifacts = _load(
        output_dir,
        [
            "upstream_readiness_report",
            "patch_dependency_graph",
            "subsystem_boundary_map",
            "vendor_contamination_report",
            "runtime_patch_correlation",
            "bisectability_report",
            "api_evolution_trace",
            "patch_series_plan",
        ],
    )
    runtime_acquisition_artifacts = _load(
        output_dir,
        [
            "runtime_equivalence_fingerprint",
            "runtime_divergence_report",
            "downstream_upstream_runtime_diff",
            "evidence_quality_report",
            "target_runtime_capture",
            "ipc_topology_map",
        ],
    )

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = UpstreamAcceptanceSimulationEngine(plugin_loader=loader)
    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        translation_artifacts=translation_artifacts,
        execution_artifacts=execution_artifacts,
        patch_artifacts=patch_artifacts,
        runtime_acquisition_artifacts=runtime_acquisition_artifacts,
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        previous_submission_history=previous_submission_history,
        evidence_references=[
            "registry://governance_state",
            "registry://upstream_acceptance_simulation",
            "artifact://runtime_equivalence_fingerprint",
            "artifact://runtime_divergence_report",
            "artifact://downstream_upstream_runtime_diff",
            "artifact://evidence_quality_report",
            "artifact://target_runtime_capture",
            "artifact://patch_dependency_graph",
            "artifact://subsystem_boundary_map",
            "artifact://bisectability_report",
            "artifact://patch_series_plan",
            "artifact://api_evolution_trace",
            "artifact://runtime_patch_correlation",
            "artifact://generated_upstream_patch.diff",
            "artifact://unsupported_vendor_constructs",
            "artifact://aura_replay_determinism_report",
        ],
    )

    store = UpstreamAcceptanceSimulationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.acceptance_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "UPSTREAM_ACCEPTANCE_SIMULATION_AND_PATCH_VALIDATION",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": result.acceptance_bundle.get("classification", "UNKNOWN"),
        "upstream_acceptance_simulation_fingerprint": result.acceptance_bundle.get(
            "upstream_acceptance_simulation_fingerprint",
            "",
        ),
        "artifact_files": {
            "upstream_acceptance_report": str((output_dir / "upstream_acceptance_report.json").resolve()),
            "patch_series_validation": str((output_dir / "patch_series_validation.json").resolve()),
            "maintainer_scope_map": str((output_dir / "maintainer_scope_map.json").resolve()),
            "regression_risk_assessment": str((output_dir / "regression_risk_assessment.json").resolve()),
            "bisectability_validation": str((output_dir / "bisectability_validation.json").resolve()),
            "upstream_submission_plan": str((output_dir / "upstream_submission_plan.json").resolve()),
            "patch_dependency_order": str((output_dir / "patch_dependency_order.json").resolve()),
            "acceptance_confidence_score": str((output_dir / "acceptance_confidence_score.json").resolve()),
            "deterministic_submission_replay": str((output_dir / "deterministic_submission_replay.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "upstream_acceptance_simulation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
