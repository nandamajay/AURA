from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_trace_ingestion_engine import (  # noqa: E402
    RuntimeTraceIngestionEngine,
    build_mock_runtime_trace_payloads,
)


def _load_fixture_payloads() -> dict[str, dict[str, list[str]]]:
    fixture_dir = Path(__file__).resolve().parent / "fixtures" / "runtime_cognition"
    keys = [
        "dmesg",
        "ftrace",
        "trace_cmd",
        "tinymix",
        "procfs",
        "debugfs",
        "soundwire",
        "dsp_mailbox",
        "irq",
        "clock",
        "regulator",
    ]
    payloads: dict[str, dict[str, list[str]]] = {}
    for key in keys:
        path = fixture_dir / f"baseline_{'tinymix.txt' if key == 'tinymix' else key + ('.txt' if key in {'procfs', 'debugfs'} else '.log')}"
        if not path.exists():
            path = fixture_dir / f"{key}.log"
        if not path.exists() and key in {"procfs", "debugfs", "tinymix"}:
            path = fixture_dir / f"{key}.txt"
        lines = []
        if path.exists():
            lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        if lines:
            payloads[key] = {"lines": lines}
    return payloads


def test_runtime_trace_ingestion_deterministic(tmp_path: Path) -> None:
    engine = RuntimeTraceIngestionEngine()
    payloads = build_mock_runtime_trace_payloads(transformed=False)

    first = engine.ingest(
        target_id="fake_target_alpha",
        session_id="runtime-ingest-session-a",
        lineage_id="runtime-ingest-lineage-a",
        trace_payloads=payloads,
        evidence_references=["test://runtime_trace_ingestion/deterministic"],
    ).ingestion_bundle
    second = engine.ingest(
        target_id="fake_target_alpha",
        session_id="runtime-ingest-session-a",
        lineage_id="runtime-ingest-lineage-a",
        trace_payloads=payloads,
        evidence_references=["test://runtime_trace_ingestion/deterministic"],
    ).ingestion_bundle

    assert first["classification"] == "PASS"
    assert first["deterministic_fingerprint"] == second["deterministic_fingerprint"]
    assert len(first["events"]) > 0

    out = tmp_path / "runtime_trace_ingestion.json"
    out.write_text(json.dumps(first, indent=2, sort_keys=True), encoding="utf-8")
    assert out.exists()


def test_runtime_trace_ingestion_fixture_payloads_present() -> None:
    engine = RuntimeTraceIngestionEngine()
    payloads = _load_fixture_payloads()

    bundle = engine.ingest(
        target_id="fake_target_alpha",
        session_id="runtime-ingest-session-fixture",
        lineage_id="runtime-ingest-lineage-fixture",
        trace_payloads=payloads,
        evidence_references=["test://runtime_trace_ingestion/fixture"],
    ).ingestion_bundle

    assert bundle["classification"] == "PASS"
    assert bundle["summary"]["event_count"] >= 20


def test_runtime_trace_ingestion_fail_closed_on_missing_sources() -> None:
    engine = RuntimeTraceIngestionEngine()
    payloads = {
        "dmesg": {"lines": ["[1.0] boot"]},
        "ftrace": {"lines": ["1.1: pcm open"]},
    }

    bundle = engine.ingest(
        target_id="fake_target_alpha",
        session_id="runtime-ingest-session-missing",
        lineage_id="runtime-ingest-lineage-missing",
        trace_payloads=payloads,
        evidence_references=["test://runtime_trace_ingestion/missing"],
    ).ingestion_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "runtime_trace_source_incomplete" in set(bundle["fail_closed_reasons"])
    assert bundle["summary"]["missing_source_count"] > 0
