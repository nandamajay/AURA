#!/usr/bin/env python3
"""Real downstream kernel ingestion cognition runner.

Builds deterministic, governance-safe conversion cognition artifacts from real
 downstream kernel trees without autonomous mutation.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.real_downstream_conversion_planner import (
    RealDownstreamConversionPlanner,
    RealDownstreamConversionRegistry,
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


def _derive_runtime_evidence(registry_payload: dict[str, Any]) -> dict[str, Any]:
    runtime_cognition = _as_dict(registry_payload.get("runtime_cognition"))
    topology_cognition = _as_dict(registry_payload.get("topology_cognition"))
    summary = _as_dict(runtime_cognition.get("last_trace_summary"))
    lock = _as_dict(runtime_cognition.get("procedural_lock"))

    deterministic_alignment = _as_dict(_as_dict(topology_cognition.get("confidence")).get("deterministic_alignment"))

    return {
        "run_id": str(summary.get("run_id", "real_ingestion_runtime_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(deterministic_alignment.get("playback_runtime_seconds", 25.0) or 25.0),
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": str(_as_dict(topology_cognition.get("runtime_route_graph")).get("route_fingerprint", "")),
        "command_sequence": [
            str(item) for item in _as_list(lock.get("successful_execution_sequence")) if str(item).strip()
        ],
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": str(_as_dict(registry_payload.get("translation_intelligence", {})).get("latest", {}).get("translation_fingerprint", "")),
        "capabilities": _as_dict(_as_dict(registry_payload.get("target_knowledge")).get("capabilities")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate real downstream ingestion cognition artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument(
        "--downstream-root",
        default=(
            "/local/mnt/workspace/AURA_V1/evidence/"
            "wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar"
        ),
    )
    parser.add_argument(
        "--upstream-root",
        default=(
            "/local/mnt/workspace/AURA_V1/evidence/"
            "wcd937x_real_study_20260519_062557/repos/linux-upstream-v6.18"
        ),
    )
    parser.add_argument("--lineage-id", default="real_downstream_ingestion_v1")
    parser.add_argument("--runtime-evidence-file", default="")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    if str(args.runtime_evidence_file).strip():
        override_payload = _read_json(Path(str(args.runtime_evidence_file)))
        if override_payload:
            runtime_evidence.update(override_payload)

    governance_state = _as_dict(registry_payload.get("governance_state"))
    if not governance_state:
        governance_state = {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        }

    replay_contract = {
        "sequence_contract": [
            "execution_ordering",
            "timing_windows",
            "route_fingerprint",
            "pcm_signature",
            "evidence_sequence",
            "cleanup_sequence",
        ]
    }

    loader = TargetPluginLoader(registry_path=args.plugin_registry) if str(args.plugin_registry).strip() else TargetPluginLoader()
    planner = RealDownstreamConversionPlanner(plugin_loader=loader)

    result = planner.analyze(
        target_id=str(args.target_id),
        downstream_root=Path(str(args.downstream_root)),
        upstream_root=Path(str(args.upstream_root)),
        runtime_evidence=runtime_evidence,
        governance_state=governance_state,
        replay_contract=replay_contract,
        lineage_id=str(args.lineage_id),
        evidence_references=[
            "registry://runtime_cognition",
            "registry://topology_cognition",
            "registry://governance_state",
            "source://downstream_kernel_tree",
            "source://upstream_kernel_tree",
        ],
        regression_history=[row for row in _as_list(registry_payload.get("regression_lineage")) if isinstance(row, dict)],
        previous_migration_lineage=[row for row in _as_list(registry_payload.get("migration_lineage")) if isinstance(row, dict)],
    )

    store = RealDownstreamConversionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.conversion_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "REAL_DOWNSTREAM_INGESTION_COGNITION",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "conversion_fingerprint": result.conversion_bundle.get("conversion_fingerprint", ""),
        "artifact_files": {
            "downstream_driver_graph": str((output_dir / "downstream_driver_graph.json").resolve()),
            "topology_runtime_graph": str((output_dir / "topology_runtime_graph.json").resolve()),
            "upstream_equivalence_map": str((output_dir / "upstream_equivalence_map.json").resolve()),
            "portability_blockers": str((output_dir / "portability_blockers.json").resolve()),
            "migration_risk_report": str((output_dir / "migration_risk_report.json").resolve()),
            "deterministic_conversion_plan": str((output_dir / "deterministic_conversion_plan.json").resolve()),
            "governance_conversion_boundaries": str((output_dir / "governance_conversion_boundaries.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "real_downstream_ingestion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
