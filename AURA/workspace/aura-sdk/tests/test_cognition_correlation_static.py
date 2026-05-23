from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.cognition_correlation import (  # noqa: E402
    CognitionCorrelationRegistry,
    UnifiedCognitionCorrelationEngine,
)
from aura_sdk.transport.confidence_evolution import evolve_confidence  # noqa: E402
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _domain_inputs() -> dict:
    return {
        "runtime_evidence": {
            "run_id": "run-001",
            "process_success": True,
            "evidence_success": True,
            "playback_completion": True,
            "classification": "ADVISORY_ONLY",
            "evidence_references": ["runtime://trace"],
        },
        "pcm_activity": {
            "pcm_signature": "pcm-signature-1",
            "active_paths": ["MultiMedia1->SPKR"],
            "pcm_entries": [{"name": "MultiMedia1", "direction": "playback"}],
        },
        "mixer_state": {
            "controls": ["WSA RX0 MUX", "WSA RX1 MUX"],
            "active_switches": ["SpkrLeft DAC", "SpkrRight DAC"],
        },
        "topology_cognition": {
            "confidence": {"topology_confidence": 0.76},
            "runtime_route_graph": {"runtime_paths": ["MM1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"]},
            "procedural_route_memory": {
                "backend_activation_orderings": [{"ordering": ["MM1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"]}],
            },
        },
        "dts_cognition": {
            "overlay_inheritance": {"overlay_candidates": ["qcs6490-audioreach.dtsi"]},
            "backend_frontend_mappings": ["MM1->PRIMARY_MI2S_RX"],
            "qcom_audio_routing": ["PRIMARY_MI2S_RX->WSA_SPKR"],
            "soundwire_topology_markers": ["SWRM"],
        },
        "semantic_cognition": {
            "classification": {
                "primary_classification": "partially_portable",
                "scores": {
                    "upstream_friendly": 0.62,
                    "vendor_coupled": 0.31,
                    "governance_risky": 0.2,
                },
            },
            "semantic_fingerprint": "semantic-fp-1",
            "evidence_references": ["semantic://classification"],
            "artifacts": {},
        },
        "replay_traces": {
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "replay-fp-1",
        },
        "regression_history": [
            {
                "run_id": "run-001",
                "regression_detected": False,
                "severity": "LOW",
                "deviations": [],
            }
        ],
        "plugin_capability_state": {
            "supported": True,
            "confidence": 0.9,
        },
        "governance_decisions": {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_mixer_mutation_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
    }


def test_cognition_fusion_determinism(tmp_path: Path) -> None:
    engine = UnifiedCognitionCorrelationEngine(_loader(tmp_path))
    payload = _domain_inputs()

    one = engine.correlate(
        target_id="fake_target_alpha",
        lineage_id="corr-alpha-v1",
        evidence_references=["test://runtime", "test://semantic"],
        previous_confidence_state={"overall_confidence": 0.6, "evidence_completeness": 0.8},
        **payload,
    ).correlation_bundle

    two = engine.correlate(
        target_id="fake_target_alpha",
        lineage_id="corr-alpha-v1",
        evidence_references=["test://runtime", "test://semantic"],
        previous_confidence_state={"overall_confidence": 0.6, "evidence_completeness": 0.8},
        **payload,
    ).correlation_bundle

    assert one["correlation_fingerprint"] == two["correlation_fingerprint"]
    assert one["artifacts"]["unified_cognition_graph"] == two["artifacts"]["unified_cognition_graph"]


def test_causal_lineage_chain_is_present(tmp_path: Path) -> None:
    engine = UnifiedCognitionCorrelationEngine(_loader(tmp_path))
    payload = _domain_inputs()
    bundle = engine.correlate(
        target_id="fake_target_alpha",
        lineage_id="corr-causal-v1",
        evidence_references=["test://causal"],
        previous_confidence_state={},
        **payload,
    ).correlation_bundle

    graph = bundle["artifacts"]["causal_reasoning_graph"]
    relations = {edge["relation"] for edge in graph["edges"]}
    assert "defines_route_graph" in relations
    assert "activates_backend_chain" in relations
    assert "drives_pcm_behavior" in relations
    assert "produces_runtime_evidence" in relations
    assert "updates_regression_confidence" in relations


def test_replay_correlation_determinism(tmp_path: Path) -> None:
    engine = UnifiedCognitionCorrelationEngine(_loader(tmp_path))
    payload = _domain_inputs()
    bundle = engine.correlate(
        target_id="fake_target_alpha",
        lineage_id="corr-replay-v1",
        evidence_references=["test://replay"],
        previous_confidence_state={},
        **payload,
    ).correlation_bundle

    registry = CognitionCorrelationRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="corr-replay-v1")
    replay_two = registry.replay(lineage_id="corr-replay-v1")

    assert persisted["lineage_id"] == "corr-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "cognition_fusion_trace.json").exists()


