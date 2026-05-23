#!/usr/bin/env python3
"""Governed adaptive remediation and translation-learning runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.governed_adaptive_remediation import (
    GovernedAdaptiveRemediationEngine,
    GovernedAdaptiveRemediationRegistry,
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


def _merge_manual_outcomes(paths: list[Path]) -> dict[str, Any]:
    merged_entries: list[dict[str, Any]] = []
    for path in paths:
        payload = _read_json(path)
        for row in _as_list(_as_dict(payload).get("entries")):
            if isinstance(row, dict):
                merged_entries.append(dict(row))
    return {
        "schema_version": "1.0",
        "report_name": "manual_remediation_outcomes",
        "entries": merged_entries,
        "summary": {"entry_count": len(merged_entries)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate governed adaptive remediation artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="governed_adaptive_remediation_session_v1")
    parser.add_argument("--lineage-id", default="governed_adaptive_remediation_v1")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument(
        "--manual-remediation-file",
        action="append",
        default=[],
        help="Optional JSON file with manual remediation outcomes {entries:[...]}",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    translation_artifacts = _load(
        output_dir,
        [
            "upstream_translation_plan",
            "api_replacement_map",
            "unsupported_vendor_constructs",
            "runtime_equivalence_validation",
            "translation_confidence_report",
        ],
    )
    execution_artifacts = _load(
        output_dir,
        [
            "runtime_validated_patch_segments",
            "translation_execution_report",
            "unsafe_transformation_blocks",
            "transformation_lineage",
            "deterministic_patch_generation_replay",
        ],
    )
    runtime_artifacts = _load(output_dir, ["runtime_truth_graph"])

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

    previous_learning_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("governed_adaptive_remediation")).get("history"))
        if isinstance(row, dict)
    ]

    manual_paths = [Path(path) for path in _as_list(args.manual_remediation_file) if str(path).strip()]
    default_manual = output_dir / "manual_remediation_outcomes.json"
    if default_manual.exists():
        manual_paths.append(default_manual)
    manual_remediation_outcomes = _merge_manual_outcomes(manual_paths)

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = GovernedAdaptiveRemediationEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        translation_artifacts=translation_artifacts,
        execution_artifacts=execution_artifacts,
        runtime_artifacts=runtime_artifacts,
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        manual_remediation_outcomes=manual_remediation_outcomes,
        previous_learning_history=previous_learning_history,
        evidence_references=[
            "registry://governance_state",
            "registry://governed_adaptive_remediation",
            "artifact://api_replacement_map",
            "artifact://runtime_equivalence_validation",
            "artifact://runtime_validated_patch_segments",
            "artifact://translation_execution_report",
            "artifact://unsafe_transformation_blocks",
            "artifact://unsupported_vendor_constructs",
            "artifact://runtime_truth_graph",
            "artifact://aura_replay_determinism_report",
            "artifact://manual_remediation_outcomes",
        ],
    )

    store = GovernedAdaptiveRemediationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.learning_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "GOVERNED_ADAPTIVE_REMEDIATION_TRANSLATION_LEARNING",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": result.learning_bundle.get("classification", "UNKNOWN"),
        "fail_closed_justification": result.learning_bundle.get("fail_closed_justification", ""),
        "governed_adaptive_remediation_fingerprint": result.learning_bundle.get(
            "governed_adaptive_remediation_fingerprint",
            "",
        ),
        "artifact_files": {
            "learned_translation_patterns": str((output_dir / "learned_translation_patterns.json").resolve()),
            "remediation_template_registry": str((output_dir / "remediation_template_registry.json").resolve()),
            "historical_blocker_similarity_map": str((output_dir / "historical_blocker_similarity_map.json").resolve()),
            "confidence_calibration_report": str((output_dir / "confidence_calibration_report.json").resolve()),
            "reusable_equivalence_library": str((output_dir / "reusable_equivalence_library.json").resolve()),
            "subsystem_translation_memory": str((output_dir / "subsystem_translation_memory.json").resolve()),
            "adaptive_remediation_trace": str((output_dir / "adaptive_remediation_trace.json").resolve()),
        },
        "manual_remediation_sources": [str(path.resolve()) for path in manual_paths],
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "governed_adaptive_remediation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
