#!/usr/bin/env python3
"""Controlled downstream-to-upstream pilot conversion runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.controlled_pilot_conversion import (
    ControlledPilotConversionEngine,
    ControlledPilotConversionRegistry,
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


def _collect_source_snapshots(
    *,
    source_manifest: Path | None,
    source_root: Path | None,
    source_files: list[str],
) -> dict[str, str]:
    snapshots: dict[str, str] = {}

    if source_manifest and source_manifest.exists():
        payload = _read_json(source_manifest)
        for path, content in _as_dict(payload).items():
            if isinstance(path, str) and isinstance(content, str):
                snapshots[path] = content

    for item in source_files:
        candidate = Path(item)
        path = candidate
        if not candidate.is_absolute() and source_root is not None:
            path = (source_root / candidate).resolve()
        if not path.exists() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        key = str(path)
        if source_root is not None:
            try:
                key = str(path.relative_to(source_root.resolve()))
            except ValueError:
                key = str(path)
        snapshots[key] = text

    return dict(sorted(snapshots.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate controlled pilot conversion artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="controlled_pilot_conversion_session_v1")
    parser.add_argument("--lineage-id", default="controlled_pilot_conversion_v1")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument(
        "--source-manifest",
        default="",
        help="JSON map of {path: source_text} for pilot transformations.",
    )
    parser.add_argument(
        "--source-root",
        default="",
        help="Optional source root for resolving relative --source-file entries.",
    )
    parser.add_argument(
        "--source-file",
        action="append",
        default=[],
        help="Source file to include in pilot conversion candidate set. May be repeated.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Generate pilot patch in dry-run mode.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_manifest = Path(args.source_manifest) if str(args.source_manifest).strip() else None
    source_root = Path(args.source_root) if str(args.source_root).strip() else None
    source_snapshots = _collect_source_snapshots(
        source_manifest=source_manifest,
        source_root=source_root,
        source_files=[str(item) for item in _as_list(args.source_file)],
    )

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
            "autonomous_runtime_mutation_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        }

    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }

    previous_pilot_history = [
        row
        for row in _as_list(_as_dict(registry_payload.get("controlled_pilot_conversion")).get("history"))
        if isinstance(row, dict)
    ]

    translation_artifacts = _load(
        output_dir,
        [
            "api_replacement_map",
            "unsupported_vendor_constructs",
            "runtime_equivalence_validation",
        ],
    )
    execution_artifacts = _load(
        output_dir,
        [
            "runtime_validated_patch_segments",
            "translation_execution_report",
        ],
    )
    acceptance_artifacts = _load(
        output_dir,
        [
            "upstream_acceptance_report",
            "acceptance_confidence_score",
            "regression_risk_assessment",
            "patch_series_validation",
        ],
    )
    runtime_artifacts = _load(
        output_dir,
        [
            "runtime_equivalence_fingerprint",
            "topology_runtime_graph",
            "runtime_divergence_report",
        ],
    )

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = ControlledPilotConversionEngine(plugin_loader=loader)
    result = engine.analyze(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        source_snapshots=source_snapshots,
        translation_artifacts=translation_artifacts,
        execution_artifacts=execution_artifacts,
        acceptance_artifacts=acceptance_artifacts,
        runtime_artifacts=runtime_artifacts,
        governance_state=governance_state,
        replay_traces=replay_traces,
        plugin_capability_state=plugin_capability_state,
        dry_run=bool(args.dry_run),
        evidence_references=[
            "registry://governance_state",
            "registry://controlled_pilot_conversion",
            "artifact://api_replacement_map",
            "artifact://unsupported_vendor_constructs",
            "artifact://runtime_equivalence_validation",
            "artifact://runtime_validated_patch_segments",
            "artifact://translation_execution_report",
            "artifact://upstream_acceptance_report",
            "artifact://acceptance_confidence_score",
            "artifact://regression_risk_assessment",
            "artifact://runtime_equivalence_fingerprint",
            "artifact://topology_runtime_graph",
            "artifact://aura_replay_determinism_report",
        ],
        previous_pilot_history=previous_pilot_history,
    )

    store = ControlledPilotConversionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.pilot_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "CONTROLLED_DOWNSTREAM_TO_UPSTREAM_PILOT_CONVERSION_FRAMEWORK",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": result.pilot_bundle.get("classification", "UNKNOWN"),
        "dry_run": bool(args.dry_run),
        "source_snapshot_count": len(source_snapshots),
        "controlled_pilot_conversion_fingerprint": result.pilot_bundle.get(
            "controlled_pilot_conversion_fingerprint",
            "",
        ),
        "artifact_files": {
            "pilot_conversion_patch": str((output_dir / "pilot_conversion_patch.diff").resolve()),
            "transformation_explainability_report": str(
                (output_dir / "transformation_explainability_report.json").resolve()
            ),
            "runtime_equivalence_validation": str((output_dir / "runtime_equivalence_validation.json").resolve()),
            "upstream_review_package": str((output_dir / "upstream_review_package.json").resolve()),
            "pilot_risk_assessment": str((output_dir / "pilot_risk_assessment.json").resolve()),
            "transformation_lineage": str((output_dir / "transformation_lineage.json").resolve()),
            "rollback_validation_report": str((output_dir / "rollback_validation_report.json").resolve()),
            "deterministic_pilot_replay": str((output_dir / "deterministic_pilot_replay.json").resolve()),
            "governance_decision_report": str((output_dir / "governance_decision_report.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "controlled_pilot_conversion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
