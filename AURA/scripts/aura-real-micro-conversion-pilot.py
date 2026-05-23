#!/usr/bin/env python3
"""Run the first real governed downstream-to-upstream micro-conversion pilot."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.real_micro_conversion_pilot import (
    RealMicroConversionPilotEngine,
    RealMicroConversionPilotRegistry,
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
    parser = argparse.ArgumentParser(description="Run real governed micro-conversion pilot")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="real_micro_conversion_session_v1")
    parser.add_argument("--lineage-id", default="real_micro_conversion_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = AURACognitionRegistry(args.registry_path)
    registry_payload = registry.load()

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
        for row in _as_list(_as_dict(registry_payload.get("real_micro_conversion_pilot")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = RealMicroConversionPilotEngine(plugin_loader=loader)
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
            "registry://real_micro_conversion_pilot",
            "artifact://runtime_truth_graph",
            "artifact://runtime_equivalence_fingerprint",
            "artifact://api_replacement_map",
            "artifact://generated_upstream_patch",
            "artifact://acceptance_confidence_score",
        ],
    )

    store = RealMicroConversionPilotRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.pilot_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "FIRST_REAL_GOVERNED_MICRO_CONVERSION_PILOT",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": result.pilot_bundle.get("classification", "UNKNOWN"),
        "real_transformed_patch_generated": bool(result.pilot_bundle.get("real_transformed_patch_generated", False)),
        "real_micro_conversion_fingerprint": result.pilot_bundle.get("real_micro_conversion_fingerprint", ""),
        "artifact_files": {
            "real_micro_conversion_patch": str((output_dir / "real_micro_conversion.patch").resolve()),
            "transformation_explainability_report": str(
                (output_dir / "transformation_explainability_report.json").resolve()
            ),
            "runtime_equivalence_validation": str((output_dir / "runtime_equivalence_validation.json").resolve()),
            "governance_decision_report": str((output_dir / "governance_decision_report.json").resolve()),
            "conversion_confidence_report": str((output_dir / "conversion_confidence_report.json").resolve()),
            "rollback_lineage": str((output_dir / "rollback_lineage.json").resolve()),
            "deterministic_conversion_replay": str((output_dir / "deterministic_conversion_replay.json").resolve()),
            "upstream_acceptance_prediction": str((output_dir / "upstream_acceptance_prediction.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "real_micro_conversion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
