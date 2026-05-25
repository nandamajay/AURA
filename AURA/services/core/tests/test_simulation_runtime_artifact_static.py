"""Runtime-artifact-backed simulation static validation."""

from __future__ import annotations

import json
from pathlib import Path

from aura_sdk.models.simulation import FidelityMode, SimulationStatus, SimulationType
from core.routers.simulation import _artifact_backed_simulation_result


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_runtime_artifacts(root: Path) -> None:
    _write_json(
        root / "runtime_governance_decision.json",
        {
            "classification": "PASS",
            "deterministic_fingerprint": "g" * 64,
        },
    )
    _write_json(
        root / "runtime_equivalence_report.json",
        {
            "classification": "PASS",
            "deterministic_fingerprint": "e" * 64,
            "dimensions": [
                {"dimension": "soundwire_topology_mismatch", "classification": "EQUIVALENT"},
                {"dimension": "pcm_transition_inconsistency", "classification": "EQUIVALENT"},
                {"dimension": "dsp_sequence_instability", "classification": "EQUIVALENT"},
                {"dimension": "irq_divergence", "classification": "EQUIVALENT"},
            ],
        },
    )
    _write_json(
        root / "runtime_confidence_report.json",
        {
            "classification": "PASS",
            "confidence_score": 0.92,
            "deterministic_fingerprint": "c" * 64,
        },
    )
    _write_json(
        root / "hardware_truth_graph.json",
        {
            "deterministic_fingerprint": "h" * 64,
            "nodes": {
                "pcm_lifecycle": [{"message": "pcm start", "timestamp_ms": 1000.0}],
                "dapm_routes": [{"message": "route enable", "timestamp_ms": 1010.0}],
                "soundwire_links": [{"node": "swr0 active", "timestamp_ms": 1020.0}],
                "dsp_events": [{"message": "dsp sync", "timestamp_ms": 1030.0}],
                "mailbox_synchronization": [{"mailbox_event": "graph_ack", "timestamp_ms": 1040.0}],
                "irq_ordering": [{"message": "irq handled", "timestamp_ms": 1050.0}],
                "clock_sequence": [{"message": "clk enabled", "timestamp_ms": 1060.0}],
                "regulator_sequence": [{"message": "vdd enabled", "timestamp_ms": 1070.0}],
                "fe_be_links": [{"from": "FE0", "to": "BE0"}],
            },
        },
    )
    _write_json(
        root / "deterministic_runtime_replay.json",
        {
            "deterministic_fingerprint": "r" * 64,
            "replay_signal": {"deterministic_event_ordering": True},
        },
    )
    _write_json(
        root / "runtime_equivalence_fingerprint.json",
        {
            "deterministic_fingerprint": "f" * 64,
            "dimensions": {
                "pcm_lifecycle_order": ["open", "start", "stop"],
            },
        },
    )
    _write_json(root / "runtime_path_graph.json", {"edges": [{"from": "DAPM", "to": "ROUTE"}]})
    _write_json(root / "ipc_topology_map.json", {"summary": {"ipc_event_count": 2}})


def test_artifact_backed_simulation_passes_with_runtime_evidence(tmp_path: Path, monkeypatch) -> None:
    transport = tmp_path / "transport"
    _seed_runtime_artifacts(transport)
    monkeypatch.setenv("AURA_TRANSPORT_ARTIFACT_ROOT", str(transport))

    status, findings, predictions, confidence_impact, _duration = _artifact_backed_simulation_result(
        SimulationType.DAPM,
        FidelityMode.STATE_MACHINE,
    )
    assert status == SimulationStatus.PASSED
    assert findings["governance_classification"] == "PASS"
    assert predictions == []
    assert confidence_impact > 0.0


def test_artifact_backed_simulation_fails_closed_when_artifacts_missing(
    tmp_path: Path, monkeypatch
) -> None:
    transport = tmp_path / "transport"
    transport.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AURA_TRANSPORT_ARTIFACT_ROOT", str(transport))

    status, _findings, predictions, confidence_impact, _duration = _artifact_backed_simulation_result(
        SimulationType.DSP,
        FidelityMode.STATE_MACHINE,
    )
    assert status == SimulationStatus.FAILED
    assert "runtime_artifact_missing" in predictions
    assert confidence_impact < 0.0
