#!/usr/bin/env python3
"""Run real patch application + sandbox build validation governance."""

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
from aura_sdk.transport.sandbox_patch_validation_engine import (
    SandboxPatchValidationEngine,
    SandboxPatchValidationRegistry,
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
    parser = argparse.ArgumentParser(description="Run sandbox patch validation")
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
        action="append",
        default=[],
        help="Patch path(s) to apply in order",
    )
    parser.add_argument("--session-id", default="sandbox_patch_validation_session_v1")
    parser.add_argument("--lineage-id", default="sandbox_patch_validation_v1")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument("--subsystem", action="append", default=[])
    parser.add_argument("--object", action="append", default=[])
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    patch_paths = [Path(str(v)) for v in args.patch_path if str(v).strip()]
    if not patch_paths:
        patch_paths = [Path("/local/mnt/workspace/AURA_V1/docs/operations/transport/downstream_to_upstream.patch")]

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
        for row in _as_list(_as_dict(registry_payload.get("sandbox_patch_validation")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = SandboxPatchValidationEngine(plugin_loader=loader)
    bundle = engine.analyze(
        target_id=str(args.target_id),
        source_root=Path(str(args.source_root)),
        patch_paths=patch_paths,
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
            "registry://sandbox_patch_validation",
            "artifact://downstream_to_upstream_patch",
            "artifact://aura_replay_determinism_report",
        ],
        subsystem_targets=[str(v) for v in args.subsystem if str(v).strip()],
        object_targets=[str(v) for v in args.object if str(v).strip()],
    ).validation_bundle

    store = SandboxPatchValidationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))
    summary = _as_dict(_as_dict(bundle.get("artifacts")).get("sandbox_patch_validation_summary"))
    runtime_promotion = _as_dict(_as_dict(bundle.get("artifacts")).get("runtime_promotion_eligibility"))

    out = {
        "schema_version": "1.0",
        "phase": "SANDBOX_PATCH_VALIDATION",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": str(bundle.get("classification", "UNKNOWN")),
        "fail_closed_reasons": _as_list(bundle.get("fail_closed_reasons")),
        "source_root": str(Path(str(args.source_root)).resolve()),
        "patch_paths": [str(path.resolve()) for path in patch_paths],
        "sandbox_patch_validation_fingerprint": str(bundle.get("sandbox_patch_validation_fingerprint", "")),
        "artifact_files": {
            "sandbox_workspace_manifest": str((output_dir / "sandbox_workspace_manifest.json").resolve()),
            "applied_patch_lineage": str((output_dir / "applied_patch_lineage.json").resolve()),
            "patch_application_trace": str((output_dir / "patch_application_trace.json").resolve()),
            "subsystem_build_validation": str((output_dir / "subsystem_build_validation.json").resolve()),
            "object_rebuild_lineage": str((output_dir / "object_rebuild_lineage.json").resolve()),
            "modpost_validation_report": str((output_dir / "modpost_validation_report.json").resolve()),
            "linker_closure_report": str((output_dir / "linker_closure_report.json").resolve()),
            "symbol_regression_report": str((output_dir / "symbol_regression_report.json").resolve()),
            "build_fingerprint_diff": str((output_dir / "build_fingerprint_diff.json").resolve()),
            "transformation_equivalence_report": str((output_dir / "transformation_equivalence_report.json").resolve()),
            "runtime_promotion_eligibility": str((output_dir / "runtime_promotion_eligibility.json").resolve()),
            "rollback_lineage_report": str((output_dir / "rollback_lineage_report.json").resolve()),
            "deterministic_patch_validation_replay": str(
                (output_dir / "deterministic_patch_validation_replay.json").resolve()
            ),
            "runtime_sensitive_patch_impact": str((output_dir / "runtime_sensitive_patch_impact.json").resolve()),
            "sandbox_patch_validation_summary": str((output_dir / "sandbox_patch_validation_summary.json").resolve()),
            "governance_patch_validation_decision": str(
                (output_dir / "governance_patch_validation_decision.json").resolve()
            ),
        },
        "summary": _as_dict(summary.get("summary")),
        "runtime_promotion_eligible": bool(runtime_promotion.get("eligible", False)),
        "confidence_score": _as_dict(_as_dict(bundle.get("artifacts")).get("build_confidence_report")).get(
            "confidence_score", 0.0
        ),
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }
    (output_dir / "sandbox_patch_validation_runner_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

