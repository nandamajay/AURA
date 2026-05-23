#!/usr/bin/env python3
"""Runtime Truth Cognition Layer runner (offline foundation mode)."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_truth_engine import RuntimeTruthEngine, RuntimeTruthRegistry


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
    lock = _as_dict(runtime_cognition.get("procedural_lock"))

    deterministic_alignment = _as_dict(_as_dict(topology_cognition.get("confidence")).get("deterministic_alignment"))

    return {
        "run_id": str(summary.get("run_id", "runtime_truth_unknown")),
        "process_success": bool(summary.get("process_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "playback_runtime_seconds": float(deterministic_alignment.get("playback_runtime_seconds", 25.0) or 25.0),
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": str(_as_dict(topology_cognition.get("runtime_route_graph")).get("route_fingerprint", "")),
        "command_sequence": [str(item) for item in _as_list(lock.get("successful_execution_sequence")) if str(item).strip()],
        "pcm_activity": _as_dict(_as_dict(registry_payload.get("cognition_correlation", {})).get("latest", {}).get("artifacts", {}).get("evidence_lineage_graph", {})),
        "mixer_state": {
            "controls": _as_list(_as_dict(_as_dict(registry_payload.get("target_knowledge", {})).get("capabilities", {})).keys()),
        },
    }


def _load_lines(path: Path, limit: int = 400) -> list[str]:
    if not path.exists():
        return []
    try:
        return [line.rstrip("\n") for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[:limit] if line.strip()]
    except Exception:
        return []


def _load_source_payloads(output_dir: Path) -> dict[str, Any]:
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
                json_payload = _read_json(path)
                if json_payload:
                    if isinstance(json_payload.get("events"), list):
                        loaded = {"events": json_payload.get("events", [])}
                        break
                    if isinstance(json_payload.get("lines"), list):
                        loaded = {"lines": [str(item) for item in json_payload.get("lines", [])]}
                        break
            lines = _load_lines(path)
            if lines:
                loaded = {"lines": lines}
                break
        payloads[source] = loaded

    # Pull additional signal from existing deterministic runtime artifacts.
    drift_report = _read_json(output_dir / "playback_drift_report.json")
    if drift_report:
        details = []
        for row in _as_list(drift_report.get("deviations")):
            details.append(str(_as_dict(row).get("details", "")))
        if details:
            payloads.setdefault("dmesg", {})
            payloads["dmesg"] = {
                "lines": _as_list(_as_dict(payloads.get("dmesg")).get("lines")) + details
            }

    source_corr = _read_json(output_dir / "runtime_source_correlation.json")
    if source_corr:
        corr_events = []
        for row in _as_list(source_corr.get("command_source_correlations")):
            item = _as_dict(row)
            corr_events.append(
                {
                    "timestamp_ms": 1000.0 + len(corr_events) * 5.0,
                    "category": "runtime_generic",
                    "detail": str(item.get("runtime_command", "")),
                }
            )
        if corr_events:
            payloads.setdefault("trace_cmd", {})
            payloads["trace_cmd"] = {"events": corr_events}

    return payloads


def _load_structural_artifacts(output_dir: Path) -> dict[str, Any]:
    names = [
        "topology_runtime_graph",
        "runtime_source_correlation",
    ]
    return {name: _read_json(output_dir / f"{name}.json") for name in names}


def _derive_dts_cognition(registry_payload: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    topology_graph = _read_json(output_dir / "dts_topology_graph.json")
    if topology_graph:
        return topology_graph
    return _as_dict(_as_dict(_as_dict(registry_payload.get("semantic_cognition", {})).get("latest", {})).get("adapters", {}).get("dts", {}))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime truth cognition artifacts (offline foundation)")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="runtime_truth_cognition_offline_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_evidence = _derive_runtime_evidence(registry_payload)
    source_payloads = _load_source_payloads(output_dir)
    structural_artifacts = _load_structural_artifacts(output_dir)
    dts_cognition = _derive_dts_cognition(registry_payload, output_dir)

    replay_traces = {
        "deterministic_event_ordering": bool(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("event_ordering_stable", True)
        ),
        "deterministic_replay_fingerprint": str(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get("deterministic_fingerprint", "")
        ),
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

    archived_runtime_lineage = [
        row for row in _as_list(_as_dict(registry_payload.get("runtime_truth_cognition", {})).get("history", [])) if isinstance(row, dict)
    ]

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    engine = RuntimeTruthEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        runtime_evidence=runtime_evidence,
        source_payloads=source_payloads,
        structural_artifacts=structural_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        dts_cognition=dts_cognition,
        archived_runtime_lineage=archived_runtime_lineage,
        evidence_references=[
            "registry://runtime_cognition",
            "registry://governance_state",
            "artifact://runtime_source_correlation",
            "artifact://topology_runtime_graph",
            "offline://synthetic_runtime_sequences",
            "offline://archived_runtime_lineage",
        ],
    )

    store = RuntimeTruthRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.runtime_truth_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_TRUTH_COGNITION_LAYER_OFFLINE_FOUNDATION",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "runtime_truth_fingerprint": result.runtime_truth_bundle.get("runtime_truth_fingerprint", ""),
        "classification": result.runtime_truth_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "runtime_truth_graph": str((output_dir / "runtime_truth_graph.json").resolve()),
            "dapm_transition_trace": str((output_dir / "dapm_transition_trace.json").resolve()),
            "pcm_lifecycle_trace": str((output_dir / "pcm_lifecycle_trace.json").resolve()),
            "soundwire_runtime_graph": str((output_dir / "soundwire_runtime_graph.json").resolve()),
            "irq_timing_report": str((output_dir / "irq_timing_report.json").resolve()),
            "dsp_sync_report": str((output_dir / "dsp_sync_report.json").resolve()),
            "runtime_drift_report": str((output_dir / "runtime_drift_report.json").resolve()),
            "deterministic_runtime_replay": str((output_dir / "deterministic_runtime_replay.json").resolve()),
            "runtime_confidence_score": str((output_dir / "runtime_confidence_score.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "runtime_truth_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
