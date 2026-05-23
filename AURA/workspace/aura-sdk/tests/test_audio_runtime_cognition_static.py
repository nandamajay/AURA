from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.command_planner import build_procedural_audio_plan
from aura_sdk.transport.dts_audio_cognition import parse_dts_audio_cognition


def _sample_fingerprint(*, confidence: str = "LOW") -> dict:
    return {
        "environment": {
            "primary_environment": "Embedded Linux",
            "detected_environments": ["Embedded Linux", "Qualcomm Linux"],
            "confidence": confidence,
            "evidence": {"embedded_linux": ["linux version"]},
        },
        "capabilities": {
            "supports_procfs": "SUPPORTED",
            "supports_tinymix": "UNKNOWN",
            "supports_debugfs": "UNKNOWN",
            "supports_getprop": "UNSUPPORTED",
        },
        "unsupported_command_evidence": [
            {
                "normalized_command": "getprop ro.build.fingerprint",
                "stdout": "/bin/sh: getprop: not found",
                "stderr": "",
                "exit_code": 127,
            }
        ],
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


def test_dts_audio_cognition_extracts_routing_and_includes(tmp_path: Path) -> None:
    entry = tmp_path / "board.dts"
    overlay_a = tmp_path / "audio-a-overlay.dtsi"
    overlay_b = tmp_path / "audio-b-overlay.dtsi"

    overlay_a.write_text(
        """
        &sound {
            qcom,audio-routing =
                \"MultiMedia1\", \"PRIMARY_MI2S_RX\",
                \"PRIMARY_MI2S_RX\", \"WSA_SPKR\";
        };
        codec_a: codec@1 { compatible = \"qcom,wcd938x\"; };
        """,
        encoding="utf-8",
    )
    overlay_b.write_text(
        """
        dai-link0 { link-name = \"mm1-playback\"; };
        """,
        encoding="utf-8",
    )
    entry.write_text(
        """
        /dts-v1/;
        #include \"audio-a-overlay.dtsi\"
        #include \"audio-b-overlay.dtsi\"
        / { model = \"RB3\"; };
        """,
        encoding="utf-8",
    )

    parsed = parse_dts_audio_cognition(entry)
    context = parsed.context

    assert context["qcom_audio_routing"]
    assert context["codec_nodes"]
    assert context["dai_links"]
    assert context["overlay_inheritance"]["ambiguous"] is True


def test_procedural_audio_plan_enters_learning_mode_for_low_confidence(tmp_path: Path) -> None:
    entry = tmp_path / "board.dts"
    overlay = tmp_path / "audio-overlay.dtsi"
    overlay.write_text(
        """
        &sound {
            qcom,audio-routing =
                \"MultiMedia1\", \"PRIMARY_MI2S_RX\",
                \"PRIMARY_MI2S_RX\", \"WSA_SPKR\";
        };
        """,
        encoding="utf-8",
    )
    entry.write_text(
        """
        /dts-v1/;
        #include \"audio-overlay.dtsi\"
        / { model = \"RB3\"; };
        """,
        encoding="utf-8",
    )

    result = build_procedural_audio_plan(_sample_fingerprint(confidence="LOW"), entry_dts=entry)

    assert result.cognition["cognition_mode"] == "Learning Mode"
    assert result.cognition["playback_workflow"]["alsa_playback_device"]["alsa_device"] == "hw:0,0"
    assert any(
        item.get("normalized_command") == "getprop ro.build.fingerprint"
        for item in result.cognition["unsupported_commands"]
    )
    question_ids = {item["id"] for item in result.cognition["targeted_questions"]}
    assert "runtime_profile" in question_ids
    assert "wav_asset" in question_ids


def test_procedural_audio_plan_known_mode_when_explicit_choices_supplied(tmp_path: Path) -> None:
    entry = tmp_path / "board.dts"
    overlay = tmp_path / "audio-overlay.dtsi"
    overlay.write_text(
        """
        &sound {
            qcom,audio-routing =
                \"MultiMedia1\", \"PRIMARY_MI2S_RX\",
                \"PRIMARY_MI2S_RX\", \"WSA_SPKR\";
        };
        codec_b: codec@2 { compatible = \"qcom,wcd937x\"; };
        """,
        encoding="utf-8",
    )
    entry.write_text(
        """
        /dts-v1/;
        #include \"audio-overlay.dtsi\"
        / { model = \"RB3\"; };
        """,
        encoding="utf-8",
    )

    result = build_procedural_audio_plan(
        _sample_fingerprint(confidence="HIGH"),
        entry_dts=entry,
        selected_overlay="audio-overlay.dtsi",
        selected_playback_target="speaker",
        wav_asset_path="/tmp/test.wav",
    )

    assert result.cognition["cognition_mode"] == "Known Mode"
    assert result.cognition["selected_playback_target"] == "speaker"
    assert not result.cognition["targeted_questions"]
    assert result.cognition["runtime_audio_knowledge_graph"]["nodes"]
