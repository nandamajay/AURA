from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.rb3_topology_cognition import (  # noqa: E402
    RB3ProceduralRouteMemory,
    build_rb3_topology_cognition,
)


def _phase_trace() -> list[dict]:
    return [
        {
            "phase": "pre_runtime_snapshot",
            "snapshot_command": "cat /proc/asound/cards",
            "skipped": False,
            "response": {"executor_command_trace": [{"normalized_command": "cat /proc/asound/cards"}]},
        },
        {
            "phase": "pre_runtime_snapshot",
            "snapshot_command": "cat /proc/asound/pcm",
            "skipped": False,
            "response": {"executor_command_trace": [{"normalized_command": "cat /proc/asound/pcm"}]},
        },
        {
            "phase": "pcm_playback",
            "response": {
                "executor_command_trace": [
                    {
                        "normalized_command": "AURA_PLAYBACK_APLAY plughw:0,0 /data/local/tmp/aura/audio/speaker_validation.wav"
                    }
                ]
            },
        },
        {
            "phase": "cleanup",
            "response": {"executor_command_trace": [{"normalized_command": "AURA_ADB_RM /data/local/tmp/aura/audio/speaker_validation.wav"}]},
        },
    ]


def test_topology_cognition_generates_graphs_and_confidence(tmp_path: Path) -> None:
    base_dts = tmp_path / "qcs6490-rb3gen2.dts"
    overlay_dtsi = tmp_path / "qcs6490-audioreach.dtsi"
    overlay_dtsi.write_text(
        """
        &sound {
            qcom,audio-routing =
                "MultiMedia1", "PRIMARY_MI2S_RX",
                "PRIMARY_MI2S_RX", "WSA_SPKR";
            dai-link@0 { link-name = "MultiMedia1"; };
        };
        """,
        encoding="utf-8",
    )
    base_dts.write_text(
        """
        /dts-v1/;
        #include "qcs6490-audioreach.dtsi"
        / {
            model = "RB3Gen2";
        };
        """,
        encoding="utf-8",
    )

    static_context = {
        "entry_dts": str(base_dts),
        "source_files": [str(base_dts), str(overlay_dtsi)],
        "include_graph": [{"from": str(base_dts), "include": str(overlay_dtsi)}],
        "sound_card_nodes": [{"node": "sound", "model": "RB3"}],
        "dai_links": ["dai-link@0 { link-name = \"MultiMedia1\"; };"],
        "backend_frontend_mappings": [{"frontend": "MultiMedia1", "backend": "PRIMARY_MI2S_RX"}],
        "qcom_audio_routing": [
            {"source": "MultiMedia1", "sink": "PRIMARY_MI2S_RX"},
            {"source": "PRIMARY_MI2S_RX", "sink": "WSA_SPKR"},
        ],
        "soundwire_topology_markers": ["wsa"],
        "codec_nodes": [{"node": "codec_a", "compatible": "qcom,wcd937x"}],
        "overlay_inheritance": {"overlay_candidates": ["qcs6490-audioreach.dtsi"], "ambiguous": False},
        "widgets": ["SpkrLeft DAC"],
    }
    workflow = {
        "pcm_inference": {"alsa_device": "hw:0,0"},
        "mixer_dependency": {"route_dependencies": ["MultiMedia1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"]},
        "playback_workflow": {
            "playback_alsa_device": "plughw:0,0",
            "mixer_apply_commands": [
                "AURA_AMIXER_NAME_SET U3BrckxlZnQgUEEgVm9sdW1l 20",
                "AURA_AMIXER_NAME_SET V1NBIFJYMCBNVVg AIF1_PB",
            ],
        },
    }
    runtime_evidence = {
        "pcm_before": "00-00: MultiMedia1 : Primary MI2S : playback 1",
        "pcm_after": "00-00: MultiMedia1 : Primary MI2S : playback 1",
        "mixer_before": "Simple mixer control 'SpkrLeft DAC',0",
        "mixer_after": "Simple mixer control 'SpkrLeft DAC',0\nSimple mixer control 'SpkrRight DAC',0",
        "snapshot_skipped_commands": [],
    }
    runtime_correlation = {
        "pcm_activation": True,
        "backend_activity": True,
        "soundwire_activity": True,
        "playback_completion": True,
        "playback_started": True,
        "route_activation_confidence": "HIGH",
    }
    profile_payload = {
        "pcm": {"signature_sha256": "pcm-a"},
        "route": {"route_fingerprint": "route-a"},
        "runtime_timing": {"playback_runtime_seconds": 25.9},
    }
    baseline_profile = {
        "pcm": {"signature_sha256": "pcm-a"},
        "route": {"route_fingerprint": "route-a"},
        "runtime_timing": {"playback_runtime_seconds": 25.8},
    }
    procedural_lock = {
        "command_ordering": [
            "cat /proc/asound/cards",
            "cat /proc/asound/pcm",
            "AURA_PLAYBACK_APLAY plughw:0,0 /data/local/tmp/aura/audio/speaker_validation.wav",
            "AURA_ADB_RM /data/local/tmp/aura/audio/speaker_validation.wav",
        ],
        "evidence_collection_sequence": ["cat /proc/asound/cards", "cat /proc/asound/pcm"],
    }

    result = build_rb3_topology_cognition(
        run_id="run-1",
        entry_dts=base_dts,
        static_context=static_context,
        workflow=workflow,
        runtime_evidence=runtime_evidence,
        runtime_correlation=runtime_correlation,
        phase_trace=_phase_trace(),
        profile_payload=profile_payload,
        baseline_profile=baseline_profile,
        procedural_lock=procedural_lock,
    )

    assert result.topology_graph["nodes"]
    assert result.runtime_route_graph["runtime_activation"]["runtime_state_transitions"]
    assert "overlay_mutation_delta" in result.overlay_mutation_graph
    assert "correlated_chains" in result.pcm_backend_correlation
    assert result.playback_route_trace["deterministic_alignment"]["baseline_pcm_match"] is True
    assert "topology_confidence" in result.topology_confidence_report


