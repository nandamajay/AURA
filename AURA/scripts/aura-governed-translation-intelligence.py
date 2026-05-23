#!/usr/bin/env python3
"""Governed downstream-to-upstream translation intelligence runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.governed_translation_intelligence import (
    GovernedTranslationIntelligenceEngine,
    GovernedTranslationIntelligenceRegistry,
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


def _load(output_dir: Path, names: list[str]) -> dict[str, Any]:
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate governed translation intelligence artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="governed_translation_session_v1")
    parser.add_argument("--lineage-id", default="governed_translation_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_artifacts = _load(
        output_dir,
        [
            "runtime_truth_graph",
            "pcm_lifecycle_trace",
            "pcm_runtime_state",
            "runtime_drift_report",
            "runtime_confidence_score",
        ],
    )
    topology_artifacts = _load(
        output_dir,
        [
            "topology_runtime_graph",
            "dts_topology_graph",
            "runtime_topology_correlation",
        ],
    )
    semantic_artifacts = _load(
        output_dir,
        [
            "semantic_entity_graph",
            "semantic_confidence_report",
            "semantic_cognition",
        ],
    )
    structural_artifacts = _load(
        output_dir,
        [
            "downstream_driver_graph",
            "structural_graph",
            "runtime_source_correlation",
            "callback_chain_graph",
        ],
    )
    translation_artifacts = _load(
        output_dir,
        [
            "downstream_upstream_mapping_graph",
            "upstream_equivalence_map",
            "topology_translation_report",
            "runtime_portability_analysis",
        ],
    )

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

    previous_translation_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("governed_translation_intelligence")).get("history"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = GovernedTranslationIntelligenceEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        runtime_artifacts=runtime_artifacts,
        topology_artifacts=topology_artifacts,
        semantic_artifacts=semantic_artifacts,
        structural_artifacts=structural_artifacts,
        translation_artifacts=translation_artifacts,
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://governed_translation_intelligence",
            "artifact://runtime_truth_graph",
            "artifact://pcm_lifecycle_trace",
            "artifact://topology_translation_report",
            "artifact://downstream_upstream_mapping_graph",
            "artifact://upstream_equivalence_map",
            "artifact://runtime_portability_analysis",
            "artifact://downstream_driver_graph",
            "artifact://semantic_entity_graph",
            "artifact://aura_replay_determinism_report",
        ],
        previous_translation_history=previous_translation_history,
    )

    store = GovernedTranslationIntelligenceRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.translation_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "GOVERNED_DOWNSTREAM_TO_UPSTREAM_TRANSLATION_INTELLIGENCE",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "governed_translation_fingerprint": result.translation_bundle.get("governed_translation_fingerprint", ""),
        "classification": result.translation_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "upstream_translation_plan": str((output_dir / "upstream_translation_plan.json").resolve()),
            "api_replacement_map": str((output_dir / "api_replacement_map.json").resolve()),
            "unsupported_vendor_constructs": str((output_dir / "unsupported_vendor_constructs.json").resolve()),
            "lifecycle_translation_graph": str((output_dir / "lifecycle_translation_graph.json").resolve()),
            "runtime_equivalence_validation": str((output_dir / "runtime_equivalence_validation.json").resolve()),
            "translation_confidence_report": str((output_dir / "translation_confidence_report.json").resolve()),
            "deterministic_translation_replay": str((output_dir / "deterministic_translation_replay.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "governed_translation_intelligence_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