def test_anomaly_detection_includes_expected_classes(tmp_path: Path) -> None:
    engine = UnifiedCognitionCorrelationEngine(_loader(tmp_path))
    payload = _domain_inputs()
    payload["runtime_evidence"]["process_success"] = True
    payload["topology_cognition"]["confidence"] = {"topology_confidence": 0.1}
    payload["semantic_cognition"]["classification"] = {
        "primary_classification": "vendor_coupled",
        "scores": {"governance_risky": 0.8, "upstream_friendly": 0.1},
    }
    payload["replay_traces"] = {}
    payload["plugin_capability_state"] = {"supported": False, "confidence": 0.1}
    payload["governance_decisions"]["autonomous_patching_allowed"] = True

    bundle = engine.correlate(
        target_id="fake_target_alpha",
        lineage_id="corr-anomaly-v1",
        evidence_references=["test://anomaly"],
        previous_confidence_state={},
        **payload,
    ).correlation_bundle

    report = bundle["artifacts"]["anomaly_correlation_report"]
    codes = {row["code"] for row in report["anomalies"]}
    assert "semantic_runtime_mismatch" in codes
    assert "topology_drift" in codes
    assert "replay_instability" in codes
    assert "governance_violations" in codes
    assert "plugin_capability_inconsistency" in codes


def test_confidence_propagation_prevents_missing_evidence_amplification() -> None:
    result = evolve_confidence(
        runtime_cognition={"confidence": {"runtime_confidence": 1.0}},
        topology_cognition={"confidence": {"topology_confidence": 1.0}},
        semantic_cognition={"classification": {"scores": {"upstream_friendly": 1.0, "governance_risky": 0.0}}},
        replay_traces={"deterministic_event_ordering": True},
        regression_history=[],
        evidence_completeness=0.4,
        mismatch_count=0,
        governance_decisions={
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_mixer_mutation_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
        previous_confidence_state={"overall_confidence": 0.85, "evidence_completeness": 1.0},
    )

    assert result.current_confidence <= 0.85
    assert result.confidence_evolution_report["integrity_guards"]["missing_evidence_never_increases_confidence"] is True


def test_plugin_isolation_correlation_core_has_no_target_branching() -> None:
    correlation_core = (SRC_DIR / "aura_sdk/transport/cognition_correlation.py").read_text(encoding="utf-8").lower()
    contract = (SRC_DIR / "aura_sdk/transport/plugins/contracts.py").read_text(encoding="utf-8")

    assert "if target ==" not in correlation_core
    assert "rb3" not in correlation_core
    assert ".runtime_evidence_adapter(" in correlation_core
    assert ".topology_evidence_adapter(" in correlation_core
    assert ".semantic_evidence_adapter(" in correlation_core

    assert "runtime_evidence_adapter" in contract
    assert "topology_evidence_adapter" in contract
    assert "semantic_evidence_adapter" in contract
