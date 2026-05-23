from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.agentization import AURAInternalAgentizationCoordinator  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_agentization_coordinator_generates_artifacts(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    out.mkdir(parents=True, exist_ok=True)

    _write(out / "runtime_capability_report.json", {"fingerprint": {"environment": {"primary_environment": "Qualcomm Linux"}}})
    _write(out / "rb3gen2_audible_baseline_registry.json", {"profiles": {"audible_25s_speaker_v1": {"baseline_profile": {"overlay": "qcs6490-audioreach.dtsi"}}}})
    _write(out / "rb3gen2_procedural_memory.json", {"history": []})
    _write(out / "rb3gen2_procedural_memory_lock.json", {"successful_execution_sequence": ["cmd-a"], "command_ordering": ["cmd-a"]})
    _write(out / "rb3gen2_procedural_route_memory.json", {"runs": []})
    _write(out / "runtime_confidence_report.json", {"runtime_confidence": 1.0})
    _write(out / "topology_confidence_report.json", {"topology_state": "INFERRED", "topology_confidence": 0.7})
    _write(out / "rb3gen2_regression_fingerprint.json", {"regression_detected": False, "severity": "NONE"})
    _write(out / "playback_drift_report.json", {"playback_timing_drift_detected": False, "route_instability_detected": False})
    _write(out / "rb3_runtime_procedural_execution_trace.json", {"process_success": True, "evidence_success": True, "classification": "ADVISORY_ONLY"})
    _write(out / "rb3_runtime_validation_correlation_live.json", {"route_activation_confidence": "HIGH", "playback_completion": True})
    _write(out / "runtime_route_graph.json", {"runtime_activation": {"runtime_state_transitions": ["playback_started"]}})
    _write(out / "topology_graph.json", {"nodes": [{"id": "n1"}], "edges": [{"from": "n1", "to": "n1"}]})

    coordinator = AURAInternalAgentizationCoordinator(
        output_dir=out,
        cognition_registry_path=out / "aura_cognition_registry.json",
        phase_state_path=out / "aura_phase_state.json",
        governance_state_path=out / "aura_governance_state.json",
        baseline_registry_path=out / "rb3gen2_audible_baseline_registry.json",
        procedural_memory_path=out / "rb3gen2_procedural_memory.json",
        procedural_lock_path=out / "rb3gen2_procedural_memory_lock.json",
        procedural_route_memory_path=out / "rb3gen2_procedural_route_memory.json",
        runtime_report_path=out / "runtime_capability_report.json",
        artifact_index_path=out / "aura_artifact_index.json",
        portable_snapshot_path=out / "aura_cognition_portable_snapshot.json",
    )
    result = coordinator.run_cycle()
    paths = coordinator.export_architecture_artifacts(result)

    assert result.agent_runtime["active_agents"]
    assert "runtime_agent" in result.agent_runtime["agent_health"]
    assert result.state_machine["current_state"] in {
        "governance_validated",
        "runtime_validated",
        "topology_validated",
        "regression_evaluated",
        "persistence_synced",
    }
    assert result.inter_agent_protocol["messages"]
    assert result.cognition_versioning["component_versions"]["runtime_agent"] == "1.0.0"
    for value in paths.values():
        assert Path(value).exists()
