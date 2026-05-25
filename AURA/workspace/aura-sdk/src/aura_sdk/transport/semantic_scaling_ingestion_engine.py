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
_PARSER_VERSION = "aura-semantic-parser-v3"
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
_OPS_STRUCT_RE = re.compile(
    r"\bstruct\s+(snd_soc_dai_ops|snd_pcm_ops)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.*?)\};",
    re.DOTALL,
)
_OPS_FIELD_RE = re.compile(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")
_CONFIG_CONDITION_RE = re.compile(r"^\s*#\s*if(?:n?def)?\s+([A-Za-z0-9_()|&! ]+)", re.MULTILINE)
_FUNCTION_START_RE = re.compile(
    r"^\s*(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:unsigned\s+)?"
    r"(?:int|void|bool|long|short|size_t|ssize_t|u8|u16|u32|u64|s8|s16|s32|s64|"
    r"struct\s+[A-Za-z_][A-Za-z0-9_]*\s*\*?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{",
    re.MULTILINE,
)

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

_OPS_INTEREST_FIELDS = (
    "open",
    "startup",
    "hw_params",
    "prepare",
    "trigger",
    "set_fmt",
    "set_sysclk",
    "hw_free",
    "shutdown",
    "close",
)
_STATE_TRANSITIONS: dict[str, tuple[str, str]] = {
    "open": ("idle", "opened"),
    "startup": ("idle", "opened"),
    "hw_params": ("opened", "params_set"),
    "set_fmt": ("opened", "format_set"),
    "set_sysclk": ("format_set", "clocked"),
    "prepare": ("params_set", "prepared"),
    "trigger": ("prepared", "running"),
    "hw_free": ("stopped", "opened"),
    "shutdown": ("stopped", "idle"),
    "close": ("stopped", "idle"),
}
_LIFECYCLE_ORDER = (
    "open",
    "startup",
    "set_fmt",
    "set_sysclk",
    "hw_params",
    "prepare",
    "trigger",
    "hw_free",
    "shutdown",
    "close",
)
_DEPENDENCY_TOKEN_HINTS: dict[str, tuple[str, ...]] = {
    "clock": ("clk_", "clock_", "devm_clk_get", "clk_get", "clk_prepare_enable"),
    "regulator": ("regulator_", "devm_regulator_get", "regulator_enable"),
    "soundwire": ("soundwire", "sdw_", "swr_"),
    "dsp": ("q6_", "spf_", "adsp_", "dsp"),
    "apr": ("apr_", "gpr_"),
    "mailbox": ("mailbox", "mbox", "qmp_"),
    "irq": ("irq", "interrupt", "request_irq"),
    "runtime_pm": ("pm_runtime", "runtime_suspend", "runtime_resume"),
    "pcm": ("snd_pcm", "substream", "runtime->"),
}


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


def _extract_function_bodies(text: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for match in _FUNCTION_START_RE.finditer(text):
        func_name = str(match.group(1))
        brace_start = text.find("{", match.start())
        if brace_start < 0:
            continue
        depth = 0
        idx = brace_start
        while idx < len(text):
            char = text[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    bodies[func_name] = text[brace_start : idx + 1]
                    break
            idx += 1
    return bodies


def _detect_dependency_tags(snippet: str) -> list[str]:
    lower = str(snippet or "").lower()
    tags = [
        name
        for name, hints in sorted(_DEPENDENCY_TOKEN_HINTS.items())
        if any(hint.lower() in lower for hint in hints)
    ]
    return sorted(tags)


def _ops_type_scope(ops_type: str) -> str:
    return "dai" if ops_type == "snd_soc_dai_ops" else "pcm"


def _detect_trigger_modes(snippet: str) -> list[str]:
    text = str(snippet or "")
    modes = []
    if "SNDRV_PCM_TRIGGER_START" in text:
        modes.append("start")
    if "SNDRV_PCM_TRIGGER_STOP" in text:
        modes.append("stop")
    if "SNDRV_PCM_TRIGGER_PAUSE_PUSH" in text:
        modes.append("pause")
    if "SNDRV_PCM_TRIGGER_RESUME" in text:
        modes.append("resume")
    return modes


def _build_lifecycle_trace(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_ops: dict[str, dict[str, Any]] = {}
    for row in bindings:
        ops_key = f'{row.get("ops_type","")}:{row.get("ops_name","")}'
        if not str(row.get("ops_name", "")).strip():
            continue
        by_ops.setdefault(ops_key, {}).update({str(row.get("stage", "")): row})

    traces: list[dict[str, Any]] = []
    for ops_key, stage_map in sorted(by_ops.items()):
        sequence = [stage for stage in _LIFECYCLE_ORDER if stage in stage_map]
        transitions = []
        for stage in sequence:
            state_from, state_to = _STATE_TRANSITIONS.get(stage, ("unknown", "unknown"))
            row = _as_dict(stage_map.get(stage))
            transitions.append(
                {
                    "stage": stage,
                    "callback": str(row.get("callback", "")),
                    "from_state": state_from,
                    "to_state": state_to,
                    "dependency_tags": _as_list(row.get("dependency_tags")),
                    "trigger_modes": _as_list(row.get("trigger_modes")),
                }
            )
        traces.append({"ops_key": ops_key, "sequence": sequence, "transitions": transitions})
    return traces


def _parse_file(path: Path, rel_path: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    function_bodies = _extract_function_bodies(text)
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
    activation_conditions = _dedupe_sorted(
        token
        for token in _CONFIG_CONDITION_RE.findall(text)
        if "CONFIG_" in str(token) or "defined(" in str(token)
    )

    frontend_dais = [name for name in dai_links if _classify_dai_name(name) == "frontend"]
    backend_dais = [name for name in dai_links if _classify_dai_name(name) == "backend"]

    ops_structs: list[dict[str, Any]] = []
    callback_bindings: list[dict[str, Any]] = []
    callback_dependency_map: dict[str, list[str]] = {}
    callback_trigger_modes: dict[str, list[str]] = {}
    for ops_type, ops_name, body in _OPS_STRUCT_RE.findall(text):
        callbacks: dict[str, str] = {}
        for field, callback in _OPS_FIELD_RE.findall(body):
            if field not in _OPS_INTEREST_FIELDS:
                continue
            callback_name = str(callback).strip()
            if not callback_name:
                continue
            snippet = function_bodies.get(callback_name, "")
            dependency_tags = _detect_dependency_tags(snippet)
            trigger_modes = _detect_trigger_modes(snippet) if field == "trigger" else []
            callbacks[str(field)] = callback_name
            callback_dependency_map[callback_name] = dependency_tags
            if trigger_modes:
                callback_trigger_modes[callback_name] = trigger_modes
            callback_bindings.append(
                {
                    "ops_type": str(ops_type),
                    "ops_scope": _ops_type_scope(str(ops_type)),
                    "ops_name": str(ops_name),
                    "stage": str(field),
                    "callback": callback_name,
                    "dependency_tags": dependency_tags,
                    "trigger_modes": trigger_modes,
                    "activation_conditions": activation_conditions,
                }
            )
        ops_structs.append(
            {
                "ops_type": str(ops_type),
                "ops_scope": _ops_type_scope(str(ops_type)),
                "ops_name": str(ops_name),
                "callbacks": {k: callbacks[k] for k in sorted(callbacks)},
            }
        )

    lifecycle_traces = _build_lifecycle_trace(callback_bindings)
    runtime_sensitive_callbacks = sorted(
        {
            str(item.get("callback", ""))
            for item in callback_bindings
            if set(_as_list(item.get("dependency_tags"))).intersection(
                {"irq", "mailbox", "dsp", "soundwire", "runtime_pm", "clock", "regulator"}
            )
        }
    )

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
        "activation_conditions": activation_conditions,
        "ops_structs": sorted(ops_structs, key=lambda row: (row["ops_scope"], row["ops_name"])),
        "dai_ops_structs": sorted(
            [row for row in ops_structs if row["ops_scope"] == "dai"],
            key=lambda row: row["ops_name"],
        ),
        "pcm_ops_structs": sorted(
            [row for row in ops_structs if row["ops_scope"] == "pcm"],
            key=lambda row: row["ops_name"],
        ),
        "callback_bindings": sorted(
            callback_bindings,
            key=lambda row: (row["ops_scope"], row["ops_name"], row["stage"], row["callback"]),
        ),
        "callback_dependency_map": {
            key: value for key, value in sorted(callback_dependency_map.items())
        },
        "callback_trigger_modes": {
            key: value for key, value in sorted(callback_trigger_modes.items())
        },
        "stream_lifecycle_traces": lifecycle_traces,
        "runtime_sensitive_callbacks": runtime_sensitive_callbacks,
    }
    parse_payload["behavioral_semantic_count"] = (
        len(parse_payload["callback_bindings"])
        + len(parse_payload["stream_lifecycle_traces"])
        + len(parse_payload["runtime_sensitive_callbacks"])
    )
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
    behavioral_state_graph: dict[str, Any]
    activation_order_graph: dict[str, Any]
    runtime_causality_graph: dict[str, Any]
    power_sequence_graph: dict[str, Any]
    causal_event_chain_graph: dict[str, Any]
    trigger_dependency_graph: dict[str, Any]
    failure_propagation_graph: dict[str, Any]
    failure_blast_radius_report: dict[str, Any]
    runtime_instability_report: dict[str, Any]
    temporal_causality_report: dict[str, Any]
    temporal_replay_divergence: dict[str, Any]
    runtime_sequence_fingerprint: dict[str, Any]
    root_cause_inference_report: dict[str, Any]
    causal_event_chains_report: dict[str, Any]
    dapm_behavioral_model: dict[str, Any]
    behavioral_replay_timeline: dict[str, Any]
    stream_intelligence_report: dict[str, Any]
    governance_confidence_report: dict[str, Any]
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
        behavioral_edges: list[dict[str, Any]] = []
        activation_edges: list[dict[str, Any]] = []
        causality_edges: list[dict[str, Any]] = []
        power_edges: list[dict[str, Any]] = []
        causal_chain_edges: list[dict[str, Any]] = []
        trigger_dependency_edges: list[dict[str, Any]] = []
        failure_edges: list[dict[str, Any]] = []
        dapm_timeline_events: list[dict[str, Any]] = []

        all_widgets: list[str] = []
        all_routes: list[dict[str, str]] = []
        all_controls: list[str] = []
        stream_paths: set[str] = set()
        frontend_dais: set[str] = set()
        backend_dais: set[str] = set()
        all_activation_conditions: set[str] = set()
        all_runtime_sensitive_callbacks: set[str] = set()
        callback_dependency_rollup: dict[str, set[str]] = {}
        callback_trigger_modes_rollup: dict[str, set[str]] = {}
        callback_owner_subsystem: dict[str, set[str]] = {}
        include_name_to_file: dict[str, set[str]] = {}
        for rel in files:
            include_name_to_file.setdefault(Path(rel).name, set()).add(rel)

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
            if funcs:
                bounded_calls = [str(item) for item in calls[:1024] if str(item).strip()]
                for idx, dst in enumerate(bounded_calls):
                    src = str(funcs[idx % len(funcs)])
                    if src == dst:
                        continue
                    call_edges.append(
                        {
                            "edge_type": "calls",
                            "source": src,
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
                dapm_timeline_events.append(
                    {
                        "event_type": "route_activation_candidate",
                        "source": src,
                        "target": sink,
                        "control": control,
                        "file": rel,
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
            for condition in _as_list(parsed.get("activation_conditions")):
                all_activation_conditions.add(str(condition))
            for callback in _as_list(parsed.get("runtime_sensitive_callbacks")):
                all_runtime_sensitive_callbacks.add(str(callback))

            callback_bindings = [
                _as_dict(item) for item in _as_list(parsed.get("callback_bindings"))
            ]
            callbacks_by_ops: dict[str, dict[str, dict[str, Any]]] = {}
            for binding in callback_bindings:
                stage = str(binding.get("stage", "")).strip()
                callback = str(binding.get("callback", "")).strip()
                ops_name = str(binding.get("ops_name", "")).strip()
                if not stage or not callback or not ops_name:
                    continue
                state_from, state_to = _STATE_TRANSITIONS.get(stage, ("unknown", "unknown"))
                behavioral_edges.append(
                    {
                        "edge_type": "state_transition",
                        "source": state_from,
                        "target": state_to,
                        "attributes": {
                            "stage": stage,
                            "callback": callback,
                            "ops_name": ops_name,
                            "ops_scope": str(binding.get("ops_scope", "")),
                        },
                        "evidence": {"file": rel},
                    }
                )
                callbacks_by_ops.setdefault(ops_name, {})[stage] = binding
                dependency_tags = [str(tag) for tag in _as_list(binding.get("dependency_tags"))]
                trigger_modes = [str(mode) for mode in _as_list(binding.get("trigger_modes"))]
                if dependency_tags:
                    callback_dependency_rollup.setdefault(callback, set()).update(dependency_tags)
                if trigger_modes:
                    callback_trigger_modes_rollup.setdefault(callback, set()).update(trigger_modes)
                callback_owner_subsystem.setdefault(callback, set()).add(subsystem)
                for tag in dependency_tags:
                    causality_edges.append(
                        {
                            "edge_type": "runtime_causality",
                            "source": callback,
                            "target": f"dependency:{tag}",
                            "attributes": {"stage": stage},
                            "evidence": {"file": rel},
                        }
                    )
                    if tag in {"clock", "regulator", "runtime_pm"}:
                        power_edges.append(
                            {
                                "edge_type": "power_sequence",
                                "source": callback,
                                "target": f"power_domain:{tag}",
                                "attributes": {"stage": stage},
                                "evidence": {"file": rel},
                            }
                        )
                for mode in trigger_modes:
                    trigger_dependency_edges.append(
                        {
                            "edge_type": "trigger_mode",
                            "source": callback,
                            "target": f"trigger:{mode}",
                            "attributes": {"stage": stage},
                            "evidence": {"file": rel},
                        }
                    )
                for tag in dependency_tags:
                    trigger_dependency_edges.append(
                        {
                            "edge_type": "trigger_dependency",
                            "source": callback,
                            "target": f"dependency:{tag}",
                            "attributes": {"stage": stage},
                            "evidence": {"file": rel},
                        }
                    )

            for ops_name, stage_map in sorted(callbacks_by_ops.items()):
                sequence = [stage for stage in _LIFECYCLE_ORDER if stage in stage_map]
                for left, right in zip(sequence, sequence[1:]):
                    activation_edges.append(
                        {
                            "edge_type": "activation_order",
                            "source": str(stage_map[left].get("callback", "")),
                            "target": str(stage_map[right].get("callback", "")),
                            "attributes": {
                                "from_stage": left,
                                "to_stage": right,
                                "ops_name": ops_name,
                            },
                            "evidence": {"file": rel},
                        }
                    )

        control_tokens = {
            name: {token for token in re.split(r"[^a-z0-9]+", name.lower()) if token}
            for name in _dedupe_sorted(all_controls)
        }
        widgets_sorted = _dedupe_sorted(all_widgets)
        widget_tokens_map: dict[str, set[str]] = {
            widget: {token for token in re.split(r"[^a-z0-9]+", widget.lower()) if token}
            for widget in widgets_sorted
        }
        widget_index: dict[str, set[str]] = {}
        for widget, tokens in sorted(widget_tokens_map.items()):
            for token in sorted(tokens):
                widget_index.setdefault(token, set()).add(widget)

        for control_name, tokens in sorted(control_tokens.items()):
            if not tokens:
                continue
            candidates: set[str] = set()
            for token in sorted(tokens):
                candidates.update(widget_index.get(token, set()))
            scored: list[tuple[int, str]] = []
            for widget in sorted(candidates):
                overlap = len(tokens.intersection(widget_tokens_map.get(widget, set())))
                if overlap > 0:
                    scored.append((-overlap, widget))
            for _, widget in sorted(scored)[:8]:
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
                causal_chain_edges.append(
                    {
                        "edge_type": "fe_be_transition",
                        "source": fe,
                        "target": be,
                        "attributes": {"relation": "frontend_to_backend"},
                        "evidence": {"derived_from": "dai_token_similarity"},
                    }
                )

        playback_paths = _topology_paths(all_routes, mode="playback")
        capture_paths = _topology_paths(all_routes, mode="capture")
        route_pairs = [(r["source"], r["sink"]) for r in all_routes]
        cycle_detected = _detect_cycles(route_pairs)
        known_widget_set = set(widgets_sorted)
        unknown_widgets = sorted(
            {
                endpoint
                for r in all_routes
                for endpoint in (r["source"], r["sink"])
                if endpoint not in known_widget_set
            }
        )

        topology_fail_reasons = (
            (["topology_references_unknown_widgets"] if unknown_widgets else [])
            + (["topology_cycle_detected"] if cycle_detected else [])
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
            "activation_conditions": sorted(all_activation_conditions),
            "runtime_sensitive_callbacks": sorted(all_runtime_sensitive_callbacks),
            "playback_paths": playback_paths,
            "capture_paths": capture_paths,
            "unknown_widget_references": unknown_widgets,
            "cycle_detected": cycle_detected,
            "classification": "FAIL_CLOSED" if topology_fail_reasons else "PASS",
            "fail_closed_reasons": topology_fail_reasons,
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
                    causal_chain_edges.append(
                        {
                            "edge_type": "route_activation",
                            "source": chain[i],
                            "target": chain[i + 1],
                            "attributes": {"mode": mode, "step": step_idx},
                            "evidence": {"derived_from": "playback_capture_path"},
                        }
                    )
        sink_to_controls: dict[str, set[str]] = {}
        for row in all_routes:
            if not row["control"]:
                continue
            sink_to_controls.setdefault(row["sink"], set()).add(row["control"])
        mux_conflicts = [
            {"sink": sink, "controls": sorted(controls)}
            for sink, controls in sorted(sink_to_controls.items())
            if len(controls) > 1
        ]

        lifecycle_events: list[dict[str, Any]] = []
        for edge in sorted(
            behavioral_edges,
            key=lambda row: (
                str(_as_dict(row.get("attributes")).get("ops_name", "")),
                str(_as_dict(row.get("attributes")).get("stage", "")),
                str(_as_dict(row.get("attributes")).get("callback", "")),
            ),
        )[:4096]:
            attrs = _as_dict(edge.get("attributes"))
            step_idx += 1
            lifecycle_events.append(
                {
                    "step": step_idx,
                    "mode": str(attrs.get("ops_scope", "runtime")),
                    "action": "callback_transition",
                    "stage": str(attrs.get("stage", "")),
                    "callback": str(attrs.get("callback", "")),
                    "ops_name": str(attrs.get("ops_name", "")),
                    "source": str(edge.get("source", "")),
                    "target": str(edge.get("target", "")),
                }
            )
            causal_chain_edges.append(
                {
                    "edge_type": "callback_transition",
                    "source": str(attrs.get("callback", "")),
                    "target": str(edge.get("target", "")),
                    "attributes": {
                        "stage": str(attrs.get("stage", "")),
                        "ops_name": str(attrs.get("ops_name", "")),
                        "step": step_idx,
                    },
                    "evidence": {"derived_from": "ops_callback_binding"},
                }
            )

        callback_stage_map: dict[str, set[str]] = {}
        for edge in behavioral_edges:
            attrs = _as_dict(edge.get("attributes"))
            callback = str(attrs.get("callback", "")).strip()
            stage = str(attrs.get("stage", "")).strip()
            if callback and stage:
                callback_stage_map.setdefault(callback, set()).add(stage)
        missing_clock_callbacks = sorted(
            callback
            for callback, stages in sorted(callback_stage_map.items())
            if stages.intersection({"hw_params", "prepare", "set_sysclk"})
            and "clock" not in callback_dependency_rollup.get(callback, set())
        )
        path_nodes = {
            node for chain in [*playback_paths, *capture_paths] for node in chain if str(node).strip()
        }
        dead_routes = sorted(
            [
                {
                    "source": str(row.get("source", "")),
                    "sink": str(row.get("sink", "")),
                    "control": str(row.get("control", "")),
                    "file": str(row.get("file", "")),
                }
                for row in all_routes
                if str(row.get("source", "")) not in path_nodes
                and str(row.get("sink", "")) not in path_nodes
            ],
            key=lambda row: (row["source"], row["sink"], row["control"], row["file"]),
        )[:512]
        invalid_routes = []
        if unknown_widgets:
            invalid_routes.append(
                {
                    "type": "unknown_widget_reference",
                    "widgets": unknown_widgets,
                }
            )
        if cycle_detected:
            invalid_routes.append({"type": "cycle_detected"})

        stream_intel_fail_reasons = (
            (["stream_conflict_detected"] if mux_conflicts else [])
            + (["missing_clock_dependency_callbacks"] if missing_clock_callbacks else [])
            + (["invalid_topology_routes_detected"] if invalid_routes else [])
        )
        stream_intelligence_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_stream_intelligence_report",
            "lineage_id": lineage_id,
            "playback_lifecycle_paths": playback_paths,
            "capture_lifecycle_paths": capture_paths,
            "fe_be_routes": sorted(
                dai_edges,
                key=lambda row: (
                    str(row.get("source", "")),
                    str(row.get("target", "")),
                ),
            )[:1024],
            "dsp_interaction_callbacks": sorted(
                [
                    callback
                    for callback, tags in sorted(callback_dependency_rollup.items())
                    if {"dsp", "apr", "mailbox"}.intersection(tags)
                ]
            ),
            "soundwire_activation_callbacks": sorted(
                [
                    callback
                    for callback, tags in sorted(callback_dependency_rollup.items())
                    if "soundwire" in tags
                ]
            ),
            "stream_conflicts": mux_conflicts,
            "dead_routes": dead_routes,
            "missing_clock_callbacks": missing_clock_callbacks,
            "invalid_routes": invalid_routes,
            "classification": "FAIL_CLOSED" if stream_intel_fail_reasons else "PASS",
            "fail_closed_reasons": stream_intel_fail_reasons,
        }
        stream_intelligence_report["deterministic_fingerprint"] = stable_sha256(
            stream_intelligence_report
        )

        dapm_behavioral_model = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_dapm_behavioral_model",
            "lineage_id": lineage_id,
            "widget_count": len(widgets_sorted),
            "route_count": len(all_routes),
            "activation_timeline": sorted(
                dapm_timeline_events,
                key=lambda row: (row["source"], row["target"], row["control"], row["file"]),
            )[:4096],
            "power_propagation_edges": sorted(
                power_edges,
                key=lambda row: (
                    str(row.get("source", "")),
                    str(row.get("target", "")),
                    str(_as_dict(row.get("attributes")).get("stage", "")),
                ),
            )[:4096],
            "classification": "FAIL_CLOSED"
            if topology_model["classification"] != "PASS"
            else "PASS",
            "fail_closed_reasons": list(topology_model["fail_closed_reasons"]),
        }
        dapm_behavioral_model["deterministic_fingerprint"] = stable_sha256(dapm_behavioral_model)

        behavioral_replay_timeline = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_behavioral_replay_timeline",
            "lineage_id": lineage_id,
            "route_transition_events": transition_steps,
            "lifecycle_transition_events": lifecycle_events,
            "combined_event_count": len(transition_steps) + len(lifecycle_events),
            "classification": "PASS",
        }
        behavioral_replay_timeline["deterministic_fingerprint"] = stable_sha256(
            behavioral_replay_timeline
        )

        simulation_fail_reasons = (
            ([] if topology_model["classification"] == "PASS" else list(topology_model["fail_closed_reasons"]))
            + (["stream_conflict_detected"] if mux_conflicts else [])
            + (["missing_clock_dependency_callbacks"] if missing_clock_callbacks else [])
        )
        simulation_replay = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_runtime_replay_simulation",
            "lineage_id": lineage_id,
            "topology_fingerprint": topology_model["deterministic_fingerprint"],
            "classification": "FAIL_CLOSED" if simulation_fail_reasons else "PASS",
            "fail_closed_reasons": simulation_fail_reasons,
            "playback_path_count": len(playback_paths),
            "capture_path_count": len(capture_paths),
            "transition_count": len(transition_steps),
            "callback_transition_count": len(lifecycle_events),
            "mux_conflicts": mux_conflicts,
            "invalid_states": (
                [{"type": "unknown_widget_reference", "widgets": unknown_widgets}] if unknown_widgets else []
            ),
            "failure_injection_simulation": {
                "missing_clock": [
                    {"callback": callback, "effect": "route_activation_blocked"}
                    for callback in missing_clock_callbacks
                ],
                "invalid_topology": invalid_routes,
            },
        }
        simulation_replay["replay_fingerprint"] = stable_sha256(
            {
                "topology_fingerprint": topology_model["deterministic_fingerprint"],
                "playback_path_count": simulation_replay["playback_path_count"],
                "capture_path_count": simulation_replay["capture_path_count"],
                "transition_count": simulation_replay["transition_count"],
                "callback_transition_count": simulation_replay["callback_transition_count"],
                "mux_conflicts": mux_conflicts,
                "invalid_states": simulation_replay["invalid_states"],
            }
        )
        simulation_replay["deterministic_fingerprint"] = stable_sha256(simulation_replay)

        activation_pair_set = {
            (
                str(edge.get("source", "")),
                str(edge.get("target", "")),
            )
            for edge in activation_edges
            if str(edge.get("source", "")).strip() and str(edge.get("target", "")).strip()
        }
        race_prone_activation_pairs = sorted(
            {
                tuple(sorted((src, dst)))
                for src, dst in activation_pair_set
                if src != dst and (dst, src) in activation_pair_set
            }
        )
        ops_stage_map: dict[str, set[str]] = {}
        for event in lifecycle_events:
            ops_name = str(_as_dict(event).get("ops_name", "")).strip()
            stage = str(_as_dict(event).get("stage", "")).strip()
            if ops_name and stage:
                ops_stage_map.setdefault(ops_name, set()).add(stage)
        partial_activation_states = sorted(
            [
                ops_name
                for ops_name, stages in sorted(ops_stage_map.items())
                if stages.intersection({"open", "startup", "hw_params", "prepare"})
                and "trigger" not in stages
            ]
        )

        for callback in missing_clock_callbacks:
            failure_edges.append(
                {
                    "edge_type": "missing_clock_propagation",
                    "source": "failure:missing_clock_dependency",
                    "target": callback,
                    "attributes": {"failure_kind": "clock"},
                    "evidence": {"derived_from": "callback_dependency_rollup"},
                }
            )
            failure_edges.append(
                {
                    "edge_type": "downstream_effect",
                    "source": callback,
                    "target": "runtime:route_activation_blocked",
                    "attributes": {"failure_kind": "clock"},
                    "evidence": {"derived_from": "stream_intelligence"},
                }
            )
        for row in mux_conflicts:
            sink = str(_as_dict(row).get("sink", "")).strip()
            if not sink:
                continue
            failure_edges.append(
                {
                    "edge_type": "stream_conflict_propagation",
                    "source": "failure:stream_conflict",
                    "target": f"route_sink:{sink}",
                    "attributes": {"controls": _as_list(_as_dict(row).get("controls"))},
                    "evidence": {"derived_from": "mux_conflicts"},
                }
            )
        for row in dead_routes:
            src = str(_as_dict(row).get("source", ""))
            sink = str(_as_dict(row).get("sink", ""))
            failure_edges.append(
                {
                    "edge_type": "dead_path_propagation",
                    "source": "failure:dead_dapm_path",
                    "target": f"route:{src}->{sink}",
                    "attributes": {"file": str(_as_dict(row).get("file", ""))},
                    "evidence": {"derived_from": "path_reconstruction"},
                }
            )
        for left, right in race_prone_activation_pairs:
            failure_edges.append(
                {
                    "edge_type": "race_prone_activation",
                    "source": "failure:race_prone_activation_order",
                    "target": f"activation_pair:{left}<->{right}",
                    "attributes": {"callbacks": [left, right]},
                    "evidence": {"derived_from": "activation_order_graph"},
                }
            )
        for callback in partial_activation_states:
            failure_edges.append(
                {
                    "edge_type": "partial_activation_state",
                    "source": "failure:partial_activation_state",
                    "target": callback,
                    "attributes": {"stages": sorted(ops_stage_map.get(callback, set()))},
                    "evidence": {"derived_from": "callback_stage_map"},
                }
            )
        if cycle_detected:
            failure_edges.append(
                {
                    "edge_type": "recursive_route_loop",
                    "source": "failure:recursive_route_loop",
                    "target": "topology:route_graph",
                    "attributes": {"cycle_detected": True},
                    "evidence": {"derived_from": "route_cycle_detection"},
                }
            )
        if invalid_routes:
            failure_edges.append(
                {
                    "edge_type": "invalid_route_activation",
                    "source": "failure:invalid_route_activation",
                    "target": "topology:invalid_routes",
                    "attributes": {"invalid_route_count": len(invalid_routes)},
                    "evidence": {"derived_from": "invalid_routes"},
                }
            )

        for edge in sorted(causality_edges, key=lambda row: (str(row.get("source", "")), str(row.get("target", ""))))[:8192]:
            causal_chain_edges.append(
                {
                    "edge_type": "dependency_propagation",
                    "source": str(edge.get("source", "")),
                    "target": str(edge.get("target", "")),
                    "attributes": _as_dict(edge.get("attributes")),
                    "evidence": _as_dict(edge.get("evidence")),
                }
            )

        ops_stage_order = {stage: idx for idx, stage in enumerate(_LIFECYCLE_ORDER)}
        causal_chains = []
        by_ops: dict[str, list[dict[str, Any]]] = {}
        for item in lifecycle_events:
            ops_name = str(_as_dict(item).get("ops_name", "")).strip() or "unknown_ops"
            by_ops.setdefault(ops_name, []).append(_as_dict(item))
        for ops_name, events in sorted(by_ops.items()):
            ordered = sorted(
                events,
                key=lambda row: (
                    ops_stage_order.get(str(row.get("stage", "")), 999),
                    int(row.get("step", 0)),
                ),
            )
            causal_chains.append(
                {
                    "chain_id": f"{ops_name}_lifecycle_chain",
                    "ops_name": ops_name,
                    "event_sequence": [
                        {
                            "stage": str(row.get("stage", "")),
                            "callback": str(row.get("callback", "")),
                            "from_state": str(row.get("source", "")),
                            "to_state": str(row.get("target", "")),
                            "order": int(row.get("step", 0)),
                        }
                        for row in ordered
                    ],
                }
            )

        propagation_paths = []
        for callback, tags in sorted(callback_dependency_rollup.items()):
            for tag in sorted(tags):
                propagation_paths.append(
                    {
                        "source": callback,
                        "through": f"dependency:{tag}",
                        "target": "runtime:state_transition",
                    }
                )
        trigger_dependency_graph = {
            "schema_version": _SCHEMA_VERSION,
            "graph_name": "semantic_trigger_dependency_graph",
            "lineage_id": lineage_id,
            "edge_count": len(trigger_dependency_edges),
            "edges": sorted(
                trigger_dependency_edges,
                key=lambda row: (
                    str(row.get("edge_type", "")),
                    str(row.get("source", "")),
                    str(row.get("target", "")),
                ),
            ),
        }
        trigger_dependency_graph["deterministic_fingerprint"] = stable_sha256(
            trigger_dependency_graph
        )

        temporal_event_ordering = sorted(
            [
                {
                    "order": int(_as_dict(row).get("step", 0)),
                    "event_type": str(_as_dict(row).get("action", "")),
                    "mode": str(_as_dict(row).get("mode", "")),
                    "stage": str(_as_dict(row).get("stage", "")),
                    "source": str(_as_dict(row).get("source", "")),
                    "target": str(_as_dict(row).get("target", "")),
                    "callback": str(_as_dict(row).get("callback", "")),
                }
                for row in [*transition_steps, *lifecycle_events]
            ],
            key=lambda row: (row["order"], row["event_type"], row["source"], row["target"]),
        )
        activation_latency_chains = [
            {
                "from_order": int(left.get("order", 0)),
                "to_order": int(right.get("order", 0)),
                "delta_steps": int(right.get("order", 0)) - int(left.get("order", 0)),
                "from_event": str(left.get("event_type", "")),
                "to_event": str(right.get("event_type", "")),
            }
            for left, right in zip(temporal_event_ordering, temporal_event_ordering[1:])
        ]

        route_sequence_fingerprint = stable_sha256(
            {
                "route_sequence": [
                    {
                        "mode": row.get("mode", ""),
                        "source": row.get("source", ""),
                        "target": row.get("target", ""),
                    }
                    for row in transition_steps
                ]
            }
        )
        lifecycle_sequence_fingerprint = stable_sha256(
            {
                "lifecycle_sequence": [
                    {
                        "stage": row.get("stage", ""),
                        "callback": row.get("callback", ""),
                        "source": row.get("source", ""),
                        "target": row.get("target", ""),
                    }
                    for row in lifecycle_events
                ]
            }
        )
        combined_sequence_fingerprint = stable_sha256(
            {
                "route": route_sequence_fingerprint,
                "lifecycle": lifecycle_sequence_fingerprint,
                "temporal_event_count": len(temporal_event_ordering),
            }
        )

        temporal_replay_divergence = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_temporal_replay_divergence",
            "lineage_id": lineage_id,
            "route_sequence_fingerprint": route_sequence_fingerprint,
            "lifecycle_sequence_fingerprint": lifecycle_sequence_fingerprint,
            "combined_sequence_fingerprint": combined_sequence_fingerprint,
            "divergence_detected": False,
            "classification": "PASS",
            "fail_closed_reasons": [],
        }
        temporal_replay_divergence["deterministic_fingerprint"] = stable_sha256(
            temporal_replay_divergence
        )

        runtime_sequence_fingerprint = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_runtime_sequence_fingerprint",
            "lineage_id": lineage_id,
            "route_sequence_fingerprint": route_sequence_fingerprint,
            "lifecycle_sequence_fingerprint": lifecycle_sequence_fingerprint,
            "combined_sequence_fingerprint": combined_sequence_fingerprint,
            "temporal_event_count": len(temporal_event_ordering),
            "classification": "PASS",
        }
        runtime_sequence_fingerprint["deterministic_fingerprint"] = stable_sha256(
            runtime_sequence_fingerprint
        )

        causal_event_chains = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_causal_event_chains",
            "lineage_id": lineage_id,
            "runtime_causality_chains": causal_chains,
            "upstream_downstream_propagation_paths": propagation_paths[:8192],
            "trigger_dependency_graph": {
                "edge_count": trigger_dependency_graph["edge_count"],
                "fingerprint": trigger_dependency_graph["deterministic_fingerprint"],
            },
            "temporal_event_ordering": temporal_event_ordering[:8192],
            "classification": "PASS" if causal_chains else "FAIL_CLOSED",
            "fail_closed_reasons": [] if causal_chains else ["causal_event_chains_empty"],
        }
        causal_event_chains["deterministic_fingerprint"] = stable_sha256(causal_event_chains)

        impacted_callbacks = set(missing_clock_callbacks).union(partial_activation_states)
        impacted_callbacks.update({str(item.get("callback", "")) for item in lifecycle_events if str(item.get("callback", "")).strip()})
        impacted_routes = {
            f"{row.get('source','')}->{row.get('sink','')}"
            for row in dead_routes
        }
        impacted_routes.update({f"{_as_dict(row).get('sink','')}" for row in mux_conflicts})
        impacted_subsystems = set()
        for callback in impacted_callbacks:
            impacted_subsystems.update(callback_owner_subsystem.get(callback, set()))
        for row in dead_routes:
            file_path = str(_as_dict(row).get("file", ""))
            if file_path:
                impacted_subsystems.add(_file_subsystem(file_path))

        failure_blast_radius_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_failure_blast_radius_report",
            "lineage_id": lineage_id,
            "impacted_callbacks": sorted(item for item in impacted_callbacks if item),
            "impacted_route_count": len(impacted_routes),
            "impacted_subsystems": sorted(item for item in impacted_subsystems if item),
            "impact_score": round(
                min(
                    1.0,
                    (
                        len(impacted_callbacks) * 0.01
                        + len(impacted_routes) * 0.02
                        + len(impacted_subsystems) * 0.05
                    ),
                ),
                6,
            ),
            "classification": "FAIL_CLOSED" if failure_edges else "PASS",
            "fail_closed_reasons": ["failure_propagation_detected"] if failure_edges else [],
        }
        failure_blast_radius_report["deterministic_fingerprint"] = stable_sha256(
            failure_blast_radius_report
        )

        runtime_instability_score = round(
            min(
                1.0,
                (
                    len(missing_clock_callbacks) * 0.3
                    + len(mux_conflicts) * 0.08
                    + len(dead_routes) * 0.01
                    + (0.2 if cycle_detected else 0.0)
                    + (0.15 if unknown_widgets else 0.0)
                    + len(race_prone_activation_pairs) * 0.1
                    + len(partial_activation_states) * 0.03
                ),
            ),
            6,
        )
        runtime_instability_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_runtime_instability_score",
            "lineage_id": lineage_id,
            "runtime_instability_score": runtime_instability_score,
            "stability_factors": {
                "missing_clock_callbacks": len(missing_clock_callbacks),
                "stream_conflicts": len(mux_conflicts),
                "dead_routes": len(dead_routes),
                "cycle_detected": bool(cycle_detected),
                "unknown_widgets": len(unknown_widgets),
                "race_prone_activation_pairs": len(race_prone_activation_pairs),
                "partial_activation_states": len(partial_activation_states),
            },
            "classification": "FAIL_CLOSED" if runtime_instability_score >= 0.25 else "PASS",
            "fail_closed_reasons": ["runtime_instability_above_threshold"]
            if runtime_instability_score >= 0.25
            else [],
        }
        runtime_instability_report["deterministic_fingerprint"] = stable_sha256(
            runtime_instability_report
        )

        failure_propagation_graph = {
            "schema_version": _SCHEMA_VERSION,
            "graph_name": "semantic_failure_propagation_graph",
            "lineage_id": lineage_id,
            "edge_count": len(failure_edges),
            "edges": sorted(
                failure_edges,
                key=lambda row: (
                    str(row.get("edge_type", "")),
                    str(row.get("source", "")),
                    str(row.get("target", "")),
                ),
            ),
            "classification": "FAIL_CLOSED" if failure_edges else "PASS",
            "fail_closed_reasons": ["failure_propagation_detected"] if failure_edges else [],
        }
        failure_propagation_graph["deterministic_fingerprint"] = stable_sha256(
            failure_propagation_graph
        )

        temporal_causality_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_temporal_causality_report",
            "lineage_id": lineage_id,
            "temporal_event_ordering": temporal_event_ordering[:8192],
            "activation_latency_chains": activation_latency_chains[:8192],
            "ordered_transition_count": len(temporal_event_ordering),
            "classification": "PASS" if temporal_event_ordering else "FAIL_CLOSED",
            "fail_closed_reasons": [] if temporal_event_ordering else ["temporal_event_ordering_empty"],
        }
        temporal_causality_report["deterministic_fingerprint"] = stable_sha256(
            temporal_causality_report
        )

        root_cause_hypotheses = []
        if missing_clock_callbacks:
            root_cause_hypotheses.append(
                {
                    "cause": "missing_sysclk_or_clock_dependency",
                    "evidence": {"callbacks": missing_clock_callbacks},
                    "confidence": 0.84,
                }
            )
        if mux_conflicts:
            root_cause_hypotheses.append(
                {
                    "cause": "invalid_mux_path",
                    "evidence": {"conflicts": mux_conflicts},
                    "confidence": 0.8,
                }
            )
        if unknown_widgets:
            root_cause_hypotheses.append(
                {
                    "cause": "missing_or_mismatched_dapm_route",
                    "evidence": {"unknown_widgets": unknown_widgets},
                    "confidence": 0.86,
                }
            )
        if cycle_detected:
            root_cause_hypotheses.append(
                {
                    "cause": "recursive_activation_dependency",
                    "evidence": {"cycle_detected": True},
                    "confidence": 0.9,
                }
            )
        if race_prone_activation_pairs:
            root_cause_hypotheses.append(
                {
                    "cause": "unstable_trigger_ordering",
                    "evidence": {"activation_pairs": race_prone_activation_pairs},
                    "confidence": 0.74,
                }
            )
        if partial_activation_states:
            root_cause_hypotheses.append(
                {
                    "cause": "partial_activation_state",
                    "evidence": {"callbacks": partial_activation_states},
                    "confidence": 0.7,
                }
            )
        root_cause_inference_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_root_cause_inference_report",
            "lineage_id": lineage_id,
            "hypotheses": root_cause_hypotheses,
            "classification": "FAIL_CLOSED" if root_cause_hypotheses else "PASS",
            "fail_closed_reasons": ["runtime_root_cause_hypotheses_detected"]
            if root_cause_hypotheses
            else [],
        }
        root_cause_inference_report["deterministic_fingerprint"] = stable_sha256(
            root_cause_inference_report
        )

        confidence_parts = {
            "semantic_completeness": round(
                (
                    (1.0 if behavioral_edges else 0.0)
                    + (1.0 if activation_edges else 0.0)
                    + (1.0 if causal_chain_edges else 0.0)
                    + (1.0 if temporal_event_ordering else 0.0)
                    + (1.0 if (playback_paths or capture_paths) else 0.0)
                )
                / 5.0,
                6,
            ),
            "parser_confidence_weighted": 1.0,
            "transition_reproducibility": 1.0 if temporal_event_ordering else 0.3,
            "causal_consistency": 1.0 if causal_chains else 0.3,
            "topology_stability": round(
                max(0.0, 1.0 - (0.35 if cycle_detected else 0.0) - (0.35 if unknown_widgets else 0.0)),
                6,
            ),
            "replay_determinism": 1.0 if not temporal_replay_divergence["divergence_detected"] else 0.0,
            "route_convergence": round(
                max(0.0, 1.0 - min(1.0, len(dead_routes) / 100.0) - (0.25 if mux_conflicts else 0.0)),
                6,
            ),
            "activation_success_consistency": round(
                max(0.0, 1.0 - min(1.0, len(partial_activation_states) / 20.0) - (0.25 if race_prone_activation_pairs else 0.0)),
                6,
            ),
        }
        overall_confidence = round(
            (
                confidence_parts["semantic_completeness"] * 0.14
                + confidence_parts["parser_confidence_weighted"] * 0.08
                + confidence_parts["transition_reproducibility"] * 0.13
                + confidence_parts["causal_consistency"] * 0.13
                + confidence_parts["topology_stability"] * 0.16
                + confidence_parts["replay_determinism"] * 0.12
                + confidence_parts["route_convergence"] * 0.12
                + confidence_parts["activation_success_consistency"] * 0.12
            ),
            6,
        )
        confidence_fail_reasons = (
            (["confidence_below_threshold"] if overall_confidence < 0.75 else [])
            + (["causal_consistency_low"] if confidence_parts["causal_consistency"] < 0.5 else [])
            + (["topology_stability_low"] if confidence_parts["topology_stability"] < 0.5 else [])
            + (["route_convergence_low"] if confidence_parts["route_convergence"] < 0.5 else [])
            + (["activation_consistency_low"] if confidence_parts["activation_success_consistency"] < 0.5 else [])
            + (["runtime_instability_high"] if runtime_instability_report["classification"] != "PASS" else [])
            + (["temporal_replay_divergence_detected"] if temporal_replay_divergence["classification"] != "PASS" else [])
        )
        governance_confidence_report = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_governance_confidence_report",
            "lineage_id": lineage_id,
            "confidence_dimensions": confidence_parts,
            "overall_confidence_score": overall_confidence,
            "classification": "FAIL_CLOSED"
            if confidence_fail_reasons or simulation_fail_reasons
            else "PASS",
            "fail_closed_reasons": confidence_fail_reasons + simulation_fail_reasons,
        }
        governance_confidence_report["deterministic_fingerprint"] = stable_sha256(
            governance_confidence_report
        )

        transition_log = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_simulation_transition_log",
            "lineage_id": lineage_id,
            "classification": "FAIL_CLOSED" if simulation_fail_reasons else "PASS",
            "transitions": transition_steps + lifecycle_events,
            "deterministic_fingerprint": stable_sha256(
                {"lineage_id": lineage_id, "transitions": transition_steps + lifecycle_events}
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
            "behavioral_state_graph": _graph_payload(
                "semantic_behavioral_state_graph", behavioral_edges
            ),
            "activation_order_graph": _graph_payload(
                "semantic_activation_order_graph", activation_edges
            ),
            "runtime_causality_graph": _graph_payload(
                "semantic_runtime_causality_graph", causality_edges
            ),
            "power_sequence_graph": _graph_payload(
                "semantic_power_sequence_graph", power_edges
            ),
            "causal_event_chain_graph": _graph_payload(
                "semantic_causal_event_chain_graph", causal_chain_edges
            ),
            "trigger_dependency_graph": trigger_dependency_graph,
            "failure_propagation_graph": failure_propagation_graph,
            "failure_blast_radius_report": failure_blast_radius_report,
            "runtime_instability_report": runtime_instability_report,
            "temporal_causality_report": temporal_causality_report,
            "temporal_replay_divergence": temporal_replay_divergence,
            "runtime_sequence_fingerprint": runtime_sequence_fingerprint,
            "root_cause_inference_report": root_cause_inference_report,
            "causal_event_chains_report": causal_event_chains,
            "dapm_behavioral_model": dapm_behavioral_model,
            "behavioral_replay_timeline": behavioral_replay_timeline,
            "stream_intelligence_report": stream_intelligence_report,
            "governance_confidence_report": governance_confidence_report,
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
                behavioral_state_graph={},
                activation_order_graph={},
                runtime_causality_graph={},
                power_sequence_graph={},
                causal_event_chain_graph={},
                trigger_dependency_graph={},
                failure_propagation_graph={},
                failure_blast_radius_report={},
                runtime_instability_report={},
                temporal_causality_report={},
                temporal_replay_divergence={},
                runtime_sequence_fingerprint={},
                root_cause_inference_report={},
                causal_event_chains_report={},
                dapm_behavioral_model={},
                behavioral_replay_timeline={},
                stream_intelligence_report={},
                governance_confidence_report={},
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

        if not discovered:
            failure_diagnostics = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_failure_diagnostics",
                "lineage_id": lineage_id,
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["no_eligible_source_files_discovered"],
                "source_root": normalize_path(root),
                "discovery_patterns": list(_DISCOVERY_PATTERNS),
                "generated_at": _utc_now_iso(),
            }
            failure_diagnostics["deterministic_fingerprint"] = stable_sha256(failure_diagnostics)
            cache_state = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_cache_state",
                "parser_version": self._parser_version,
                "lineage_id": lineage_id,
                "source_root": normalize_path(root),
                "files": {},
                "parsed": {},
                "include_reverse_deps": {},
                "generated_at": _utc_now_iso(),
            }
            cache_state["deterministic_fingerprint"] = stable_sha256(cache_state)
            summary = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_scaling_summary",
                "lineage_id": lineage_id,
                "classification": "FAIL_CLOSED",
                "file_count": 0,
                "changed_file_count": 0,
                "reparsed_file_count": 0,
                "reused_file_count": 0,
                "cache_reuse_ratio": 0.0,
                "edge_counts": {"include": 0, "call": 0, "macro": 0, "dapm": 0},
                "topology_classification": "FAIL_CLOSED",
                "simulation_classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["no_eligible_source_files_discovered"],
                "generated_at": _utc_now_iso(),
            }
            summary["deterministic_fingerprint"] = stable_sha256(summary)
            discovery_registry = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_driver_discovery_registry",
                "parser_version": self._parser_version,
                "lineage_id": lineage_id,
                "source_root": normalize_path(root),
                "discovery_patterns": list(_DISCOVERY_PATTERNS),
                "file_count": 0,
                "files": [],
                "subsystem_groups": {},
                "registry": {},
                "evidence_references": evidence,
                "generated_at": _utc_now_iso(),
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["no_eligible_source_files_discovered"],
            }
            discovery_registry["deterministic_fingerprint"] = stable_sha256(discovery_registry)
            incremental_ingestion_report = {
                "schema_version": _SCHEMA_VERSION,
                "report_name": "semantic_incremental_ingestion_report",
                "parser_version": self._parser_version,
                "lineage_id": lineage_id,
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["no_eligible_source_files_discovered"],
                "changed_files": [],
                "removed_files": [],
                "header_invalidation_dependents": [],
                "reparsed_files": [],
                "reused_files": [],
                "reused_file_count": 0,
                "reparsed_file_count": 0,
                "cache_reuse_ratio": 0.0,
                "include_reverse_deps_count": 0,
                "parse_lineage": {},
                "dependency_invalidation": {
                    "dependency_engine": "include_reverse_deps",
                    "graph_invalidation": [],
                },
                "generated_at": _utc_now_iso(),
            }
            incremental_ingestion_report["deterministic_fingerprint"] = stable_sha256(
                incremental_ingestion_report
            )

            dump_canonical_json(out_dir / "semantic_driver_discovery_registry.json", discovery_registry)
            dump_canonical_json(out_dir / "semantic_incremental_ingestion_report.json", incremental_ingestion_report)
            dump_canonical_json(out_dir / "semantic_failure_diagnostics.json", failure_diagnostics)
            dump_canonical_json(cache_path, cache_state)
            dump_canonical_json(out_dir / "semantic_scaling_summary.json", summary)

            return SemanticScalingResult(
                discovery_registry=discovery_registry,
                incremental_ingestion_report=incremental_ingestion_report,
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
                behavioral_state_graph={},
                activation_order_graph={},
                runtime_causality_graph={},
                power_sequence_graph={},
                causal_event_chain_graph={},
                trigger_dependency_graph={},
                failure_propagation_graph={},
                failure_blast_radius_report={},
                runtime_instability_report={},
                temporal_causality_report={},
                temporal_replay_divergence={},
                runtime_sequence_fingerprint={},
                root_cause_inference_report={},
                causal_event_chains_report={},
                dapm_behavioral_model={},
                behavioral_replay_timeline={},
                stream_intelligence_report={},
                governance_confidence_report={},
                topology_model={},
                simulation_replay={},
                transition_log={},
                failure_diagnostics=failure_diagnostics,
                cache_state=cache_state,
                summary=summary,
            )

        previous_cache = {}
        if cache_path.exists():
            try:
                previous_cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except Exception:
                previous_cache = {}
        cached_files = _as_dict(previous_cache.get("files"))
        previous_parsed = _as_dict(previous_cache.get("parsed"))
        previous_includes = _as_dict(previous_cache.get("include_reverse_deps"))
        previous_parser_version = str(previous_cache.get("parser_version", ""))
        parser_version_changed = previous_parser_version != self._parser_version

        changed: set[str] = set()
        removed: set[str] = set(set(cached_files.keys()) - set(discovered))
        if parser_version_changed:
            changed = set(discovered)
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
            cached_parsed = _as_dict(previous_parsed.get(rel))
            cached_has_behavioral_fields = (
                "callback_bindings" in cached_parsed
                and "stream_lifecycle_traces" in cached_parsed
            )
            if rel not in to_reparse and rel in previous_parsed and cached_has_behavioral_fields:
                parsed_by_file[rel] = _as_dict(previous_parsed.get(rel))
                reused_count += 1

        reparsed = await self._parse_async(root, to_reparse, workers=workers) if to_reparse else {}
        parsed_by_file.update(reparsed)
        parsed_by_file = {rel: _as_dict(parsed_by_file.get(rel)) for rel in sorted(parsed_by_file.keys())}

        include_reverse_deps = self._build_include_reverse_deps(parsed_by_file, headers)
        graphs = self._build_graphs(parsed_by_file, root, lineage_id)
        previous_sequence_fingerprint = str(previous_cache.get("runtime_sequence_fingerprint", "")).strip()
        current_sequence_fingerprint = str(
            _as_dict(graphs.get("runtime_sequence_fingerprint")).get("combined_sequence_fingerprint", "")
        ).strip()
        divergence_detected = bool(
            previous_sequence_fingerprint
            and current_sequence_fingerprint
            and previous_sequence_fingerprint != current_sequence_fingerprint
        )
        if divergence_detected:
            temporal_divergence = _as_dict(graphs.get("temporal_replay_divergence"))
            temporal_divergence["previous_sequence_fingerprint"] = previous_sequence_fingerprint
            temporal_divergence["current_sequence_fingerprint"] = current_sequence_fingerprint
            temporal_divergence["divergence_detected"] = True
            temporal_divergence["classification"] = "FAIL_CLOSED"
            reasons = _as_list(temporal_divergence.get("fail_closed_reasons"))
            if "temporal_replay_divergence_detected" not in reasons:
                reasons.append("temporal_replay_divergence_detected")
            temporal_divergence["fail_closed_reasons"] = reasons
            temporal_divergence["deterministic_fingerprint"] = stable_sha256(temporal_divergence)
            graphs["temporal_replay_divergence"] = temporal_divergence

            simulation = _as_dict(graphs.get("simulation_replay"))
            sim_reasons = _as_list(simulation.get("fail_closed_reasons"))
            if "temporal_replay_divergence_detected" not in sim_reasons:
                sim_reasons.append("temporal_replay_divergence_detected")
            simulation["fail_closed_reasons"] = sim_reasons
            simulation["classification"] = "FAIL_CLOSED"
            simulation["deterministic_fingerprint"] = stable_sha256(simulation)
            graphs["simulation_replay"] = simulation

            governance = _as_dict(graphs.get("governance_confidence_report"))
            gov_reasons = _as_list(governance.get("fail_closed_reasons"))
            if "temporal_replay_divergence_detected" not in gov_reasons:
                gov_reasons.append("temporal_replay_divergence_detected")
            governance["fail_closed_reasons"] = gov_reasons
            governance["classification"] = "FAIL_CLOSED"
            governance["deterministic_fingerprint"] = stable_sha256(governance)
            graphs["governance_confidence_report"] = governance

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
            "dai_ops": sorted(
                [
                    row
                    for rel in discovered
                    for row in _as_list(_as_dict(parsed_by_file.get(rel)).get("dai_ops_structs"))
                ],
                key=lambda row: (
                    str(_as_dict(row).get("ops_name", "")),
                    str(_as_dict(row).get("ops_scope", "")),
                ),
            ),
            "pcm_ops": sorted(
                [
                    row
                    for rel in discovered
                    for row in _as_list(_as_dict(parsed_by_file.get(rel)).get("pcm_ops_structs"))
                ],
                key=lambda row: (
                    str(_as_dict(row).get("ops_name", "")),
                    str(_as_dict(row).get("ops_scope", "")),
                ),
            ),
            "callback_bindings": sorted(
                [
                    row
                    for rel in discovered
                    for row in _as_list(_as_dict(parsed_by_file.get(rel)).get("callback_bindings"))
                ],
                key=lambda row: (
                    str(_as_dict(row).get("ops_name", "")),
                    str(_as_dict(row).get("stage", "")),
                    str(_as_dict(row).get("callback", "")),
                ),
            ),
            "activation_conditions": _dedupe_sorted(
                item
                for rel in discovered
                for item in _as_list(_as_dict(parsed_by_file.get(rel)).get("activation_conditions"))
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
            "parser_version_changed": parser_version_changed,
            "temporal_replay_divergence_detected": divergence_detected,
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

        replay_mismatches = (
            (["topology_or_simulation_fail_closed"] if (
                graphs["topology_model"].get("classification") != "PASS"
                or graphs["simulation_replay"].get("classification") != "PASS"
            ) else [])
            + (["stream_intelligence_fail_closed"] if graphs["stream_intelligence_report"].get("classification") != "PASS" else [])
            + (["governance_confidence_fail_closed"] if graphs["governance_confidence_report"].get("classification") != "PASS" else [])
            + (["runtime_instability_fail_closed"] if graphs["runtime_instability_report"].get("classification") != "PASS" else [])
            + (["root_cause_inference_fail_closed"] if graphs["root_cause_inference_report"].get("classification") != "PASS" else [])
            + (["temporal_replay_divergence_detected"] if graphs["temporal_replay_divergence"].get("classification") != "PASS" else [])
        )

        failure_diagnostics = {
            "schema_version": _SCHEMA_VERSION,
            "report_name": "semantic_failure_diagnostics",
            "lineage_id": lineage_id,
            "classification": "FAIL_CLOSED"
            if (
                graphs["topology_model"].get("classification") != "PASS"
                or graphs["simulation_replay"].get("classification") != "PASS"
                or graphs["stream_intelligence_report"].get("classification") != "PASS"
                or graphs["governance_confidence_report"].get("classification") != "PASS"
                or graphs["runtime_instability_report"].get("classification") != "PASS"
                or graphs["root_cause_inference_report"].get("classification") != "PASS"
                or graphs["temporal_replay_divergence"].get("classification") != "PASS"
            )
            else "PASS",
            "parser_failures": [],
            "semantic_drift": [],
            "replay_mismatches": replay_mismatches,
            "causal_failures": _as_list(_as_dict(graphs["root_cause_inference_report"]).get("hypotheses")),
            "semantic_completeness": {
                "behavioral_state_edges": int(graphs["behavioral_state_graph"].get("edge_count", 0)),
                "activation_order_edges": int(graphs["activation_order_graph"].get("edge_count", 0)),
                "runtime_causality_edges": int(graphs["runtime_causality_graph"].get("edge_count", 0)),
                "power_sequence_edges": int(graphs["power_sequence_graph"].get("edge_count", 0)),
            },
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
            "runtime_sequence_fingerprint": str(
                _as_dict(graphs.get("runtime_sequence_fingerprint")).get(
                    "combined_sequence_fingerprint", ""
                )
            ),
            "generated_at": _utc_now_iso(),
        }
        cache_state["deterministic_fingerprint"] = stable_sha256(
            {
                "parser_version": cache_state["parser_version"],
                "source_root": cache_state["source_root"],
                "files": cache_state["files"],
                "include_reverse_deps": cache_state["include_reverse_deps"],
                "runtime_sequence_fingerprint": cache_state["runtime_sequence_fingerprint"],
            }
        )

        summary_fail_reasons = sorted(
            set(
                [str(item) for item in _as_list(failure_diagnostics.get("replay_mismatches"))]
                + [str(item) for item in _as_list(_as_dict(graphs["topology_model"]).get("fail_closed_reasons"))]
                + [str(item) for item in _as_list(_as_dict(graphs["simulation_replay"]).get("fail_closed_reasons"))]
                + [str(item) for item in _as_list(_as_dict(graphs["stream_intelligence_report"]).get("fail_closed_reasons"))]
                + [str(item) for item in _as_list(_as_dict(graphs["governance_confidence_report"]).get("fail_closed_reasons"))]
                + [str(item) for item in _as_list(_as_dict(graphs["root_cause_inference_report"]).get("fail_closed_reasons"))]
                + [str(item) for item in _as_list(_as_dict(graphs["runtime_instability_report"]).get("fail_closed_reasons"))]
            )
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
                or graphs["stream_intelligence_report"].get("classification") != "PASS"
                or graphs["governance_confidence_report"].get("classification") != "PASS"
                or graphs["runtime_instability_report"].get("classification") != "PASS"
                or graphs["root_cause_inference_report"].get("classification") != "PASS"
                or graphs["temporal_replay_divergence"].get("classification") != "PASS"
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
                "behavioral_state": int(graphs["behavioral_state_graph"].get("edge_count", 0)),
                "activation_order": int(graphs["activation_order_graph"].get("edge_count", 0)),
                "runtime_causality": int(graphs["runtime_causality_graph"].get("edge_count", 0)),
                "power_sequence": int(graphs["power_sequence_graph"].get("edge_count", 0)),
                "causal_event_chain": int(graphs["causal_event_chain_graph"].get("edge_count", 0)),
                "trigger_dependency": int(graphs["trigger_dependency_graph"].get("edge_count", 0)),
                "failure_propagation": int(graphs["failure_propagation_graph"].get("edge_count", 0)),
            },
            "topology_classification": graphs["topology_model"].get("classification", "UNKNOWN"),
            "simulation_classification": graphs["simulation_replay"].get("classification", "UNKNOWN"),
            "stream_intelligence_classification": graphs["stream_intelligence_report"].get(
                "classification", "UNKNOWN"
            ),
            "governance_confidence_classification": graphs["governance_confidence_report"].get(
                "classification", "UNKNOWN"
            ),
            "runtime_instability_classification": graphs["runtime_instability_report"].get(
                "classification", "UNKNOWN"
            ),
            "root_cause_classification": graphs["root_cause_inference_report"].get(
                "classification", "UNKNOWN"
            ),
            "overall_confidence_score": float(
                _as_dict(graphs["governance_confidence_report"]).get("overall_confidence_score", 0.0)
            ),
            "runtime_instability_score": float(
                _as_dict(graphs["runtime_instability_report"]).get("runtime_instability_score", 0.0)
            ),
            "temporal_replay_divergence": bool(
                _as_dict(graphs["temporal_replay_divergence"]).get("divergence_detected", False)
            ),
            "fail_closed_reasons": summary_fail_reasons,
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
        dump_canonical_json(out_dir / "semantic_behavioral_state_graph.json", graphs["behavioral_state_graph"])
        dump_canonical_json(out_dir / "semantic_activation_order_graph.json", graphs["activation_order_graph"])
        dump_canonical_json(out_dir / "semantic_runtime_causality_graph.json", graphs["runtime_causality_graph"])
        dump_canonical_json(out_dir / "semantic_power_sequence_graph.json", graphs["power_sequence_graph"])
        dump_canonical_json(out_dir / "semantic_causal_event_chain_graph.json", graphs["causal_event_chain_graph"])
        dump_canonical_json(out_dir / "semantic_trigger_dependency_graph.json", graphs["trigger_dependency_graph"])
        dump_canonical_json(out_dir / "semantic_failure_propagation_graph.json", graphs["failure_propagation_graph"])
        dump_canonical_json(out_dir / "semantic_failure_blast_radius_report.json", graphs["failure_blast_radius_report"])
        dump_canonical_json(out_dir / "semantic_runtime_instability_score.json", graphs["runtime_instability_report"])
        dump_canonical_json(out_dir / "semantic_temporal_causality_report.json", graphs["temporal_causality_report"])
        dump_canonical_json(out_dir / "semantic_temporal_replay_divergence.json", graphs["temporal_replay_divergence"])
        dump_canonical_json(out_dir / "semantic_runtime_sequence_fingerprint.json", graphs["runtime_sequence_fingerprint"])
        dump_canonical_json(out_dir / "semantic_root_cause_inference_report.json", graphs["root_cause_inference_report"])
        dump_canonical_json(out_dir / "semantic_causal_event_chains_report.json", graphs["causal_event_chains_report"])
        dump_canonical_json(out_dir / "semantic_dapm_behavioral_model.json", graphs["dapm_behavioral_model"])
        dump_canonical_json(out_dir / "semantic_behavioral_replay_timeline.json", graphs["behavioral_replay_timeline"])
        dump_canonical_json(out_dir / "semantic_stream_intelligence_report.json", graphs["stream_intelligence_report"])
        dump_canonical_json(out_dir / "semantic_governance_confidence_report.json", graphs["governance_confidence_report"])
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
            behavioral_state_graph=graphs["behavioral_state_graph"],
            activation_order_graph=graphs["activation_order_graph"],
            runtime_causality_graph=graphs["runtime_causality_graph"],
            power_sequence_graph=graphs["power_sequence_graph"],
            causal_event_chain_graph=graphs["causal_event_chain_graph"],
            trigger_dependency_graph=graphs["trigger_dependency_graph"],
            failure_propagation_graph=graphs["failure_propagation_graph"],
            failure_blast_radius_report=graphs["failure_blast_radius_report"],
            runtime_instability_report=graphs["runtime_instability_report"],
            temporal_causality_report=graphs["temporal_causality_report"],
            temporal_replay_divergence=graphs["temporal_replay_divergence"],
            runtime_sequence_fingerprint=graphs["runtime_sequence_fingerprint"],
            root_cause_inference_report=graphs["root_cause_inference_report"],
            causal_event_chains_report=graphs["causal_event_chains_report"],
            dapm_behavioral_model=graphs["dapm_behavioral_model"],
            behavioral_replay_timeline=graphs["behavioral_replay_timeline"],
            stream_intelligence_report=graphs["stream_intelligence_report"],
            governance_confidence_report=graphs["governance_confidence_report"],
            topology_model=graphs["topology_model"],
            simulation_replay=graphs["simulation_replay"],
            transition_log=graphs["transition_log"],
            failure_diagnostics=failure_diagnostics,
            cache_state=cache_state,
            summary=summary,
        )
