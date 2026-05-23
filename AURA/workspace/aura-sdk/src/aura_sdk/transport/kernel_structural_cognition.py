"""Kernel Structural Cognition Layer.

Builds deterministic, governance-safe structural cognition artifacts from
real Linux kernel source trees for runtime/topology/debug/migration reasoning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ALLOWED_EXTENSIONS = {".c", ".h", ".dts", ".dtsi", ".mk"}
_IGNORED_DIR_NAMES = {
    ".git",
    ".repo",
    "build",
    "out",
    "Documentation",
    "debian",
    "usr",
    "tools",
    "samples",
    "scripts",
}

_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "fingerprint",
    "trace",
    "replay",
    "recommend",
]

_FORBIDDEN_ACTIONS = [
    "autonomous_patch_generation",
    "autonomous_topology_mutation",
    "unsafe_runtime_rewrite",
    "autonomous_source_rewrite",
]

_KCONFIG_ENTRY_RE = re.compile(r"^\s*(?:menuconfig|config)\s+([A-Za-z0-9_]+)", re.MULTILINE)
_KCONFIG_SOURCE_RE = re.compile(r"^\s*source\s+\"([^\"]+)\"", re.MULTILINE)

_MAKE_OBJ_RULE_RE = re.compile(r"^\s*obj-[^\n]*?\+=\s*(.+)$", re.MULTILINE)
_MAKE_MULTI_RULE_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)-y\s*[:+]?=\s*(.+)$", re.MULTILINE)

_DTS_INCLUDE_RE = re.compile(r"^\s*#include\s+[<\"]([^>\"]+)[>\"]", re.MULTILINE)
_DTS_NODE_LABELED_RE = re.compile(r"^\s*([A-Za-z0-9_\-]+)\s*:\s*([A-Za-z0-9,_@/\-]+)\s*\{", re.MULTILINE)
_DTS_NODE_SIMPLE_RE = re.compile(r"^\s*([A-Za-z0-9,_@/\-]+)\s*\{", re.MULTILINE)

_DAI_LINK_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_dai_link\s+([A-Za-z_][A-Za-z0-9_]*)")
_COMPONENT_DRIVER_RE = re.compile(
    r"\b(?:const\s+)?struct\s+snd_soc_component_driver\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_COMPONENT_DRIVER_BLOCK_RE = re.compile(
    r"(?:const\s+)?struct\s+snd_soc_component_driver\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.*?)\};",
    re.DOTALL,
)
_OPS_STRUCT_BLOCK_RE = re.compile(
    r"(?:const\s+)?struct\s+snd_soc_ops\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\{(.*?)\};",
    re.DOTALL,
)

_CALLBACK_ASSIGNMENT_RE = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)")

_REGISTRATION_API_RE = re.compile(
    r"\b("
    r"devm_snd_soc_register_component|"
    r"snd_soc_register_component|"
    r"devm_snd_soc_register_card|"
    r"snd_soc_register_card|"
    r"platform_driver_register|"
    r"module_platform_driver|"
    r"snd_soc_add_component_controls"
    r")\s*\("
)

_DAPM_WIDGET_STRUCT_RE = re.compile(
    r"\b(?:const\s+)?struct\s+snd_soc_dapm_widget\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_DAPM_WIDGET_MACRO_RE = re.compile(r"\bSND_SOC_DAPM_[A-Z0-9_]+\s*\(\s*\"([^\"]+)\"")
_DAPM_ROUTE_STRUCT_RE = re.compile(r"\b(?:const\s+)?struct\s+snd_soc_dapm_route\s+([A-Za-z_][A-Za-z0-9_]*)")
_DAPM_ROUTE_ENTRY_RE = re.compile(r"\{\s*\"([^\"]+)\"\s*,\s*(?:\"([^\"]*)\"|NULL)\s*,\s*\"([^\"]+)\"\s*\}")

_PCM_STRING_RE = re.compile(r'"([^"\n]*(?:PCM|MultiMedia|Playback|Capture)[^"\n]*)"')

_VENDOR_TOKEN_RE = re.compile(
    r"\b(?:msm_[A-Za-z0-9_]+|qcom_[A-Za-z0-9_]+|wcd[A-Za-z0-9_]*|lpass_[A-Za-z0-9_]+|"
    r"bolero_[A-Za-z0-9_]+|swr_[A-Za-z0-9_]+|sdw_[A-Za-z0-9_]+|q6_[A-Za-z0-9_]+|spf_[A-Za-z0-9_]+)\b"
)

_VENDOR_HOOK_RE = re.compile(
    r"\b(?:vendor_hook_[A-Za-z0-9_]+|trace_android_vh_[A-Za-z0-9_]+|"
    r"msm_audio_[A-Za-z0-9_]+|qcom_snd_[A-Za-z0-9_]+|apr_[A-Za-z0-9_]+|gpr_[A-Za-z0-9_]+|"
    r"audio_prm_[A-Za-z0-9_]+)\b"
)

_SND_SOC_COMPONENT_LIFECYCLE_CALLBACKS = {
    "probe",
    "remove",
    "suspend",
    "resume",
    "set_bias_level",
    "pcm_construct",
    "of_xlate_dai_name",
}

_SND_SOC_OPS_CALLBACKS = {
    "startup",
    "shutdown",
    "hw_params",
    "hw_free",
    "prepare",
    "trigger",
    "sync_stop",
    "ioctl",
    "mute_stream",
    "set_sysclk",
    "set_fmt",
}


@dataclass(frozen=True)
class KernelStructuralCognitionPlannerResult:
    structural_bundle: dict[str, Any]


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


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success", "supported"}
    return False


def _dedupe_sorted(items: Iterable[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def _limit(items: list[Any], max_items: int) -> list[Any]:
    if len(items) <= max_items:
        return items
    return items[:max_items]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _iter_source_files(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    if not root.exists() or not root.is_dir():
        return files

    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        if not path.is_file():
            continue
        if any(part in _IGNORED_DIR_NAMES for part in path.parts):
            continue

        name = path.name
        suffix = path.suffix.lower()
        if suffix in _ALLOWED_EXTENSIONS or name == "Makefile" or name.startswith("Kconfig"):
            files.append(path)

    files.sort(key=lambda item: str(item))
    return files


def _iter_upstream_focus_files(root: Path, max_files: int, focus_paths: list[str]) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []

    files: list[Path] = []
    normalized_focus = [str(item).strip().strip("/") for item in focus_paths if str(item).strip()]

    if normalized_focus:
        for rel in normalized_focus:
            focus = root / rel
            if not focus.exists():
                continue
            for path in focus.rglob("*"):
                if len(files) >= max_files:
                    break
                if not path.is_file():
                    continue
                if any(part in _IGNORED_DIR_NAMES for part in path.parts):
                    continue
                if path.suffix.lower() in _ALLOWED_EXTENSIONS or path.name == "Makefile" or path.name.startswith("Kconfig"):
                    files.append(path)
            if len(files) >= max_files:
                break

    if not files:
        files = _iter_source_files(root, max_files=max_files)

    files.sort(key=lambda item: str(item))
    return _limit(files, max_files)


def _split_objects(line_value: str) -> list[str]:
    return [
        token.strip()
        for token in re.split(r"\s+", str(line_value).strip())
        if token.strip() and token.strip().endswith(".o")
    ]


def _name_tokens(name: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(name).lower())
        if token and token not in {"msm", "qcom", "audio", "dai", "link", "links", "be", "fe", "rx", "tx"}
    }


def _infer_fe_be_links(frontend: list[str], backend: list[str]) -> list[dict[str, Any]]:
    if not frontend or not backend:
        return []

    inferred: list[dict[str, Any]] = []
    sorted_backend = sorted(backend)

    for fe in sorted(frontend):
        fe_tokens = _name_tokens(fe)
        matches = [be for be in sorted_backend if fe_tokens.intersection(_name_tokens(be))]
        if not matches:
            matches = sorted_backend[:1]
        inferred.append(
            {
                "frontend": fe,
                "backend_candidates": matches[:4],
                "confidence": 0.82 if fe_tokens and matches else 0.55,
            }
        )

    return inferred


def _classify_fe_be(dai_links: list[str]) -> tuple[list[str], list[str], list[str]]:
    frontend: list[str] = []
    backend: list[str] = []
    other: list[str] = []

    for name in dai_links:
        lower = str(name).lower()
        if "_fe_" in lower or lower.endswith("_fe_dai_links") or "frontend" in lower:
            frontend.append(name)
        elif "_be_" in lower or lower.endswith("_be_dai_links") or "backend" in lower:
            backend.append(name)
        else:
            other.append(name)

    return _dedupe_sorted(frontend), _dedupe_sorted(backend), _dedupe_sorted(other)


def _find_callback_assignments(body: str, allowed_names: set[str]) -> list[dict[str, str]]:
    callbacks: list[dict[str, str]] = []
    for callback_name, function_name in _CALLBACK_ASSIGNMENT_RE.findall(body):
        if callback_name not in allowed_names:
            continue
        callbacks.append(
            {
                "callback": str(callback_name),
                "function": str(function_name),
            }
        )
    callbacks.sort(key=lambda item: (item["callback"], item["function"]))
    return callbacks


def _extract_downstream_signals(root: Path, max_files: int) -> dict[str, Any]:
    files = _iter_source_files(root, max_files=max_files)

    kconfig_symbols: list[dict[str, Any]] = []
    kconfig_includes: list[dict[str, Any]] = []
    makefile_rules: list[dict[str, Any]] = []

    dts_includes: list[dict[str, Any]] = []
    dts_nodes: list[dict[str, Any]] = []

    registration_calls: list[dict[str, Any]] = []
    component_drivers: list[dict[str, Any]] = []
    ops_structures: list[dict[str, Any]] = []

    dai_links: list[str] = []
    dapm_widgets: list[str] = []
    dapm_widget_macros: list[str] = []
    dapm_routes: list[dict[str, str]] = []
    route_structures: list[str] = []

    pcm_strings: list[str] = []
    vendor_tokens: list[str] = []
    vendor_hooks: list[str] = []
    soundwire_markers: list[str] = []

    source_files: list[str] = []
    file_summaries: list[dict[str, Any]] = []

    for path in files:
        text = _read_text(path)
        if not text:
            continue

        rel = str(path.relative_to(root))
        source_files.append(rel)

        file_signals: dict[str, Any] = {
            "file": rel,
            "kconfig_symbols": 0,
            "makefile_rules": 0,
            "registration_calls": 0,
            "component_drivers": 0,
            "ops_structures": 0,
            "dai_links": 0,
            "dapm_widgets": 0,
            "vendor_hooks": 0,
            "soundwire_markers": 0,
            "signal_terms": [],
        }

        name = path.name
        suffix = path.suffix.lower()

        if name.startswith("Kconfig"):
            for symbol in _KCONFIG_ENTRY_RE.findall(text):
                kconfig_symbols.append({"symbol": str(symbol), "file": rel})
            for include in _KCONFIG_SOURCE_RE.findall(text):
                kconfig_includes.append({"source": str(include), "file": rel})
            file_signals["kconfig_symbols"] = len(_KCONFIG_ENTRY_RE.findall(text))

        if name == "Makefile" or suffix == ".mk":
            for object_line in _MAKE_OBJ_RULE_RE.findall(text):
                objects = _split_objects(object_line)
                if objects:
                    makefile_rules.append(
                        {
                            "file": rel,
                            "rule_type": "obj",
                            "objects": objects,
                        }
                    )
            for module, object_line in _MAKE_MULTI_RULE_RE.findall(text):
                objects = _split_objects(object_line)
                if objects:
                    makefile_rules.append(
                        {
                            "file": rel,
                            "rule_type": "module_objects",
                            "module": str(module),
                            "objects": objects,
                        }
                    )
            file_signals["makefile_rules"] = len(_MAKE_OBJ_RULE_RE.findall(text)) + len(_MAKE_MULTI_RULE_RE.findall(text))

        if suffix in {".dts", ".dtsi"}:
            for include in _DTS_INCLUDE_RE.findall(text):
                dts_includes.append({"include": str(include), "file": rel})
            for label, node_name in _DTS_NODE_LABELED_RE.findall(text):
                dts_nodes.append({"node": str(node_name), "label": str(label), "file": rel})
            for node_name in _DTS_NODE_SIMPLE_RE.findall(text):
                # Skip entries already captured as labeled nodes.
                if any(item.get("node") == str(node_name) and item.get("file") == rel for item in dts_nodes):
                    continue
                dts_nodes.append({"node": str(node_name), "label": "", "file": rel})

            if "soundwire" in text.lower() or "swr" in text.lower() or "sdw" in text.lower():
                soundwire_markers.append(rel)
                file_signals["soundwire_markers"] = 1

        for api_name in _REGISTRATION_API_RE.findall(text):
            registration_calls.append({"api": str(api_name), "file": rel})
        file_signals["registration_calls"] = len(_REGISTRATION_API_RE.findall(text))

        for name_match, body in _COMPONENT_DRIVER_BLOCK_RE.findall(text):
            callbacks = _find_callback_assignments(body, _SND_SOC_COMPONENT_LIFECYCLE_CALLBACKS)
            component_drivers.append(
                {
                    "name": str(name_match),
                    "file": rel,
                    "callbacks": callbacks,
                }
            )
        for name_match in _COMPONENT_DRIVER_RE.findall(text):
            if not any(item["name"] == str(name_match) and item["file"] == rel for item in component_drivers):
                component_drivers.append({"name": str(name_match), "file": rel, "callbacks": []})
        file_signals["component_drivers"] = len([row for row in component_drivers if row.get("file") == rel])

        for name_match, body in _OPS_STRUCT_BLOCK_RE.findall(text):
            callbacks = _find_callback_assignments(body, _SND_SOC_OPS_CALLBACKS)
            ops_structures.append(
                {
                    "name": str(name_match),
                    "file": rel,
                    "callbacks": callbacks,
                }
            )
        file_signals["ops_structures"] = len([row for row in ops_structures if row.get("file") == rel])

        dai_in_file = [str(item) for item in _DAI_LINK_RE.findall(text)]
        dai_links.extend(dai_in_file)
        file_signals["dai_links"] = len(dai_in_file)

        dapm_widgets.extend(str(item) for item in _DAPM_WIDGET_STRUCT_RE.findall(text))
        dapm_widget_macros.extend(str(item) for item in _DAPM_WIDGET_MACRO_RE.findall(text))
        route_structures.extend(str(item) for item in _DAPM_ROUTE_STRUCT_RE.findall(text))

        for sink, control, source in _DAPM_ROUTE_ENTRY_RE.findall(text):
            dapm_routes.append(
                {
                    "sink": str(sink),
                    "control": str(control),
                    "source": str(source),
                    "file": rel,
                }
            )
        file_signals["dapm_widgets"] = len(_DAPM_WIDGET_STRUCT_RE.findall(text)) + len(_DAPM_WIDGET_MACRO_RE.findall(text))

        pcm_in_file = [str(item).strip() for item in _PCM_STRING_RE.findall(text) if str(item).strip()]
        pcm_strings.extend(pcm_in_file)

        vendor_tokens_in_file = [str(item) for item in _VENDOR_TOKEN_RE.findall(text)]
        vendor_hooks_in_file = [str(item) for item in _VENDOR_HOOK_RE.findall(text)]
        vendor_tokens.extend(vendor_tokens_in_file)
        vendor_hooks.extend(vendor_hooks_in_file)

        file_signals["vendor_hooks"] = len(vendor_hooks_in_file)
        signal_terms = set()
        signal_terms.update(token.lower() for token in dai_in_file)
        signal_terms.update(token.lower() for token in vendor_tokens_in_file)
        signal_terms.update(token.lower() for token in vendor_hooks_in_file)
        signal_terms.update(token.lower() for token in pcm_in_file)
        signal_terms.update(token.lower() for token in _REGISTRATION_API_RE.findall(text))
        file_signals["signal_terms"] = sorted(signal_terms)[:50]

        if any(value for key, value in file_signals.items() if key not in {"file", "signal_terms"}):
            file_summaries.append(file_signals)

    frontend_links, backend_links, other_links = _classify_fe_be(_dedupe_sorted(dai_links))
    inferred_fe_be = _infer_fe_be_links(frontend_links, backend_links)

    soundwire_files = sorted({str(item) for item in soundwire_markers if str(item).strip()})
    if not soundwire_files:
        # fallback: any file containing swr/sdw marker in vendor tokens.
        soundwire_files = sorted(
            {
                str(summary.get("file", ""))
                for summary in file_summaries
                if isinstance(summary, dict)
                and any(token.startswith("swr_") or token.startswith("sdw_") for token in _as_list(summary.get("signal_terms")))
            }
        )

    return {
        "downstream_root": str(root),
        "scanned_files": {
            "total": len(source_files),
            "source_files": source_files,
        },
        "kconfig": {
            "symbols": _limit(sorted(kconfig_symbols, key=lambda row: (row.get("symbol", ""), row.get("file", ""))), 2000),
            "includes": _limit(sorted(kconfig_includes, key=lambda row: (row.get("source", ""), row.get("file", ""))), 2000),
        },
        "makefile": {
            "rules": _limit(
                sorted(
                    makefile_rules,
                    key=lambda row: (
                        row.get("file", ""),
                        row.get("rule_type", ""),
                        str(row.get("module", "")),
                        " ".join(_as_list(row.get("objects"))),
                    ),
                ),
                3000,
            ),
        },
        "dts": {
            "includes": _limit(sorted(dts_includes, key=lambda row: (row.get("include", ""), row.get("file", ""))), 3000),
            "nodes": _limit(sorted(dts_nodes, key=lambda row: (row.get("node", ""), row.get("label", ""), row.get("file", ""))), 5000),
            "soundwire_markers": soundwire_files,
        },
        "registration": {
            "calls": _limit(sorted(registration_calls, key=lambda row: (row.get("api", ""), row.get("file", ""))), 4000),
            "component_drivers": _limit(sorted(component_drivers, key=lambda row: (row.get("name", ""), row.get("file", ""))), 1500),
            "ops_structures": _limit(sorted(ops_structures, key=lambda row: (row.get("name", ""), row.get("file", ""))), 2000),
        },
        "topology": {
            "dai_links": {
                "all": _dedupe_sorted(dai_links),
                "frontend": frontend_links,
                "backend": backend_links,
                "other": other_links,
                "inferred_fe_be_links": inferred_fe_be,
            },
            "dapm_widgets": _dedupe_sorted(dapm_widgets + dapm_widget_macros),
            "dapm_routes": _limit(sorted(dapm_routes, key=lambda row: (row.get("sink", ""), row.get("source", ""), row.get("file", ""))), 5000),
            "dapm_route_structures": _dedupe_sorted(route_structures),
            "pcm_strings": _dedupe_sorted(pcm_strings),
        },
        "vendor": {
            "vendor_tokens": _dedupe_sorted(vendor_tokens),
            "vendor_hooks": _dedupe_sorted(vendor_hooks),
        },
        "source_file_summaries": _limit(sorted(file_summaries, key=lambda row: str(row.get("file", ""))), 4000),
    }


def _build_upstream_index(root: Path, max_files: int, focus_paths: list[str]) -> dict[str, Any]:
    files = _iter_upstream_focus_files(root, max_files=max_files, focus_paths=focus_paths)

    token_index: set[str] = set()
    path_index: list[str] = []

    for path in files:
        text = _read_text(path)
        if not text:
            continue

        rel = str(path.relative_to(root))
        path_index.append(rel)

        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text):
            if len(token) <= 96:
                token_index.add(token.lower())

    path_index.sort()
    return {
        "root": str(root),
        "files_indexed": len(path_index),
        "path_index": path_index,
        "token_index": token_index,
    }


def _heuristic_upstream_equivalent(construct: str, hints: Mapping[str, Any]) -> tuple[str, float, str]:
    lower = str(construct).lower()

    prefix_hints = _as_dict(_as_dict(hints).get("prefix"))
    for prefix, mapped in sorted(prefix_hints.items()):
        key = str(prefix).strip().lower()
        if key and lower.startswith(key):
            return str(mapped), 0.82, "plugin_prefix_hint"

    if "snd_soc_component_driver" in lower or "register_component" in lower:
        return "snd_soc_component", 0.9, "heuristic_registration"
    if "snd_soc_ops" in lower or lower.endswith("_ops"):
        return "snd_soc_ops", 0.86, "heuristic_ops"
    if "dai_link" in lower or "_fe_" in lower or "_be_" in lower:
        return "snd_soc_dai_link", 0.84, "heuristic_dai_link"
    if "dapm" in lower or "route" in lower or "widget" in lower:
        return "snd_soc_dapm", 0.8, "heuristic_dapm"
    if "soundwire" in lower or lower.startswith("swr_") or lower.startswith("sdw_"):
        return "soundwire", 0.86, "heuristic_soundwire"
    if "pcm" in lower:
        return "snd_pcm", 0.74, "heuristic_pcm"
    if "vendor_hook" in lower or "trace_android_vh" in lower:
        return "tracepoint_or_standard_callback", 0.63, "heuristic_vendor_hook"
    if lower.startswith("msm_") or lower.startswith("qcom_"):
        return "snd_soc_component", 0.7, "heuristic_vendor_prefix"
    return "UNRESOLVED", 0.22, "unresolved"


def _candidate_presence(candidate: str, token_index: set[str], path_index: list[str]) -> tuple[bool, list[str]]:
    candidate_value = str(candidate).strip().lower()
    if not candidate_value or candidate_value == "unresolved":
        return False, []

    terms = [item for item in re.split(r"[^a-z0-9_]+", candidate_value) if item]
    if not terms:
        return False, []

    matched_terms = [term for term in terms if term in token_index]
    matched = bool(matched_terms)

    matched_paths: list[str] = []
    if matched:
        for rel in path_index:
            lower_rel = rel.lower()
            if any(term in lower_rel for term in matched_terms[:3]):
                matched_paths.append(rel)
            if len(matched_paths) >= 6:
                break

    return matched, matched_paths


def _build_upstream_equivalence_trace(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    upstream_index: Mapping[str, Any],
    adapter_payload: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    registration = _as_dict(_as_dict(downstream_signals).get("registration"))
    topology = _as_dict(_as_dict(downstream_signals).get("topology"))
    vendor = _as_dict(_as_dict(downstream_signals).get("vendor"))

    constructs: list[str] = []
    constructs.extend(str(item.get("api", "")) for item in _as_list(registration.get("calls")) if isinstance(item, dict))
    constructs.extend(str(item.get("name", "")) for item in _as_list(registration.get("component_drivers")) if isinstance(item, dict))
    constructs.extend(str(item.get("name", "")) for item in _as_list(registration.get("ops_structures")) if isinstance(item, dict))
    constructs.extend(str(item) for item in _as_list(_as_dict(topology.get("dai_links")).get("all")))
    constructs.extend(str(item) for item in _as_list(vendor.get("vendor_hooks")))
    constructs.extend(str(item) for item in _as_list(vendor.get("vendor_tokens")))

    unique_constructs = _dedupe_sorted(constructs)

    hint_payload = _as_dict(adapter_payload.get("upstream_equivalent_hints"))
    confidence_hints = _as_dict(adapter_payload.get("equivalence_confidence_hints"))

    token_index = set(_as_list(upstream_index.get("token_index")))
    path_index = [str(item) for item in _as_list(upstream_index.get("path_index"))]

    entries: list[dict[str, Any]] = []
    exact = 0
    partial = 0
    unresolved = 0

    for construct in unique_constructs:
        candidate, base_confidence, reason = _heuristic_upstream_equivalent(construct, hint_payload)
        hinted_confidence = _to_float(confidence_hints.get(construct, 0.0))
        if hinted_confidence > 0.0:
            base_confidence = max(base_confidence, min(1.0, hinted_confidence))

        matched, evidence_paths = _candidate_presence(candidate, token_index, path_index)

        if candidate == "UNRESOLVED":
            status = "UNRESOLVED"
            confidence = 0.22
            unresolved += 1
        elif matched:
            status = "EXACT" if base_confidence >= 0.75 else "PARTIAL"
            confidence = min(1.0, base_confidence + 0.1)
            if status == "EXACT":
                exact += 1
            else:
                partial += 1
        else:
            status = "PARTIAL"
            confidence = min(0.69, base_confidence)
            partial += 1

        entries.append(
            {
                "downstream_construct": construct,
                "upstream_equivalent": candidate,
                "equivalence_status": status,
                "equivalence_confidence": round(confidence, 3),
                "reasoning": reason,
                "evidence_paths": evidence_paths,
            }
        )

    confidence = 0.0
    if entries:
        confidence = round(sum(_to_float(row.get("equivalence_confidence", 0.0)) for row in entries) / len(entries), 3)

    payload = {
        "schema_version": "1.0",
        "graph_name": "upstream_equivalence_trace",
        "target_id": str(target_id),
        "upstream_root": str(upstream_index.get("root", "")),
        "entries": entries,
        "summary": {
            "total": len(entries),
            "exact": exact,
            "partial": partial,
            "unresolved": unresolved,
            "semantic_equivalence_confidence": confidence,
        },
        "evidence_references": list(evidence_references),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_driver_registration_graph(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    registration = _as_dict(_as_dict(downstream_signals).get("registration"))

    calls = [row for row in _as_list(registration.get("calls")) if isinstance(row, dict)]
    components = [row for row in _as_list(registration.get("component_drivers")) if isinstance(row, dict)]
    ops_structures = [row for row in _as_list(registration.get("ops_structures")) if isinstance(row, dict)]

    api_counts: dict[str, int] = {}
    for row in calls:
        key = str(row.get("api", "")).strip()
        if not key:
            continue
        api_counts[key] = api_counts.get(key, 0) + 1

    component_lifecycle: list[dict[str, Any]] = []
    for component in components:
        callback_pairs = [
            {
                "callback": str(item.get("callback", "")),
                "function": str(item.get("function", "")),
            }
            for item in _as_list(component.get("callbacks"))
            if isinstance(item, dict)
        ]
        component_lifecycle.append(
            {
                "component_driver": str(component.get("name", "")),
                "file": str(component.get("file", "")),
                "callbacks": callback_pairs,
            }
        )

    ops_lifecycle: list[dict[str, Any]] = []
    for ops in ops_structures:
        callback_pairs = [
            {
                "callback": str(item.get("callback", "")),
                "function": str(item.get("function", "")),
            }
            for item in _as_list(ops.get("callbacks"))
            if isinstance(item, dict)
        ]
        ops_lifecycle.append(
            {
                "ops_structure": str(ops.get("name", "")),
                "file": str(ops.get("file", "")),
                "callbacks": callback_pairs,
            }
        )

    payload = {
        "schema_version": "1.0",
        "graph_name": "driver_registration_graph",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "PASS",
        "registration_api_counts": dict(sorted(api_counts.items())),
        "component_lifecycle": sorted(
            component_lifecycle,
            key=lambda row: (row.get("component_driver", ""), row.get("file", "")),
        ),
        "ops_lifecycle": sorted(
            ops_lifecycle,
            key=lambda row: (row.get("ops_structure", ""), row.get("file", "")),
        ),
        "summary": {
            "registration_calls": len(calls),
            "component_driver_count": len(components),
            "ops_structure_count": len(ops_structures),
            "callback_bindings": sum(len(_as_list(row.get("callbacks"))) for row in component_lifecycle)
            + sum(len(_as_list(row.get("callbacks"))) for row in ops_lifecycle),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_topology_structure_graph(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    dts = _as_dict(_as_dict(downstream_signals).get("dts"))
    topology = _as_dict(_as_dict(downstream_signals).get("topology"))

    dai_links = _as_dict(topology.get("dai_links"))
    frontend = [str(item) for item in _as_list(dai_links.get("frontend")) if str(item).strip()]
    backend = [str(item) for item in _as_list(dai_links.get("backend")) if str(item).strip()]

    payload = {
        "schema_version": "1.0",
        "graph_name": "topology_structure_graph",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "PASS",
        "dts_includes": [row for row in _as_list(dts.get("includes")) if isinstance(row, dict)],
        "dts_nodes": [row for row in _as_list(dts.get("nodes")) if isinstance(row, dict)],
        "soundwire_topology": {
            "markers": [str(item) for item in _as_list(dts.get("soundwire_markers")) if str(item).strip()],
            "detected": bool(_as_list(dts.get("soundwire_markers"))),
        },
        "fe_be_topology": {
            "frontend_dais": frontend,
            "backend_dais": backend,
            "inferred_links": [row for row in _as_list(dai_links.get("inferred_fe_be_links")) if isinstance(row, dict)],
        },
        "dapm_graph": {
            "widgets": [str(item) for item in _as_list(topology.get("dapm_widgets")) if str(item).strip()],
            "route_structures": [str(item) for item in _as_list(topology.get("dapm_route_structures")) if str(item).strip()],
            "routes": [row for row in _as_list(topology.get("dapm_routes")) if isinstance(row, dict)],
        },
    }

    payload["summary"] = {
        "dts_include_count": len(_as_list(payload.get("dts_includes"))),
        "dts_node_count": len(_as_list(payload.get("dts_nodes"))),
        "frontend_count": len(frontend),
        "backend_count": len(backend),
        "dapm_widget_count": len(_as_list(_as_dict(payload.get("dapm_graph")).get("widgets"))),
        "dapm_route_count": len(_as_list(_as_dict(payload.get("dapm_graph")).get("routes"))),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_callback_chain_graph(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    registration = _as_dict(_as_dict(downstream_signals).get("registration"))

    nodes: list[dict[str, Any]] = [{"id": f"target:{target_id}", "kind": "target"}]
    edges: list[dict[str, Any]] = []

    for ops in [row for row in _as_list(registration.get("ops_structures")) if isinstance(row, dict)]:
        ops_name = str(ops.get("name", "")).strip()
        if not ops_name:
            continue
        ops_id = f"ops:{ops_name}"
        nodes.append({"id": ops_id, "kind": "snd_soc_ops", "file": str(ops.get("file", ""))})
        edges.append({"from": f"target:{target_id}", "to": ops_id, "relation": "defines"})

        for callback in [item for item in _as_list(ops.get("callbacks")) if isinstance(item, dict)]:
            callback_name = str(callback.get("callback", "")).strip()
            function_name = str(callback.get("function", "")).strip()
            if not callback_name or not function_name:
                continue
            callback_id = f"callback:{function_name}"
            nodes.append({"id": callback_id, "kind": "callback_function", "callback_role": callback_name})
            edges.append(
                {
                    "from": ops_id,
                    "to": callback_id,
                    "relation": "callback_chain",
                    "role": callback_name,
                }
            )

    for component in [row for row in _as_list(registration.get("component_drivers")) if isinstance(row, dict)]:
        comp_name = str(component.get("name", "")).strip()
        if not comp_name:
            continue
        component_id = f"component:{comp_name}"
        nodes.append({"id": component_id, "kind": "snd_soc_component_driver", "file": str(component.get("file", ""))})
        edges.append({"from": f"target:{target_id}", "to": component_id, "relation": "registers"})

        for callback in [item for item in _as_list(component.get("callbacks")) if isinstance(item, dict)]:
            callback_name = str(callback.get("callback", "")).strip()
            function_name = str(callback.get("function", "")).strip()
            if not callback_name or not function_name:
                continue
            callback_id = f"callback:{function_name}"
            nodes.append({"id": callback_id, "kind": "callback_function", "callback_role": callback_name})
            edges.append(
                {
                    "from": component_id,
                    "to": callback_id,
                    "relation": "lifecycle_callback",
                    "role": callback_name,
                }
            )

    # De-duplicate nodes by id.
    dedup_nodes: dict[str, dict[str, Any]] = {}
    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        if not node_id:
            continue
        dedup_nodes[node_id] = node

    dedup_edges: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for edge in edges:
        key = (
            str(edge.get("from", "")),
            str(edge.get("to", "")),
            str(edge.get("relation", "")),
            str(edge.get("role", "")),
        )
        dedup_edges[key] = edge

    payload = {
        "schema_version": "1.0",
        "graph_name": "callback_chain_graph",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "PASS",
        "nodes": sorted(dedup_nodes.values(), key=lambda row: str(row.get("id", ""))),
        "edges": sorted(
            dedup_edges.values(),
            key=lambda row: (
                str(row.get("from", "")),
                str(row.get("to", "")),
                str(row.get("relation", "")),
                str(row.get("role", "")),
            ),
        ),
        "summary": {
            "ops_structures": len([node for node in dedup_nodes.values() if str(node.get("kind", "")) == "snd_soc_ops"]),
            "component_drivers": len(
                [node for node in dedup_nodes.values() if str(node.get("kind", "")) == "snd_soc_component_driver"]
            ),
            "callback_functions": len(
                [node for node in dedup_nodes.values() if str(node.get("kind", "")) == "callback_function"]
            ),
            "callback_edges": len(dedup_edges),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_downstream_hook_inventory(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    adapter_payload: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    vendor = _as_dict(_as_dict(downstream_signals).get("vendor"))

    vendor_tokens = [str(item) for item in _as_list(vendor.get("vendor_tokens")) if str(item).strip()]
    vendor_hooks = [str(item) for item in _as_list(vendor.get("vendor_hooks")) if str(item).strip()]

    portability_patterns = [str(item) for item in _as_list(adapter_payload.get("portability_blocker_patterns")) if str(item).strip()]
    upstream_hint_map = _as_dict(adapter_payload.get("upstream_equivalence_hints"))

    downstream_only_apis = [
        token
        for token in vendor_tokens
        if token.startswith("msm_")
        or token.startswith("qcom_")
        or token.startswith("wcd")
        or token.startswith("lpass_")
    ]

    proprietary_hooks = [
        token for token in vendor_hooks if token.startswith("vendor_hook_") or token.startswith("trace_android_vh_")
    ]

    payload = {
        "schema_version": "1.0",
        "report_name": "downstream_hook_inventory",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "ADVISORY_ONLY",
        "inventory": {
            "downstream_vendor_hooks": _dedupe_sorted(vendor_hooks),
            "downstream_only_apis": _dedupe_sorted(downstream_only_apis),
            "vendor_tokens": _dedupe_sorted(vendor_tokens),
            "proprietary_runtime_hooks": _dedupe_sorted(proprietary_hooks),
            "known_portability_blocker_patterns": _dedupe_sorted(portability_patterns),
        },
        "upstream_equivalence_hints": upstream_hint_map,
        "summary": {
            "vendor_hook_count": len(_dedupe_sorted(vendor_hooks)),
            "downstream_only_api_count": len(_dedupe_sorted(downstream_only_apis)),
            "proprietary_hook_count": len(_dedupe_sorted(proprietary_hooks)),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_runtime_source_correlation(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    downstream_signals: Mapping[str, Any],
    topology_graph: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    runtime = _as_dict(runtime_evidence)
    file_summaries = [item for item in _as_list(_as_dict(downstream_signals).get("source_file_summaries")) if isinstance(item, dict)]

    command_sequence = [str(item) for item in _as_list(runtime.get("command_sequence")) if str(item).strip()]
    route_fingerprint = str(runtime.get("route_fingerprint", "")).strip()
    playback_runtime_seconds = _to_float(runtime.get("playback_runtime_seconds", 0.0))

    correlations: list[dict[str, Any]] = []

    for command in command_sequence:
        tokens = {item for item in re.split(r"[^a-z0-9]+", command.lower()) if item}
        matched_files: list[str] = []
        for summary in file_summaries:
            file_path = str(summary.get("file", "")).strip()
            if not file_path:
                continue
            terms = {str(item).lower() for item in _as_list(summary.get("signal_terms")) if str(item).strip()}
            if tokens.intersection(terms) or any(token in file_path.lower() for token in tokens):
                matched_files.append(file_path)
            if len(matched_files) >= 8:
                break

        confidence = 0.0
        if matched_files:
            confidence = min(1.0, 0.45 + 0.05 * len(tokens) + 0.03 * len(matched_files))

        correlations.append(
            {
                "runtime_command": command,
                "matched_source_files": sorted(matched_files),
                "correlation_confidence": round(confidence, 3),
            }
        )

    topology = _as_dict(topology_graph)
    fe_be = _as_dict(topology.get("fe_be_topology"))
    inferred_links = [item for item in _as_list(fe_be.get("inferred_links")) if isinstance(item, dict)]

    route_correlation = {
        "route_fingerprint": route_fingerprint,
        "inferred_fe_be_link_count": len(inferred_links),
        "route_structural_alignment": bool(route_fingerprint and inferred_links),
    }

    coverage = 0.0
    if correlations:
        coverage = round(sum(_to_float(item.get("correlation_confidence", 0.0)) for item in correlations) / len(correlations), 3)

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_source_correlation",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "PASS",
        "runtime_snapshot": {
            "run_id": str(runtime.get("run_id", "")),
            "process_success": bool(runtime.get("process_success", False)),
            "playback_completion": bool(runtime.get("playback_completion", False)),
            "playback_runtime_seconds": playback_runtime_seconds,
            "route_fingerprint": route_fingerprint,
            "command_sequence": command_sequence,
        },
        "command_source_correlations": correlations,
        "route_correlation": route_correlation,
        "correlation_confidence": coverage,
        "runtime_truth_precedence": True,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_portability_blocker_graph(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    hook_inventory: Mapping[str, Any],
    upstream_trace: Mapping[str, Any],
) -> dict[str, Any]:
    runtime = _as_dict(runtime_evidence)
    governance = _as_dict(governance_state)

    summary = _as_dict(upstream_trace.get("summary"))
    unresolved = int(summary.get("unresolved", 0))

    inventory = _as_dict(hook_inventory.get("inventory"))
    vendor_hook_count = len(_as_list(inventory.get("downstream_vendor_hooks")))
    downstream_only_count = len(_as_list(inventory.get("downstream_only_apis")))

    blockers: list[dict[str, Any]] = []

    if unresolved > 0:
        blockers.append(
            {
                "code": "unresolved_upstream_equivalence",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": {"unresolved_constructs": unresolved},
            }
        )

    if vendor_hook_count or downstream_only_count:
        blockers.append(
            {
                "code": "vendor_hook_coupling",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": {
                    "vendor_hook_count": vendor_hook_count,
                    "downstream_only_api_count": downstream_only_count,
                },
            }
        )

    replay_ok = _is_true(runtime.get("deterministic_event_ordering", False)) or bool(
        str(runtime.get("deterministic_replay_fingerprint", "")).strip()
    )
    if not replay_ok:
        blockers.append(
            {
                "code": "replay_evidence_missing",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Deterministic replay evidence missing",
            }
        )

    runtime_ok = _is_true(runtime.get("process_success", False)) or _is_true(runtime.get("playback_completion", False))
    if not runtime_ok:
        blockers.append(
            {
                "code": "runtime_evidence_unstable",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Runtime execution evidence indicates instability",
            }
        )

    governance_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )
    if governance_violation:
        blockers.append(
            {
                "code": "governance_boundary_violation",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Autonomous mutation flags enabled",
            }
        )

    blocked = [item for item in blockers if str(item.get("classification", "")) == "blocked_unsafe"]
    advisory = [item for item in blockers if str(item.get("classification", "")) == "advisory_only"]

    score = round(max(0.0, 1.0 - 0.3 * len(blocked) - 0.08 * len(advisory)), 3)
    classification = "FAIL_CLOSED" if blocked else ("ADVISORY_ONLY" if advisory else "PASS")

    payload = {
        "schema_version": "1.0",
        "graph_name": "portability_blocker_graph",
        "target_id": str(target_id),
        "classification": classification,
        "portability_score": score,
        "detected_blockers": blockers,
        "summary": {
            "blocked_unsafe_count": len(blocked),
            "advisory_count": len(advisory),
            "total_detected": len(blockers),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_structural_graph(
    *,
    target_id: str,
    downstream_signals: Mapping[str, Any],
    runtime_source_correlation: Mapping[str, Any],
    driver_registration_graph: Mapping[str, Any],
    topology_structure_graph: Mapping[str, Any],
    upstream_equivalence_trace: Mapping[str, Any],
    governance_classification: str,
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [{"id": f"target:{target_id}", "kind": "target"}]
    edges: list[dict[str, Any]] = []

    kconfig_symbols = [
        str(item.get("symbol", ""))
        for item in _as_list(_as_dict(_as_dict(downstream_signals).get("kconfig")).get("symbols"))
        if isinstance(item, dict) and str(item.get("symbol", "")).strip()
    ]

    for symbol in _limit(_dedupe_sorted(kconfig_symbols), 250):
        node_id = f"kconfig:{symbol}"
        nodes.append({"id": node_id, "kind": "kconfig_symbol"})
        edges.append({"from": f"target:{target_id}", "to": node_id, "relation": "enables"})

    make_rules = [
        row
        for row in _as_list(_as_dict(_as_dict(downstream_signals).get("makefile")).get("rules"))
        if isinstance(row, dict)
    ]
    for row in _limit(make_rules, 300):
        file_path = str(row.get("file", "")).strip()
        objects = [str(item) for item in _as_list(row.get("objects")) if str(item).strip()]
        if not file_path or not objects:
            continue
        make_id = f"make:{file_path}"
        nodes.append({"id": make_id, "kind": "makefile"})
        edges.append({"from": f"target:{target_id}", "to": make_id, "relation": "build_file"})
        for obj in objects[:8]:
            obj_id = f"object:{obj}"
            nodes.append({"id": obj_id, "kind": "object"})
            edges.append({"from": make_id, "to": obj_id, "relation": "builds"})

    registration = _as_dict(driver_registration_graph)
    for row in _limit([r for r in _as_list(registration.get("component_lifecycle")) if isinstance(r, dict)], 200):
        name = str(row.get("component_driver", "")).strip()
        if not name:
            continue
        comp_id = f"component:{name}"
        nodes.append({"id": comp_id, "kind": "component_driver"})
        edges.append({"from": f"target:{target_id}", "to": comp_id, "relation": "registers"})

    topology = _as_dict(topology_structure_graph)
    for link in _limit([r for r in _as_list(_as_dict(topology.get("fe_be_topology")).get("inferred_links")) if isinstance(r, dict)], 300):
        fe = str(link.get("frontend", "")).strip()
        if not fe:
            continue
        fe_id = f"fe:{fe}"
        nodes.append({"id": fe_id, "kind": "frontend_dai"})
        edges.append({"from": f"target:{target_id}", "to": fe_id, "relation": "frontend"})
        for be in [str(item) for item in _as_list(link.get("backend_candidates")) if str(item).strip()][:3]:
            be_id = f"be:{be}"
            nodes.append({"id": be_id, "kind": "backend_dai"})
            edges.append({"from": fe_id, "to": be_id, "relation": "links_to_backend"})

    runtime_corr = _as_dict(runtime_source_correlation)
    runtime_id = f"runtime:{str(_as_dict(runtime_corr.get('runtime_snapshot')).get('run_id', 'unknown'))}"
    nodes.append({"id": runtime_id, "kind": "runtime_trace"})
    edges.append({"from": f"target:{target_id}", "to": runtime_id, "relation": "runtime_truth"})

    for row in _limit([r for r in _as_list(runtime_corr.get("command_source_correlations")) if isinstance(r, dict)], 200):
        command = str(row.get("runtime_command", "")).strip()
        if not command:
            continue
        cmd_id = f"runtime_command:{command}"
        nodes.append({"id": cmd_id, "kind": "runtime_command"})
        edges.append({"from": runtime_id, "to": cmd_id, "relation": "executes"})
        for path in [str(item) for item in _as_list(row.get("matched_source_files")) if str(item).strip()][:3]:
            src_id = f"source:{path}"
            nodes.append({"id": src_id, "kind": "source_file"})
            edges.append({"from": cmd_id, "to": src_id, "relation": "correlates"})

    upstream_summary = _as_dict(upstream_equivalence_trace.get("summary"))
    nodes.append(
        {
            "id": "upstream:equivalence_summary",
            "kind": "upstream_equivalence",
            "confidence": _to_float(upstream_summary.get("semantic_equivalence_confidence", 0.0)),
        }
    )
    edges.append({"from": f"target:{target_id}", "to": "upstream:equivalence_summary", "relation": "maps_to_upstream"})

    dedup_nodes: dict[str, dict[str, Any]] = {}
    for row in nodes:
        node_id = str(row.get("id", "")).strip()
        if node_id:
            dedup_nodes[node_id] = row

    dedup_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in edges:
        key = (str(row.get("from", "")), str(row.get("to", "")), str(row.get("relation", "")))
        dedup_edges[key] = row

    payload = {
        "schema_version": "1.0",
        "graph_name": "structural_graph",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if governance_classification == "FAIL_CLOSED" else "PASS",
        "nodes": sorted(dedup_nodes.values(), key=lambda row: str(row.get("id", ""))),
        "edges": sorted(
            dedup_edges.values(),
            key=lambda row: (str(row.get("from", "")), str(row.get("to", "")), str(row.get("relation", ""))),
        ),
        "summary": {
            "node_count": len(dedup_nodes),
            "edge_count": len(dedup_edges),
            "kconfig_symbol_count": len(_dedupe_sorted(kconfig_symbols)),
            "runtime_source_correlation_confidence": _to_float(runtime_corr.get("correlation_confidence", 0.0)),
            "upstream_semantic_equivalence_confidence": _to_float(upstream_summary.get("semantic_equivalence_confidence", 0.0)),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _governance_boundary(governance_state: Mapping[str, Any]) -> dict[str, Any]:
    gov = _as_dict(governance_state)

    violations = {
        "autonomous_patch_generation": _is_true(gov.get("autonomous_patching_allowed", False)),
        "autonomous_topology_mutation": _is_true(gov.get("autonomous_topology_rewrite_allowed", False))
        or _is_true(gov.get("autonomous_mixer_mutation_allowed", False)),
        "unsafe_runtime_rewrite": _is_true(gov.get("autonomous_runtime_mutation_allowed", False)),
        "autonomous_source_rewrite": _is_true(gov.get("autonomous_upstream_generation_allowed", False)),
    }
    blocked = sorted([key for key, value in violations.items() if value])

    classification = "FAIL_CLOSED" if blocked else "PASS"
    payload = {
        "schema_version": "1.0",
        "report_name": "structural_governance_boundaries",
        "classification": classification,
        "fail_closed_posture": bool(gov.get("fail_closed_posture", True)),
        "runtime_truth_precedence": True,
        "advisory_only_model": True,
        "allowed_actions": list(_ALLOWED_ACTIONS),
        "forbidden_actions": list(_FORBIDDEN_ACTIONS),
        "blocked_by_state": blocked,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class KernelStructuralCognitionPlanner:
    """Planner for deterministic structural cognition artifacts."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        downstream_root: str | Path,
        upstream_root: str | Path,
        runtime_evidence: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        lineage_id: str,
        evidence_references: list[str] | None,
    ) -> KernelStructuralCognitionPlannerResult:
        plugin = self._plugins.load_plugin(target_id)

        adapter_payload = _as_dict(
            plugin.structural_cognition_adapter(
                {
                    "target_id": str(target_id),
                    "downstream_root": str(downstream_root),
                    "upstream_root": str(upstream_root),
                    "runtime_evidence": dict(runtime_evidence),
                    "governance_state": dict(governance_state),
                }
            )
        )

        max_downstream_files = int(adapter_payload.get("max_downstream_scan_files", 8000) or 8000)
        max_upstream_files = int(adapter_payload.get("max_upstream_scan_files", 9000) or 9000)
        upstream_focus_paths = [
            str(item)
            for item in _as_list(adapter_payload.get("upstream_focus_paths"))
            if str(item).strip()
        ]
        if not upstream_focus_paths:
            upstream_focus_paths = ["sound/soc", "include/sound", "drivers/soundwire"]

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        governance_boundary = _governance_boundary(governance_state)
        governance_classification = str(governance_boundary.get("classification", "PASS"))

        downstream_signals = _extract_downstream_signals(
            Path(str(downstream_root)),
            max_files=max(1, max_downstream_files),
        )

        upstream_index = _build_upstream_index(
            Path(str(upstream_root)),
            max_files=max(1, max_upstream_files),
            focus_paths=upstream_focus_paths,
        )

        driver_registration_graph = _build_driver_registration_graph(
            target_id=target_id,
            downstream_signals=downstream_signals,
            governance_classification=governance_classification,
        )

        topology_structure_graph = _build_topology_structure_graph(
            target_id=target_id,
            downstream_signals=downstream_signals,
            governance_classification=governance_classification,
        )

        callback_chain_graph = _build_callback_chain_graph(
            target_id=target_id,
            downstream_signals=downstream_signals,
            governance_classification=governance_classification,
        )

        hook_inventory = _build_downstream_hook_inventory(
            target_id=target_id,
            downstream_signals=downstream_signals,
            adapter_payload=adapter_payload,
            governance_classification=governance_classification,
        )

        upstream_equivalence_trace = _build_upstream_equivalence_trace(
            target_id=target_id,
            downstream_signals=downstream_signals,
            upstream_index=upstream_index,
            adapter_payload=adapter_payload,
            evidence_references=evidence,
        )

        runtime_source_correlation = _build_runtime_source_correlation(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            downstream_signals=downstream_signals,
            topology_graph=topology_structure_graph,
            governance_classification=governance_classification,
        )

        portability_blocker_graph = _build_portability_blocker_graph(
            target_id=target_id,
            runtime_evidence=runtime_evidence,
            governance_state=governance_state,
            hook_inventory=hook_inventory,
            upstream_trace=upstream_equivalence_trace,
        )

        structural_graph = _build_structural_graph(
            target_id=target_id,
            downstream_signals=downstream_signals,
            runtime_source_correlation=runtime_source_correlation,
            driver_registration_graph=driver_registration_graph,
            topology_structure_graph=topology_structure_graph,
            upstream_equivalence_trace=upstream_equivalence_trace,
            governance_classification=governance_classification,
        )

        structural_classification = "PASS"
        if governance_classification == "FAIL_CLOSED":
            structural_classification = "FAIL_CLOSED"
        elif str(portability_blocker_graph.get("classification", "")) == "FAIL_CLOSED":
            structural_classification = "FAIL_CLOSED"
        elif str(portability_blocker_graph.get("classification", "")) == "ADVISORY_ONLY":
            structural_classification = "ADVISORY_ONLY"

        artifact_fingerprints = {
            "structural_graph": str(structural_graph.get("deterministic_fingerprint", "")),
            "driver_registration_graph": str(driver_registration_graph.get("deterministic_fingerprint", "")),
            "topology_structure_graph": str(topology_structure_graph.get("deterministic_fingerprint", "")),
            "runtime_source_correlation": str(runtime_source_correlation.get("deterministic_fingerprint", "")),
            "downstream_hook_inventory": str(hook_inventory.get("deterministic_fingerprint", "")),
            "upstream_equivalence_trace": str(upstream_equivalence_trace.get("deterministic_fingerprint", "")),
            "portability_blocker_graph": str(portability_blocker_graph.get("deterministic_fingerprint", "")),
            "callback_chain_graph": str(callback_chain_graph.get("deterministic_fingerprint", "")),
        }

        deterministic_structural_fingerprint = {
            "schema_version": "1.0",
            "report_name": "deterministic_structural_fingerprint",
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "classification": structural_classification,
            "runtime_truth_precedence": True,
            "advisory_only_model": True,
            "plugin_isolation": True,
            "governance_classification": governance_classification,
            "portability_blocker_classification": str(portability_blocker_graph.get("classification", "UNKNOWN")),
            "artifact_fingerprints": artifact_fingerprints,
            "governance_boundaries": governance_boundary,
            "evidence_references": evidence,
        }
        deterministic_structural_fingerprint["deterministic_fingerprint"] = stable_fingerprint(
            deterministic_structural_fingerprint
        )

        artifacts = {
            "structural_graph": structural_graph,
            "driver_registration_graph": driver_registration_graph,
            "topology_structure_graph": topology_structure_graph,
            "runtime_source_correlation": runtime_source_correlation,
            "downstream_hook_inventory": hook_inventory,
            "upstream_equivalence_trace": upstream_equivalence_trace,
            "portability_blocker_graph": portability_blocker_graph,
            "callback_chain_graph": callback_chain_graph,
            "deterministic_structural_fingerprint": deterministic_structural_fingerprint,
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "KERNEL_STRUCTURAL_COGNITION_LAYER",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "lineage_id": str(lineage_id),
            "downstream_root": str(Path(str(downstream_root)).resolve()),
            "upstream_root": str(Path(str(upstream_root)).resolve()),
            "runtime_truth_precedence": True,
            "advisory_only_model": True,
            "plugin_adapter_payload": adapter_payload,
            "governance_boundaries": governance_boundary,
            "evidence_references": evidence,
            "artifacts": artifacts,
        }
        bundle["structural_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "lineage_id": str(lineage_id),
                "artifacts": artifacts,
                "governance_boundaries": governance_boundary,
            }
        )

        return KernelStructuralCognitionPlannerResult(structural_bundle=bundle)


