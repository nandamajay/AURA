from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_equivalence_engine import RuntimeEquivalenceEngine  # noqa: E402
from aura_sdk.transport.runtime_fingerprint_engine import RuntimeFingerprintEngine  # noqa: E402
from aura_sdk.transport.runtime_governance_engine import RuntimeGovernanceEngine  # noqa: E402
from aura_sdk.transport.runtime_hardware_truth_graph import RuntimeHardwareTruthGraphBuilder  # noqa: E402
from aura_sdk.transport.runtime_trace_ingestion_engine import (  # noqa: E402
    RuntimeTraceIngestionEngine,
    build_mock_runtime_trace_payloads,
)


def _prepare(transformed: bool) -> tuple[list[dict], dict]:
    ingest = RuntimeTraceIngestionEngine().ingest(
        target_id="fake_target_alpha",
        session_id="runtime-governance-prep",
        lineage_id="runtime-governance-prep",
        trace_payloads=build_mock_runtime_trace_payloads(transformed=transformed),
        evidence_references=["test://runtime_governance/prep"],
    ).ingestion_bundle
    events = list(ingest.get("events", []))
    graph = RuntimeHardwareTruthGraphBuilder().build(
        target_id="fake_target_alpha",
        session_id="runtime-governance-prep",
        lineage_id="runtime-governance-prep",
        normalized_events=events,
        evidence_references=["test://runtime_governance/prep_graph"],
    ).hardware_truth_graph
    return events, graph


def _reports(diverged: bool) -> tuple[dict, dict, dict, dict]:
    base_events, base_graph = _prepare(False)
    tx_events, tx_graph = _prepare(diverged)

    eq = RuntimeEquivalenceEngine().evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-governance-eq",
        lineage_id="runtime-governance-eq",
        baseline_events=base_events,
        transformed_events=tx_events,
        baseline_truth_graph=base_graph,
        transformed_truth_graph=tx_graph,
        evidence_references=["test://runtime_governance/equivalence"],
    )

    fp = RuntimeFingerprintEngine().build(
        target_id="fake_target_alpha",
        session_id="runtime-governance-fp",
        lineage_id="runtime-governance-fp",
        normalized_events=tx_events,
        hardware_truth_graph=tx_graph,
        divergence_report=eq.runtime_divergence_report,
        confidence_report=eq.runtime_confidence_report,
        evidence_references=["test://runtime_governance/fingerprint"],
    )
    return (
        eq.runtime_equivalence_report,
        eq.runtime_divergence_report,
        eq.runtime_confidence_report,
        fp.deterministic_runtime_replay,
    )


def _governance_state() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_upstream_generation_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
    }


def test_runtime_governance_fail_closed_on_runtime_divergence() -> None:
    eq, div, conf, replay = _reports(True)
    result = RuntimeGovernanceEngine().evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-governance-session-a",
        lineage_id="runtime-governance-lineage-a",
        governance_state=_governance_state(),
        runtime_equivalence_report=eq,
        runtime_divergence_report=div,
        runtime_confidence_report=conf,
        deterministic_runtime_replay=replay,
        runtime_sensitive_impact_count=1,
        previous_confidence_history=[0.9, 0.8],
        evidence_references=["test://runtime_governance/fail_closed"],
    )

    decision = result.runtime_governance_decision
    assert decision["classification"] == "FAIL_CLOSED"
    reasons = set(decision["fail_closed_reasons"])
    assert "runtime_confidence_below_threshold" in reasons
    assert "runtime_sensitive_region_instability" in reasons


def test_runtime_governance_pass_on_stable_runtime() -> None:
    eq, div, conf, replay = _reports(False)
    result = RuntimeGovernanceEngine().evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-governance-session-b",
        lineage_id="runtime-governance-lineage-b",
        governance_state=_governance_state(),
        runtime_equivalence_report=eq,
        runtime_divergence_report=div,
        runtime_confidence_report=conf,
        deterministic_runtime_replay=replay,
        runtime_sensitive_impact_count=0,
        previous_confidence_history=[0.98],
        evidence_references=["test://runtime_governance/pass"],
    )

    decision = result.runtime_governance_decision
    assert decision["classification"] == "PASS"
    assert decision["promotion_eligible"] is True
