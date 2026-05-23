#!/usr/bin/env python3
"""Run real source-tree governed conversion on Qualcomm downstream audio tree."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.real_source_tree_governed_conversion import (
    RealSourceTreeGovernedConversionEngine,
    RealSourceTreeGovernedConversionRegistry,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real source-tree governed conversion")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument(
        "--source-root",
        default=(
            "/local/mnt/workspace/AURA_V1/evidence/"
            "wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar"
        ),
    )
    parser.add_argument("--session-id", default="real_source_tree_conversion_session_v1")
    parser.add_argument("--lineage-id", default="real_source_tree_governed_conversion_v1")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument("--max-files", type=int, default=7000)
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
    previous_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("real_source_tree_governed_conversion")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = RealSourceTreeGovernedConversionEngine(plugin_loader=loader)
    result = engine.analyze(
        target_id=str(args.target_id),
        source_root=Path(str(args.source_root)),
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        previous_history=previous_history,
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        evidence_references=[
            "registry://governance_state",
            "registry://runtime_cognition",
            "registry://topology_cognition",
            "registry://real_source_tree_governed_conversion",
            "source://downstream_audio_kernel_tree",
            "artifact://aura_replay_determinism_report",
        ],
        max_files=max(500, int(args.max_files)),
    )

    store = RealSourceTreeGovernedConversionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.conversion_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = _as_dict(_as_dict(result.conversion_bundle.get("artifacts")).get("real_driver_conversion_summary"))
    out = {
        "schema_version": "1.0",
        "phase": "REAL_SOURCE_TREE_GOVERNED_CONVERSION",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": str(result.conversion_bundle.get("classification", "UNKNOWN")),
        "fail_closed_reasons": _as_list(result.conversion_bundle.get("fail_closed_reasons")),
        "source_root": str(Path(str(args.source_root)).resolve()),
        "conversion_fingerprint": str(result.conversion_bundle.get("conversion_fingerprint", "")),
        "artifact_files": {
            "source_tree_graph": str((output_dir / "source_tree_graph.json").resolve()),
            "subsystem_boundary_map": str((output_dir / "subsystem_boundary_map.json").resolve()),
            "symbol_dependency_graph": str((output_dir / "symbol_dependency_graph.json").resolve()),
            "wrapper_classification_report": str((output_dir / "wrapper_classification_report.json").resolve()),
            "governed_conversion_plan": str((output_dir / "governed_conversion_plan.json").resolve()),
            "compile_validation_report": str((output_dir / "compile_validation_report.json").resolve()),
            "runtime_sensitive_regions": str((output_dir / "runtime_sensitive_regions.json").resolve()),
            "governance_escalation_report": str((output_dir / "governance_escalation_report.json").resolve()),
            "deterministic_driver_replay": str((output_dir / "deterministic_driver_replay.json").resolve()),
            "transformation_confidence_report": str((output_dir / "transformation_confidence_report.json").resolve()),
            "upstream_equivalence_map": str((output_dir / "upstream_equivalence_map.json").resolve()),
            "downstream_to_upstream_patch": str((output_dir / "downstream_to_upstream.patch").resolve()),
            "real_driver_conversion_summary": str((output_dir / "real_driver_conversion_summary.json").resolve()),
        },
        "summary": _as_dict(summary.get("summary")),
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "real_source_tree_governed_conversion_runner_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
