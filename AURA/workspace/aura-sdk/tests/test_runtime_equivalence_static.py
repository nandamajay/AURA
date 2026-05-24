from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_equivalence_engine import RuntimeEquivalenceEngine  # noqa: E402
from aura_sdk.transport.runtime_hardware_truth_graph import RuntimeHardwareTruthGraphBuilder  # noqa: E402
from aura_sdk.transport.runtime_trace_ingestion_engine import (  # noqa: E402
    RuntimeTraceIngestionEngine,
    build_mock_runtime_trace_payloads,
)


def _ingested_events(transformed: bool) -> list[dict]:
    ingestion = RuntimeTraceIngestionEngine()
    bundle = ingestion.ingest(
        target_id="fake_target_alpha",
        session_id="runtime-eq-ingest",
        lineage_id="runtime-eq-lineage",
        trace_payloads=build_mock_runtime_trace_payloads(transformed=transformed),
        evidence_references=["test://runtime_equivalence/ingestion"],
    ).ingestion_bundle
    return list(bundle.get("events", []))


def _truth(events: list[dict], suffix: str) -> dict:
    builder = RuntimeHardwareTruthGraphBuilder()
    graphs = builder.build(
        target_id="fake_target_alpha",
        session_id="runtime-eq-session",
        lineage_id=f"runtime-eq-{suffix}",
        normalized_events=events,
        evidence_references=[f"test://runtime_equivalence/{suffix}"],
    )
    return graphs.hardware_truth_graph


def test_runtime_equivalence_detects_divergence() -> None:
    base_events = _ingested_events(False)
    tx_events = _ingested_events(True)

    engine = RuntimeEquivalenceEngine()
    result = engine.evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-eq-session-a",
        lineage_id="runtime-eq-lineage-a",
        baseline_events=base_events,
        transformed_events=tx_events,
        baseline_truth_graph=_truth(base_events, "base"),
        transformed_truth_graph=_truth(tx_events, "tx"),
        evidence_references=["test://runtime_equivalence/divergence"],
    )

    assert result.runtime_divergence_report["classification"] == "FAIL_CLOSED"
    assert result.runtime_confidence_report["classification"] == "FAIL_CLOSED"
    assert result.runtime_confidence_report["confidence_score"] < 0.75


def test_runtime_equivalence_pass_when_sequences_match() -> None:
    base_events = _ingested_events(False)

    engine = RuntimeEquivalenceEngine()
    result = engine.evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-eq-session-b",
        lineage_id="runtime-eq-lineage-b",
        baseline_events=base_events,
        transformed_events=base_events,
        baseline_truth_graph=_truth(base_events, "base-pass"),
        transformed_truth_graph=_truth(base_events, "tx-pass"),
        evidence_references=["test://runtime_equivalence/pass"],
    )

    assert result.runtime_equivalence_report["classification"] == "PASS"
    assert result.runtime_divergence_report["classification"] == "PASS"
    assert result.runtime_confidence_report["classification"] == "PASS"
    assert result.runtime_confidence_report["confidence_score"] >= 0.99
