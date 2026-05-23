#!/usr/bin/env python3
"""Translation intelligence layer generator.

Builds deterministic downstream->upstream conversion cognition artifacts using
runtime evidence, topology cognition, semantic cognition, regression lineage,
replay traces, and governance state.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.upstream_conversion_planner import (
    TranslationIntelligenceRegistry,
    UpstreamConversionPlanner,
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
    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    baseline_registry = _as_dict(registry_payload.get("baseline_registry"))
    lock = _as_dict(runtime_cognition.get("procedural_lock"))
    summary = _as_dict(runtime_cognition.get("last_trace_summary"))

    known_routes = _as_list(target_knowledge.get("known_route_fingerprints"))
    route_fingerprint = str(known_routes[0]) if known_routes else ""

    capabilities = _as_dict(target_knowledge.get("capabilities"))
    if not capabilities:
        capabilities = _as_dict(_as_dict(_as_dict(baseline_registry.get("profile", {})).get("baseline_profile", {})).get("mixer_capability_state", {}))

    return {
        "run_id": str(summary.get("run_id", "translation_runtime_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "evidence_success": bool(summary.get("evidence_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(_as_dict(_as_dict(registry_payload.get("topology_cognition", {})).get("confidence", {})).get("deterministic_alignment", {}).get("playback_runtime_seconds", 25.0) or 25.0),
        "route_fingerprint": route_fingerprint,
        "capabilities": capabilities,
        "command_sequence": [str(item) for item in _as_list(lock.get("successful_execution_sequence")) if str(item).strip()],
        "evidence_references": [
            "registry://runtime_cognition/last_trace_summary",
            "registry://runtime_cognition/procedural_lock",
            "registry://target_knowledge",
        ],
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate translation intelligence layer artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="translation_intelligence_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    topology_cognition = _as_dict(registry_payload.get("topology_cognition"))
    semantic_latest = _as_dict(_as_dict(registry_payload.get("semantic_cognition")).get("latest"))
    dts_cognition = _derive_dts_cognition(registry_payload)
    replay_traces = {
        "semantic_replay": _read_json(output_dir / "semantic_replay_trace.json"),
        "correlation_replay": _read_json(output_dir / "cognition_fusion_trace.json"),
        "deterministic_event_ordering": bool(_as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("event_ordering_stable", True)),
        "deterministic_replay_fingerprint": str(_as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("deterministic_fingerprint", "")),
    }
    regression_history = [row for row in _as_list(registry_payload.get("regression_lineage")) if isinstance(row, dict)]
    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }
    governance_state = _as_dict(registry_payload.get("governance_state"))
    previous_migration_lineage = [row for row in _as_list(registry_payload.get("migration_lineage")) if isinstance(row, dict)]

    loader = TargetPluginLoader(registry_path=args.plugin_registry) if str(args.plugin_registry).strip() else TargetPluginLoader()
    planner = UpstreamConversionPlanner(plugin_loader=loader)

    result = planner.analyze(
        target_id=str(args.target_id),
        runtime_evidence=runtime_evidence,
        topology_cognition=topology_cognition,
        dts_cognition=dts_cognition,
        semantic_cognition=semantic_latest,
        replay_traces=replay_traces,
        regression_history=regression_history,
        plugin_capability_state=plugin_capability_state,
        governance_state=governance_state,
        lineage_id=str(args.lineage_id),
        evidence_references=[
            "registry://runtime_cognition",
            "registry://topology_cognition",
            "registry://semantic_cognition",
            "registry://regression_lineage",
            "registry://governance_state",
            "artifact://aura_replay_determinism_report",
            "artifact://semantic_replay_trace",
            "artifact://cognition_fusion_trace",
        ],
        previous_migration_lineage=previous_migration_lineage,
    )

    store = TranslationIntelligenceRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.conversion_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "TRANSLATION_INTELLIGENCE_LAYER",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "translation_fingerprint": result.conversion_bundle.get("translation_fingerprint", ""),
        "artifact_files": {
            "downstream_upstream_mapping_graph": str((output_dir / "downstream_upstream_mapping_graph.json").resolve()),
            "topology_translation_report": str((output_dir / "topology_translation_report.json").resolve()),
            "runtime_portability_analysis": str((output_dir / "runtime_portability_analysis.json").resolve()),
            "migration_lineage": str((output_dir / "migration_lineage.json").resolve()),
            "upstream_conversion_confidence": str((output_dir / "upstream_conversion_confidence.json").resolve()),
            "deterministic_translation_replay": str((output_dir / "deterministic_translation_replay.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "translation_intelligence_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