class KernelStructuralCognitionRegistry:
    """Replay-safe persistence for structural cognition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "structural_graph": self._output_dir / "structural_graph.json",
            "driver_registration_graph": self._output_dir / "driver_registration_graph.json",
            "topology_structure_graph": self._output_dir / "topology_structure_graph.json",
            "runtime_source_correlation": self._output_dir / "runtime_source_correlation.json",
            "downstream_hook_inventory": self._output_dir / "downstream_hook_inventory.json",
            "upstream_equivalence_trace": self._output_dir / "upstream_equivalence_trace.json",
            "portability_blocker_graph": self._output_dir / "portability_blocker_graph.json",
            "callback_chain_graph": self._output_dir / "callback_chain_graph.json",
            "deterministic_structural_fingerprint": self._output_dir / "deterministic_structural_fingerprint.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)

        paths = self._artifact_paths()
        for key, path in paths.items():
            artifact_payload = _as_dict(artifacts.get(key))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(artifact_payload, indent=2, sort_keys=True), encoding="utf-8")

        registry = self._registry.load()
        state = _as_dict(registry.get("kernel_structural_cognition"))
        history = _as_list(state.get("history"))

        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "structural_fingerprint": str(payload.get("structural_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "classification": str(
                _as_dict(artifacts.get("deterministic_structural_fingerprint")).get("classification", "UNKNOWN")
            ),
            "evidence_references": [
                str(item)
                for item in _as_list(payload.get("evidence_references"))
                if str(item).strip()
            ],
        }

        history.append(entry)
        history = history[-1500:]

        registry["kernel_structural_cognition"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }

        registry.setdefault("cognition_lineage", [])
        lineage = _as_list(registry.get("cognition_lineage"))
        lineage.append(
            {
                "lineage_id": lineage_id,
                "type": "kernel_structural_cognition",
                "recorded_at": _utc_now_iso(),
                "structural_fingerprint": str(payload.get("structural_fingerprint", "")),
                "evidence_references": entry["evidence_references"],
            }
        )
        registry["cognition_lineage"] = lineage[-7000:]
        registry["updated_at"] = _utc_now_iso()

        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "structural_fingerprint": str(payload.get("structural_fingerprint", "")),
            "artifact_paths": entry["artifact_paths"],
            "classification": entry["classification"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("kernel_structural_cognition"))
        history = _as_list(state.get("history"))

        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                entry = _as_dict(row)
                if str(entry.get("lineage_id", "")) == str(lineage_id):
                    selected = entry
                    break

        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "kernel_structural_cognition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "structural_fingerprint": str(_as_dict(selected).get("structural_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "evidence_references": _as_list(_as_dict(selected).get("evidence_references", [])),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "structural_fingerprint": str(_as_dict(selected).get("structural_fingerprint", "")),
                    "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }

        out = self._output_dir / "deterministic_structural_replay.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(replay_payload, indent=2, sort_keys=True), encoding="utf-8")
        return replay_payload
