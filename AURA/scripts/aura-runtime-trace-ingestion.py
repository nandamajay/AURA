#!/usr/bin/env python3
"""Run runtime trace ingestion cognition using mocked/offline traces."""

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

from aura_sdk.transport.runtime_trace_ingestion_engine import (
    RuntimeTraceIngestionEngine,
    build_mock_runtime_trace_payloads,
    save_runtime_trace_ingestion,
)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run runtime trace ingestion cognition")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="runtime_trace_ingestion_session_v1")
    parser.add_argument("--lineage-id", default="runtime_trace_ingestion_v1")
    parser.add_argument("--variant", choices=["baseline", "transformed"], default="baseline")
    parser.add_argument(
        "--fixture-dir",
        default="/local/mnt/workspace/AURA_V1/AURA/workspace/aura-sdk/tests/fixtures/runtime_cognition",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fixture_payloads = _load_fixture_payloads(Path(str(args.fixture_dir)), variant=str(args.variant))
    trace_payloads = fixture_payloads if fixture_payloads else build_mock_runtime_trace_payloads(
        transformed=(str(args.variant) == "transformed")
    )

    engine = RuntimeTraceIngestionEngine()
    result = engine.ingest(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=f"{args.lineage_id}_{args.variant}",
        trace_payloads=trace_payloads,
        evidence_references=[
            "artifact://mocked_runtime_traces",
            "artifact://runtime_trace_fixture",
        ],
    ).ingestion_bundle

    artifact_name = f"runtime_trace_ingestion_{args.variant}.json"
    save_runtime_trace_ingestion(output_dir / artifact_name, result)

    normalized_payload = {
        "schema_version": "1.0",
        "report_name": f"normalized_runtime_events_{args.variant}",
        "classification": str(result.get("classification", "UNKNOWN")),
        "events": _as_dict(result).get("events", []),
        "deterministic_fingerprint": str(result.get("deterministic_fingerprint", "")),
    }
    normalized_path = output_dir / f"normalized_runtime_events_{args.variant}.json"
    normalized_path.write_text(json.dumps(normalized_payload, indent=2, sort_keys=True), encoding="utf-8")

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_TRACE_INGESTION",
        "variant": str(args.variant),
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": f"{args.lineage_id}_{args.variant}",
        "classification": str(result.get("classification", "UNKNOWN")),
        "fail_closed_reasons": list(result.get("fail_closed_reasons", [])),
        "artifact_files": {
            "runtime_trace_ingestion": str((output_dir / artifact_name).resolve()),
            "normalized_runtime_events": str(normalized_path.resolve()),
        },
        "summary": _as_dict(result).get("summary", {}),
        "generated_at_epoch": time.time(),
    }
    summary_path = output_dir / f"runtime_trace_ingestion_runner_summary_{args.variant}.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
