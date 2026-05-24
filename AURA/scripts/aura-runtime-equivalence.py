#!/usr/bin/env python3
"""Run runtime cognition equivalence pipeline using offline/mock traces."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_equivalence_engine import RuntimeEquivalenceEngine
from aura_sdk.transport.runtime_fingerprint_engine import RuntimeFingerprintEngine
from aura_sdk.transport.runtime_hardware_truth_graph import RuntimeHardwareTruthGraphBuilder
from aura_sdk.transport.runtime_trace_ingestion_engine import RuntimeTraceIngestionEngine, build_mock_runtime_trace_payloads


_SOURCE_FILES = {
    "dmesg": "dmesg.log",
    "ftrace": "ftrace.log",
    "trace_cmd": "trace_cmd.log",
    "tinymix": "tinymix.txt",
    "procfs": "procfs.txt",
    "debugfs": "debugfs.txt",
    "soundwire": "soundwire.log",
    "dsp_mailbox": "dsp_mailbox.log",
    "irq": "irq.log",
    "clock": "clock.log",
    "regulator": "regulator.log",
}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
    except Exception:
        return []


def _load_fixture_payloads(fixture_dir: Path, *, variant: str) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    prefix = "baseline" if variant == "baseline" else "transformed"
    for key, name in _SOURCE_FILES.items():
        preferred = fixture_dir / f"{prefix}_{name}"
        fallback = fixture_dir / name
        lines = _read_lines(preferred)
        if not lines:
            lines = _read_lines(fallback)
        if lines:
            payloads[key] = {"lines": lines}
    return payloads


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run runtime equivalence cognition")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="runtime_equivalence_session_v1")
    parser.add_argument("--lineage-id", default="runtime_equivalence_v1")
    parser.add_argument(
        "--fixture-dir",
        default="/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/tests/fixtures/runtime_cognition",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fixture_dir = Path(str(args.fixture_dir))
    baseline_payload = _load_fixture_payloads(fixture_dir, variant="baseline")
    transformed_payload = _load_fixture_payloads(fixture_dir, variant="transformed")
    if not baseline_payload:
        baseline_payload = build_mock_runtime_trace_payloads(transformed=False)
    if not transformed_payload:
        transformed_payload = build_mock_runtime_trace_payloads(transformed=True)

    ingestion = RuntimeTraceIngestionEngine()
    baseline_ingested = ingestion.ingest(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=f"{args.lineage_id}_baseline",
        trace_payloads=baseline_payload,
        evidence_references=["artifact://mock_runtime_baseline"],
    ).ingestion_bundle
    transformed_ingested = ingestion.ingest(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=f"{args.lineage_id}_transformed",
        trace_payloads=transformed_payload,
        evidence_references=["artifact://mock_runtime_transformed"],
    ).ingestion_bundle

    graph_builder = RuntimeHardwareTruthGraphBuilder()
    baseline_graphs = graph_builder.build(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=f"{args.lineage_id}_baseline",
        normalized_events=list(_as_dict(baseline_ingested).get("events", [])),
        evidence_references=["artifact://baseline_runtime_trace_ingestion"],
    )
    transformed_graphs = graph_builder.build(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=f"{args.lineage_id}_transformed",
        normalized_events=list(_as_dict(transformed_ingested).get("events", [])),
        evidence_references=["artifact://transformed_runtime_trace_ingestion"],
    )

    eq_engine = RuntimeEquivalenceEngine()
    equivalence = eq_engine.evaluate(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        baseline_events=list(_as_dict(baseline_ingested).get("events", [])),
        transformed_events=list(_as_dict(transformed_ingested).get("events", [])),
        baseline_truth_graph=baseline_graphs.hardware_truth_graph,
        transformed_truth_graph=transformed_graphs.hardware_truth_graph,
        evidence_references=[
            "artifact://baseline_hardware_truth_graph",
            "artifact://transformed_hardware_truth_graph",
        ],
    )

    fp_engine = RuntimeFingerprintEngine()
    fingerprints = fp_engine.build(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        normalized_events=list(_as_dict(transformed_ingested).get("events", [])),
        hardware_truth_graph=transformed_graphs.hardware_truth_graph,
        divergence_report=equivalence.runtime_divergence_report,
        confidence_report=equivalence.runtime_confidence_report,
        evidence_references=[
            "artifact://runtime_divergence_report",
            "artifact://runtime_confidence_report",
        ],
    )

    _write_json(output_dir / "runtime_equivalence_report.json", equivalence.runtime_equivalence_report)
    _write_json(output_dir / "runtime_divergence_report.json", equivalence.runtime_divergence_report)
    _write_json(output_dir / "runtime_confidence_report.json", equivalence.runtime_confidence_report)
    _write_json(output_dir / "hardware_truth_graph.json", transformed_graphs.hardware_truth_graph)
    _write_json(output_dir / "ipc_topology_map.json", transformed_graphs.ipc_topology_map)
    _write_json(output_dir / "runtime_path_graph.json", transformed_graphs.runtime_path_graph)
    _write_json(output_dir / "runtime_equivalence_fingerprint.json", fingerprints.runtime_equivalence_fingerprint)
    _write_json(output_dir / "deterministic_runtime_replay.json", fingerprints.deterministic_runtime_replay)

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_EQUIVALENCE",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": str(_as_dict(equivalence.runtime_confidence_report).get("classification", "UNKNOWN")),
        "confidence_score": float(_as_dict(equivalence.runtime_confidence_report).get("confidence_score", 0.0)),
        "fail_closed_reasons": list(_as_dict(equivalence.runtime_confidence_report).get("fail_closed_reasons", [])),
        "artifact_files": {
            "runtime_equivalence_fingerprint": str((output_dir / "runtime_equivalence_fingerprint.json").resolve()),
            "runtime_divergence_report": str((output_dir / "runtime_divergence_report.json").resolve()),
            "hardware_truth_graph": str((output_dir / "hardware_truth_graph.json").resolve()),
            "ipc_topology_map": str((output_dir / "ipc_topology_map.json").resolve()),
            "runtime_confidence_report": str((output_dir / "runtime_confidence_report.json").resolve()),
            "deterministic_runtime_replay": str((output_dir / "deterministic_runtime_replay.json").resolve()),
        },
        "generated_at_epoch": time.time(),
    }
    _write_json(output_dir / "runtime_equivalence_runner_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
