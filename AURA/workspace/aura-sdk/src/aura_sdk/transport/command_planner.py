"""Adaptive command planner using capability fingerprint evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.audio_runtime_cognition import build_audio_runtime_cognition
from aura_sdk.transport.dts_audio_cognition import parse_dts_audio_cognition
from aura_sdk.transport.rb3_playback_cognition import (
    RB3ProceduralMemory,
    build_rb3_speaker_playback_plan,
)

CAP_SUPPORTED = "SUPPORTED"


@dataclass(frozen=True)
class PlanResult:
    selected_commands: list[str]
    skipped_commands: list[dict[str, str]]
    planning_mode: str


@dataclass(frozen=True)
class ProceduralAudioPlanResult:
    static_context: dict[str, Any]
    cognition: dict[str, Any]


@dataclass(frozen=True)
class RB3SpeakerWorkflowResult:
    static_context: dict[str, Any]
    workflow: dict[str, Any]


def _capability(capabilities: Mapping[str, Any], key: str) -> str:
    return str(capabilities.get(key, "UNKNOWN"))


def build_adaptive_plan(fingerprint: Mapping[str, Any]) -> PlanResult:
    capabilities = fingerprint.get("capabilities", {})
    environment = fingerprint.get("environment", {})
    detected_env = [str(item) for item in environment.get("detected_environments", [])]

    selected: list[str] = []
    skipped: list[dict[str, str]] = []

    # Environment strategy selection.
    if "Android" in detected_env:
        strategy = "ANDROID"
        candidate = [
            ("getprop ro.build.fingerprint", "supports_getprop"),
            ("logcat -d -t 200", "supports_logcat"),
            ("dumpsys media.audio_flinger", "supports_dumpsys"),
        ]
    else:
        strategy = "EMBEDDED_LINUX"
        candidate = [
            ("uname -a", "supports_uname"),
            ("cat /proc/version", "supports_procfs"),
            ("cat /proc/asound/cards", "supports_procfs"),
            ("dmesg", "supports_dmesg"),
            ("lsmod", "supports_lsmod"),
        ]

    # QEMU specific enrichers.
    if "QEMU" in detected_env:
        candidate.extend(
            [
                ("cat /proc/cpuinfo", "supports_procfs"),
            ]
        )

    # Qualcomm audio enrichers.
    if "Qualcomm Linux" in detected_env:
        candidate.extend(
            [
                ("cat /proc/asound/pcm", "supports_procfs"),
                ("tinymix", "supports_tinymix"),
                ("amixer", "supports_amixer"),
                ("ls /sys/kernel/debug/asoc", "supports_debugfs"),
                ("cat /sys/kernel/debug/asoc/*/dapm", "supports_dapm"),
            ]
        )

    for command, cap_key in candidate:
        state = _capability(capabilities, cap_key)
        if state == CAP_SUPPORTED:
            if command not in selected:
                selected.append(command)
        else:
            skipped.append(
                {
                    "command": command,
                    "reason": f"{cap_key}:{state.lower()}",
                }
            )

    return PlanResult(
        selected_commands=selected,
        skipped_commands=skipped,
        planning_mode=strategy,
    )


def build_procedural_audio_plan(
    fingerprint: Mapping[str, Any],
    *,
    entry_dts: str | Path | None = None,
    selected_overlay: str | None = None,
    selected_playback_target: str | None = None,
    wav_asset_path: str | None = None,
) -> ProceduralAudioPlanResult:
    """Build subsystem-aware audio workflows from static + runtime evidence.

    The function is cognition-only and preserves fail-closed semantics:
    unresolved static files produce UNKNOWN-like context rather than assumptions.
    """

    static_context: dict[str, Any] = {
        "entry_dts": "UNAVAILABLE",
        "source_files": [],
        "include_graph": [],
        "unresolved_includes": [],
        "sound_card_nodes": [],
        "dai_links": [],
        "backend_frontend_mappings": [],
        "qcom_audio_routing": [],
        "soundwire_topology_markers": [],
        "codec_nodes": [],
        "overlay_inheritance": {"overlay_candidates": [], "ambiguous": False},
        "widgets": [],
        "parse_confidence": "LOW",
        "governance_posture": "ADVISORY_ONLY",
    }
    if entry_dts is not None and Path(entry_dts).exists():
        static_context = parse_dts_audio_cognition(entry_dts, max_include_depth=6).context

    cognition = build_audio_runtime_cognition(
        fingerprint,
        static_audio_context=static_context,
        selected_overlay=selected_overlay,
        selected_playback_target=selected_playback_target,
        wav_asset_path=wav_asset_path,
    ).cognition
    return ProceduralAudioPlanResult(
        static_context=static_context,
        cognition=cognition,
    )


def build_rb3_speaker_workflow(
    fingerprint: Mapping[str, Any],
    *,
    entry_dts: str | Path,
    memory_path: str | Path,
    bridge_root: str | Path,
    intent: str = "validate speaker playback",
    target_path: str = "/data/local/tmp/aura/audio/speaker_validation.wav",
    overwrite_policy: str = "no_overwrite",
) -> RB3SpeakerWorkflowResult:
    """Build RB3Gen2 speaker playback activation workflow cognition."""

    static_context = parse_dts_audio_cognition(entry_dts, max_include_depth=6).context
    memory = RB3ProceduralMemory(memory_path).load()
    workflow = build_rb3_speaker_playback_plan(
        fingerprint,
        static_context=static_context,
        memory=memory,
        bridge_root=bridge_root,
        intent=intent,
        target_path=target_path,
        overwrite_policy=overwrite_policy,
    ).plan
    return RB3SpeakerWorkflowResult(static_context=static_context, workflow=workflow)
