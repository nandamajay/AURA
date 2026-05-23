"""Runtime capability graph builder for evidence-centric cognition outputs."""

from __future__ import annotations

from typing import Any, Mapping


def build_runtime_capability_graph(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    capabilities = fingerprint.get("capabilities", {})
    environments = fingerprint.get("environment", {}).get("detected_environments", [])
    audio = fingerprint.get("audio_discovery", {})

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    nodes.append({"id": "target", "kind": "target", "label": fingerprint.get("target_id", "target")})

    for env in environments:
        env_id = f"env:{env}"
        nodes.append({"id": env_id, "kind": "environment", "label": env})
        edges.append({"from": "target", "to": env_id, "relation": "classified_as"})

    for name, value in capabilities.items():
        cap_id = f"cap:{name}"
        nodes.append({"id": cap_id, "kind": "capability", "label": f"{name}={value}"})
        edges.append({"from": "target", "to": cap_id, "relation": "has_capability"})

    for key in ("rb3gen2_detected", "qdsp_present"):
        if key in audio:
            audio_id = f"audio:{key}"
            nodes.append({"id": audio_id, "kind": "audio", "label": f"{key}={audio[key]}"})
            edges.append({"from": "target", "to": audio_id, "relation": "audio_signal"})

    if audio.get("cards"):
        nodes.append({"id": "audio:alsa_cards", "kind": "audio", "label": "alsa_cards"})
        edges.append({"from": "target", "to": "audio:alsa_cards", "relation": "reports"})

    if audio.get("pcm_entries"):
        nodes.append({"id": "audio:pcm_entries", "kind": "audio", "label": "pcm_entries"})
        edges.append({"from": "target", "to": "audio:pcm_entries", "relation": "reports"})

    if audio.get("tinymix_controls"):
        nodes.append({"id": "audio:tinymix", "kind": "audio", "label": "tinymix_controls"})
        edges.append({"from": "target", "to": "audio:tinymix", "relation": "reports"})

    if audio.get("amixer_controls"):
        nodes.append({"id": "audio:amixer", "kind": "audio", "label": "amixer_controls"})
        edges.append({"from": "target", "to": "audio:amixer", "relation": "reports"})

    if audio.get("dapm_widgets"):
        nodes.append({"id": "audio:dapm", "kind": "audio", "label": "dapm_widgets"})
        edges.append({"from": "target", "to": "audio:dapm", "relation": "reports"})

    return {
        "nodes": nodes,
        "edges": edges,
    }
