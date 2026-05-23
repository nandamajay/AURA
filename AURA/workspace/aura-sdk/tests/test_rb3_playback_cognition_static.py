from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.rb3_playback_cognition import (
    RB3ProceduralMemory,
    build_audio_route_knowledge_graph,
    build_playback_state_machine,
    build_rb3_speaker_playback_plan,
    correlate_runtime_evidence,
    explain_playback_failure,
)
from aura_sdk.transport.command_planner import build_rb3_speaker_workflow


def _fingerprint() -> dict:
    return {
        "capabilities": {
            "supports_tinymix": "SUPPORTED",
            "supports_debugfs": "SUPPORTED",
        },
        "audio_discovery": {
            "alsa_topology_cards": [
                {
                    "card_index": 0,
                    "card_id": "QCS6490RB3Gen2",
                    "descriptor": "qcs6490 - QCS6490-RB3Gen2",
                }
            ],
            "pcm_entries": [
                {
                    "pcm_id": "00-00",
                    "name": "MultiMedia1",
                    "interface": "Primary MI2S",
                    "direction": "playback",
                    "streams": 1,
                }
            ],
        },
    }


def _static_context() -> dict:
    return {
        "overlay_inheritance": {
            "overlay_candidates": ["qcs6490-audioreach.dtsi"],
            "ambiguous": False,
        },
        "qcom_audio_routing": [
            {"source": "MultiMedia1", "sink": "PRIMARY_MI2S_RX"},
            {"source": "PRIMARY_MI2S_RX", "sink": "WSA_SPKR"},
        ],
        "backend_frontend_mappings": [
            {"frontend": "MultiMedia1", "backend": "PRIMARY_MI2S_RX"}
        ],
        "soundwire_topology_markers": ["wsa", "rx_macro"],
        "codec_nodes": [{"node": "codec_a", "compatible": "qcom,wcd937x"}],
    }


def test_rb3_plan_selects_asset_and_generates_push_command(tmp_path: Path) -> None:
    memory_path = tmp_path / "memory.json"
    memory = RB3ProceduralMemory(memory_path).load()

    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()

    plan = build_rb3_speaker_playback_plan(
        _fingerprint(),
        static_context=_static_context(),
        memory=memory,
        bridge_root=bridge_root,
    ).plan

    assert plan["intent"] == "validate speaker playback"
    assert plan["pcm_inference"]["alsa_device"].startswith("hw:")
    deployment = plan["asset_deployment"]
    assert deployment["asset_selected"] is True
    assert "push_command" in deployment
    assert deployment["push_command"].startswith("AURA_ADB_PUSH ")


def test_runtime_correlation_and_failure_reasoning() -> None:
    corr = correlate_runtime_evidence(
        {
            "pcm_before": "before",
            "pcm_after": "after",
            "dmesg_before": "old",
            "dmesg_after": "new snd asoc lpass",
            "dapm_before": "A off",
            "dapm_after": "A on",
            "mixer_before": "x",
            "mixer_after": "y",
            "playback_exit_code": 0,
            "playback_stderr": "",
        }
    )
    assert corr["playback_completion"] is True
    assert corr["route_activation_confidence"] in {"HIGH", "MEDIUM"}

    plan = {
        "overlay": {"status": "ADVISORY_ONLY"},
        "mixer_dependency": {"route_dependencies": []},
    }
    static_context = {"backend_frontend_mappings": [], "soundwire_topology_markers": ["wsa"]}
    failure = explain_playback_failure(plan, corr, static_context=static_context)
    assert failure["failure_reasons"]


def test_audio_route_knowledge_graph() -> None:
    graph = build_audio_route_knowledge_graph(
        static_context=_static_context(),
        mixer_dependency={
            "route_dependencies": ["MultiMedia1->PRIMARY_MI2S_RX", "PRIMARY_MI2S_RX->WSA_SPKR"]
        },
        overlay={"overlay": "qcs6490-audioreach.dtsi"},
        pcm_inference={"alsa_device": "hw:0,0"},
    )
    assert graph["nodes"]
    assert graph["edges"]


def test_procedural_memory_roundtrip(tmp_path: Path) -> None:
    memory_path = tmp_path / "rb3_memory.json"
    memory = RB3ProceduralMemory(memory_path)

    payload = memory.record_result(
        run_id="run-1",
        success=True,
        asset_id="rb3_speaker_48k_stereo_v1",
        overlay="qcs6490-audioreach.dtsi",
        mixer_sequence=["validate_route_topology", "snapshot_mixer_state"],
        quirks=["codec_requires_route_settle_delay"],
        unsupported_format="S24_LE",
        route_constraints=["speaker_only_path"],
        recovery_patterns=["reapply_overlay_then_retry"],
        runtime_signature={"route_activation_confidence": "HIGH"},
        failure_signature="",
    )

    assert "rb3_speaker_48k_stereo_v1" in payload["successful_wav_assets"]
    assert payload["history"]
    assert payload["runtime_signatures"]

    loaded = json.loads(memory_path.read_text(encoding="utf-8"))
    assert loaded["board"] == "RB3Gen2"


def test_state_machine_progress() -> None:
    plan = {
        "overlay": {"status": "RESOLVED"},
        "pcm_inference": {"alsa_device": "hw:0,0"},
        "asset_deployment": {
            "asset_selected": True,
            "staging": {"staged": True},
        },
    }
    correlation = {
        "playback_attempted": True,
        "playback_started": True,
        "playback_completion": True,
        "cleanup_completed": True,
        "route_activation_confidence": "HIGH",
    }
    sm = build_playback_state_machine(plan, correlation=correlation)
    assert sm["current_state"] == "cleanup_completed"


def test_command_planner_rb3_workflow_integration(tmp_path: Path) -> None:
    dts = tmp_path / "rb3.dts"
    overlay = tmp_path / "overlay-audio.dtsi"
    overlay.write_text(
        """
        &sound {
            qcom,audio-routing =
                "MultiMedia1", "PRIMARY_MI2S_RX",
                "PRIMARY_MI2S_RX", "WSA_SPKR";
        };
        """,
        encoding="utf-8",
    )
    dts.write_text(
        """
        /dts-v1/;
        #include "overlay-audio.dtsi"
        / { model = "RB3"; };
        """,
        encoding="utf-8",
    )

    bridge_root = tmp_path / "bridge"
    bridge_root.mkdir()
    memory_path = tmp_path / "memory.json"
    result = build_rb3_speaker_workflow(
        _fingerprint(),
        entry_dts=dts,
        memory_path=memory_path,
        bridge_root=bridge_root,
    )
    assert result.workflow["board"] == "RB3Gen2"
    assert result.workflow["intent"] == "validate speaker playback"
