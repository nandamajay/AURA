"""Subsystem-aware Linux audio/runtime cognition for governed planning.

Linux remains the authoritative cognition/governance layer. This module performs
reasoning only; it does not execute runtime commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

MODE_KNOWN = "Known Mode"
MODE_LEARNING = "Learning Mode"
MODE_DISCOVERY = "Discovery Mode"


@dataclass(frozen=True)
class AudioCognitionResult:
    cognition: dict[str, Any]


def _extract_targets_from_text(values: list[str]) -> list[str]:
    targets: set[str] = set()
    for value in values:
        lowered = value.lower()
        if any(token in lowered for token in ("rb3gen2", "qcs6490", "qcm6490")):
            targets.add("speaker")
        if any(token in lowered for token in ("speaker", "spkr", "wsa", "rx")):
            targets.add("speaker")
        if any(token in lowered for token in ("headset", "hph", "hp", "jack")):
            targets.add("headset")
        if any(token in lowered for token in ("bt", "bluetooth", "a2dp")):
            targets.add("bt")
        if any(token in lowered for token in ("earpiece", "ear")):
            targets.add("earpiece")
    return sorted(targets)


def _derive_runtime_targets(audio_discovery: Mapping[str, Any]) -> list[str]:
    cards = audio_discovery.get("alsa_topology_cards", [])
    pcm = audio_discovery.get("pcm_entries", [])

    values: list[str] = []
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                values.append(str(card.get("card_id", "")))
                values.append(str(card.get("descriptor", "")))
    if isinstance(pcm, list):
        for entry in pcm:
            if isinstance(entry, dict):
                values.append(str(entry.get("name", "")))
                values.append(str(entry.get("interface", "")))
    return _extract_targets_from_text(values)


def _derive_static_targets(static_context: Mapping[str, Any]) -> list[str]:
    values: list[str] = []

    routing = static_context.get("qcom_audio_routing", [])
    if isinstance(routing, list):
        for item in routing:
            if isinstance(item, dict):
                values.append(str(item.get("source", "")))
                values.append(str(item.get("sink", "")))

    codecs = static_context.get("codec_nodes", [])
    if isinstance(codecs, list):
        for item in codecs:
            if isinstance(item, dict):
                values.append(str(item.get("node", "")))
                values.append(str(item.get("compatible", "")))

    return _extract_targets_from_text(values)


def _parse_hw_device_from_pcm_id(pcm_id: str) -> tuple[int, int] | None:
    match = re.match(r"^(\d+)-(\d+)", pcm_id.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _infer_playback_device(audio_discovery: Mapping[str, Any]) -> dict[str, Any]:
    pcm_entries = audio_discovery.get("pcm_entries", [])
    if not isinstance(pcm_entries, list):
        pcm_entries = []

    for entry in pcm_entries:
        if not isinstance(entry, dict):
            continue
        direction = str(entry.get("direction", "")).lower()
        streams = int(entry.get("streams", 0))
        if direction != "playback" or streams < 1:
            continue

        parsed = _parse_hw_device_from_pcm_id(str(entry.get("pcm_id", "")))
        if parsed is not None:
            card_index, device_index = parsed
            return {
                "alsa_device": f"hw:{card_index},{device_index}",
                "source": "runtime_pcm",
                "confidence": "HIGH",
                "pcm_entry": entry,
            }

    cards = audio_discovery.get("alsa_topology_cards", [])
    if isinstance(cards, list) and cards:
        first = cards[0]
        if isinstance(first, dict):
            card_index = int(first.get("card_index", 0))
            return {
                "alsa_device": f"hw:{card_index},0",
                "source": "card_fallback",
                "confidence": "LOW",
                "pcm_entry": None,
            }

    return {
        "alsa_device": "UNKNOWN",
        "source": "insufficient_runtime_evidence",
        "confidence": "LOW",
        "pcm_entry": None,
    }


def _cognition_mode(
    runtime_confidence: str,
    *,
    has_runtime_audio: bool,
    overlay_ambiguous: bool,
    target_ambiguous: bool,
) -> str:
    if not has_runtime_audio:
        return MODE_DISCOVERY
    if runtime_confidence == "HIGH" and not overlay_ambiguous and not target_ambiguous:
        return MODE_KNOWN
    return MODE_LEARNING


def _build_targeted_questions(
    *,
    mode: str,
    runtime_confidence: str,
    overlay_ambiguous: bool,
    target_ambiguous: bool,
    wav_asset_path: str | None,
    supported_targets: list[str],
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []

    if mode in {MODE_LEARNING, MODE_DISCOVERY} and runtime_confidence in {"LOW", "MEDIUM"}:
        questions.append(
            {
                "id": "runtime_profile",
                "question": "Runtime confidence is low. Confirm if this boot uses production audio overlay or bring-up overlay.",
            }
        )

    if overlay_ambiguous:
        questions.append(
            {
                "id": "overlay_selection",
                "question": "Select active DTS overlay/config before playback planning continues.",
            }
        )

    if target_ambiguous:
        values = ", ".join(supported_targets) if supported_targets else "speaker/headset/bt"
        questions.append(
            {
                "id": "playback_target",
                "question": f"Select playback target ({values}) for route-specific planning.",
            }
        )

    if not wav_asset_path:
        questions.append(
            {
                "id": "wav_asset",
                "question": "Provide WAV asset path and format (sample rate/channels/bit depth).",
            }
        )

    return questions


def _build_mixer_dependency_graph(
    static_context: Mapping[str, Any],
    runtime_audio: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    for widget in static_context.get("widgets", []):
        node_id = f"widget:{widget}"
        nodes.append({"id": node_id, "kind": "widget", "label": str(widget)})

    for route in static_context.get("qcom_audio_routing", []):
        if not isinstance(route, dict):
            continue
        source = str(route.get("source", "")).strip()
        sink = str(route.get("sink", "")).strip()
        if not source or not sink:
            continue

        source_id = f"route:{source}"
        sink_id = f"route:{sink}"
        nodes.append({"id": source_id, "kind": "route", "label": source})
        nodes.append({"id": sink_id, "kind": "route", "label": sink})
        edges.append({"from": source_id, "to": sink_id, "relation": "connects"})

    pcm_entries = runtime_audio.get("pcm_entries", [])
    if isinstance(pcm_entries, list):
        for entry in pcm_entries:
            if not isinstance(entry, dict):
                continue
            label = f"{entry.get('pcm_id', '?')}:{entry.get('direction', '?')}"
            node_id = f"pcm:{entry.get('pcm_id', 'unknown')}"
            nodes.append({"id": node_id, "kind": "pcm", "label": label})

    dedup_nodes = {node["id"]: node for node in nodes}
    return {
        "nodes": list(dedup_nodes.values()),
        "edges": edges,
    }


def _unsupported_mixer_paths(
    fingerprint: Mapping[str, Any],
    static_context: Mapping[str, Any],
) -> list[str]:
    unsupported: list[str] = []
    capabilities = fingerprint.get("capabilities", {})
    if str(capabilities.get("supports_tinymix", "UNKNOWN")) != "SUPPORTED":
        unsupported.append("tinymix_control_paths:unsupported_or_unknown")
    if str(capabilities.get("supports_debugfs", "UNKNOWN")) != "SUPPORTED":
        unsupported.append("dapm_debugfs_paths:unsupported_or_unknown")

    if not static_context.get("qcom_audio_routing"):
        unsupported.append("qcom_audio_routing:not_available")

    return unsupported


def _build_audio_knowledge_graph(
    *,
    fingerprint: Mapping[str, Any],
    static_context: Mapping[str, Any],
    supported_targets: list[str],
    unsupported_mixer_paths: list[str],
    playback_device: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []

    nodes.append({"id": "audio_target", "kind": "target", "label": "runtime_audio_target"})

    for card in fingerprint.get("audio_discovery", {}).get("alsa_topology_cards", []):
        if not isinstance(card, dict):
            continue
        card_id = f"card:{card.get('card_index', 'x')}"
        nodes.append(
            {
                "id": card_id,
                "kind": "device",
                "label": str(card.get("card_id", "unknown")),
            }
        )
        edges.append({"from": "audio_target", "to": card_id, "relation": "reports"})

    for codec in static_context.get("codec_nodes", []):
        if not isinstance(codec, dict):
            continue
        cid = f"codec:{codec.get('node', 'unknown')}"
        nodes.append({"id": cid, "kind": "codec", "label": str(codec.get("compatible", "codec"))})
        edges.append({"from": "audio_target", "to": cid, "relation": "declares"})

    for route in static_context.get("qcom_audio_routing", []):
        if not isinstance(route, dict):
            continue
        source = str(route.get("source", ""))
        sink = str(route.get("sink", ""))
        if not source or not sink:
            continue
        sid = f"route:{source}"
        tid = f"route:{sink}"
        nodes.append({"id": sid, "kind": "route", "label": source})
        nodes.append({"id": tid, "kind": "route", "label": sink})
        edges.append({"from": sid, "to": tid, "relation": "active_path_candidate"})

    for target in supported_targets:
        tid = f"playback_target:{target}"
        nodes.append({"id": tid, "kind": "playback_target", "label": target})
        edges.append({"from": "audio_target", "to": tid, "relation": "supports"})

    for path in unsupported_mixer_paths:
        uid = f"unsupported:{path}"
        nodes.append({"id": uid, "kind": "unsupported_path", "label": path})
        edges.append({"from": "audio_target", "to": uid, "relation": "unsupported"})

    if playback_device.get("alsa_device") and playback_device["alsa_device"] != "UNKNOWN":
        did = f"alsa:{playback_device['alsa_device']}"
        nodes.append({"id": did, "kind": "device", "label": playback_device["alsa_device"]})
        edges.append({"from": "audio_target", "to": did, "relation": "candidate_playback_device"})

    dedup_nodes = {node["id"]: node for node in nodes}
    return {
        "nodes": list(dedup_nodes.values()),
        "edges": edges,
    }


def build_audio_runtime_cognition(
    fingerprint: Mapping[str, Any],
    *,
    static_audio_context: Mapping[str, Any] | None = None,
    selected_overlay: str | None = None,
    selected_playback_target: str | None = None,
    wav_asset_path: str | None = None,
) -> AudioCognitionResult:
    """Build subsystem-aware audio cognition with fail-closed planning outputs."""

    static_context = dict(static_audio_context or {})
    audio_discovery = fingerprint.get("audio_discovery", {})
    runtime_confidence = str(fingerprint.get("environment", {}).get("confidence", "LOW"))

    runtime_targets = _derive_runtime_targets(audio_discovery)
    static_targets = _derive_static_targets(static_context)
    supported_targets = sorted(set(runtime_targets + static_targets))

    overlay_candidates = static_context.get("overlay_inheritance", {}).get("overlay_candidates", [])
    overlay_ambiguous = bool(overlay_candidates) and selected_overlay is None

    target_ambiguous = (
        selected_playback_target is None and len(supported_targets) != 1
    )

    has_runtime_audio = bool(audio_discovery.get("alsa_topology_cards"))
    mode = _cognition_mode(
        runtime_confidence,
        has_runtime_audio=has_runtime_audio,
        overlay_ambiguous=overlay_ambiguous,
        target_ambiguous=target_ambiguous,
    )

    selected_target = selected_playback_target
    if selected_target is None and len(supported_targets) == 1:
        selected_target = supported_targets[0]

    playback_device = _infer_playback_device(audio_discovery)
    unsupported_mixer_paths = _unsupported_mixer_paths(fingerprint, static_context)

    playback_workflow = {
        "workflow_name": "adaptive_playback",
        "mode": mode,
        "selected_playback_target": selected_target or "UNRESOLVED",
        "selected_overlay": selected_overlay or "UNRESOLVED",
        "alsa_playback_device": playback_device,
        "wav_asset_requirements": {
            "path": wav_asset_path or "REQUIRED",
            "format": "wav_pcm",
            "sample_rate_hz": "operator_selected",
            "channels": "operator_selected",
            "bit_depth": "operator_selected",
        },
        "runtime_sequence": [
            "validate governance allowlist and execution classification",
            "collect read-only route evidence (/proc/asound, dmesg, debugfs when available)",
            "resolve overlay + target ambiguity before any mixer mutation",
            "derive ALSA playback command template",
        ],
        "command_templates": [
            {
                "classification": "SAFE_READ",
                "command": "cat /proc/asound/cards",
            },
            {
                "classification": "SAFE_READ",
                "command": "cat /proc/asound/pcm",
            },
            {
                "classification": "REQUIRES_OPERATOR_APPROVAL",
                "command": f"aplay -D {playback_device['alsa_device']} <wav_asset_path>",
                "enabled": playback_device.get("alsa_device") != "UNKNOWN",
            },
        ],
        "blocked_mutation_commands": [
            "tinymix set ...",
            "amixer cset ...",
            "echo ... > /sys/...",
        ],
        "validation_status": (
            "VALIDATED_TEMPLATE"
            if playback_device.get("alsa_device") != "UNKNOWN"
            else "PARTIAL_TEMPLATE"
        ),
    }

    capture_workflow = {
        "workflow_name": "adaptive_capture",
        "mode": mode,
        "selected_overlay": selected_overlay or "UNRESOLVED",
        "runtime_sequence": [
            "collect capture PCM endpoints",
            "resolve backend/frontend capture route",
            "build capture template only after target selection",
        ],
        "command_templates": [
            {
                "classification": "SAFE_READ",
                "command": "cat /proc/asound/pcm",
            },
            {
                "classification": "REQUIRES_OPERATOR_APPROVAL",
                "command": "arecord -D <capture_device> -f S16_LE -r 48000 -c 2 <capture.wav>",
            },
        ],
    }

    targeted_questions = _build_targeted_questions(
        mode=mode,
        runtime_confidence=runtime_confidence,
        overlay_ambiguous=overlay_ambiguous,
        target_ambiguous=target_ambiguous,
        wav_asset_path=wav_asset_path,
        supported_targets=supported_targets,
    )

    mixer_dependency_graph = _build_mixer_dependency_graph(static_context, audio_discovery)
    knowledge_graph = _build_audio_knowledge_graph(
        fingerprint=fingerprint,
        static_context=static_context,
        supported_targets=supported_targets,
        unsupported_mixer_paths=unsupported_mixer_paths,
        playback_device=playback_device,
    )

    cognition: dict[str, Any] = {
        "cognition_mode": mode,
        "runtime_confidence": runtime_confidence,
        "supported_playback_targets": supported_targets,
        "selected_playback_target": selected_target or "UNRESOLVED",
        "overlay_selection": selected_overlay or "UNRESOLVED",
        "targeted_questions": targeted_questions,
        "playback_workflow": playback_workflow,
        "capture_workflow": capture_workflow,
        "mixer_dependency_graph": mixer_dependency_graph,
        "runtime_audio_knowledge_graph": knowledge_graph,
        "unsupported_mixer_paths": unsupported_mixer_paths,
        "unsupported_commands": fingerprint.get("unsupported_command_evidence", []),
        "governance": {
            "linux_role": "governance_and_cognition",
            "windows_role": "execution_worker_only",
            "fail_closed": True,
            "immutable_lineage": True,
            "normalized_execution": True,
        },
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }
    return AudioCognitionResult(cognition=cognition)
