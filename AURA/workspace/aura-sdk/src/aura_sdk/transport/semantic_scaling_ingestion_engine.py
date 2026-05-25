"""Large-scale Linux audio semantic ingestion expansion engine.

Source-derived, deterministic, fail-closed semantic ingestion with:
- recursive driver discovery
- incremental file/cache invalidation
- typed graph generation
- DAPM topology extraction
- topology replay simulation
- lineage/evidence preservation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aura_sdk.transport.deterministic_serialization import (
    deterministic_uuid,
    dump_canonical_json,
    normalize_path,
    stable_sha256,
)


_DISCOVERY_PATTERNS = (
    "sound/soc/qcom/**/*.c",
    "sound/soc/codecs/**/*.c",
    "techpack/audio/**/*.c",
    "include/sound/**/*.h",
)
_ALLOWED_EXTENSIONS = {".c", ".h"}
_PARSER_VERSION = "aura-semantic-parser-v2"
_SCHEMA_VERSION = "1.0"
_DEFAULT_MAX_PATHS = 200_000

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+[<"]([^>"]+)[>"]', re.MULTILINE)
_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Z][A-Z0-9_]+)\b", re.MULTILINE)
_UPPER_MACRO_USE_RE = re.compile(r"\b([A-Z][A-Z0-9_]{2,})\b")
_DAPM_WIDGET_RE = re.compile(r'\bSND_SOC_DAPM_([A-Z0-9_]+)\s*\(\s*"([^"]+)"')
_DAPM_ROUTE_ENTRY_RE = re.compile(r'\{\s*"([^"]+)"\s*,\s*(?:"([^"]*)"|NULL)\s*,\s*"([^"]+)"\s*\}')
_KCONTROL_STRUCT_RE = re.compile(r"\bstruct\s+snd_kcontrol_new\s+([A-Za-z_][A-Za-z0-9_]*)")
_CONTROL_MACRO_RE = re.compile(r'\b(SOC(?:_DAPM)?_[A-Z0-9_]+)\s*\(\s*"([^"]+)"')
_SOC_ENUM_RE = re.compile(r"\bSOC_ENUM(?:_SINGLE(?:_DECL)?)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)")
_FUNC_DEF_RE = re.compile(
    r"^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:unsigned\s+)?"
    r"(?:int|void|bool|long|short|size_t|ssize_t|u8|u16|u32|u64|s8|s16|s32|s64|"
    r"struct\s+[A-Za-z_][A-Za-z0-9_]*\s*\*?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{",
    re.MULTILINE,
)
_FUNC_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DAI_LINK_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_dai_link\s+([A-Za-z_][A-Za-z0-9_]*)")
_APR_IFACE_RE = re.compile(r"\b(apr_[a-zA-Z0-9_]+)\b")
_DSP_IFACE_RE = re.compile(r"\b(?:q6_[a-zA-Z0-9_]+|spf_[a-zA-Z0-9_]+|adsp_[a-zA-Z0-9_]+)\b")
_SOUNDWIRE_RE = re.compile(r"\b(?:soundwire|swr_[a-zA-Z0-9_]+|sdw_[a-zA-Z0-9_]+)\b", re.IGNORECASE)
_CLOCK_RE = re.compile(r"\b(?:clk_[a-zA-Z0-9_]+|clock_[a-zA-Z0-9_]+|devm_clk_get|clk_get|clk_prepare_enable)\b")
_STREAM_TOKEN_RE = re.compile(r'"([^"\n]*(?:PCM|Playback|Capture|MultiMedia)[^"\n]*)"')
_EVENT_HANDLER_RE = re.compile(r"\.event\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")

_CALL_SKIP = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "likely",
    "unlikely",
}

_PLAYBACK_HINTS = ("playback", "rx", "speaker", "spk", "aif")
_CAPTURE_HINTS = ("capture", "tx", "mic", "adc")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(values: Iterable[str]) -> list[str]:
    return sorted({str(v).strip() for v in values if str(v).strip()})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_subsystem(rel: str) -> str:
    text = rel.strip("/")
    if text.startswith("sound/soc/qcom/"):
        return "sound/soc/qcom"
    if text.startswith("sound/soc/codecs/"):
        return "sound/soc/codecs"
    if text.startswith("techpack/audio/"):
        return "techpack/audio"
    if text.startswith("include/sound/"):
        return "include/sound"
    return "/".join(text.split("/")[:3]) if text else "unknown"


def _classify_dai_name(name: str) -> str:
    lower = name.lower()
    if "_fe_" in lower or "frontend" in lower or lower.endswith("_fe_links"):
        return "frontend"
    if "_be_" in lower or "backend" in lower or lower.endswith("_be_links"):
        return "backend"
    return "unclassified"


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(h in low for h in hints)


def _parse_file(path: Path, rel_path: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    includes = _dedupe_sorted(_INCLUDE_RE.findall(text))
    defines = _dedupe_sorted(_DEFINE_RE.findall(text))
    macro_uses = _dedupe_sorted(_UPPER_MACRO_USE_RE.findall(text))
    dapm_widgets = [
        {"widget_type": str(kind), "name": str(name)}
        for kind, name in _DAPM_WIDGET_RE.findall(text)
    ]
    dapm_routes = [
        {"sink": str(sink), "control": str(control or ""), "source": str(source)}
        for sink, control, source in _DAPM_ROUTE_ENTRY_RE.findall(text)
    ]
    controls = [
        {"macro": str(macro), "name": str(name)}
        for macro, name in _CONTROL_MACRO_RE.findall(text)
    ]
    kcontrol_structs = _dedupe_sorted(_KCONTROL_STRUCT_RE.findall(text))
    soc_enums = _dedupe_sorted(_SOC_ENUM_RE.findall(text))
    func_defs = _dedupe_sorted(_FUNC_DEF_RE.findall(text))
    calls = [
        item
        for item in _FUNC_CALL_RE.findall(text)
        if item not in _CALL_SKIP and not item.startswith("SND_SOC_")
    ]
    func_calls = _dedupe_sorted(calls)
    dai_links = _dedupe_sorted(_DAI_LINK_RE.findall(text))
    apr_interfaces = _dedupe_sorted(_APR_IFACE_RE.findall(text))
    dsp_interfaces = _dedupe_sorted(_DSP_IFACE_RE.findall(text))
    soundwire_devices = _dedupe_sorted(_SOUNDWIRE_RE.findall(text))
    clocks = _dedupe_sorted(_CLOCK_RE.findall(text))
    stream_paths = _dedupe_sorted(_STREAM_TOKEN_RE.findall(text))
    event_handlers = _dedupe_sorted(_EVENT_HANDLER_RE.findall(text))

    frontend_dais = [name for name in dai_links if _classify_dai_name(name) == "frontend"]
    backend_dais = [name for name in dai_links if _classify_dai_name(name) == "backend"]

    parse_payload = {
        "relative_path": rel_path,
        "subsystem": _file_subsystem(rel_path),
        "includes": includes,
        "defines": defines,
        "macro_uses": macro_uses,
        "dapm_widgets": sorted(dapm_widgets, key=lambda row: (row["name"], row["widget_type"])),
        "dapm_routes": sorted(
            dapm_routes, key=lambda row: (row["source"], row["sink"], row["control"])
        ),
        "controls": sorted(controls, key=lambda row: (row["name"], row["macro"])),
        "kcontrol_structs": kcontrol_structs,
        "soc_enums": soc_enums,
        "function_defs": func_defs,
        "function_calls": func_calls,
        "dai_links": dai_links,
        "frontend_dais": _dedupe_sorted(frontend_dais),
        "backend_dais": _dedupe_sorted(backend_dais),
        "apr_interfaces": apr_interfaces,
        "dsp_interfaces": dsp_interfaces,
        "soundwire_devices": soundwire_devices,
        "clocks": clocks,
        "stream_paths": stream_paths,
        "event_handlers": event_handlers,
    }
    parse_payload["semantic_fingerprint"] = stable_sha256(parse_payload)
    return parse_payload


def _topology_paths(routes: list[dict[str, str]], *, mode: str) -> list[list[str]]:
    adjacency: dict[str, set[str]] = {}
    nodes: set[str] = set()
    for route in routes:
        src = str(route.get("source", "")).strip()
        sink = str(route.get("sink", "")).strip()
        if not src or not sink:
            continue
        adjacency.setdefault(src, set()).add(sink)
        nodes.add(src)
        nodes.add(sink)

    sources = [node for node in sorted(nodes) if _contains_any(node, _PLAYBACK_HINTS if mode == "playback" else _CAPTURE_HINTS)]
    sinks = [node for node in sorted(nodes) if _contains_any(node, _PLAYBACK_HINTS if mode == "playback" else _CAPTURE_HINTS)]
    if not sources or not sinks:
        return []

    max_paths = 256
    found: list[list[str]] = []

    for source in sources[:64]:
        stack: list[tuple[str, list[str]]] = [(source, [source])]
        while stack and len(found) < max_paths:
            node, path = stack.pop()
            if len(path) > 24:
                continue
            if node in sinks and len(path) > 1:
                found.append(path)
            for nxt in sorted(adjacency.get(node, set()), reverse=True):
                if nxt in path:
                    continue
                stack.append((nxt, [*path, nxt]))
        if len(found) >= max_paths:
            break
    return found


def _detect_cycles(edges: list[tuple[str, str]]) -> bool:
    graph: dict[str, set[str]] = {}
    for src, dst in edges:
        graph.setdefault(src, set()).add(dst)
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in graph.get(node, set()):
            if dfs(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(dfs(node) for node in list(graph.keys()))


@dataclass(frozen=True)
class SemanticScalingResult:
    discovery_registry: dict[str, Any]
    incremental_ingestion_report: dict[str, Any]
    include_dependency_graph: dict[str, Any]
    function_call_graph: dict[str, Any]
    macro_lineage_graph: dict[str, Any]
    dapm_route_graph: dict[str, Any]
    clock_dependency_graph: dict[str, Any]
    control_propagation_graph: dict[str, Any]
    subsystem_ownership_graph: dict[str, Any]
    stream_path_relationships: dict[str, Any]
    backend_frontend_dai_graph: dict[str, Any]
    inter_driver_dependency_graph: dict[str, Any]
    topology_model: dict[str, Any]
    simulation_replay: dict[str, Any]
    transition_log: dict[str, Any]
    failure_diagnostics: dict[str, Any]
    cache_state: dict[str, Any]
    summary: dict[str, Any]


class SemanticScalingIngestionEngine:
    """Large-scale semantic ingestion expansion with incremental rebuild."""

    def __init__(self, *, parser_version: str = _PARSER_VERSION) -> None:
        self._parser_version = parser_version

    def _discover(self, source_root: Path, max_paths: int) -> list[str]:
        discovered: set[str] = set()
        for pattern in _DISCOVERY_PATTERNS:
            for path in source_root.glob(pattern):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in _ALLOWED_EXTENSIONS:
                    continue
                rel = normalize_path(path, repo_root=source_root)
                discovered.add(rel)
                if len(discovered) >= max_paths:
                    break
            if len(discovered) >= max_paths:
                break
        return sorted(discovered)

    async def _parse_async(
        self,
        source_root: Path,
        rel_paths: list[str],
        workers: int,
    ) -> dict[str, dict[str, Any]]:
        semaphore = asyncio.Semaphore(max(1, workers))
        out: dict[str, dict[str, Any]] = {}

        async def _run_one(rel: str) -> None:
            async with semaphore:
                file_path = (source_root / rel).resolve()
                parsed = await asyncio.to_thread(_parse_file, file_path, rel)
                out[rel] = parsed

        await asyncio.gather(*[_run_one(rel) for rel in sorted(rel_paths)])
        return out

    def _build_include_reverse_deps(self, parsed_by_file: Mapping[str, Any], headers: set[str]) -> dict[str, list[str]]:
        reverse: dict[str, set[str]] = {header: set() for header in headers}
        header_by_name: dict[str, set[str]] = {}
        for header in headers:
            name = Path(header).name
            header_by_name.setdefault(name, set()).add(header)

        for rel, parsed in sorted(parsed_by_file.items()):
            includes = _as_list(_as_dict(parsed).get("includes"))
            for include in includes:
                token = str(include).strip()
                if not token:
                    continue
                candidates: set[str] = set()
                if token in headers:
                    candidates.add(token)
                basename = Path(token).name
                candidates.update(header_by_name.get(basename, set()))
                for candidate in candidates:
                    reverse.setdefault(candidate, set()).add(str(rel))

        return {key: sorted(values) for key, values in sorted(reverse.items()) if values}

    def _build_graphs(
        self,
        parsed_by_file: Mapping[str, Any],
        source_root: Path,
        lineage_id: str,
    ) -> dict[str, dict[str, Any]]:
        files = sorted(parsed_by_file.keys())
        include_edges: list[dict[str, Any]] = []
        call_edges: list[dict[str, Any]] = []
        macro_edges: list[dict[str, Any]] = []
        dapm_edges: list[dict[str, Any]] = []
        clock_edges: list[dict[str, Any]] = []
        control_edges: list[dict[str, Any]] = []
        ownership_edges: list[dict[str, Any]] = []
        dai_edges: list[dict[str, Any]] = []
        inter_driver_edges: list[dict[str, Any]] = []

        all_widgets: list[str] = []
        all_routes: list[dict[str, str]] = []
        all_controls: list[str] = []
        stream_paths: set[str] = set()
        frontend_dais: set[str] = set()
        backend_dais: set[str] = set()
        include_name_to_file: dict[str, set[str]] = {}

        for rel in files:
            parsed = _as_dict(parsed_by_file[rel])
            subsystem = str(parsed.get("subsystem", "unknown"))
            ownership_edges.append(
                {
                    "edge_type": "owns_file",
                    "source": subsystem,
                    "target": rel,
                    "evidence": {"file": rel},
                }
            )

            include_name_to_file.setdefault(Path(rel).name, set()).add(rel)

            for include in _as_list(parsed.get("includes")):
                include_token = str(include)
                include_edges.append(
                    {
                        "edge_type": "includes",
                        "source": rel,
                        "target": include_token,
                        "evidence": {"file": rel},
                    }
                )
                include_base = Path(include_token).name
                for matched_file in sorted(include_name_to_file.get(include_base, set())):
                    if matched_file == rel:
                        continue
                    inter_driver_edges.append(
                        {
                            "edge_type": "depends_on_driver",
                            "source": rel,
                            "target": matched_file,
                            "evidence": {"file": rel, "include": include_token},
                        }
                    )

            for macro in _as_list(parsed.get("defines")):
                macro_edges.append(
                    {
                        "edge_type": "defines_macro",
                        "source": rel,
                        "target": str(macro),
                        "evidence": {"file": rel},
                    }
                )
            for macro in _as_list(parsed.get("macro_uses")):
                macro_edges.append(
                    {
                        "edge_type": "uses_macro",
                        "source": rel,
                        "target": str(macro),
                        "evidence": {"file": rel},
                    }
                )

            funcs = _as_list(parsed.get("function_defs"))
            calls = _as_list(parsed.get("function_calls"))
            for src in funcs[:120]:
                for dst in calls[:160]:
                    if str(src) == str(dst):
                        continue
                    call_edges.append(
                        {
                            "edge_type": "calls",
                            "source": str(src),
                            "target": str(dst),
                            "evidence": {"file": rel},
                        }
                    )

            for widget in _as_list(parsed.get("dapm_widgets")):
                item = _as_dict(widget)
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                all_widgets.append(name)
            for route in _as_list(parsed.get("dapm_routes")):
                item = _as_dict(route)
                src = str(item.get("source", "")).strip()
                sink = str(item.get("sink", "")).strip()
                control = str(item.get("control", "")).strip()
                if not src or not sink:
                    continue
                row = {"source": src, "sink": sink, "control": control, "file": rel}
                all_routes.append(row)
                dapm_edges.append(
                    {
                        "edge_type": "dapm_route",
                        "source": src,
                        "target": sink,
                        "attributes": {"control": control},
                        "evidence": {"file": rel},
                    }
                )
            for control in _as_list(parsed.get("controls")):
                name = str(_as_dict(control).get("name", "")).strip()
                if name:
                    all_controls.append(name)
            for token in _as_list(parsed.get("clocks")):
                clock_edges.append(
                    {
                        "edge_type": "clock_dependency",
                        "source": rel,
                        "target": str(token),
                        "evidence": {"file": rel},
                    }
                )
            for path in _as_list(parsed.get("stream_paths")):
                stream_paths.add(str(path))
            for name in _as_list(parsed.get("frontend_dais")):
                frontend_dais.add(str(name))
            for name in _as_list(parsed.get("backend_dais")):
                backend_dais.add(str(name))

        control_tokens = {
            name: {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}
            for name in _dedupe_sorted(all_controls)
        }
        widgets_sorted = _dedupe_sorted(all_widgets)
        for control_name, tokens in sorted(control_tokens.items()):
            for widget in widgets_sorted:
                widget_tokens = {token for token in re.split(r"[^a-z0-9]+", widget.lower()) if token}
                if not tokens or not widget_tokens:
                    continue
                if tokens.intersection(widget_tokens):
                    control_edges.append(
                        {
                            "edge_type": "control_affects_widget",
                            "source": control_name,
                            "target": widget,
                            "evidence": {"derived_from": "token_intersection"},
                        }
                    )

        fe_sorted = sorted(frontend_dais)
        be_sorted = sorted(backend_dais)
        for fe in fe_sorted:
            fe_tokens = {token for token in re.split(r"[^a-z0-9]+", fe.lower()) if token}
            candidates = [be for be in be_sorted if fe_tokens.intersection({t for t in re.split(r"[^a-z0-9]+", be.lower()) if t})]
            if not candidates and be_sorted:
                candidates = [be_sorted[0]]
            for be in candidates[:4]:
                dai_edges.append(
                    {
                        "edge_type": "frontend_backend_link",
                        "source": fe,
                        "target": be,
                        "evidence": {"derived_from": "dai_token_similarity"},
                    }
                )

        playback_paths = _topology_paths(all_routes, mode="playback")
        capture_paths = _topology_paths(all_routes, mode="capture")
        route_pairs = [(r["source"], r["sink"]) for r in all_routes]
        cycle_detected = _detect_cycles(route_pairs)
        unknown_widgets = sorted(
            {
                endpoint
                for r in all_routes
                for endpoint in (r["source"], r["sink"])
                if endpoint not in set(widgets_sorted)
            }
        )

        topology_model = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_topology_model",
            "lineage_id": lineage_id,
            "source_root": normalize_path(source_root),
            "widgets": widgets_sorted,
            "routes": sorted(all_routes, key=lambda row: (row["source"], row["sink"], row["control"], row["file"])),
            "controls": sorted(all_controls),
            "stream_paths": sorted(stream_paths),
            "frontend_dais": fe_sorted,
            "backend_dais": be_sorted,
            "playback_paths": playback_paths,
            "capture_paths": capture_paths,
            "unknown_widget_references": unknown_widgets,
            "cycle_detected": cycle_detected,
            "classification": "FAIL_CLOSED" if unknown_widgets else "PASS",
            "fail_closed_reasons": (
                ["topology_references_unknown_widgets"] if unknown_widgets else []
            ) + (["topology_cycle_detected"] if cycle_detected else []),
        }
        topology_model["deterministic_fingerprint"] = stable_sha256(topology_model)

        transition_steps: list[dict[str, Any]] = []
        step_idx = 0
        for mode, paths in (("playback", playback_paths), ("capture", capture_paths)):
            for chain in paths[:128]:
                for i in range(len(chain) - 1):
                    step_idx += 1
                    transition_steps.append(
                        {
                            "step": step_idx,
                            "mode": mode,
                            "action": "enable_route",
                            "source": chain[i],
                            "target": chain[i + 1],
                        }
                    )
        mux_conflicts = []
        sink_to_controls: dict[str, set[str]] = {}
        for row in all_routes:
            if not row["control"]:
                continue
            sink_to_controls.setdefault(row["sink"], set()).add(row["control"])
        for sink, controls in sorted(sink_to_controls.items()):
            if len(controls) > 1:
                mux_conflicts.append({"sink": sink, "controls": sorted(controls)})

        simulation_replay = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_runtime_replay_simulation",
            "lineage_id": lineage_id,
            "topology_fingerprint": topology_model["deterministic_fingerprint"],
            "classification": "FAIL_CLOSED"
            if topology_model["classification"] != "PASS" or mux_conflicts
            else "PASS",
            "fail_closed_reasons": (
                ([] if topology_model["classification"] == "PASS" else list(topology_model["fail_closed_reasons"]))
                + (["stream_conflict_detected"] if mux_conflicts else [])
            ),
            "playback_path_count": len(playback_paths),
            "capture_path_count": len(capture_paths),
            "transition_count": len(transition_steps),
            "mux_conflicts": mux_conflicts,
            "invalid_states": (
                [{"type": "unknown_widget_reference", "widgets": unknown_widgets}] if unknown_widgets else []
            ),
        }
        simulation_replay["replay_fingerprint"] = stable_sha256(
            {
                "topology_fingerprint": topology_model["deterministic_fingerprint"],
                "playback_path_count": simulation_replay["playback_path_count"],
                "capture_path_count": simulation_replay["capture_path_count"],
                "transition_count": simulation_replay["transition_count"],
                "mux_conflicts": mux_conflicts,
                "invalid_states": simulation_replay["invalid_states"],
            }
        )
        simulation_replay["deterministic_fingerprint"] = stable_sha256(simulation_replay)

        transition_log = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_simulation_transition_log",
            "lineage_id": lineage_id,
            "classification": "PASS",
            "transitions": transition_steps,
            "deterministic_fingerprint": stable_sha256(
                {"lineage_id": lineage_id, "transitions": transition_steps}
            ),
        }

        def _graph_payload(name: str, edges: list[dict[str, Any]]) -> dict[str, Any]:
            payload = {
                "schema_version": _SCHEMA_VERSION,
                "graph_name": name,
                "lineage_id": lineage_id,
                "edge_count": len(edges),
                "edges": sorted(
                    edges,
                    key=lambda row: (
                        str(row.get("edge_type", "")),
                        str(row.get("source", "")),
                        str(row.get("target", "")),
                    ),
                ),
            }
            payload["deterministic_fingerprint"] = stable_sha256(payload)
            return payload

        return {
            "include_dependency_graph": _graph_payload("semantic_include_dependency_graph", include_edges),
            "function_call_graph": _graph_payload("semantic_function_call_graph", call_edges),
            "macro_lineage_graph": _graph_payload("semantic_macro_lineage_graph", macro_edges),
            "dapm_route_graph": _graph_payload("semantic_dapm_route_graph", dapm_edges),
            "clock_dependency_graph": _graph_payload("semantic_clock_dependency_graph", clock_edges),
            "control_propagation_graph": _graph_payload("semantic_control_propagation_graph", control_edges),
            "subsystem_ownership_graph": _graph_payload("semantic_subsystem_ownership_graph", ownership_edges),
            "stream_path_relationships": {
                "schema_version": _SCHEMA_VERSION,
                "graph_name": "semantic_stream_path_relationships",
                "lineage_id": lineage_id,
                "playback_paths": playback_paths,
                "capture_paths": capture_paths,
                "deterministic_fingerprint": stable_sha256(
                    {
                        "lineage_id": lineage_id,
                        "playback_paths": playback_paths,
                        "capture_paths": capture_paths,
                    }
                ),
            },
            "backend_frontend_dai_graph": _graph_payload(
                "semantic_backend_frontend_dai_graph", dai_edges
            ),
            "inter_driver_dependency_graph": _graph_payload(
                "semantic_inter_driver_dependency_graph", inter_driver_edges
            ),
            "topology_model": topology_model,
            "simulation_replay": simulation_replay,
            "transition_log": transition_log,
        }

    async def run(
        self,
        *,
        source_root: str | Path,
        output_dir: str | Path,
        cache_file: str | Path | None = None,
        max_paths: int = _DEFAULT_MAX_PATHS,
        workers: int = 8,
        evidence_references: list[str] | None = None,
    ) -> SemanticScalingResult:
        start_ts = datetime.now(timezone.utc)
        root = Path(source_root).resolve()
        out_dir = Path(output_dir).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        cache_path = Path(cache_file).resolve() if cache_file else (out_dir / "semantic_cache_state.json")
        evidence = _dedupe_sorted(evidence_references or [])

        if not root.exists() or not root.is_dir():
            fail = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_scaling_failure_diagnostics",
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["source_root_missing_or_invalid"],
                "source_root": str(root),
                "generated_at": _utc_now_iso(),
            }
            fail["deterministic_fingerprint"] = stable_sha256(fail)
            summary = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_scaling_summary",
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["source_root_missing_or_invalid"],
                "source_root": str(root),
                "generated_at": _utc_now_iso(),
            }
            summary["deterministic_fingerprint"] = stable_sha256(summary)
            return SemanticScalingResult(
                discovery_registry={},
                incremental_ingestion_report={},
                include_dependency_graph={},
                function_call_graph={},
                macro_lineage_graph={},
                dapm_route_graph={},
                clock_dependency_graph={},
                control_propagation_graph={},
                subsystem_ownership_graph={},
                stream_path_relationships={},
                backend_frontend_dai_graph={},
                inter_driver_dependency_graph={},
                topology_model={},
                simulation_replay={},
                transition_log={},
                failure_diagnostics=fail,
                cache_state={},
                summary=summary,
            )

        discovered = self._discover(root, max_paths=max_paths)
        headers = {rel for rel in discovered if rel.endswith(".h")}
        file_hashes = {rel: _sha256_file((root / rel).resolve()) for rel in discovered}
        corpus_fingerprint = stable_sha256({"files": sorted(file_hashes.items())})
        lineage_id = deterministic_uuid(f"semantic_scaling:{normalize_path(root)}:{corpus_fingerprint}")

        previous_cache = {}
        if cache_path.exists():
            try:
                previous_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                previous_cache = {}
        cached_files = _as_dict(previous_cache.get("files"))
        previous_parsed = _as_dict(previous_cache.get("parsed"))
        previous_includes = _as_dict(previous_cache.get("include_reverse_deps"))

        changed: set[str] = set()
        removed: set[str] = set(set(cached_files.keys()) - set(discovered))
        for rel in discovered:
            old = _as_dict(cached_files.get(rel))
            if str(old.get("sha256", "")) != str(file_hashes.get(rel, "")):
                changed.add(rel)

        header_change_dependents: set[str] = set()
        for rel in sorted(changed):
            if not rel.endswith(".h"):
                continue
            for dependent in _as_list(previous_includes.get(rel)):
                header_change_dependents.add(str(dependent))
        to_reparse = sorted(set(changed).union(header_change_dependents))

        parsed_by_file: dict[str, dict[str, Any]] = {}
        reused_count = 0
        for rel in discovered:
            if rel not in to_reparse and rel in previous_parsed:
                parsed_by_file[rel] = _as_dict(previous_parsed.get(rel))
                reused_count += 1

        reparsed = await self._parse_async(root, to_reparse, workers=workers) if to_reparse else {}
        parsed_by_file.update(reparsed)
        parsed_by_file = {rel: _as_dict(parsed_by_file.get(rel)) for rel in sorted(parsed_by_file.keys())}

        include_reverse_deps = self._build_include_reverse_deps(parsed_by_file, headers)
        graphs = self._build_graphs(parsed_by_file, root, lineage_id)

        codecs = sorted(
            {
                rel
                for rel in discovered
                if rel.startswith("sound/soc/codecs/") or "codec" in Path(rel).name.lower()
            }
        )
        machine_drivers = sorted(
            {
                rel
                for rel in discovered
                if any(token in Path(rel).name.lower() for token in ("machine", "card"))
            }
        )
        aggregate = {
            "dais": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("dai_links"))
            ),
            "frontend_dais": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("frontend_dais"))
            ),
            "backend_dais": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("backend_dais"))
            ),
            "dapm_widgets": _dedupe_sorted(
                _as_dict(widget).get("name", "")
                for rel in discovered
                for widget in _as_list(_as_dict(parsed_by_file.get(rel)).get("dapm_widgets"))
            ),
            "dapm_routes": [
                route
                for rel in discovered
                for route in _as_list(_as_dict(parsed_by_file.get(rel)).get("dapm_routes"))
            ],
            "controls": _dedupe_sorted(
                _as_dict(item).get("name", "")
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("controls"))
            ),
            "mixers": _dedupe_sorted(
                _as_dict(item).get("name", "")
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("controls"))
                if "MIXER" in str(_as_dict(item).get("macro", "")).upper()
            ),
            "muxes": _dedupe_sorted(
                _as_dict(item).get("name", "")
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("controls"))
                if "MUX" in str(_as_dict(item).get("macro", "")).upper()
            ),
            "kcontrols": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("kcontrol_structs"))
            ),
            "soundwire_devices": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("soundwire_devices"))
            ),
            "apr_interfaces": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("apr_interfaces"))
            ),
            "dsp_interfaces": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("dsp_interfaces"))
            ),
            "clocks": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("clocks"))
            ),
            "macros": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("defines"))
            ),
            "stream_paths": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("stream_paths"))
            ),
            "widgets": _dedupe_sorted(
                _as_dict(widget).get("name", "")
                for rel in discovered
                for widget in _as_list(_as_dict(parsed_by_file.get(rel)).get("dapm_widgets"))
            ),
            "codecs": codecs,
            "machine_drivers": machine_drivers,
        }

        subsystem_groups: dict[str, list[str]] = {}
        for rel in discovered:
            subsystem_groups.setdefault(_file_subsystem(rel), []).append(rel)
        subsystem_groups = {key: sorted(value) for key, value in sorted(subsystem_groups.items())}

        discovery_registry = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_driver_discovery_registry",
            "parser_version": self._parser_version,
            "lineage_id": lineage_id,
            "source_root": normalize_path(root),
            "discovery_patterns": list(_DISCOVERY_PATTERNS),
            "file_count": len(discovered),
            "files": discovered,
            "subsystem_groups": subsystem_groups,
            "registry": aggregate,
            "evidence_references": evidence,
            "generated_at": _utc_now_iso(),
        }
        discovery_registry["deterministic_fingerprint"] = stable_sha256(discovery_registry)

        parse_lineage = {
            rel: {
                "source_sha256": file_hashes[rel],
                "semantic_fingerprint": str(_as_dict(parsed_by_file.get(rel)).get("semantic_fingerprint", "")),
                "parser_version": self._parser_version,
                "subsystem": str(_as_dict(parsed_by_file.get(rel)).get("subsystem", "unknown")),
            }
            for rel in discovered
        }
        incremental_ingestion_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_incremental_ingestion_report",
            "parser_version": self._parser_version,
            "lineage_id": lineage_id,
            "classification": "PASS",
            "changed_files": sorted(changed),
            "removed_files": sorted(removed),
            "header_invalidation_dependents": sorted(header_change_dependents),
            "reparsed_files": sorted(reparsed.keys()),
            "reused_files": sorted(set(discovered) - set(reparsed.keys())),
            "reused_file_count": reused_count,
            "reparsed_file_count": len(reparsed),
            "cache_reuse_ratio": round(
                float(reused_count) / float(len(discovered)) if discovered else 0.0, 6
            ),
            "include_reverse_deps_count": len(include_reverse_deps),
            "parse_lineage": parse_lineage,
            "dependency_invalidation": {
                "dependency_engine": "include_reverse_deps",
                "graph_invalidation": sorted(set(changed).union(header_change_dependents)),
            },
            "generated_at": _utc_now_iso(),
        }
        incremental_ingestion_report["deterministic_fingerprint"] = stable_sha256(
            incremental_ingestion_report
        )

        failure_diagnostics = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_failure_diagnostics",
            "lineage_id": lineage_id,
            "classification": "FAIL_CLOSED"
            if (
                graphs["topology_model"].get("classification") != "PASS"
                or graphs["simulation_replay"].get("classification") != "PASS"
            )
            else "PASS",
            "parser_failures": [],
            "semantic_drift": [],
            "replay_mismatches": (
                ["topology_or_simulation_fail_closed"]
                if (
                    graphs["topology_model"].get("classification") != "PASS"
                    or graphs["simulation_replay"].get("classification") != "PASS"
                )
                else []
            ),
            "graph_divergence": [],
            "ingestion_bottlenecks": [],
            "cache_invalidations": {
                "changed_files": sorted(changed),
                "header_dependents": sorted(header_change_dependents),
            },
            "extraction_latency_seconds": round(
                (datetime.now(timezone.utc) - start_ts).total_seconds(), 6
            ),
            "generated_at": _utc_now_iso(),
        }
        failure_diagnostics["deterministic_fingerprint"] = stable_sha256(failure_diagnostics)

        cache_state = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_cache_state",
            "parser_version": self._parser_version,
            "lineage_id": lineage_id,
            "source_root": normalize_path(root),
            "files": {
                rel: {
                    "sha256": file_hashes[rel],
                    "semantic_fingerprint": str(
                        _as_dict(parsed_by_file.get(rel)).get("semantic_fingerprint", "")
                    ),
                }
                for rel in discovered
            },
            "parsed": parsed_by_file,
            "include_reverse_deps": include_reverse_deps,
            "generated_at": _utc_now_iso(),
        }
        cache_state["deterministic_fingerprint"] = stable_sha256(
            {
                "parser_version": cache_state["parser_version"],
                "source_root": cache_state["source_root"],
                "files": cache_state["files"],
                "include_reverse_deps": cache_state["include_reverse_deps"],
            }
        )

        summary = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_scaling_summary",
            "lineage_id": lineage_id,
            "classification": "FAIL_CLOSED"
            if (
                failure_diagnostics["classification"] != "PASS"
                or graphs["topology_model"].get("classification") != "PASS"
                or graphs["simulation_replay"].get("classification") != "PASS"
            )
            else "PASS",
            "file_count": len(discovered),
            "changed_file_count": len(changed),
            "reparsed_file_count": len(reparsed),
            "reused_file_count": reused_count,
            "cache_reuse_ratio": incremental_ingestion_report["cache_reuse_ratio"],
            "edge_counts": {
                "include": int(graphs["include_dependency_graph"].get("edge_count", 0)),
                "call": int(graphs["function_call_graph"].get("edge_count", 0)),
                "macro": int(graphs["macro_lineage_graph"].get("edge_count", 0)),
                "dapm": int(graphs["dapm_route_graph"].get("edge_count", 0)),
            },
            "topology_classification": graphs["topology_model"].get("classification", "UNKNOWN"),
            "simulation_classification": graphs["simulation_replay"].get("classification", "UNKNOWN"),
            "generated_at": _utc_now_iso(),
        }
        summary["deterministic_fingerprint"] = stable_sha256(summary)

        # persist deterministic artifacts
        dump_canonical_json(out_dir / "semantic_driver_discovery_registry.json", discovery_registry)
        dump_canonical_json(out_dir / "semantic_incremental_ingestion_report.json", incremental_ingestion_report)
        dump_canonical_json(out_dir / "semantic_include_dependency_graph.json", graphs["include_dependency_graph"])
        dump_canonical_json(out_dir / "semantic_function_call_graph.json", graphs["function_call_graph"])
        dump_canonical_json(out_dir / "semantic_macro_lineage_graph.json", graphs["macro_lineage_graph"])
        dump_canonical_json(out_dir / "semantic_dapm_route_graph.json", graphs["dapm_route_graph"])
        dump_canonical_json(out_dir / "semantic_clock_dependency_graph.json", graphs["clock_dependency_graph"])
        dump_canonical_json(out_dir / "semantic_control_propagation_graph.json", graphs["control_propagation_graph"])
        dump_canonical_json(out_dir / "semantic_subsystem_ownership_graph.json", graphs["subsystem_ownership_graph"])
        dump_canonical_json(out_dir / "semantic_stream_path_relationships.json", graphs["stream_path_relationships"])
        dump_canonical_json(out_dir / "semantic_backend_frontend_dai_graph.json", graphs["backend_frontend_dai_graph"])
        dump_canonical_json(out_dir / "semantic_inter_driver_dependency_graph.json", graphs["inter_driver_dependency_graph"])
        dump_canonical_json(out_dir / "semantic_topology_model.json", graphs["topology_model"])
        dump_canonical_json(out_dir / "semantic_runtime_replay_simulation.json", graphs["simulation_replay"])
        dump_canonical_json(out_dir / "semantic_simulation_transition_log.json", graphs["transition_log"])
        dump_canonical_json(out_dir / "semantic_failure_diagnostics.json", failure_diagnostics)
        dump_canonical_json(cache_path, cache_state)
        dump_canonical_json(out_dir / "semantic_scaling_summary.json", summary)

        return SemanticScalingResult(
            discovery_registry=discovery_registry,
            incremental_ingestion_report=incremental_ingestion_report,
            include_dependency_graph=graphs["include_dependency_graph"],
            function_call_graph=graphs["function_call_graph"],
            macro_lineage_graph=graphs["macro_lineage_graph"],
            dapm_route_graph=graphs["dapm_route_graph"],
            clock_dependency_graph=graphs["clock_dependency_graph"],
            control_propagation_graph=graphs["control_propagation_graph"],
            subsystem_ownership_graph=graphs["subsystem_ownership_graph"],
            stream_path_relationships=graphs["stream_path_relationships"],
            backend_frontend_dai_graph=graphs["backend_frontend_dai_graph"],
            inter_driver_dependency_graph=graphs["inter_driver_dependency_graph"],
            topology_model=graphs["topology_model"],
            simulation_replay=graphs["simulation_replay"],
            transition_log=graphs["transition_log"],
            failure_diagnostics=failure_diagnostics,
            cache_state=cache_state,
            summary=summary,
        )
