"""RB3Gen2 topology-aware audio cognition for deterministic playback governance.

This module is reasoning-only. It correlates static DTS/DTSI topology signals with
runtime ALSA evidence and deterministic replay signatures, then emits fail-closed
confidence classifications and targeted clarification prompts.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_AUDIO_ROUTING_RE = re.compile(r"qcom,audio-routing\s*=\s*(.*?);", re.DOTALL)
_QSTR_RE = re.compile(r'"([^"]+)"')
_NODE_RE = re.compile(r"^\s*([A-Za-z0-9_\-]+:)?\s*([A-Za-z0-9,._@/+\-]+)\s*\{", re.MULTILINE)
_COMPAT_RE = re.compile(r"compatible\s*=\s*(.*?);", re.DOTALL)
_DAI_LINK_RE = re.compile(r"\b(dai-link\d*|link-name)\b", re.IGNORECASE)
_SOUNDWIRE_RE = re.compile(r"\b(soundwire|swr\d+|wsa|rx_macro|tx_macro|va_macro)\b", re.IGNORECASE)
_PCM_RE = re.compile(r"^(\S+):\s*(.*?)\s*:\s*(.*?)\s*:\s*(playback|capture)\s+(\d+)\s*$")
_CARD_RE = re.compile(r"^\s*(\d+)\s+\[(.+?)\s*\]:\s*(.+)$")
_AMIXER_CTRL_RE = re.compile(r"Simple mixer control '([^']+)',\s*(\d+)")

_CODEC_MARKERS = ("wcd", "codec", "rt5682", "rt1011", "max983", "tas", "es83")
_OVERLAY_MARKERS = ("overlay", "audio", "audioreach")
_FE_MARKERS = ("multimedia", "mm", "hostless", "compress", "voip")
_BE_MARKERS = ("primary", "secondary", "tertiary", "quaternary", "rx", "tx", "slim", "i2s", "wsa", "va", "dmic")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_bool(value: Any) -> bool:
    return bool(value)


def _safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _stable_hash(payload: Mapping[str, Any]) -> str:
    return re.sub(
        r"\s+",
        "",
        base64.urlsafe_b64encode(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).decode("ascii"),
    )


def _extract_routing_pairs(text: str) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for match in _AUDIO_ROUTING_RE.finditer(text):
        quoted = _QSTR_RE.findall(match.group(1))
        for index in range(0, len(quoted) - 1, 2):
            pairs.append({"source": quoted[index], "sink": quoted[index + 1]})
    return pairs


def _extract_dai_links(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        value = line.strip()
        if value and _DAI_LINK_RE.search(value):
            lines.append(value)
    return sorted(set(lines))


def _extract_sound_cards(text: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    node_name = ""
    for line in text.splitlines():
        node_match = _NODE_RE.search(line)
        if node_match:
            node_name = node_match.group(2)
        if "model =" not in line and "qcom,model" not in line:
            continue
        for item in _QSTR_RE.findall(line):
            cards.append({"node": node_name or "unknown", "model": item})
    return cards


def _extract_codec_nodes(text: str) -> list[dict[str, str]]:
    codecs: list[dict[str, str]] = []
    current_node = ""
    for line in text.splitlines():
        node_match = _NODE_RE.search(line)
        if node_match:
            current_node = node_match.group(2)
        if "compatible" not in line:
            continue
        for compat in _QSTR_RE.findall(line):
            lowered = compat.lower()
            if any(marker in lowered for marker in _CODEC_MARKERS):
                codecs.append({"node": current_node or "unknown", "compatible": compat})
    return codecs


def _extract_widgets(text: str) -> list[str]:
    widgets: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if "widget" in lowered or "widgets" in lowered or "dapm" in lowered:
            widgets.append(line.strip())
    return sorted(set(item for item in widgets if item))


def _extract_soundwire_markers(text: str) -> list[str]:
    return sorted(set(item.lower() for item in _SOUNDWIRE_RE.findall(text)))


def _extract_fe_be_nodes(routing_pairs: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    fe: set[str] = set()
    be: set[str] = set()
    for pair in routing_pairs:
        src = str(pair.get("source", ""))
        sink = str(pair.get("sink", ""))
        src_l = src.lower()
        sink_l = sink.lower()

        if any(marker in src_l for marker in _FE_MARKERS):
            fe.add(src)
        if any(marker in sink_l for marker in _FE_MARKERS):
            fe.add(sink)
        if any(marker in src_l for marker in _BE_MARKERS):
            be.add(src)
        if any(marker in sink_l for marker in _BE_MARKERS):
            be.add(sink)
    return sorted(fe), sorted(be)


def _parse_proc_cards(raw: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _CARD_RE.match(line)
        if not match:
            continue
        cards.append(
            {
                "card_index": int(match.group(1)),
                "card_id": match.group(2).strip(),
                "descriptor": match.group(3).strip(),
            }
        )
    return cards


def _parse_proc_pcm(raw: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _PCM_RE.match(line.strip())
        if not match:
            continue
        entries.append(
            {
                "pcm_id": match.group(1),
                "name": match.group(2).strip(),
                "interface": match.group(3).strip(),
                "direction": match.group(4).strip(),
                "streams": int(match.group(5)),
            }
        )
    return entries


def _parse_amixer_controls(raw: str) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for line in raw.splitlines():
        match = _AMIXER_CTRL_RE.search(line.strip())
        if not match:
            continue
        controls.append({"name": match.group(1), "index": int(match.group(2))})
    return controls


def _decode_amixer_name(command: str) -> str:
    value = str(command).strip()
    prefix = "AURA_AMIXER_NAME_SET "
    if not value.startswith(prefix):
        return ""
    parts = value.split(maxsplit=2)
    if len(parts) < 2:
        return ""
    encoded = parts[1]
    pad = "=" * ((4 - len(encoded) % 4) % 4)
    try:
        return base64.urlsafe_b64decode((encoded + pad).encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _extract_mixer_controls_from_workflow(workflow: Mapping[str, Any]) -> list[str]:
    commands = workflow.get("playback_workflow", {}).get("mixer_apply_commands", [])
    names: list[str] = []
    if not isinstance(commands, list):
        return names
    for command in commands:
        decoded = _decode_amixer_name(str(command))
        if decoded:
            names.append(decoded)
    return sorted(set(names))


def _extract_command_sequence(phase_trace: list[dict[str, Any]]) -> list[str]:
    sequence: list[str] = []
    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        response = phase.get("response")
        if not isinstance(response, dict):
            continue
        for item in response.get("executor_command_trace", []):
            if not isinstance(item, dict):
                continue
            cmd = str(item.get("normalized_command", "")).strip()
            if cmd:
                sequence.append(cmd)
    return sequence


def _extract_evidence_sequence(phase_trace: list[dict[str, Any]]) -> list[str]:
    sequence: list[str] = []
    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        if phase.get("skipped", False):
            continue
        command = str(phase.get("snapshot_command", "")).strip()
        if command:
            sequence.append(command)
    return sequence


def _parse_source_topology(path: Path) -> dict[str, Any]:
    text = _safe_text(path)
    if not text:
        return {
            "path": str(path),
            "readable": False,
            "routing_pairs": [],
            "dai_links": [],
            "sound_cards": [],
            "codec_nodes": [],
            "widgets": [],
            "soundwire_markers": [],
            "frontend_nodes": [],
            "backend_nodes": [],
        }

    routing_pairs = _extract_routing_pairs(text)
    fe_nodes, be_nodes = _extract_fe_be_nodes(routing_pairs)

    return {
        "path": str(path),
        "readable": True,
        "routing_pairs": routing_pairs,
        "dai_links": _extract_dai_links(text),
        "sound_cards": _extract_sound_cards(text),
        "codec_nodes": _extract_codec_nodes(text),
        "widgets": _extract_widgets(text),
        "soundwire_markers": _extract_soundwire_markers(text),
        "frontend_nodes": fe_nodes,
        "backend_nodes": be_nodes,
    }


def _merge_unique_dicts(items: list[dict[str, Any]], key_fields: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in items:
        key = tuple(str(item.get(field, "")) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _merge_file_features(entries: list[dict[str, Any]]) -> dict[str, Any]:
    routing_pairs: list[dict[str, str]] = []
    dai_links: list[str] = []
    sound_cards: list[dict[str, str]] = []
    codec_nodes: list[dict[str, str]] = []
    widgets: list[str] = []
    soundwire_markers: list[str] = []
    frontend_nodes: list[str] = []
    backend_nodes: list[str] = []

    for entry in entries:
        routing_pairs.extend(entry.get("routing_pairs", []))
        dai_links.extend(entry.get("dai_links", []))
        sound_cards.extend(entry.get("sound_cards", []))
        codec_nodes.extend(entry.get("codec_nodes", []))
        widgets.extend(entry.get("widgets", []))
        soundwire_markers.extend(entry.get("soundwire_markers", []))
        frontend_nodes.extend(entry.get("frontend_nodes", []))
        backend_nodes.extend(entry.get("backend_nodes", []))

    return {
        "routing_pairs": _merge_unique_dicts(routing_pairs, ["source", "sink"]),
        "dai_links": sorted(set(dai_links)),
        "sound_cards": _merge_unique_dicts(sound_cards, ["node", "model"]),
        "codec_nodes": _merge_unique_dicts(codec_nodes, ["node", "compatible"]),
        "widgets": sorted(set(item for item in widgets if item)),
        "soundwire_markers": sorted(set(soundwire_markers)),
        "frontend_nodes": sorted(set(frontend_nodes)),
        "backend_nodes": sorted(set(backend_nodes)),
    }


def _is_overlay_file(path: Path) -> bool:
    lowered = path.name.lower()
    return any(marker in lowered for marker in _OVERLAY_MARKERS)


def _overlay_mutation_graph(
    *,
    entry_dts: Path,
    source_file_entries: list[dict[str, Any]],
    static_context: Mapping[str, Any],
) -> dict[str, Any]:
    overlay_entries: list[dict[str, Any]] = []
    base_entries: list[dict[str, Any]] = []
    for entry in source_file_entries:
        path = Path(str(entry.get("path", "")))
        if _is_overlay_file(path):
            overlay_entries.append(entry)
        else:
            base_entries.append(entry)

    if not base_entries:
        base_entries.append(
            {
                "path": str(entry_dts),
                "readable": entry_dts.exists(),
                "routing_pairs": list(static_context.get("qcom_audio_routing", [])),
                "dai_links": list(static_context.get("dai_links", [])),
                "sound_cards": list(static_context.get("sound_card_nodes", [])),
                "codec_nodes": list(static_context.get("codec_nodes", [])),
                "widgets": list(static_context.get("widgets", [])),
                "soundwire_markers": list(static_context.get("soundwire_topology_markers", [])),
                "frontend_nodes": [],
                "backend_nodes": [],
            }
        )

    base = _merge_file_features(base_entries)
    overlay = _merge_file_features(overlay_entries)

    base_routes = {f"{item['source']}->{item['sink']}" for item in base["routing_pairs"]}
    overlay_routes = {f"{item['source']}->{item['sink']}" for item in overlay["routing_pairs"]}
    base_dai = set(base["dai_links"])
    overlay_dai = set(overlay["dai_links"])
    base_widgets = set(base["widgets"])
    overlay_widgets = set(overlay["widgets"])

    overlay_candidates = static_context.get("overlay_inheritance", {}).get("overlay_candidates", [])
    if not isinstance(overlay_candidates, list):
        overlay_candidates = []

    conflicting_overlays = bool(
        static_context.get("overlay_inheritance", {}).get("ambiguous", False)
        or len(set(overlay_candidates)) > 1
    )

    return {
        "entry_dts": str(entry_dts),
        "base_files": [str(item.get("path", "")) for item in base_entries],
        "overlay_files": [str(item.get("path", "")) for item in overlay_entries],
        "include_chain": list(static_context.get("include_graph", [])),
        "overlay_candidates": overlay_candidates,
        "overlay_mutation_delta": {
            "added_routes": sorted(overlay_routes - base_routes),
            "removed_routes": sorted(base_routes - overlay_routes),
            "added_dai_links": sorted(overlay_dai - base_dai),
            "removed_dai_links": sorted(base_dai - overlay_dai),
            "added_widgets": sorted(overlay_widgets - base_widgets),
            "removed_widgets": sorted(base_widgets - overlay_widgets),
            "added_codecs": sorted(
                set(item.get("compatible", "") for item in overlay["codec_nodes"])
                - set(item.get("compatible", "") for item in base["codec_nodes"])
            ),
            "added_soundwire_markers": sorted(set(overlay["soundwire_markers"]) - set(base["soundwire_markers"])),
        },
        "merged_runtime_topology_reasoning": {
            "base_summary": base,
            "overlay_summary": overlay,
            "conflicting_overlays": conflicting_overlays,
        },
    }


def _topology_graph(
    *,
    entry_dts: Path,
    static_context: Mapping[str, Any],
    source_file_entries: list[dict[str, Any]],
    workflow: Mapping[str, Any],
    runtime_correlation: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    nodes.append({"id": "board:RB3Gen2", "kind": "board", "label": "RB3Gen2", "layer": "board"})
    nodes.append({"id": f"dts:{entry_dts.name}", "kind": "dts_entry", "label": entry_dts.name, "layer": "dts"})
    edges.append({"from": "board:RB3Gen2", "to": f"dts:{entry_dts.name}", "relation": "defines"})

    for file_entry in source_file_entries:
        file_path = Path(str(file_entry.get("path", "")))
        file_node_id = f"dtsi:{file_path.name}"
        nodes.append({"id": file_node_id, "kind": "dtsi_file", "label": file_path.name, "layer": "dts"})
        edges.append({"from": f"dts:{entry_dts.name}", "to": file_node_id, "relation": "includes_or_references"})

    for card in static_context.get("sound_card_nodes", []):
        if not isinstance(card, dict):
            continue
        node = str(card.get("node", "unknown"))
        model = str(card.get("model", "unknown"))
        card_id = f"soundcard:{node}"
        nodes.append({"id": card_id, "kind": "sound_card", "label": model, "layer": "sound_card"})
        edges.append({"from": "board:RB3Gen2", "to": card_id, "relation": "has_sound_card"})

    for mapping in static_context.get("backend_frontend_mappings", []):
        if not isinstance(mapping, dict):
            continue
        fe = str(mapping.get("frontend", "")).strip()
        be = str(mapping.get("backend", "")).strip()
        if not fe or not be:
            continue
        fe_id = f"fe:{fe}"
        be_id = f"be:{be}"
        nodes.append({"id": fe_id, "kind": "frontend_dai", "label": fe, "layer": "dai"})
        nodes.append({"id": be_id, "kind": "backend_dai", "label": be, "layer": "dai"})
        edges.append({"from": fe_id, "to": be_id, "relation": "fe_to_be"})

    for codec in static_context.get("codec_nodes", []):
        if not isinstance(codec, dict):
            continue
        node = str(codec.get("node", "unknown"))
        compat = str(codec.get("compatible", "unknown"))
        codec_id = f"codec:{node}"
        nodes.append({"id": codec_id, "kind": "codec", "label": compat, "layer": "codec"})
        edges.append({"from": "board:RB3Gen2", "to": codec_id, "relation": "codec_node"})

    for marker in static_context.get("soundwire_topology_markers", []):
        value = str(marker)
        sw_id = f"soundwire:{value}"
        nodes.append({"id": sw_id, "kind": "soundwire", "label": value, "layer": "soundwire"})
        edges.append({"from": "board:RB3Gen2", "to": sw_id, "relation": "soundwire_link"})

    for widget in static_context.get("widgets", []):
        value = str(widget).strip()
        if not value:
            continue
        widget_id = f"widget:{value[:96]}"
        nodes.append({"id": widget_id, "kind": "widget", "label": value, "layer": "widget"})

    for route in static_context.get("qcom_audio_routing", []):
        if not isinstance(route, dict):
            continue
        source = str(route.get("source", "")).strip()
        sink = str(route.get("sink", "")).strip()
        if not source or not sink:
            continue
        source_id = f"route:{source}"
        sink_id = f"route:{sink}"
        nodes.append({"id": source_id, "kind": "route_node", "label": source, "layer": "routing"})
        nodes.append({"id": sink_id, "kind": "route_node", "label": sink, "layer": "routing"})
        edges.append({"from": source_id, "to": sink_id, "relation": "routing"})

    for dai in static_context.get("dai_links", []):
        value = str(dai).strip()
        if not value:
            continue
        dai_id = f"dai_link:{value[:96]}"
        nodes.append({"id": dai_id, "kind": "dai_link", "label": value, "layer": "dai_link"})
        edges.append({"from": f"dts:{entry_dts.name}", "to": dai_id, "relation": "defines_dai_link"})

    pcm_device = str(workflow.get("pcm_inference", {}).get("alsa_device", "UNKNOWN"))
    pcm_node_id = f"pcm:{pcm_device}"
    nodes.append({"id": pcm_node_id, "kind": "pcm_device", "label": pcm_device, "layer": "pcm"})
    edges.append({"from": "board:RB3Gen2", "to": pcm_node_id, "relation": "playback_pcm"})

    for mixer in _extract_mixer_controls_from_workflow(workflow):
        mid = f"mixer:{mixer}"
        nodes.append({"id": mid, "kind": "mixer_control", "label": mixer, "layer": "mixer"})
        edges.append({"from": pcm_node_id, "to": mid, "relation": "depends_on_mixer"})

    runtime_node = "runtime:playback_activation"
    nodes.append(
        {
            "id": runtime_node,
            "kind": "runtime_activation",
            "label": "playback_activation",
            "layer": "runtime",
            "route_activation_confidence": str(runtime_correlation.get("route_activation_confidence", "LOW")),
        }
    )
    edges.append({"from": pcm_node_id, "to": runtime_node, "relation": "runtime_activation"})

    unique_nodes = {str(item.get("id", "")): item for item in nodes if str(item.get("id", ""))}
    return {
        "entry_dts": str(entry_dts),
        "nodes": list(unique_nodes.values()),
        "edges": edges,
        "layers": [
            "dts_dtsi_topology",
            "sound_card_nodes",
            "dai_links",
            "frontend_dais",
            "backend_dais",
            "codec_nodes",
            "soundwire_links",
            "widgets",
            "routing_paths",
            "mixer_controls",
            "pcm_devices",
            "runtime_activation",
            "overlay_mutations",
        ],
        "governance_posture": "ADVISORY_ONLY",
    }


def _runtime_route_graph(
    *,
    runtime_evidence: Mapping[str, Any],
    workflow: Mapping[str, Any],
    runtime_correlation: Mapping[str, Any],
    phase_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    cards_before = _parse_proc_cards(str(runtime_evidence.get("pcm_before", "")))
    cards_after = _parse_proc_cards(str(runtime_evidence.get("pcm_after", "")))
    pcm_before = _parse_proc_pcm(str(runtime_evidence.get("pcm_before", "")))
    pcm_after = _parse_proc_pcm(str(runtime_evidence.get("pcm_after", "")))
    amixer_before = _parse_amixer_controls(str(runtime_evidence.get("mixer_before", "")))
    amixer_after = _parse_amixer_controls(str(runtime_evidence.get("mixer_after", "")))

    route_dependencies = list(workflow.get("mixer_dependency", {}).get("route_dependencies", []))
    route_dependencies = [str(item) for item in route_dependencies if str(item).strip()]

    backend_paths = []
    if _to_bool(runtime_correlation.get("backend_activity")) or str(
        runtime_correlation.get("route_activation_confidence", "LOW")
    ) in {"HIGH", "MEDIUM"}:
        backend_paths = route_dependencies

    transitions: list[str] = []
    if _to_bool(runtime_correlation.get("mixer_change")):
        transitions.append("mixers_applied")
    if _to_bool(runtime_correlation.get("backend_activity")):
        transitions.append("backend_enabled")
    if _to_bool(runtime_correlation.get("pcm_activation")):
        transitions.append("pcm_active")
    if _to_bool(runtime_correlation.get("playback_started")):
        transitions.append("playback_started")
    if _to_bool(runtime_correlation.get("playback_completion")):
        transitions.append("playback_completed")
    if _to_bool(runtime_correlation.get("cleanup_completed")):
        transitions.append("cleanup_completed")

    return {
        "playback_target": "speaker",
        "playback_pcm_device": str(workflow.get("playback_workflow", {}).get("playback_alsa_device", "UNKNOWN")),
        "pcm_activation_before": pcm_before,
        "pcm_activation_after": pcm_after,
        "cards_before": cards_before,
        "cards_after": cards_after,
        "active_backend_paths": backend_paths,
        "mixer_dependencies": _extract_mixer_controls_from_workflow(workflow),
        "amixer_controls_before": amixer_before,
        "amixer_controls_after": amixer_after,
        "runtime_activation": {
            "pcm_activation": _to_bool(runtime_correlation.get("pcm_activation")),
            "backend_activity": _to_bool(runtime_correlation.get("backend_activity")),
            "soundwire_activity": _to_bool(runtime_correlation.get("soundwire_activity")),
            "playback_completion": _to_bool(runtime_correlation.get("playback_completion")),
            "route_activation_confidence": str(runtime_correlation.get("route_activation_confidence", "LOW")),
            "runtime_state_transitions": transitions,
            "evidence_collection_sequence": _extract_evidence_sequence(phase_trace),
        },
    }


def _pcm_backend_correlation(
    *,
    runtime_evidence: Mapping[str, Any],
    static_context: Mapping[str, Any],
    workflow: Mapping[str, Any],
    runtime_correlation: Mapping[str, Any],
) -> dict[str, Any]:
    pcm_after = _parse_proc_pcm(str(runtime_evidence.get("pcm_after", "")))
    if not pcm_after:
        pcm_after = _parse_proc_pcm(str(runtime_evidence.get("pcm_before", "")))

    mappings = list(static_context.get("backend_frontend_mappings", []))
    if not mappings:
        derived: list[dict[str, str]] = []
        for pair in static_context.get("qcom_audio_routing", []):
            if not isinstance(pair, dict):
                continue
            source = str(pair.get("source", "")).strip()
            sink = str(pair.get("sink", "")).strip()
            source_l = source.lower()
            sink_l = sink.lower()
            source_is_fe = any(marker in source_l for marker in _FE_MARKERS)
            sink_is_fe = any(marker in sink_l for marker in _FE_MARKERS)
            source_is_be = any(marker in source_l for marker in _BE_MARKERS)
            sink_is_be = any(marker in sink_l for marker in _BE_MARKERS)
            if source_is_fe and sink_is_be:
                derived.append({"frontend": source, "backend": sink})
            elif sink_is_fe and source_is_be:
                derived.append({"frontend": sink, "backend": source})
        mappings = _merge_unique_dicts(derived, ["frontend", "backend"])
    route_dependencies = [
        str(item).strip()
        for item in workflow.get("mixer_dependency", {}).get("route_dependencies", [])
        if str(item).strip()
    ]
    codec_nodes = [
        str(item.get("compatible", "unknown"))
        for item in static_context.get("codec_nodes", [])
        if isinstance(item, dict)
    ]
    selected_pcm = str(workflow.get("pcm_inference", {}).get("alsa_device", "UNKNOWN"))

    chain_confidence = (
        "CONFIRMED"
        if _to_bool(runtime_correlation.get("playback_completion"))
        and str(runtime_correlation.get("route_activation_confidence", "LOW")) == "HIGH"
        else "INFERRED"
    )

    correlated_chains: list[dict[str, Any]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        fe = str(mapping.get("frontend", "")).strip()
        be = str(mapping.get("backend", "")).strip()
        if not fe or not be:
            continue
        correlated_chains.append(
            {
                "pcm_device": selected_pcm,
                "frontend_dai": fe,
                "backend_dai": be,
                "codec": codec_nodes[0] if codec_nodes else "UNKNOWN",
                "route_chain": [f"{fe}->{be}"],
                "confidence": chain_confidence,
            }
        )
    if not correlated_chains and route_dependencies:
        correlated_chains.append(
            {
                "pcm_device": selected_pcm,
                "frontend_dai": "INFERRED",
                "backend_dai": "INFERRED",
                "codec": codec_nodes[0] if codec_nodes else "UNKNOWN",
                "route_chain": route_dependencies,
                "confidence": "INFERRED",
            }
        )

    backend_by_fe: dict[str, list[str]] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        fe = str(mapping.get("frontend", "")).strip()
        be = str(mapping.get("backend", "")).strip()
        if not fe or not be:
            continue
        backend_by_fe.setdefault(fe, []).append(be)

    ambiguous_backend_links = [
        {"frontend": fe, "backends": sorted(set(backends))}
        for fe, backends in backend_by_fe.items()
        if len(set(backends)) > 1
    ]

    unresolved_routes = []
    static_route_set = set(
        f"{item.get('frontend', '')}->{item.get('backend', '')}"
        for item in mappings
        if isinstance(item, dict)
    )
    for route in static_context.get("qcom_audio_routing", []):
        if not isinstance(route, dict):
            continue
        source = str(route.get("source", "")).strip()
        sink = str(route.get("sink", "")).strip()
        if source and sink:
            static_route_set.add(f"{source}->{sink}")
    for route in route_dependencies:
        if route not in static_route_set and route not in unresolved_routes:
            unresolved_routes.append(route)

    skipped = runtime_evidence.get("snapshot_skipped_commands", [])
    unsupported_mixer_evidence = [
        str(item.get("command", ""))
        for item in skipped
        if isinstance(item, dict) and str(item.get("command", "")) in {"tinymix", "amixer"}
    ]

    return {
        "selected_pcm_device": selected_pcm,
        "runtime_pcm_entries": pcm_after,
        "fe_be_mappings": mappings,
        "route_dependencies": route_dependencies,
        "correlated_chains": correlated_chains,
        "ambiguous_backend_links": ambiguous_backend_links,
        "unresolved_routes": unresolved_routes,
        "runtime_only_inferred_paths": unresolved_routes,
        "unsupported_mixer_evidence": unsupported_mixer_evidence,
    }


def _playback_route_trace(
    *,
    run_id: str,
    phase_trace: list[dict[str, Any]],
    workflow: Mapping[str, Any],
    profile_payload: Mapping[str, Any],
    baseline_profile: Mapping[str, Any] | None,
    procedural_lock: Mapping[str, Any] | None,
    runtime_route_graph: Mapping[str, Any],
) -> dict[str, Any]:
    command_sequence = _extract_command_sequence(phase_trace)
    evidence_sequence = _extract_evidence_sequence(phase_trace)
    route_dependencies = [
        str(item).strip()
        for item in workflow.get("mixer_dependency", {}).get("route_dependencies", [])
        if str(item).strip()
    ]
    backend_activation_ordering = route_dependencies
    mixer_dependency_chains = _extract_mixer_controls_from_workflow(workflow)

    baseline_pcm = str((baseline_profile or {}).get("pcm", {}).get("signature_sha256", ""))
    baseline_route = str((baseline_profile or {}).get("route", {}).get("route_fingerprint", ""))
    current_pcm = str(profile_payload.get("pcm", {}).get("signature_sha256", ""))
    current_route = str(profile_payload.get("route", {}).get("route_fingerprint", ""))
    baseline_play = _to_float((baseline_profile or {}).get("runtime_timing", {}).get("playback_runtime_seconds"))
    current_play = _to_float(profile_payload.get("runtime_timing", {}).get("playback_runtime_seconds"))
    playback_runtime_drift = abs(current_play - baseline_play) if baseline_play > 0 else 0.0
    playback_runtime_within_baseline = (
        playback_runtime_drift <= max(1.0, baseline_play * 0.1) if baseline_play > 0 else True
    )

    def _ordered_subset(small: list[str], large: list[str]) -> bool:
        if not small or not large:
            return False
        index = 0
        for item in large:
            if item == small[index]:
                index += 1
                if index == len(small):
                    return True
        return False

    expected_order = list((procedural_lock or {}).get("command_ordering", []))
    command_ordering_match = bool(
        command_sequence
        and expected_order
        and (
            command_sequence == expected_order
            or _ordered_subset(command_sequence, expected_order)
            or _ordered_subset(expected_order, command_sequence)
        )
    )
    evidence_expected = list((procedural_lock or {}).get("evidence_collection_sequence", []))
    evidence_ordering_match = bool(
        evidence_sequence
        and evidence_expected
        and (
            evidence_sequence == evidence_expected
            or _ordered_subset(evidence_sequence, evidence_expected)
            or _ordered_subset(evidence_expected, evidence_sequence)
        )
    )

    return {
        "run_id": run_id,
        "execution_ordering": command_sequence,
        "evidence_collection_sequence": evidence_sequence,
        "backend_activation_ordering": backend_activation_ordering,
        "mixer_dependency_chains": mixer_dependency_chains,
        "runtime_state_transitions": list(runtime_route_graph.get("runtime_activation", {}).get("runtime_state_transitions", [])),
        "deterministic_alignment": {
            "baseline_pcm_match": bool(baseline_pcm and current_pcm and baseline_pcm == current_pcm),
            "baseline_route_match": bool(baseline_route and current_route and baseline_route == current_route),
            "playback_runtime_drift_seconds": round(playback_runtime_drift, 6),
            "playback_runtime_within_baseline_window": playback_runtime_within_baseline,
            "command_ordering_match_locked_sequence": command_ordering_match,
            "evidence_ordering_match_locked_sequence": evidence_ordering_match,
        },
    }


def _build_targeted_questions(
    *,
    overlay_conflicting: bool,
    codec_missing: bool,
    route_unresolved: bool,
    board_variant_uncertain: bool,
    playback_endpoint_uncertain: bool,
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    if overlay_conflicting:
        questions.append(
            {
                "id": "overlay_identity",
                "question": "Topology confidence is low: provide exact active RB3Gen2 overlay DTSI filename.",
            }
        )
    if playback_endpoint_uncertain:
        questions.append(
            {
                "id": "playback_endpoint",
                "question": "Confirm intended playback endpoint (speaker/headset/earpiece) for this run.",
            }
        )
    if codec_missing:
        questions.append(
            {
                "id": "codec_identity",
                "question": "Codec endpoint could not be confirmed from evidence. Provide codec identity from target.",
            }
        )
    if route_unresolved:
        questions.append(
            {
                "id": "intended_route",
                "question": "Confirm intended FE->BE route chain for playback validation.",
            }
        )
    if board_variant_uncertain:
        questions.append(
            {
                "id": "board_variant",
                "question": "Board variant evidence is ambiguous. Confirm exact board variant (RB3Gen2 expected).",
            }
        )
    return questions


def _topology_confidence_report(
    *,
    static_context: Mapping[str, Any],
    overlay_mutation_graph: Mapping[str, Any],
    pcm_backend_correlation: Mapping[str, Any],
    playback_route_trace: Mapping[str, Any],
    runtime_correlation: Mapping[str, Any],
) -> dict[str, Any]:
    has_sound_card = bool(static_context.get("sound_card_nodes"))
    has_dai = bool(static_context.get("dai_links"))
    has_routing = bool(static_context.get("qcom_audio_routing"))
    static_score = (
        1.0
        if has_sound_card and has_dai and has_routing
        else 0.75
        if (has_routing and (has_sound_card or has_dai))
        else 0.4
        if has_routing
        else 0.1
    )

    route_conf = str(runtime_correlation.get("route_activation_confidence", "LOW"))
    runtime_score = (
        1.0
        if route_conf == "HIGH" and _to_bool(runtime_correlation.get("playback_completion"))
        else 0.7
        if route_conf == "MEDIUM" and _to_bool(runtime_correlation.get("playback_completion"))
        else 0.3
        if _to_bool(runtime_correlation.get("playback_started"))
        else 0.1
    )

    overlay_conflicting = _to_bool(overlay_mutation_graph.get("merged_runtime_topology_reasoning", {}).get("conflicting_overlays"))
    overlay_files = overlay_mutation_graph.get("overlay_files", [])
    overlay_score = 0.3 if overlay_conflicting else 0.8 if overlay_files else 0.5

    deterministic = playback_route_trace.get("deterministic_alignment", {})
    deterministic_score = (
        (
            (1.0 if _to_bool(deterministic.get("baseline_pcm_match")) else 0.0)
            + (1.0 if _to_bool(deterministic.get("baseline_route_match")) else 0.0)
            + (1.0 if _to_bool(deterministic.get("playback_runtime_within_baseline_window")) else 0.0)
            + (1.0 if _to_bool(deterministic.get("command_ordering_match_locked_sequence")) else 0.0)
        )
        / 4.0
    )

    topology_confidence = round(
        (0.35 * static_score) + (0.30 * runtime_score) + (0.15 * overlay_score) + (0.20 * deterministic_score),
        3,
    )

    ambiguous_backend_links = list(pcm_backend_correlation.get("ambiguous_backend_links", []))
    unresolved_routes = list(pcm_backend_correlation.get("unresolved_routes", []))
    runtime_only_paths = list(pcm_backend_correlation.get("runtime_only_inferred_paths", []))
    unsupported_mixer = list(pcm_backend_correlation.get("unsupported_mixer_evidence", []))

    confirmed_topology: list[str] = []
    inferred_mappings: list[str] = []

    if _to_bool(deterministic.get("baseline_pcm_match")):
        confirmed_topology.append("Stable PCM fingerprint aligned with deterministic baseline.")
    if _to_bool(deterministic.get("baseline_route_match")):
        confirmed_topology.append("Stable route fingerprint aligned with deterministic baseline.")
    if route_conf == "HIGH" and _to_bool(runtime_correlation.get("playback_completion")):
        confirmed_topology.append("Runtime playback completion confirms active route chain.")

    if not confirmed_topology:
        inferred_mappings.append("Topology mapping inferred from partial runtime and static evidence.")
    if runtime_only_paths:
        inferred_mappings.append("Some runtime paths exist without static FE/BE confirmation.")

    topology_state = (
        "CONFIRMED"
        if topology_confidence >= 0.85 and not ambiguous_backend_links and not unresolved_routes and not overlay_conflicting
        else "INFERRED"
        if topology_confidence >= 0.55
        else "LOW_CONFIDENCE"
    )

    entry_dts_text = str(static_context.get("entry_dts", "")).lower()
    board_variant_uncertain = ("rb3gen2" not in entry_dts_text) and ("qcs6490" not in entry_dts_text)
    playback_endpoint_uncertain = False
    codec_missing = not bool(static_context.get("codec_nodes"))
    route_unresolved = bool(unresolved_routes)
    targeted_questions = _build_targeted_questions(
        overlay_conflicting=overlay_conflicting,
        codec_missing=codec_missing,
        route_unresolved=route_unresolved,
        board_variant_uncertain=board_variant_uncertain,
        playback_endpoint_uncertain=playback_endpoint_uncertain,
    )
    targeted_mode = topology_state == "LOW_CONFIDENCE" or bool(targeted_questions)

    return {
        "topology_state": topology_state,
        "topology_confidence": topology_confidence,
        "static_topology_confidence": round(static_score, 3),
        "runtime_correlation_confidence": round(runtime_score, 3),
        "overlay_confidence": round(overlay_score, 3),
        "deterministic_alignment_confidence": round(deterministic_score, 3),
        "deterministic_alignment": deterministic,
        "confirmed_topology": confirmed_topology,
        "inferred_mappings": inferred_mappings,
        "ambiguous_backend_links": ambiguous_backend_links,
        "unresolved_routes": unresolved_routes,
        "conflicting_overlays": overlay_conflicting,
        "unsupported_mixer_evidence": unsupported_mixer,
        "runtime_only_inferred_paths": runtime_only_paths,
        "targeted_interrogation_mode": targeted_mode,
        "targeted_questions": targeted_questions,
        "governance_posture": "ADVISORY_ONLY",
        "fail_closed": True,
    }


@dataclass(frozen=True)
class TopologyCognitionResult:
    topology_graph: dict[str, Any]
    runtime_route_graph: dict[str, Any]
    overlay_mutation_graph: dict[str, Any]
    pcm_backend_correlation: dict[str, Any]
    playback_route_trace: dict[str, Any]
    topology_confidence_report: dict[str, Any]


def build_rb3_topology_cognition(
    *,
    run_id: str,
    entry_dts: str | Path,
    static_context: Mapping[str, Any],
    workflow: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    runtime_correlation: Mapping[str, Any],
    phase_trace: list[dict[str, Any]],
    profile_payload: Mapping[str, Any],
    baseline_profile: Mapping[str, Any] | None,
    procedural_lock: Mapping[str, Any] | None,
) -> TopologyCognitionResult:
    entry_path = Path(entry_dts).resolve()
    source_files = [Path(str(item)) for item in static_context.get("source_files", []) if str(item).strip()]
    source_entries = [_parse_source_topology(path) for path in source_files]

    topology_graph = _topology_graph(
        entry_dts=entry_path,
        static_context=static_context,
        source_file_entries=source_entries,
        workflow=workflow,
        runtime_correlation=runtime_correlation,
    )
    runtime_route_graph = _runtime_route_graph(
        runtime_evidence=runtime_evidence,
        workflow=workflow,
        runtime_correlation=runtime_correlation,
        phase_trace=phase_trace,
    )
    overlay_mutation_graph = _overlay_mutation_graph(
        entry_dts=entry_path,
        source_file_entries=source_entries,
        static_context=static_context,
    )
    pcm_backend_correlation = _pcm_backend_correlation(
        runtime_evidence=runtime_evidence,
        static_context=static_context,
        workflow=workflow,
        runtime_correlation=runtime_correlation,
    )
    playback_route_trace = _playback_route_trace(
        run_id=run_id,
        phase_trace=phase_trace,
        workflow=workflow,
        profile_payload=profile_payload,
        baseline_profile=baseline_profile,
        procedural_lock=procedural_lock,
        runtime_route_graph=runtime_route_graph,
    )
    topology_confidence_report = _topology_confidence_report(
        static_context=static_context,
        overlay_mutation_graph=overlay_mutation_graph,
        pcm_backend_correlation=pcm_backend_correlation,
        playback_route_trace=playback_route_trace,
        runtime_correlation=runtime_correlation,
    )
    topology_confidence_report["confidence_fingerprint"] = _stable_hash(
        {
            "topology_confidence": topology_confidence_report.get("topology_confidence", 0.0),
            "topology_state": topology_confidence_report.get("topology_state", "LOW_CONFIDENCE"),
            "deterministic_alignment": topology_confidence_report.get("deterministic_alignment", {}),
            "generated_at": _utc_now_iso(),
        }
    )

    return TopologyCognitionResult(
        topology_graph=topology_graph,
        runtime_route_graph=runtime_route_graph,
        overlay_mutation_graph=overlay_mutation_graph,
        pcm_backend_correlation=pcm_backend_correlation,
        playback_route_trace=playback_route_trace,
        topology_confidence_report=topology_confidence_report,
    )


class RB3ProceduralRouteMemory:
    """Persistent procedural topology memory for RB3Gen2 playback routes."""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def _default_payload(self) -> dict[str, Any]:
        now = _utc_now_iso()
        return {
            "schema_version": "1.0",
            "board": "RB3Gen2",
            "created_at": now,
            "updated_at": now,
            "runs": [],
            "stable_pcm_fingerprints": [],
            "stable_route_fingerprints": [],
            "successful_playback_routes": [],
            "backend_activation_orderings": [],
            "mixer_dependency_chains": [],
            "runtime_evidence_patterns": [],
            "overlay_specific_procedural_flows": [],
            "confidence_history": [],
        }

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._default_payload()
        return json.loads(self._path.read_text(encoding="utf-8"))

    def save(self, payload: Mapping[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")

    def record_run(
        self,
        *,
        run_id: str,
        profile_id: str,
        overlay: str,
        process_success: bool,
        evidence_success: bool,
        topology_state: str,
        topology_confidence: float,
        pcm_signature: str,
        route_fingerprint: str,
        successful_playback_route: list[str],
        backend_activation_ordering: list[str],
        mixer_dependency_chains: list[str],
        runtime_evidence_pattern: Mapping[str, Any],
        overlay_mutation_delta: Mapping[str, Any],
        deterministic_alignment: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = self.load()

        payload["updated_at"] = _utc_now_iso()
        run = {
            "run_id": run_id,
            "recorded_at": _utc_now_iso(),
            "profile_id": profile_id,
            "overlay": overlay,
            "process_success": process_success,
            "evidence_success": evidence_success,
            "topology_state": topology_state,
            "topology_confidence": round(_to_float(topology_confidence), 3),
            "pcm_signature": pcm_signature,
            "route_fingerprint": route_fingerprint,
        }
        payload.setdefault("runs", []).append(run)
        payload["runs"] = payload["runs"][-500:]

        if pcm_signature and pcm_signature not in payload.setdefault("stable_pcm_fingerprints", []):
            payload["stable_pcm_fingerprints"].append(pcm_signature)
        if route_fingerprint and route_fingerprint not in payload.setdefault("stable_route_fingerprints", []):
            payload["stable_route_fingerprints"].append(route_fingerprint)

        route_entry = {
            "overlay": overlay,
            "route_chain": list(successful_playback_route),
            "route_fingerprint": route_fingerprint,
        }
        if route_entry not in payload.setdefault("successful_playback_routes", []):
            payload["successful_playback_routes"].append(route_entry)

        backend_entry = {"overlay": overlay, "ordering": list(backend_activation_ordering)}
        if backend_entry not in payload.setdefault("backend_activation_orderings", []):
            payload["backend_activation_orderings"].append(backend_entry)

        mixer_entry = {"overlay": overlay, "chain": list(mixer_dependency_chains)}
        if mixer_entry not in payload.setdefault("mixer_dependency_chains", []):
            payload["mixer_dependency_chains"].append(mixer_entry)

        evidence_entry = dict(runtime_evidence_pattern)
        if evidence_entry not in payload.setdefault("runtime_evidence_patterns", []):
            payload["runtime_evidence_patterns"].append(evidence_entry)

        overlay_entry = {
            "overlay": overlay,
            "mutation_delta": dict(overlay_mutation_delta),
            "deterministic_alignment": dict(deterministic_alignment),
        }
        if overlay_entry not in payload.setdefault("overlay_specific_procedural_flows", []):
            payload["overlay_specific_procedural_flows"].append(overlay_entry)

        payload.setdefault("confidence_history", []).append(
            {
                "run_id": run_id,
                "recorded_at": _utc_now_iso(),
                "topology_confidence": round(_to_float(topology_confidence), 3),
                "topology_state": topology_state,
            }
        )
        payload["confidence_history"] = payload["confidence_history"][-500:]

        self.save(payload)
        return payload
