from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.cognitive_persistence import (  # noqa: E402
    AURAArtifactIndexEngine,
    AURACognitionBootLoader,
    AURACognitionPortability,
    AURACognitionReplayEngine,
    AURAGovernanceEngine,
    AURAPhaseEngine,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_boot_loader_reconstructs_registry_and_policies(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    out.mkdir()
    runtime_report = out / "runtime_capability_report.json"
    _write_json(
        runtime_report,
        {
            "fingerprint": {
                "environment": {"primary_environment": "Qualcomm Linux"},
                "capabilities": {"supports_amixer": "SUPPORTED"},
                "audio_discovery": {"alsa_topology_cards": [{"card_id": "RB3"}]},
            }
        },
    )
    _write_json(
        out / "rb3gen2_audible_baseline_registry.json",
        {
            "profiles": {
                "audible_25s_speaker_v1": {
                    "profile_id": "audible_25s_speaker_v1",
                    "baseline_profile": {
                        "overlay": "qcs6490-audioreach.dtsi",
                        "pcm": {"signature_sha256": "pcm-a"},
                        "route": {"route_fingerprint": "route-a"},
                    },
                }
            }
        },
    )
    _write_json(out / "rb3gen2_procedural_memory.json", {"successful_wav_assets": ["asset-a"]})
    _write_json(out / "rb3gen2_procedural_memory_lock.json", {"successful_execution_sequence": ["cmd-a"]})
    _write_json(out / "rb3gen2_procedural_route_memory.json", {"runs": [{"run_id": "x"}]})
    _write_json(out / "runtime_confidence_report.json", {"runtime_confidence": 1.0})
    _write_json(out / "topology_confidence_report.json", {"topology_confidence": 0.7})
    _write_json(out / "rb3gen2_regression_fingerprint.json", {"regression_detected": False})
    _write_json(out / "rb3_runtime_procedural_execution_trace.json", {"run_id": "run-1", "classification": "ADVISORY_ONLY"})

    registry_path = out / "aura_cognition_registry.json"
    phase_path = out / "aura_phase_state.json"
    governance_path = out / "aura_governance_state.json"

    boot = AURACognitionBootLoader(
        registry_path=registry_path,
        phase_state_path=phase_path,
        governance_state_path=governance_path,
        output_dir=out,
        runtime_report_path=runtime_report,
        baseline_registry_path=out / "rb3gen2_audible_baseline_registry.json",
        procedural_memory_path=out / "rb3gen2_procedural_memory.json",
        procedural_lock_path=out / "rb3gen2_procedural_memory_lock.json",
        procedural_route_memory_path=out / "rb3gen2_procedural_route_memory.json",
    ).boot()

    assert boot.boot_summary["execution_policies_restored"] is True
    assert boot.registry["cognition_graph"]["nodes"]

    phase = AURAPhaseEngine(boot.phase_state)
    phase.assert_capability("rb3_topology_cognition")
    phase.assert_execution_scope("board:RB3Gen2")

    governance = AURAGovernanceEngine(boot.governance_state)
    governance.assert_action(
        action="rb3_controlled_playback",
        execution_mode="governed_write_approved",
        allow_write_ops=True,
        transport_mode="adb_shell",
    )


def test_phase_and_governance_fail_closed_enforcement() -> None:
    phase = AURAPhaseEngine(
        {
            "enabled_capabilities": ["rb3_playback_execution"],
            "blocked_capabilities": ["capture_workflows"],
            "allowed_execution_scope": ["board:RB3Gen2"],
        }
    )
    phase.assert_capability("rb3_playback_execution")
    try:
        phase.assert_capability("capture_workflows")
        assert False, "expected blocked capability"
    except PermissionError:
        pass

    governance = AURAGovernanceEngine(
        {
            "fail_closed_posture": True,
            "write_policy": "governed_write_approved_only",
            "transport_restrictions": {"allowed_modes": ["adb_shell"], "blocked_modes": ["serial_raw"]},
            "patching_restrictions": {"autonomous_patching_allowed": False, "autonomous_upstream_generation_allowed": False},
            "topology_mutation_restrictions": {"autonomous_topology_rewrite_allowed": False},
        }
    )
    governance.assert_action(
        action="rb3_controlled_playback",
        execution_mode="governed_write_approved",
        allow_write_ops=True,
        transport_mode="adb_shell",
    )
    try:
        governance.assert_action(
            action="topology_mutation_attempt",
            execution_mode="governed_write_approved",
            allow_write_ops=True,
            transport_mode="adb_shell",
        )
        assert False, "expected topology mutation block"
    except PermissionError:
        pass


def test_artifact_index_portability_and_replay(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    out.mkdir()
    (out / "rb3_runtime_procedural_execution_trace.json").write_text("{}", encoding="utf-8")
    (out / "topology_graph.json").write_text("{}", encoding="utf-8")
    (out / "rb3gen2_regression_fingerprint.json").write_text("{}", encoding="utf-8")
    (out / "rb3gen2_baseline_profile_a.json").write_text("{}", encoding="utf-8")
    (out / "procedural_signature.json").write_text("{}", encoding="utf-8")
    (out / "rb3gen2_baseline_evidence_lineage.json").write_text("{}", encoding="utf-8")
    (out / "aura_governance_state.json").write_text("{}", encoding="utf-8")

    index_path = out / "aura_artifact_index.json"
    index = AURAArtifactIndexEngine(index_path=index_path, artifact_root=out).refresh()
    assert index["artifacts"]
    assert AURAArtifactIndexEngine(index_path=index_path, artifact_root=out).search(category="topology_graph")

    baseline_registry = {
        "profiles": {
            "audible_25s_speaker_v1": {
                "baseline_profile": {
                    "overlay": "qcs6490-audioreach.dtsi",
                    "wav_asset": {"sha256": "abc"},
                    "pcm": {"signature_sha256": "pcm-a"},
                    "route": {"route_fingerprint": "route-a"},
                }
            }
        }
    }
    _write_json(out / "rb3gen2_audible_baseline_registry.json", baseline_registry)
    _write_json(out / "rb3gen2_procedural_memory_lock_snapshot.json", {"successful_execution_sequence": ["cmd-1"], "timing_windows": {}})
    _write_json(out / "procedural_route_memory.json", {"runs": []})
    _write_json(out / "aura_phase_state.json", {"enabled_capabilities": ["rb3_playback_execution"]})
    _write_json(out / "aura_governance_state.json", {"fail_closed_posture": True})

    replay = AURACognitionReplayEngine(
        baseline_registry_path=out / "rb3gen2_audible_baseline_registry.json",
        procedural_lock_path=out / "rb3gen2_procedural_memory_lock_snapshot.json",
        procedural_route_memory_path=out / "procedural_route_memory.json",
        phase_state_path=out / "aura_phase_state.json",
        governance_state_path=out / "aura_governance_state.json",
    ).build_known_good_replay()
    assert replay["replay_ready"] is True
    assert replay["execution_sequence"]

    portability = AURACognitionPortability()
    snapshot_path = out / "portable_snapshot.json"
    portability.export_snapshot(
        output_path=snapshot_path,
        registry={"schema_version": "1.0"},
        phase_state={"current_phase": "RB3"},
        governance_state={"fail_closed_posture": True},
        artifact_index=index,
        artifact_root=out,
    )

    imported_root = tmp_path / "imported"
    result = portability.import_snapshot(
        snapshot_path=snapshot_path,
        target_registry_path=imported_root / "aura_cognition_registry.json",
        target_phase_state_path=imported_root / "aura_phase_state.json",
        target_governance_state_path=imported_root / "aura_governance_state.json",
        target_artifact_index_path=imported_root / "aura_artifact_index.json",
        target_artifact_root=imported_root / "ops",
    )
    assert result["status"] == "IMPORTED"
    assert (imported_root / "aura_cognition_registry.json").exists()
