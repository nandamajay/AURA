"""Static DTS/DTSI audio cognition parser for Linux governance planning.

The parser is intentionally heuristic and fail-closed. It preserves raw evidence and
returns UNKNOWN-style ambiguity markers instead of asserting semantic certainty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_INCLUDE_RE = re.compile(r'^\s*#include\s+["<]([^">]+)[">]', re.MULTILINE)
_NODE_RE = re.compile(r'^\s*([A-Za-z0-9_\-]+:)?\s*([A-Za-z0-9,._@/+\-]+)\s*\{', re.MULTILINE)
_COMPAT_RE = re.compile(r'compatible\s*=\s*(.*?);', re.DOTALL)
_QSTR_RE = re.compile(r'"([^"]+)"')
_AUDIO_ROUTING_RE = re.compile(r'qcom,audio-routing\s*=\s*(.*?);', re.DOTALL)
_SOUNDWIRE_RE = re.compile(r'\b(soundwire|swr\d+|wsa|rx_macro|tx_macro|va_macro)\b', re.IGNORECASE)
_DAI_LINK_RE = re.compile(r'\b(dai-link\d*|link-name)\b', re.IGNORECASE)
_WIDGET_RE = re.compile(r'\b(widget|widgets|dapm)\b', re.IGNORECASE)

_CODEC_MARKERS = (
    "wcd",
    "codec",
    "rt5682",
    "rt1011",
    "max983",
    "tas",
    "es83",
)

_FE_MARKERS = (
    "multimedia",
    "mm",
    "hostless",
    "compress",
    "voip",
)

_BE_MARKERS = (
    "primary",
    "secondary",
    "tertiary",
    "quaternary",
    "rx",
    "tx",
    "slim",
    "i2s",
    "wsa",
    "va",
    "dmic",
)


@dataclass(frozen=True)
class DtsAudioCognitionResult:
    context: dict[str, Any]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _collect_includes(text: str) -> list[str]:
    return [match.group(1) for match in _INCLUDE_RE.finditer(text)]


def _resolve_include(include_name: str, parent: Path) -> Path | None:
    if include_name.startswith("dt-bindings/"):
        return None

    candidate = (parent.parent / include_name).resolve()
    if candidate.exists() and candidate.is_file():
        return candidate

    # Fallback search under parent tree for quoted includes with partial paths.
    matches = list(parent.parent.rglob(Path(include_name).name))
    if len(matches) == 1:
        return matches[0]
    return None


def _extract_audio_routing(text: str) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for match in _AUDIO_ROUTING_RE.finditer(text):
        quoted = _QSTR_RE.findall(match.group(1))
        for index in range(0, len(quoted) - 1, 2):
            pairs.append({"source": quoted[index], "sink": quoted[index + 1]})
    return pairs


def _extract_codec_nodes(text: str) -> list[dict[str, str]]:
    nodes: list[dict[str, str]] = []
    current_node = ""
    for line in text.splitlines():
        node_match = _NODE_RE.search(line)
        if node_match:
            current_node = node_match.group(2)
        if "compatible" not in line:
            continue
        compat_items = _QSTR_RE.findall(line)
        for compat in compat_items:
            lowered = compat.lower()
            if any(marker in lowered for marker in _CODEC_MARKERS):
                nodes.append(
                    {
                        "node": current_node or "unknown_node",
                        "compatible": compat,
                    }
                )
    return nodes


def _extract_sound_cards(text: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    node_name = ""
    for line in text.splitlines():
        node_match = _NODE_RE.search(line)
        if node_match:
            node_name = node_match.group(2)

        if "model =" in line and node_name:
            for model in _QSTR_RE.findall(line):
                cards.append({"node": node_name, "model": model})

        if "qcom,model" in line and node_name:
            for model in _QSTR_RE.findall(line):
                cards.append({"node": node_name, "model": model})
    return cards


def _extract_widgets(text: str) -> list[str]:
    widgets: list[str] = []
    for match in _WIDGET_RE.finditer(text):
        widgets.append(match.group(0).lower())
    return sorted(set(widgets))


def _extract_dai_links(text: str) -> list[str]:
    links: list[str] = []
    for line in text.splitlines():
        if _DAI_LINK_RE.search(line):
            links.append(line.strip())
    return links


def _extract_soundwire_markers(text: str) -> list[str]:
    return sorted(set(marker.lower() for marker in _SOUNDWIRE_RE.findall(text)))


def _build_be_fe_mapping(routing: list[dict[str, str]]) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    for pair in routing:
        source = pair["source"]
        sink = pair["sink"]
        source_l = source.lower()
        sink_l = sink.lower()

        source_is_fe = any(marker in source_l for marker in _FE_MARKERS)
        sink_is_fe = any(marker in sink_l for marker in _FE_MARKERS)
        source_is_be = any(marker in source_l for marker in _BE_MARKERS)
        sink_is_be = any(marker in sink_l for marker in _BE_MARKERS)

        if source_is_fe and sink_is_be:
            mappings.append({"frontend": source, "backend": sink})
        elif sink_is_fe and source_is_be:
            mappings.append({"frontend": sink, "backend": source})
    return mappings


def parse_dts_audio_cognition(
    entry_dts: str | Path,
    *,
    max_include_depth: int = 2,
) -> DtsAudioCognitionResult:
    """Parse DTS/DTSI audio signals for governance-side cognition planning.

    The parser keeps ambiguity explicit. Missing files become UNKNOWN evidence,
    never inferred success.
    """

    root = Path(entry_dts).resolve()
    visited: set[Path] = set()
    files_to_parse: list[tuple[Path, int]] = [(root, 0)]

    source_files: list[str] = []
    include_graph: list[dict[str, str]] = []
    unresolved_includes: list[dict[str, str]] = []

    sound_cards: list[dict[str, str]] = []
    codec_nodes: list[dict[str, str]] = []
    dai_links: list[str] = []
    widgets: list[str] = []
    soundwire_markers: list[str] = []
    audio_routing: list[dict[str, str]] = []

    while files_to_parse:
        current, depth = files_to_parse.pop(0)
        if current in visited:
            continue
        visited.add(current)

        text = _read_text(current)
        if not text:
            unresolved_includes.append(
                {
                    "from": str(current),
                    "include": "__self__",
                    "reason": "unreadable_or_missing",
                }
            )
            continue

        source_files.append(str(current))
        sound_cards.extend(_extract_sound_cards(text))
        codec_nodes.extend(_extract_codec_nodes(text))
        dai_links.extend(_extract_dai_links(text))
        widgets.extend(_extract_widgets(text))
        soundwire_markers.extend(_extract_soundwire_markers(text))
        audio_routing.extend(_extract_audio_routing(text))

        if depth >= max_include_depth:
            continue

        for include_name in _collect_includes(text):
            resolved = _resolve_include(include_name, current)
            if resolved is None:
                unresolved_includes.append(
                    {
                        "from": str(current),
                        "include": include_name,
                        "reason": "not_resolved",
                    }
                )
                continue
            include_graph.append({"from": str(current), "include": str(resolved)})
            files_to_parse.append((resolved, depth + 1))

    audio_routing_unique: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pair in audio_routing:
        key = (pair["source"], pair["sink"])
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        audio_routing_unique.append(pair)

    codec_unique: list[dict[str, str]] = []
    seen_codecs: set[tuple[str, str]] = set()
    for item in codec_nodes:
        key = (item["node"], item["compatible"])
        if key in seen_codecs:
            continue
        seen_codecs.add(key)
        codec_unique.append(item)

    be_fe_mapping = _build_be_fe_mapping(audio_routing_unique)

    overlay_candidates = [
        Path(path).name
        for path in source_files
        if any(token in path.lower() for token in ("overlay", "audio", "audioreach"))
    ]

    context: dict[str, Any] = {
        "entry_dts": str(root),
        "source_files": sorted(set(source_files)),
        "include_graph": include_graph,
        "unresolved_includes": unresolved_includes,
        "sound_card_nodes": sound_cards,
        "dai_links": sorted(set(dai_links)),
        "backend_frontend_mappings": be_fe_mapping,
        "qcom_audio_routing": audio_routing_unique,
        "soundwire_topology_markers": sorted(set(soundwire_markers)),
        "codec_nodes": codec_unique,
        "overlay_inheritance": {
            "overlay_candidates": sorted(set(overlay_candidates)),
            "ambiguous": len(set(overlay_candidates)) > 1,
        },
        "widgets": sorted(set(widgets)),
        "parse_confidence": "MEDIUM" if source_files else "LOW",
        "governance_posture": "ADVISORY_ONLY",
    }
    return DtsAudioCognitionResult(context=context)
