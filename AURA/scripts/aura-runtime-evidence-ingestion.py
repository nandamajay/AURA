#!/usr/bin/env python3
"""Real Runtime Evidence Ingestion Layer runner."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_evidence_ingestor import RuntimeEvidenceIngestor
from aura_sdk.transport.runtime_session_registry import RuntimeSessionRegistry


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


def _load_lines(path: Path, limit: int = 1200) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:limit]
    except Exception:
        return []
    return [line.rstrip("\n") for line in lines if line.strip()]


def _find_payload(output_dir: Path, candidates: list[str]) -> dict[str, Any]:
    for name in candidates:
        path = output_dir / name
        if not path.exists():
            continue
        if path.suffix.lower() == ".json":
            maybe_json = _read_json(path)
            if isinstance(maybe_json.get("events"), list):
                return {"events": maybe_json.get("events", [])}
            if isinstance(maybe_json.get("lines"), list):
                return {"lines": [str(item) for item in maybe_json.get("lines", [])]}
        lines = _load_lines(path)
        if lines:
            return {"lines": lines}
    return {}


def _load_source_payloads(output_dir: Path) -> dict[str, Any]:
    payloads = {
        "dmesg": _find_payload(output_dir, ["runtime_dmesg.log", "dmesg.log", "kernel.log"]),
        "ftrace": _find_payload(output_dir, ["runtime_ftrace.log", "ftrace.log"]),
        "trace_cmd": _find_payload(output_dir, ["trace_cmd.json", "runtime_trace_cmd.json", "trace_cmd.log"]),
        "perf": _find_payload(output_dir, ["perf_trace.json", "perf_trace.log", "runtime_perf.log"]),
        "tinymix_state": _find_payload(output_dir, ["tinymix_dump.txt", "tinyalsa_dump.txt", "tinymix_state.log"]),
        "procfs_runtime": _find_payload(output_dir, ["procfs_sysfs_runtime.txt", "runtime_procfs_sysfs.txt", "alsa_procfs_state.txt"]),
        "debugfs_runtime": _find_payload(output_dir, ["debugfs_runtime.txt", "runtime_debugfs.txt", "asoc_debugfs.txt"]),
        "soundwire_runtime": _find_payload(output_dir, ["soundwire_debugfs.txt", "runtime_soundwire_debugfs.txt", "soundwire_runtime.log"]),
        "dsp_mailbox": _find_payload(output_dir, ["mailbox_trace.log", "dsp_response.log", "runtime_dsp_response.log"]),
        "irq_runtime": _find_payload(output_dir, ["irq_trace.log", "runtime_irq.log", "irq_timing_trace.log"]),
    }

    # Deterministic offline fallback sources from already generated artifacts.
    if not _as_dict(payloads.get("ftrace")):
        pcm = _read_json(output_dir / "pcm_lifecycle_trace.json")
        lines = []
        for row in _as_list(pcm.get("transitions")):
            item = _as_dict(row)
            ts = float(item.get("timestamp_ms", 0.0) or 0.0) / 1000.0
            lines.append(f"{ts:.3f}: pcm {item.get('stage', 'STATE')}")
        if lines:
            payloads["ftrace"] = {"lines": lines}

    if not _as_dict(payloads.get("trace_cmd")):
        dapm = _read_json(output_dir / "dapm_transition_trace.json")
        events = []
        for row in _as_list(dapm.get("transitions")):
            item = _as_dict(row)
            events.append(
                {
                    "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                    "event_type": "dapm_trace",
                    "detail": str(item.get("transition", "STATE")),
                }
            )
        if events:
            payloads["trace_cmd"] = {"events": events}

    if not _as_dict(payloads.get("dmesg")):
        drift = _read_json(output_dir / "runtime_drift_report.json")
        lines = [
            str(_as_dict(row).get("details", ""))
            for row in _as_list(drift.get("drifts"))
            if str(_as_dict(row).get("details", "")).strip()
        ]
        if lines:
            payloads["dmesg"] = {"lines": lines}

    if not _as_dict(payloads.get("perf")):
        drift = _read_json(output_dir / "runtime_drift_report.json")
        lines = [
            f"perf:{idx}:{str(_as_dict(row).get('type', 'drift'))}"
            for idx, row in enumerate(_as_list(drift.get("drifts")), start=1)
        ]
        if lines:
            payloads["perf"] = {"lines": lines}

    if not _as_dict(payloads.get("tinymix_state")):
        correlation = _read_json(output_dir / "runtime_patch_correlation.json")
        lines = [
            f"{str(_as_dict(row).get('runtime_command', 'mixer_cmd'))}:{str(_as_dict(row).get('correlation_confidence', 0.0))}"
            for row in _as_list(correlation.get("command_patch_mappings"))
        ]
        if lines:
            payloads["tinymix_state"] = {"lines": lines}

    if not _as_dict(payloads.get("procfs_runtime")):
        topology = _read_json(output_dir / "topology_runtime_graph.json")
        routes = _as_list(_as_dict(topology.get("normalized_portable_audio_graph")).get("fe_be_routes"))
        lines = [f"procfs route {item}" for item in routes if str(item).strip()]
        if lines:
            payloads["procfs_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("debugfs_runtime")):
        topology = _read_json(output_dir / "topology_runtime_graph.json")
        lines = [
            str(_as_dict(edge).get("from", "")) + "->" + str(_as_dict(edge).get("to", ""))
            for edge in _as_list(topology.get("edges"))
        ]
        lines = [line for line in lines if line.strip() and line != "->"]
        if lines:
            payloads["debugfs_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("soundwire_runtime")):
        swr = _read_json(output_dir / "soundwire_runtime_graph.json")
        lines = [
            str(_as_dict(node).get("id", ""))
            for node in _as_list(swr.get("nodes"))
            if "swr" in str(_as_dict(node).get("id", "")).lower()
            or "soundwire" in str(_as_dict(node).get("id", "")).lower()
        ]
        if lines:
            payloads["soundwire_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("dsp_mailbox")):
        dsp = _read_json(output_dir / "dsp_sync_report.json")
        lines = [
            f"dsp latency {value}"
            for value in _as_list(dsp.get("pair_latencies_ms"))
        ]
        if lines:
            payloads["dsp_mailbox"] = {"lines": lines}

    if not _as_dict(payloads.get("irq_runtime")):
        irq = _read_json(output_dir / "irq_timing_report.json")
        lines = [
            f"irq {str(_as_dict(row).get('event_id', 'irq'))}"
            for row in _as_list(irq.get("ordered_irq_events"))
        ]
        if lines:
            payloads["irq_runtime"] = {"lines": lines}

    return payloads


def _load_domain_artifacts(output_dir: Path) -> dict[str, Any]:
    return {
        "runtime_truth_graph": _read_json(output_dir / "runtime_truth_graph.json"),
        "topology_cognition": _read_json(output_dir / "topology_runtime_graph.json"),
        "migration_lineage": _read_json(output_dir / "migration_lineage.json"),
        "patch_lineage": _read_json(output_dir / "patch_runtime_lineage.json"),
        "structural_cognition": _read_json(output_dir / "structural_graph.json"),
        "semantic_ontology": _read_json(output_dir / "semantic_ontology.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime evidence ingestion artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="runtime_session_v1")
    parser.add_argument("--lineage-id", default="runtime_evidence_ingestion_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    replay_det = _read_json(output_dir / "aura_replay_determinism_report.json")
    replay_traces = {
        "deterministic_event_ordering": bool(
            _as_dict(replay_det).get("event_ordering_stable", True)
        ),
        "deterministic_replay_fingerprint": str(
            _as_dict(replay_det).get("deterministic_fingerprint", "")
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

    previous_session_history = [
        row
        for row in _as_list(registry_payload.get("runtime_session_lineage"))
        if isinstance(row, dict)
    ]

    source_payloads = _load_source_payloads(output_dir)
    domain_artifacts = _load_domain_artifacts(output_dir)

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    ingestor = RuntimeEvidenceIngestor(plugin_loader=loader)

    result = ingestor.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        session_id=str(args.session_id),
        source_payloads=source_payloads,
        domain_artifacts=domain_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://runtime_truth_cognition",
            "registry://migration_lineage",
            "registry://patch_cognition",
            "artifact://runtime_truth_graph",
            "artifact://topology_runtime_graph",
            "artifact://migration_lineage",
            "artifact://patch_runtime_lineage",
            "artifact://structural_graph",
            "artifact://semantic_ontology",
        ],
        previous_session_history=previous_session_history,
    )

    store = RuntimeSessionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.runtime_evidence_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "REAL_RUNTIME_EVIDENCE_INGESTION_LAYER",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "runtime_evidence_ingestion_fingerprint": result.runtime_evidence_bundle.get(
            "runtime_evidence_ingestion_fingerprint", ""
        ),
        "classification": result.runtime_evidence_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "normalized_runtime_evidence": str((output_dir / "normalized_runtime_evidence.json").resolve()),
            "runtime_session_graph": str((output_dir / "runtime_session_graph.json").resolve()),
            "evidence_capture_lineage": str((output_dir / "evidence_capture_lineage.json").resolve()),
            "subsystem_runtime_state": str((output_dir / "subsystem_runtime_state.json").resolve()),
            "dsp_runtime_trace": str((output_dir / "dsp_runtime_trace.json").resolve()),
            "soundwire_runtime_trace": str((output_dir / "soundwire_runtime_trace.json").resolve()),
            "pcm_runtime_state": str((output_dir / "pcm_runtime_state.json").resolve()),
            "runtime_capture_fingerprint": str((output_dir / "runtime_capture_fingerprint.json").resolve()),
            "deterministic_runtime_session_replay": str(
                (output_dir / "deterministic_runtime_session_replay.json").resolve()
            ),
        },
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "runtime_evidence_ingestion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