def test_topology_low_confidence_enables_targeted_interrogation(tmp_path: Path) -> None:
    dts = tmp_path / "rb3.dts"
    dts.write_text("/dts-v1/;/ { model = \"RB3\"; };", encoding="utf-8")
    static_context = {
        "entry_dts": str(dts),
        "source_files": [str(dts)],
        "include_graph": [],
        "sound_card_nodes": [],
        "dai_links": [],
        "backend_frontend_mappings": [],
        "qcom_audio_routing": [],
        "soundwire_topology_markers": [],
        "codec_nodes": [],
        "overlay_inheritance": {"overlay_candidates": ["a.dtsi", "b.dtsi"], "ambiguous": True},
        "widgets": [],
    }
    workflow = {"pcm_inference": {"alsa_device": "UNKNOWN"}, "mixer_dependency": {"route_dependencies": []}, "playback_workflow": {}}
    runtime_correlation = {"playback_completion": False, "playback_started": False, "route_activation_confidence": "LOW"}

    result = build_rb3_topology_cognition(
        run_id="run-2",
        entry_dts=dts,
        static_context=static_context,
        workflow=workflow,
        runtime_evidence={},
        runtime_correlation=runtime_correlation,
        phase_trace=[],
        profile_payload={"pcm": {"signature_sha256": "x"}, "route": {"route_fingerprint": "y"}, "runtime_timing": {}},
        baseline_profile=None,
        procedural_lock=None,
    )

    assert result.topology_confidence_report["targeted_interrogation_mode"] is True
    assert result.topology_confidence_report["targeted_questions"]


def test_procedural_route_memory_roundtrip(tmp_path: Path) -> None:
    memory = RB3ProceduralRouteMemory(tmp_path / "route_memory.json")
    snapshot = memory.record_run(
        run_id="run-3",
        profile_id="audible_25s_speaker_v1",
        overlay="qcs6490-audioreach.dtsi",
        process_success=True,
        evidence_success=True,
        topology_state="CONFIRMED",
        topology_confidence=0.93,
        pcm_signature="pcm-1",
        route_fingerprint="route-1",
        successful_playback_route=["MultiMedia1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"],
        backend_activation_ordering=["MultiMedia1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"],
        mixer_dependency_chains=["SpkrLeft DAC", "SpkrRight DAC"],
        runtime_evidence_pattern={"playback_completion": True, "backend_activity": True},
        overlay_mutation_delta={"added_routes": ["MultiMedia1->PRIMARY_MI2S_RX"]},
        deterministic_alignment={"baseline_pcm_match": True, "baseline_route_match": True},
    )

    assert snapshot["stable_pcm_fingerprints"] == ["pcm-1"]
    assert snapshot["stable_route_fingerprints"] == ["route-1"]
    assert snapshot["successful_playback_routes"]
