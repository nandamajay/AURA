#!/usr/bin/env python3
"""Run governed patchset orchestration for tiny realistic multi-patch flows."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.governed_patchset_orchestration import (
    GovernedPatchsetOrchestrationEngine,
    GovernedPatchsetOrchestrationRegistry,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed patchset orchestration")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="governed_patchset_session_v1")
    parser.add_argument("--lineage-id", default="governed_patchset_orchestration_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()
    governance_state = _as_dict(registry_payload.get("governance_state"))

    replay_det = _read_json(output_dir / "aura_replay_determinism_report.json")
    replay_traces = {
        "deterministic_event_ordering": bool(_as_dict(replay_det).get("event_ordering_stable", True)),
        "deterministic_replay_fingerprint": str(_as_dict(replay_det).get("deterministic_fingerprint", "")),
    }

    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }

    previous_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("governed_patchset_orchestration")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = GovernedPatchsetOrchestrationEngine(plugin_loader=loader)
    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        previous_history=previous_history,
        evidence_references=[
            "registry://governance_state",
            "registry://governed_patchset_orchestration",
            "artifact://runtime_truth_graph",
            "artifact://runtime_equivalence_fingerprint",
            "artifact://runtime_equivalence_validation",
            "artifact://acceptance_confidence_score",
            "artifact://aura_replay_determinism_report",
        ],
    )

    store = GovernedPatchsetOrchestrationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.patchset_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "GOVERNED_PATCHSET_ORCHESTRATION_ENGINE",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": result.patchset_bundle.get("classification", "UNKNOWN"),
        "fail_closed_reasons": result.patchset_bundle.get("fail_closed_reasons", []),
        "real_multi_patchset_generated": _as_dict(result.patchset_bundle.get("artifacts", {}))
        .get("tiny_multi_patchset", {})
        .get("real_multi_patchset_generated", False),
        "governed_patchset_orchestration_fingerprint": result.patchset_bundle.get(
            "governed_patchset_orchestration_fingerprint",
            "",
        ),
        "artifact_files": {
            "governed_patchset_plan": str((output_dir / "governed_patchset_plan.json").resolve()),
            "patch_dependency_graph": str((output_dir / "patch_dependency_graph.json").resolve()),
            "runtime_patchset_equivalence": str((output_dir / "runtime_patchset_equivalence.json").resolve()),
            "patch_ordering_rationale": str((output_dir / "patch_ordering_rationale.json").resolve()),
            "bisectability_report": str((output_dir / "bisectability_report.json").resolve()),
            "patchset_review_risk_report": str((output_dir / "patchset_review_risk_report.json").resolve()),
            "rollback_checkpoint_registry": str((output_dir / "rollback_checkpoint_registry.json").resolve()),
            "deterministic_patchset_replay": str((output_dir / "deterministic_patchset_replay.json").resolve()),
            "cumulative_runtime_validation": str((output_dir / "cumulative_runtime_validation.json").resolve()),
            "upstream_patchset_prediction": str((output_dir / "upstream_patchset_prediction.json").resolve()),
            "governed_patchset_summary": str((output_dir / "governed_patchset_summary.json").resolve()),
            "tiny_multi_patchset": str((output_dir / "tiny_multi_patchset.patch").resolve()),
            "tiny_patchset_model": str((output_dir / "tiny_patchset_model.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "governed_patchset_orchestration_runner_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
