#!/usr/bin/env python3
"""Runtime Incident Reconstruction and Root-Cause Reasoning runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_incident_reconstructor import (
    RuntimeIncidentReconstructionRegistry,
    RuntimeIncidentReconstructor,
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


def _load_lines(path: Path, limit: int = 800) -> list[str]:
    if not path.exists():
        return []
    try:
        return [line.rstrip("\n") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:limit] if line.strip()]
    except Exception:
        return []


def _load_runtime_sources(output_dir: Path) -> dict[str, Any]:
    candidates = {
        "dmesg": ["runtime_dmesg.log", "dmesg.log"],
        "ftrace": ["runtime_ftrace.log", "ftrace.log"],
        "trace_cmd": ["trace_cmd.json", "runtime_trace_cmd.json"],
        "tinyalsa_dump": ["tinymix_dump.txt", "tinyalsa_dump.txt"],
        "procfs_sysfs": ["procfs_sysfs_runtime.txt", "runtime_procfs_sysfs.txt"],
        "soundwire_debugfs": ["soundwire_debugfs.txt", "runtime_soundwire_debugfs.txt"],
        "alsa_topology_runtime": ["alsa_topology_runtime.txt", "runtime_alsa_topology.txt"],
        "mailbox_trace": ["mailbox_trace.log", "runtime_mailbox_trace.log"],
        "dsp_response_log": ["dsp_response.log", "runtime_dsp_response.log"],
    }

    payloads: dict[str, Any] = {}
    for source, names in candidates.items():
        loaded: dict[str, Any] = {}
        for name in names:
            path = output_dir / name
            if not path.exists():
                continue
            if path.suffix.lower() == ".json":
                maybe_json = _read_json(path)
                if isinstance(maybe_json.get("events"), list):
                    loaded = {"events": maybe_json.get("events", [])}
                    break
                if isinstance(maybe_json.get("lines"), list):
                    loaded = {"lines": [str(item) for item in maybe_json.get("lines", [])]}
                    break
            lines = _load_lines(path)
            if lines:
                loaded = {"lines": lines}
                break
        payloads[source] = loaded

    # Fallback deterministic offline runtime sources from existing artifacts.
    if not _as_dict(payloads.get("ftrace")):
        pcm = _read_json(output_dir / "pcm_lifecycle_trace.json")
        ftrace_lines = []
        for row in _as_list(pcm.get("transitions")):
            item = _as_dict(row)
            ftrace_lines.append(f"{float(item.get('timestamp_ms', 0.0) or 0.0)/1000.0:.3f}: pcm {item.get('stage', 'STATE')}")
        if ftrace_lines:
            payloads["ftrace"] = {"lines": ftrace_lines}

    if not _as_dict(payloads.get("trace_cmd")):
        dapm = _read_json(output_dir / "dapm_transition_trace.json")
        trace_events = []
        for row in _as_list(dapm.get("transitions")):
            item = _as_dict(row)
            trace_events.append(
                {
                    "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                    "category": "dapm",
                    "detail": str(item.get("transition", "STATE")),
                }
            )
        if trace_events:
            payloads["trace_cmd"] = {"events": trace_events}

    if not _as_dict(payloads.get("dmesg")):
        drift = _read_json(output_dir / "runtime_drift_report.json")
        lines = [str(_as_dict(row).get("details", "")) for row in _as_list(drift.get("drifts")) if str(_as_dict(row).get("details", "")).strip()]
        if lines:
            payloads["dmesg"] = {"lines": lines}

    return payloads


def _load_runtime_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "runtime_truth_graph",
        "pcm_lifecycle_trace",
        "dapm_transition_trace",
        "soundwire_runtime_graph",
        "irq_timing_report",
        "dsp_sync_report",
        "runtime_drift_report",
        "regression_rootcause_report",
    ]
    payload = {name: _read_json(output_dir / f"{name}.json") for name in names}
    payload["fusion_rootcause_report"] = payload.get("regression_rootcause_report", {})
    return payload


def _load_topology_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "topology_runtime_graph",
        "runtime_topology_correlation",
        "unified_engineering_truth_graph",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_patch_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "patch_series_plan",
        "runtime_patch_correlation",
        "vendor_contamination_report",
        "upstream_readiness_report",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_migration_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "migration_runtime_alignment",
        "portability_blockers",
        "upstream_equivalence_map",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _load_semantic_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "semantic_confidence_report",
        "dts_topology_graph",
        "semantic_entity_graph",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime incident reconstruction artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="runtime_incident_reconstruction_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_sources = _load_runtime_sources(output_dir)
    runtime_artifacts = _load_runtime_artifacts(output_dir)
    topology_artifacts = _load_topology_artifacts(output_dir)
    patch_artifacts = _load_patch_artifacts(output_dir)
    migration_artifacts = _load_migration_artifacts(output_dir)
    semantic_artifacts = _load_semantic_artifacts(output_dir)

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

    previous_incident_lineage = [
        row
        for row in _as_list(registry_payload.get("runtime_incident_lineage"))
        if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    reconstructor = RuntimeIncidentReconstructor(plugin_loader=loader)

    result = reconstructor.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_sources=runtime_sources,
        runtime_artifacts=runtime_artifacts,
        topology_artifacts=topology_artifacts,
        patch_artifacts=patch_artifacts,
        migration_artifacts=migration_artifacts,
        semantic_artifacts=semantic_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://runtime_truth_cognition",
            "registry://runtime_evidence_fusion",
            "artifact://runtime_truth_graph",
            "artifact://pcm_lifecycle_trace",
            "artifact://dapm_transition_trace",
            "artifact://soundwire_runtime_graph",
            "artifact://irq_timing_report",
            "artifact://dsp_sync_report",
            "artifact://topology_runtime_graph",
            "artifact://patch_series_plan",
            "artifact://runtime_patch_correlation",
            "artifact://migration_runtime_alignment",
            "artifact://upstream_equivalence_map",
        ],
        previous_incident_lineage=previous_incident_lineage,
    )

    store = RuntimeIncidentReconstructionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.incident_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_INCIDENT_RECONSTRUCTION_LAYER",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "runtime_incident_reconstruction_fingerprint": result.incident_bundle.get(
            "runtime_incident_reconstruction_fingerprint", ""
        ),
        "classification": result.incident_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "runtime_incident_graph": str((output_dir / "runtime_incident_graph.json").resolve()),
            "root_cause_candidates": str((output_dir / "root_cause_candidates.json").resolve()),
            "lifecycle_violation_report": str((output_dir / "lifecycle_violation_report.json").resolve()),
            "runtime_sequence_drift": str((output_dir / "runtime_sequence_drift.json").resolve()),
            "topology_runtime_causality": str((output_dir / "topology_runtime_causality.json").resolve()),
            "regression_causality_report": str((output_dir / "regression_causality_report.json").resolve()),
            "deterministic_incident_replay": str((output_dir / "deterministic_incident_replay.json").resolve()),
            "engineering_confidence_report": str((output_dir / "engineering_confidence_report.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "runtime_incident_reconstruction_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
