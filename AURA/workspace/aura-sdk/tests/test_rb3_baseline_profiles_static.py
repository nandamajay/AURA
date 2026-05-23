from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.rb3_baseline_profiles import (
    RB3BaselineProfileRegistry,
    RB3ProceduralMemoryLock,
    build_runtime_regression_comparison,
)


def _runtime_profile(*, pcm_sig: str, route_sig: str, timeout_count: int = 0) -> dict:
    return {
        "run_id": "run-x",
        "board": "RB3Gen2",
        "overlay": "qcs6490-audioreach.dtsi",
        "pcm": {
            "alsa_device": "hw:0,0",
            "pcm_id": "00-00",
            "signature_sha256": pcm_sig,
        },
        "route": {
            "route_dependencies": ["MultiMedia1->PRIMARY_MI2S_RX"],
            "route_fingerprint": route_sig,
            "route_activation_confidence": "HIGH",
        },
        "wav_asset": {
            "asset_id": "rb3_speaker_48k_stereo_v1",
            "sha256": "abc",
            "duration_seconds": 25.0,
        },
        "runtime_timing": {
            "total_runtime_seconds": 35.0,
            "playback_runtime_seconds": 25.1,
        },
        "transport": {
            "timeout_count": timeout_count,
        },
        "evidence": {
            "missing_evidence": [],
            "evidence_quality": "HIGH",
        },
        "final_classification": "CAPTURE_READY",
    }


def test_baseline_registry_lock_and_confidence(tmp_path: Path) -> None:
    registry = RB3BaselineProfileRegistry(tmp_path / "baseline_registry.json")
    profile = _runtime_profile(pcm_sig="pcm-a", route_sig="route-a")
    regression = build_runtime_regression_comparison(profile, None)

    result = registry.record_run(
        profile_id="audible_25s_speaker_v1",
        profile_version=1,
        run_id="run-1",
        runtime_profile=profile,
        regression=regression,
        evidence_lineage={"request_ids": ["req-1"]},
        process_success=True,
        evidence_success=True,
        audible_status="confirmed",
    )

    assert result.baseline_locked is True
    assert result.profile["state"] == "LOCKED"
    assert result.profile["baseline_profile"]["pcm"]["signature_sha256"] == "pcm-a"
    assert result.profile["confidence"]["score"] > 0.0


def test_regression_detects_pcm_and_transport_drift() -> None:
    baseline = _runtime_profile(pcm_sig="pcm-a", route_sig="route-a", timeout_count=0)
    current = _runtime_profile(pcm_sig="pcm-b", route_sig="route-a", timeout_count=2)
    current["runtime_timing"]["total_runtime_seconds"] = 50.0

    regression = build_runtime_regression_comparison(current, baseline)
    codes = {item["code"] for item in regression["deviations"]}
    assert regression["regression_detected"] is True
    assert "pcm_change" in codes
    assert "transport_degradation" in codes
    assert "runtime_latency_drift" in codes


def test_procedural_memory_lock_records_sequence(tmp_path: Path) -> None:
    lock = RB3ProceduralMemoryLock(tmp_path / "procedural_lock.json")

    snapshot = lock.record_run(
        run_id="run-2",
        profile_id="audible_25s_speaker_v1",
        successful_sequence=["AURA_ADB_PUSH x y z allow_overwrite", "AURA_PLAYBACK_APLAY plughw:0,0 /tmp/a.wav"],
        command_ordering=["AURA_ADB_PUSH x y z allow_overwrite", "AURA_PLAYBACK_APLAY plughw:0,0 /tmp/a.wav"],
        cleanup_ordering=["AURA_ADB_RM /tmp/a.wav"],
        evidence_sequence=["cat /proc/asound/cards", "cat /proc/asound/pcm"],
        timing_windows={
            "total_runtime_seconds": 40.0,
            "playback_runtime_seconds": 25.0,
            "cleanup_runtime_seconds": 1.0,
            "evidence_collection_runtime_seconds": 7.0,
        },
        degradation_decisions=[],
        process_success=True,
        evidence_success=True,
        audible_status="confirmed",
    )

    assert snapshot["lock_revision"] == 1
    assert snapshot["locked_profile_id"] == "audible_25s_speaker_v1"
    assert snapshot["successful_execution_sequence"]
    assert snapshot["timing_windows"]["playback_runtime_seconds"]["last_seconds"] == 25.0

