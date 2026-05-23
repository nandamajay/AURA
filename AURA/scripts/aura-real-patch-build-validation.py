#!/usr/bin/env python3
"""Run real patch application + governed build validation."""

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
from aura_sdk.transport.real_patch_application_governed_build import (
    RealPatchApplicationGovernedBuildEngine,
    RealPatchApplicationGovernedBuildRegistry,
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
    parser = argparse.ArgumentParser(description="Run real patch application + governed build validation")
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
    parser.add_argument(
        "--patch-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch",
    )
    parser.add_argument("--session-id", default="real_patch_build_validation_session_v1")
    parser.add_argument("--lineage-id", default="real_patch_application_governed_build_v1")
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
    previous_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("real_patch_application_governed_build")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = RealPatchApplicationGovernedBuildEngine(plugin_loader=loader)
    result = engine.analyze(
        target_id=str(args.target_id),
        source_root=Path(str(args.source_root)),
        patch_path=Path(str(args.patch_path)),
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
            "registry://real_patch_application_governed_build",
            "artifact://downstream_to_upstream_patch",
            "artifact://aura_replay_determinism_report",
        ],
    ).build_bundle

    store = RealPatchApplicationGovernedBuildRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result)
    replay = store.replay(lineage_id=str(args.lineage_id))
    summary = _as_dict(_as_dict(result.get("artifacts")).get("real_patch_validation_summary"))

    out = {
        "schema_version": "1.0",
        "phase": "REAL_PATCH_APPLICATION_GOVERNED_BUILD",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": str(result.get("classification", "UNKNOWN")),
        "fail_closed_reasons": _as_list(result.get("fail_closed_reasons")),
        "source_root": str(Path(str(args.source_root)).resolve()),
        "patch_path": str(Path(str(args.patch_path)).resolve()),
        "build_validation_fingerprint": str(result.get("build_validation_fingerprint", "")),
        "artifact_files": {
            "applied_patch_diff": str((output_dir / "applied_patch.diff").resolve()),
            "patch_apply_report": str((output_dir / "patch_apply_report.json").resolve()),
            "incremental_build_report": str((output_dir / "incremental_build_report.json").resolve()),
            "touched_object_graph": str((output_dir / "touched_object_graph.json").resolve()),
            "symbol_resolution_report": str((output_dir / "symbol_resolution_report.json").resolve()),
            "include_closure_report": str((output_dir / "include_closure_report.json").resolve()),
            "runtime_sensitive_compile_report": str((output_dir / "runtime_sensitive_compile_report.json").resolve()),
            "build_confidence_report": str((output_dir / "build_confidence_report.json").resolve()),
            "rollback_lineage": str((output_dir / "rollback_lineage.json").resolve()),
            "deterministic_build_replay": str((output_dir / "deterministic_build_replay.json").resolve()),
            "compile_warning_clusters": str((output_dir / "compile_warning_clusters.json").resolve()),
            "governance_build_escalation": str((output_dir / "governance_build_escalation.json").resolve()),
            "real_patch_validation_summary": str((output_dir / "real_patch_validation_summary.json").resolve()),
        },
        "summary": _as_dict(summary.get("summary")),
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }
    (output_dir / "real_patch_build_validation_runner_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

