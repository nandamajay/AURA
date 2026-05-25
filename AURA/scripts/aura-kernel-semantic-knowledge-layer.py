#!/usr/bin/env python3
"""Kernel Semantic Knowledge Layer generator.

Advisory-only semantic cognition derived from Qualcomm Audio Knowledge Hub HTML,
with deterministic replay, traceability, governance boundaries, and plugin-safe
adapter integration.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.deterministic_serialization import dump_canonical_json
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_execution_contract import enforce_runtime_contract
from aura_sdk.transport.semantic_confidence_engine import build_semantic_confidence_report
from aura_sdk.transport.semantic_entity_extractor import extract_semantic_entities
from aura_sdk.transport.semantic_equivalence_mapper import build_semantic_equivalence_map
from aura_sdk.transport.semantic_governance_boundary import evaluate_semantic_governance_boundary
from aura_sdk.transport.semantic_html_parser import parse_semantic_html
from aura_sdk.transport.semantic_ontology_builder import build_semantic_ontology
from aura_sdk.transport.semantic_portability_reasoning import build_semantic_portability_rules
from aura_sdk.transport.semantic_relationship_graph import build_semantic_relationship_map
from aura_sdk.transport.semantic_replay_compatibility import build_semantic_replay_compatibility
from aura_sdk.transport.semantic_runtime_advisory import SemanticRuntimeAdvisoryEngine
from aura_sdk.transport.semantic_traceability_engine import (
    KernelSemanticKnowledgeRegistry,
    build_semantic_traceability_graph,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


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

    deterministic_alignment = _as_dict(_as_dict(topology_cognition.get("confidence")).get("deterministic_alignment"))

    return {
        "run_id": str(summary.get("run_id", "semantic_runtime_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(deterministic_alignment.get("playback_runtime_seconds", 25.0) or 25.0),
        "route_fingerprint": str(_as_dict(topology_cognition.get("runtime_route_graph")).get("route_fingerprint", "")),
        "command_sequence": [str(item) for item in _as_list(_as_dict(runtime_cognition.get("procedural_lock")).get("successful_execution_sequence")) if str(item).strip()],
    }


def main() -> int:
    enforce_runtime_contract("aura-kernel-semantic-knowledge-layer")
    parser = argparse.ArgumentParser(description="Generate Kernel Semantic Knowledge Layer artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="kernel_semantic_knowledge_layer_v1")
    parser.add_argument(
        "--knowledge-html",
        default="/local/mnt/workspace/Audio_knowledge_Hub/qcom_audio_knowledge_hub_v16.html",
    )
    parser.add_argument("--source-id", default="qcom_audio_knowledge_hub")
    parser.add_argument("--source-version", default="v16")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument("--runtime-evidence-file", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    if str(args.runtime_evidence_file).strip():
        override = _read_json(Path(str(args.runtime_evidence_file)))
        if override:
            runtime_evidence.update(override)

    governance_state = _as_dict(registry_payload.get("governance_state"))
    if not governance_state:
        governance_state = {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        }

    plugin_loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    plugin = plugin_loader.load_plugin(str(args.target_id))
    semantic_adapter = _as_dict(
        plugin.semantic_knowledge_adapter(
            {
                "source_id": str(args.source_id),
                "source_version": str(args.source_version),
                "runtime_evidence": runtime_evidence,
            }
        )
    )

    parsed = parse_semantic_html(
        source_path=Path(str(args.knowledge_html)),
        source_id=str(args.source_id),
        source_version=str(args.source_version),
    )

    entity_graph = extract_semantic_entities(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        parsed_document=parsed.parsed_document,
        adapter_payload=semantic_adapter,
    )

    relationship_map = build_semantic_relationship_map(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        parsed_document=parsed.parsed_document,
    )

    ontology = build_semantic_ontology(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        semantic_relationship_map=relationship_map.semantic_relationship_map,
    )

    governance_boundary = evaluate_semantic_governance_boundary(
        governance_state=governance_state,
        requested_actions=["analyze", "classify", "correlate", "lookup", "recommend", "replay", "trace"],
    )

    equivalence_map = build_semantic_equivalence_map(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        adapter_payload=semantic_adapter,
    )

    portability_rules = build_semantic_portability_rules(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        semantic_equivalence_map=equivalence_map.semantic_equivalence_map,
        semantic_relationship_map=relationship_map.semantic_relationship_map,
        adapter_payload=semantic_adapter,
    )

    advisory_engine = SemanticRuntimeAdvisoryEngine(plugin_loader=plugin_loader)
    runtime_advisory = advisory_engine.analyze(
        target_id=str(args.target_id),
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        runtime_evidence=runtime_evidence,
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        semantic_portability_rules=portability_rules.semantic_portability_rules,
        semantic_governance_boundary=governance_boundary.governance_boundary,
    )

    pre_trace_artifacts = {
        "semantic_entity_graph": entity_graph.semantic_entity_graph,
        "semantic_relationship_map": relationship_map.semantic_relationship_map,
        "semantic_ontology": ontology.semantic_ontology,
        "semantic_portability_rules": portability_rules.semantic_portability_rules,
        "semantic_equivalence_map": equivalence_map.semantic_equivalence_map,
        "semantic_runtime_advisories": runtime_advisory.semantic_runtime_advisories,
    }

    replay_compatibility = build_semantic_replay_compatibility(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        artifacts=pre_trace_artifacts,
        governance_boundary=governance_boundary.governance_boundary,
    )

    confidence_report = build_semantic_confidence_report(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        semantic_entity_graph=entity_graph.semantic_entity_graph,
        semantic_relationship_map=relationship_map.semantic_relationship_map,
        semantic_portability_rules=portability_rules.semantic_portability_rules,
        semantic_equivalence_map=equivalence_map.semantic_equivalence_map,
        semantic_replay_compatibility=replay_compatibility.semantic_replay_compatibility,
        semantic_governance_boundary=governance_boundary.governance_boundary,
    )

    traceability = build_semantic_traceability_graph(
        source_id=str(args.source_id),
        source_version=str(args.source_version),
        source_path=str(Path(str(args.knowledge_html)).resolve()),
        source_sha256=str(_as_dict(parsed.parsed_document).get("source_sha256", "")),
        lineage_id=str(args.lineage_id),
        artifacts={
            **pre_trace_artifacts,
            "semantic_confidence_report": confidence_report.semantic_confidence_report,
            "semantic_replay_compatibility": replay_compatibility.semantic_replay_compatibility,
            "semantic_governance_boundary": governance_boundary.governance_boundary,
        },
    )

    artifacts = {
        "semantic_entity_graph": entity_graph.semantic_entity_graph,
        "semantic_relationship_map": relationship_map.semantic_relationship_map,
        "semantic_ontology": ontology.semantic_ontology,
        "semantic_portability_rules": portability_rules.semantic_portability_rules,
        "semantic_equivalence_map": equivalence_map.semantic_equivalence_map,
        "semantic_runtime_advisories": runtime_advisory.semantic_runtime_advisories,
        "semantic_traceability_graph": traceability.semantic_traceability_graph,
        "semantic_confidence_report": confidence_report.semantic_confidence_report,
        "semantic_replay_compatibility": replay_compatibility.semantic_replay_compatibility,
        "semantic_governance_boundary": governance_boundary.governance_boundary,
    }

    bundle = {
        "schema_version": "1.0",
        "phase": "KERNEL_SEMANTIC_KNOWLEDGE_LAYER",
        "created_at_epoch": time.time(),
        "target_id": str(args.target_id),
        "source_id": str(args.source_id),
        "source_version": str(args.source_version),
        "source_path": str(Path(str(args.knowledge_html)).resolve()),
        "source_sha256": str(_as_dict(parsed.parsed_document).get("source_sha256", "")),
        "lineage_id": str(args.lineage_id),
        "governance_mode": "ADVISORY_ONLY",
        "runtime_truth_precedence": True,
        "evidence_references": [
            "source://qcom_audio_knowledge_hub_html",
            "registry://runtime_cognition",
            "registry://governance_state",
            "artifact://semantic_entity_graph",
            "artifact://semantic_relationship_map",
            "artifact://semantic_ontology",
        ],
        "plugin_adapter_payload": semantic_adapter,
        "artifacts": artifacts,
    }
    bundle["semantic_knowledge_fingerprint"] = stable_fingerprint(
        {
            "target_id": str(args.target_id),
            "source_id": str(args.source_id),
            "source_version": str(args.source_version),
            "lineage_id": str(args.lineage_id),
            "artifacts": artifacts,
        }
    )

    store = KernelSemanticKnowledgeRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "KERNEL_SEMANTIC_KNOWLEDGE_LAYER",
        "target_id": str(args.target_id),
        "source_id": str(args.source_id),
        "source_version": str(args.source_version),
        "lineage_id": str(args.lineage_id),
        "semantic_knowledge_fingerprint": bundle.get("semantic_knowledge_fingerprint", ""),
        "classification": str(_as_dict(confidence_report.semantic_confidence_report).get("classification", "UNKNOWN")),
        "artifact_files": {
            "semantic_entity_graph": str((output_dir / "semantic_entity_graph.json").resolve()),
            "semantic_relationship_map": str((output_dir / "semantic_relationship_map.json").resolve()),
            "semantic_ontology": str((output_dir / "semantic_ontology.json").resolve()),
            "semantic_portability_rules": str((output_dir / "semantic_portability_rules.json").resolve()),
            "semantic_equivalence_map": str((output_dir / "semantic_equivalence_map.json").resolve()),
            "semantic_runtime_advisories": str((output_dir / "semantic_runtime_advisories.json").resolve()),
            "semantic_traceability_graph": str((output_dir / "semantic_traceability_graph.json").resolve()),
            "semantic_confidence_report": str((output_dir / "semantic_confidence_report.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "governance_boundary": governance_boundary.governance_boundary,
        "replay_compatibility": replay_compatibility.semantic_replay_compatibility,
    }

    dump_canonical_json(output_dir / "kernel_semantic_knowledge_layer_summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
