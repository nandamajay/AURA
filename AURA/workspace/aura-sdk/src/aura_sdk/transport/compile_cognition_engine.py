"""Kernel dependency closure + compile cognition layer.

Deterministic compile-closure reasoning for governed downstream-to-upstream
transformations. This engine is evidence-backed and fail-closed by default.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_SOURCE_EXTS = {".c", ".h"}
_SOURCE_NAMES = {"kconfig", "makefile"}
_IGNORE_DIRS = {".git", ".repo", "out", "build", "__pycache__"}

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"][^>"]+[>"])', re.MULTILINE)
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)
_FUNC_RE = re.compile(
    r"(?m)^[ \t]*(?:static\s+)?(?:inline\s+)?(?:const\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*[\s\*]+)+([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\(([^;{}]*)\)\s*\{"
)
_EXPORT_RE = re.compile(r"\bEXPORT_SYMBOL(?:_GPL)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_KCONFIG_TOKEN_RE = re.compile(r"\b([A-Z][A-Z0-9_]+)\b")
_OBJ_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.$()\-+]+)\s*\+?=\s*(.+)$")
_PATCH_FILE_RE = re.compile(r"^---\s+a/(.+)$")

_BUILTIN_SYMBOLS = {
    "if",
    "for",
    "while",
    "switch",
    "return",
    "sizeof",
    "do",
    "case",
    "defined",
    "struct",
    "ARRAY_SIZE",
    "max",
    "min",
    "pr_debug",
    "pr_info",
    "pr_err",
    "dev_dbg",
    "dev_info",
    "dev_err",
    "memcpy",
    "memset",
    "strlen",
    "strcmp",
    "snprintf",
}

_KCONFIG_RESERVED = {
    "Y",
    "N",
    "M",
    "BROKEN",
    "COMPILE_TEST",
    "EXPERT",
    "ARCH_QCOM",
    "SND",
    "OF",
    "PM",
    "DEBUG_FS",
}

_SENSITIVE_KEYWORDS = (
    "soundwire",
    "swr_",
    "pcm",
    "dapm",
    "irq",
    "dsp",
    "mailbox",
    "pm_runtime",
    "runtime_pm",
    "regulator",
    "clk",
    "q6",
    "apr",
)


@dataclass(frozen=True)
class CompileCognitionResult:
    compile_bundle: dict[str, Any]


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


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _is_source_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in _IGNORE_DIRS for part in path.parts):
        return False
    if path.suffix.lower() in _SOURCE_EXTS:
        return True
    return path.name.lower() in _SOURCE_NAMES


def _iter_sources(root: Path, max_files: int) -> list[Path]:
    rows: list[Path] = []
    for item in root.rglob("*"):
        if len(rows) >= max_files:
            break
        if _is_source_file(item):
            rows.append(item)
    rows.sort(key=lambda p: str(p))
    return rows


def _extract_includes(text: str) -> list[str]:
    out: list[str] = []
    for item in _INCLUDE_RE.findall(text):
        token = str(item).strip()
        if not token:
            continue
        if token.startswith("<") and token.endswith(">"):
            out.append(token[1:-1].strip())
        elif token.startswith('"') and token.endswith('"'):
            out.append(token[1:-1].strip())
    return sorted({v for v in out if v})


def _extract_calls(text: str) -> list[str]:
    calls: set[str] = set()
    for token in _CALL_RE.findall(text):
        symbol = str(token).strip()
        if not symbol or symbol in _BUILTIN_SYMBOLS:
            continue
        calls.add(symbol)
    return sorted(calls)


def _extract_defines(text: str) -> list[str]:
    return sorted({str(v).strip() for v in _DEFINE_RE.findall(text) if str(v).strip()})


def _extract_function_defs(text: str) -> list[str]:
    out: set[str] = set()
    for match in _FUNC_RE.findall(text):
        if isinstance(match, tuple) and len(match) >= 1:
            symbol = str(match[0]).strip()
            if symbol:
                out.add(symbol)
    return sorted(out)


def _extract_exported_symbols(text: str) -> list[str]:
    return sorted({str(v).strip() for v in _EXPORT_RE.findall(text) if str(v).strip()})


def _subsystem_for(rel_path: str) -> str:
    low = rel_path.replace("\\", "/").lower()
    if low.startswith("asoc/codecs/"):
        return "asoc_codecs"
    if low.startswith("asoc/"):
        return "asoc_machine"
    if low.startswith("dsp/"):
        return "dsp"
    if low.startswith("ipc/"):
        return "ipc"
    if low.startswith("soundwire/") or "soundwire" in low:
        return "soundwire"
    if low.startswith("include/"):
        return "include"
    if low.endswith("/kconfig") or "/kconfig" in low:
        return "kconfig"
    if low.endswith("/makefile") or "/makefile" in low:
        return "makefile"
    return "other"


def _driver_for(rel_path: str) -> str:
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] == "asoc" and parts[1] == "codecs":
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return rel_path


def _resolve_include(source_root: Path, file_path: Path, include: str) -> str:
    rel = str(include).strip().replace("\\", "/")
    if not rel:
        return ""
    candidates = [
        file_path.parent / rel,
        source_root / rel,
        source_root / "include" / rel,
        source_root / "asoc" / rel,
        source_root / "dsp" / rel,
        source_root / "ipc" / rel,
        source_root / "sound" / rel,
        source_root / "soundwire" / rel,
        source_root / "soc" / rel,
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            try:
                return str(path.relative_to(source_root)).replace("\\", "/")
            except ValueError:
                return str(path.resolve())
    return ""


def _missing_include_severity(include: str) -> str:
    low = include.strip().lower()
    if low.startswith(("linux/", "sound/", "soc/", "asm/", "uapi/")):
        return "high"
    return "critical"


def _parse_patch_touched_files(patch_text: str) -> list[str]:
    rows: list[str] = []
    for raw in patch_text.splitlines():
        match = _PATCH_FILE_RE.match(str(raw))
        if not match:
            continue
        rel = str(match.group(1)).strip()
        if rel and rel != "/dev/null":
            rows.append(rel)
    return sorted(set(rows))


def _load_file_data(source_root: Path, files: list[Path]) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for path in files:
        rel = str(path.relative_to(source_root)).replace("\\", "/")
        text = _read_text(path)
        kind = "other"
        low_name = path.name.lower()
        if low_name == "kconfig":
            kind = "kconfig"
        elif low_name == "makefile":
            kind = "makefile"
        elif path.suffix.lower() == ".h":
            kind = "header"
        elif path.suffix.lower() == ".c":
            kind = "source"
        data[rel] = {
            "kind": kind,
            "subsystem": _subsystem_for(rel),
            "driver": _driver_for(rel),
            "text": text,
            "line_count": text.count("\n") + 1 if text else 0,
            "includes": _extract_includes(text) if kind in {"source", "header"} else [],
            "calls": _extract_calls(text) if kind == "source" else [],
            "defines": _extract_defines(text) if kind in {"source", "header"} else [],
            "function_defs": _extract_function_defs(text) if kind == "source" else [],
            "exported_symbols": _extract_exported_symbols(text) if kind == "source" else [],
            "runtime_sensitive": any(key in (rel.lower() + "\n" + text.lower()) for key in _SENSITIVE_KEYWORDS),
        }
    return data


def _build_include_closure_graph(
    *,
    target_id: str,
    source_root: Path,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    adjacency: dict[str, list[str]] = {}

    for rel, row in sorted(file_data.items()):
        entry = _as_dict(row)
        includes = [str(v) for v in _as_list(entry.get("includes")) if str(v).strip()]
        path = source_root / rel
        for inc in includes:
            resolved = _resolve_include(source_root, path, inc)
            status = "resolved" if resolved else "missing"
            if status == "resolved":
                adjacency.setdefault(rel, []).append(resolved)
            else:
                missing_rows.append(
                    {
                        "from_file": rel,
                        "include": inc,
                        "severity": _missing_include_severity(inc),
                        "subsystem": str(entry.get("subsystem", "")),
                    }
                )
            edges.append(
                {
                    "from_file": rel,
                    "include": inc,
                    "to_file": resolved,
                    "status": status,
                }
            )

    unresolved_chains: list[dict[str, Any]] = []
    for row in missing_rows[:4000]:
        item = _as_dict(row)
        unresolved_chains.append(
            {
                "chain": [str(item.get("from_file", "")), str(item.get("include", ""))],
                "severity": str(item.get("severity", "high")),
            }
        )

    classification = "PASS" if not missing_rows else "FAIL_CLOSED"
    report = {
        "schema_version": "1.0",
        "graph_name": "include_closure_graph",
        "target_id": str(target_id),
        "classification": classification,
        "include_edges": edges[:40000],
        "unresolved_include_chains": unresolved_chains,
        "summary": {
            "edge_count": len(edges),
            "resolved_edge_count": sum(1 for row in edges if str(_as_dict(row).get("status")) == "resolved"),
            "missing_edge_count": len(missing_rows),
            "critical_missing_count": sum(1 for row in missing_rows if str(_as_dict(row).get("severity")) == "critical"),
            "high_missing_count": sum(1 for row in missing_rows if str(_as_dict(row).get("severity")) == "high"),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    unresolved = {
        "missing_includes": missing_rows[:12000],
        "missing_include_count": len(missing_rows),
    }
    return report, unresolved


def _build_symbol_dependency_graph(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    providers: dict[str, set[str]] = {}
    exported_symbols: dict[str, set[str]] = {}
    for rel, row in sorted(file_data.items()):
        entry = _as_dict(row)
        symbols = [str(v) for v in _as_list(entry.get("function_defs"))] + [str(v) for v in _as_list(entry.get("defines"))]
        for sym in symbols:
            if not sym:
                continue
            providers.setdefault(sym, set()).add(rel)
        for sym in _as_list(entry.get("exported_symbols")):
            token = str(sym).strip()
            if token:
                exported_symbols.setdefault(token, set()).add(rel)

    dependency_edges: list[dict[str, Any]] = []
    unresolved_calls: list[dict[str, Any]] = []
    propagation: list[dict[str, Any]] = []
    for rel, row in sorted(file_data.items()):
        entry = _as_dict(row)
        for call in _as_list(entry.get("calls")):
            symbol = str(call).strip()
            if not symbol or symbol in _BUILTIN_SYMBOLS:
                continue
            owners = sorted(providers.get(symbol, set()))
            if not owners:
                unresolved_calls.append(
                    {
                        "consumer_file": rel,
                        "symbol": symbol,
                        "subsystem": str(entry.get("subsystem", "")),
                        "runtime_sensitive": bool(entry.get("runtime_sensitive", False)),
                        "impact": "critical" if bool(entry.get("runtime_sensitive", False)) else "high",
                    }
                )
                continue
            dependency_edges.append(
                {
                    "consumer_file": rel,
                    "symbol": symbol,
                    "provider_files": owners[:20],
                    "resolution": "resolved",
                }
            )
            for owner in owners[:20]:
                if _driver_for(owner) != _driver_for(rel):
                    propagation.append(
                        {
                            "provider_file": owner,
                            "consumer_file": rel,
                            "symbol": symbol,
                            "provider_driver": _driver_for(owner),
                            "consumer_driver": _driver_for(rel),
                        }
                    )

    unresolved_exports: list[dict[str, Any]] = []
    for sym, owners in sorted(exported_symbols.items()):
        provider_files = sorted(providers.get(sym, set()))
        if provider_files:
            continue
        unresolved_exports.append(
            {
                "symbol": sym,
                "export_decl_files": sorted(set(owners))[:30],
                "impact": "critical",
            }
        )

    classification = "PASS" if not unresolved_calls and not unresolved_exports else "FAIL_CLOSED"
    report = {
        "schema_version": "1.0",
        "graph_name": "symbol_dependency_graph",
        "target_id": str(target_id),
        "classification": classification,
        "dependency_edges": dependency_edges[:40000],
        "cross_driver_dependency_propagation": propagation[:12000],
        "unresolved_calls": unresolved_calls[:8000],
        "unresolved_exported_symbols": unresolved_exports[:4000],
        "summary": {
            "resolved_edge_count": len(dependency_edges),
            "cross_driver_propagation_count": len(propagation),
            "unresolved_call_count": len(unresolved_calls),
            "unresolved_exported_symbol_count": len(unresolved_exports),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    unresolved = {
        "unresolved_symbols": unresolved_calls[:8000],
        "unresolved_exported_symbols": unresolved_exports[:4000],
        "unresolved_symbol_count": len(unresolved_calls) + len(unresolved_exports),
    }
    return report, unresolved


def _parse_kconfig_dependencies(text: str) -> dict[str, Any]:
    config_map: dict[str, dict[str, set[str]]] = {}
    current = ""
    for raw in text.splitlines():
        line = str(raw).strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("config ") or line.startswith("menuconfig "):
            parts = line.split()
            if len(parts) >= 2:
                current = parts[1].strip()
                if current:
                    config_map.setdefault(current, {"depends_on": set(), "selects": set(), "implies": set()})
            continue
        if not current:
            continue
        if line.startswith("depends on "):
            expr = line[len("depends on ") :]
            for token in _KCONFIG_TOKEN_RE.findall(expr):
                if token:
                    config_map[current]["depends_on"].add(token)
            continue
        if line.startswith("select "):
            token = line[len("select ") :].split()[0].strip()
            if token:
                config_map[current]["selects"].add(token)
            continue
        if line.startswith("imply "):
            token = line[len("imply ") :].split()[0].strip()
            if token:
                config_map[current]["implies"].add(token)
            continue
    return config_map


def _parse_makefile_objects(file_path: str, text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    order = 0
    for raw in text.splitlines():
        line = str(raw).strip()
        if not line or line.startswith("#"):
            continue
        match = _OBJ_LINE_RE.match(line)
        if not match:
            continue
        lhs = str(match.group(1)).strip()
        rhs = str(match.group(2)).strip()
        if not lhs or not rhs:
            continue
        guard = ""
        if "CONFIG_" in lhs:
            start = lhs.find("CONFIG_")
            end = lhs.find(")", start)
            guard_token = lhs[start:end] if start >= 0 and end > start else ""
            guard = guard_token[len("CONFIG_") :] if guard_token.startswith("CONFIG_") else guard_token
        for token in rhs.replace("\\", " ").split():
            obj = token.strip()
            if not obj or not obj.endswith(".o"):
                continue
            order += 1
            rows.append(
                {
                    "makefile": file_path,
                    "lhs": lhs,
                    "object": obj,
                    "guard_config": guard,
                    "order": order,
                }
            )
    return rows


def _build_kconfig_map_and_makefile_topology(
    *,
    target_id: str,
    source_root: Path,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    configs: dict[str, dict[str, set[str]]] = {}
    config_sources: dict[str, list[str]] = {}
    make_rows: list[dict[str, Any]] = []

    for rel, row in sorted(file_data.items()):
        entry = _as_dict(row)
        kind = str(entry.get("kind", ""))
        if kind == "kconfig":
            parsed = _parse_kconfig_dependencies(str(entry.get("text", "")))
            for sym, deps in parsed.items():
                dest = configs.setdefault(sym, {"depends_on": set(), "selects": set(), "implies": set()})
                dest["depends_on"].update(set(_as_dict(deps).get("depends_on", set())))
                dest["selects"].update(set(_as_dict(deps).get("selects", set())))
                dest["implies"].update(set(_as_dict(deps).get("implies", set())))
                config_sources.setdefault(sym, []).append(rel)
        elif kind == "makefile":
            make_rows.extend(_parse_makefile_objects(rel, str(entry.get("text", ""))))

    unknown_refs: list[dict[str, Any]] = []
    for sym, deps in sorted(configs.items()):
        for dep in sorted(set(deps.get("depends_on", set())) | set(deps.get("selects", set())) | set(deps.get("implies", set()))):
            if dep in configs or dep in _KCONFIG_RESERVED:
                continue
            unknown_refs.append(
                {
                    "config": sym,
                    "missing_reference": dep,
                    "impact": "high",
                }
            )

    impossible_configs: list[dict[str, Any]] = []
    object_rows: list[dict[str, Any]] = []
    for row in make_rows:
        item = _as_dict(row)
        makefile = str(item.get("makefile", ""))
        obj = str(item.get("object", ""))
        guard = str(item.get("guard_config", ""))
        source_candidate = str((Path(makefile).parent / obj).with_suffix(".c")).replace("\\", "/")
        source_exists = source_candidate in file_data
        if guard and guard not in configs:
            impossible_configs.append(
                {
                    "guard_config": guard,
                    "makefile": makefile,
                    "object": obj,
                    "impact": "critical",
                }
            )
        object_rows.append(
            {
                "makefile": makefile,
                "object": obj,
                "source_candidate": source_candidate,
                "source_exists": source_exists,
                "subsystem": _subsystem_for(source_candidate),
                "guard_config": guard,
                "order": int(item.get("order", 0)),
            }
        )

    missing_object_sources = [row for row in object_rows if not bool(_as_dict(row).get("source_exists", False))]
    topology_classification = "PASS" if not missing_object_sources and not impossible_configs else "FAIL_CLOSED"

    kconfig_map = {
        "schema_version": "1.0",
        "graph_name": "kconfig_dependency_map",
        "target_id": str(target_id),
        "classification": "PASS" if not unknown_refs and not impossible_configs else "FAIL_CLOSED",
        "configs": [
            {
                "symbol": sym,
                "defined_in": sorted(set(config_sources.get(sym, []))),
                "depends_on": sorted(set(v.get("depends_on", set()))),
                "selects": sorted(set(v.get("selects", set()))),
                "implies": sorted(set(v.get("implies", set()))),
            }
            for sym, v in sorted(configs.items())
        ],
        "unknown_dependency_references": unknown_refs[:6000],
        "impossible_compile_configurations": impossible_configs[:6000],
        "summary": {
            "config_count": len(configs),
            "unknown_dependency_reference_count": len(unknown_refs),
            "impossible_compile_configuration_count": len(impossible_configs),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    kconfig_map["deterministic_fingerprint"] = stable_fingerprint(kconfig_map)

    subsystem_groups: dict[str, list[dict[str, Any]]] = {}
    for row in object_rows:
        subsystem = str(_as_dict(row).get("subsystem", "other"))
        subsystem_groups.setdefault(subsystem, []).append(row)
    topology = {
        "schema_version": "1.0",
        "graph_name": "subsystem_compile_topology",
        "target_id": str(target_id),
        "classification": topology_classification,
        "objects": object_rows[:40000],
        "subsystems": [
            {
                "subsystem": name,
                "object_count": len(rows),
                "objects": rows[:800],
            }
            for name, rows in sorted(subsystem_groups.items())
        ],
        "missing_object_sources": missing_object_sources[:8000],
        "summary": {
            "object_count": len(object_rows),
            "subsystem_count": len(subsystem_groups),
            "missing_object_source_count": len(missing_object_sources),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    topology["deterministic_fingerprint"] = stable_fingerprint(topology)

    unresolved = {
        "kconfig_unknown_references": unknown_refs[:6000],
        "kconfig_impossible_configurations": impossible_configs[:6000],
        "missing_object_sources": missing_object_sources[:8000],
        "kconfig_inconsistency_count": len(unknown_refs) + len(impossible_configs),
        "makefile_inconsistency_count": len(missing_object_sources),
    }
    return kconfig_map, topology, unresolved


def _build_compile_boundary_report(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    touched_files: list[str],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    touched_rows: list[dict[str, Any]] = []
    touched_subsystems: set[str] = set()
    sensitive_touches = 0
    for rel in touched_files:
        row = _as_dict(file_data.get(rel))
        subsystem = str(row.get("subsystem", _subsystem_for(rel)))
        runtime_sensitive = bool(row.get("runtime_sensitive", False))
        touched_subsystems.add(subsystem)
        if runtime_sensitive:
            sensitive_touches += 1
        touched_rows.append(
            {
                "file": rel,
                "subsystem": subsystem,
                "runtime_sensitive": runtime_sensitive,
                "driver": str(row.get("driver", _driver_for(rel))),
            }
        )

    crossings: list[dict[str, Any]] = []
    if len(touched_subsystems) > 1:
        crossings.append(
            {
                "type": "cross_subsystem_patch_scope",
                "subsystems": sorted(touched_subsystems),
                "severity": "critical" if sensitive_touches > 0 else "high",
            }
        )

    classification = "PASS"
    if crossings and any(str(_as_dict(v).get("severity", "")) == "critical" for v in crossings):
        classification = "FAIL_CLOSED"
    report = {
        "schema_version": "1.0",
        "report_name": "compile_boundary_report",
        "target_id": str(target_id),
        "classification": classification,
        "touched_files": touched_rows,
        "boundary_crossings": crossings,
        "summary": {
            "touched_file_count": len(touched_rows),
            "touched_subsystem_count": len(touched_subsystems),
            "runtime_sensitive_touch_count": sensitive_touches,
            "crossing_count": len(crossings),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    unresolved = {
        "boundary_crossing_count": len(crossings),
        "critical_boundary_crossing_count": sum(1 for row in crossings if str(_as_dict(row).get("severity")) == "critical"),
    }
    return report, unresolved


def _build_unresolved_dependency_report(
    *,
    target_id: str,
    include_unresolved: Mapping[str, Any],
    symbol_unresolved: Mapping[str, Any],
    topology_unresolved: Mapping[str, Any],
    boundary_unresolved: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    include_missing = int(include_unresolved.get("missing_include_count", 0))
    symbol_missing = int(symbol_unresolved.get("unresolved_symbol_count", 0))
    kconfig_bad = int(topology_unresolved.get("kconfig_inconsistency_count", 0))
    makefile_bad = int(topology_unresolved.get("makefile_inconsistency_count", 0))
    boundary_critical = int(boundary_unresolved.get("critical_boundary_crossing_count", 0))
    total = include_missing + symbol_missing + kconfig_bad + makefile_bad + boundary_critical
    payload = {
        "schema_version": "1.0",
        "report_name": "unresolved_dependency_report",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if total > 0 else "PASS",
        "include": {
            "missing_include_count": include_missing,
            "samples": _as_list(include_unresolved.get("missing_includes"))[:2000],
        },
        "symbols": {
            "unresolved_symbol_count": symbol_missing,
            "samples": _as_list(symbol_unresolved.get("unresolved_symbols"))[:2000],
            "unresolved_exported_symbols": _as_list(symbol_unresolved.get("unresolved_exported_symbols"))[:1000],
        },
        "kconfig_makefile": {
            "kconfig_inconsistency_count": kconfig_bad,
            "makefile_inconsistency_count": makefile_bad,
            "kconfig_unknown_references": _as_list(topology_unresolved.get("kconfig_unknown_references"))[:1000],
            "kconfig_impossible_configurations": _as_list(topology_unresolved.get("kconfig_impossible_configurations"))[:1000],
            "missing_object_sources": _as_list(topology_unresolved.get("missing_object_sources"))[:1000],
        },
        "compile_boundary": {
            "critical_boundary_crossing_count": boundary_critical,
            "boundary_crossing_count": int(boundary_unresolved.get("boundary_crossing_count", 0)),
        },
        "summary": {
            "total_unresolved_count": total,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_confidence_report(
    *,
    target_id: str,
    include_graph: Mapping[str, Any],
    symbol_graph: Mapping[str, Any],
    kconfig_map: Mapping[str, Any],
    subsystem_topology: Mapping[str, Any],
    boundary_report: Mapping[str, Any],
    unresolved_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    score = 1.0
    include_summary = _as_dict(include_graph.get("summary"))
    symbol_summary = _as_dict(symbol_graph.get("summary"))
    kconfig_summary = _as_dict(kconfig_map.get("summary"))
    topology_summary = _as_dict(subsystem_topology.get("summary"))
    boundary_summary = _as_dict(boundary_report.get("summary"))

    critical_missing = int(include_summary.get("critical_missing_count", 0))
    high_missing = int(include_summary.get("high_missing_count", 0))
    unresolved_symbols = int(symbol_summary.get("unresolved_call_count", 0)) + int(
        symbol_summary.get("unresolved_exported_symbol_count", 0)
    )
    kconfig_bad = int(kconfig_summary.get("unknown_dependency_reference_count", 0)) + int(
        kconfig_summary.get("impossible_compile_configuration_count", 0)
    )
    topology_bad = int(topology_summary.get("missing_object_source_count", 0))
    critical_crossings = int(boundary_summary.get("crossing_count", 0)) if str(boundary_report.get("classification")) != "PASS" else 0

    if critical_missing > 0:
        score -= 0.35
    if high_missing > 0:
        score -= 0.15
    if unresolved_symbols > 0:
        score -= 0.25
    if kconfig_bad > 0:
        score -= 0.20
    if topology_bad > 0:
        score -= 0.20
    if critical_crossings > 0:
        score -= 0.15
    score = max(0.0, min(1.0, round(score, 3)))
    classification = "PASS" if score >= 0.78 else "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "compile_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "confidence_score": score,
        "confidence_threshold": 0.78,
        "inputs": {
            "critical_missing_include_count": critical_missing,
            "high_missing_include_count": high_missing,
            "unresolved_symbol_count": unresolved_symbols,
            "kconfig_inconsistency_count": kconfig_bad,
            "subsystem_topology_unproven_count": topology_bad,
            "compile_boundary_crossing_count": critical_crossings,
            "unresolved_dependency_total": int(_as_dict(unresolved_report.get("summary")).get("total_unresolved_count", 0)),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_governance_escalation(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    include_graph: Mapping[str, Any],
    symbol_graph: Mapping[str, Any],
    kconfig_map: Mapping[str, Any],
    subsystem_topology: Mapping[str, Any],
    boundary_report: Mapping[str, Any],
    unresolved_report: Mapping[str, Any],
    confidence_report: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if str(include_graph.get("classification", "")) != "PASS":
        reasons.append("include_closure_incomplete")
    if str(symbol_graph.get("classification", "")) != "PASS":
        reasons.append("symbol_lineage_unresolved")
    if str(kconfig_map.get("classification", "")) != "PASS":
        reasons.append("kconfig_dependency_chain_inconsistent")
    if str(subsystem_topology.get("classification", "")) != "PASS":
        reasons.append("subsystem_compile_topology_unproven")
    if str(boundary_report.get("classification", "")) != "PASS":
        reasons.append("compile_boundary_crossing_unsafe")
    if int(_as_dict(boundary_report.get("summary")).get("runtime_sensitive_touch_count", 0)) > 0 and str(
        boundary_report.get("classification", "")
    ) != "PASS":
        reasons.append("runtime_sensitive_compile_regions_impacted")
    if str(confidence_report.get("classification", "")) != "PASS":
        reasons.append("compile_confidence_below_threshold")

    if bool(_as_dict(governance_state).get("autonomous_patching_allowed", False)):
        reasons.append("governance_violation:autonomous_patching_allowed")
    if bool(_as_dict(governance_state).get("autonomous_runtime_mutation_allowed", False)):
        reasons.append("governance_violation:autonomous_runtime_mutation_allowed")
    if bool(_as_dict(governance_state).get("autonomous_topology_rewrite_allowed", False)):
        reasons.append("governance_violation:autonomous_topology_rewrite_allowed")
    if bool(_as_dict(governance_state).get("autonomous_upstream_generation_allowed", False)):
        reasons.append("governance_violation:autonomous_upstream_generation_allowed")

    reasons = sorted(set(reasons))
    payload = {
        "schema_version": "1.0",
        "report_name": "compile_governance_escalation",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if reasons else "PASS",
        "escalation_reasons": reasons,
        "governance_state": dict(_as_dict(governance_state)),
        "summary": {
            "reason_count": len(reasons),
            "unresolved_dependency_total": int(_as_dict(unresolved_report.get("summary")).get("total_unresolved_count", 0)),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, reasons


class CompileCognitionEngine:
    """Dependency closure and compile cognition for governed conversion."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        source_root: str | Path,
        patch_path: str | Path | None,
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_history: list[Mapping[str, Any]] | None,
        session_id: str,
        lineage_id: str,
        evidence_references: list[str] | None,
        max_files: int = 12000,
    ) -> CompileCognitionResult:
        source_path = Path(str(source_root))
        evidence = [str(v) for v in (evidence_references or []) if str(v).strip()]

        if not source_path.exists() or not source_path.is_dir():
            fail = {
                "schema_version": "1.0",
                "phase": "COMPILE_COGNITION",
                "created_at": _utc_now_iso(),
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["source_root_missing_or_invalid"],
                "artifacts": {},
                "runtime_truth_precedence": True,
                "advisory_only_behavior": True,
                "evidence_references": evidence,
            }
            fail["compile_cognition_fingerprint"] = stable_fingerprint(fail)
            return CompileCognitionResult(compile_bundle=fail)

        patch_text = ""
        if patch_path:
            patch = Path(str(patch_path))
            if patch.exists() and patch.is_file():
                patch_text = _read_text(patch)

        plugin = self._plugins.load_plugin(target_id)
        _ = plugin.capability_provider(
            {
                "target_id": str(target_id),
                "plugin_capability_state": dict(_as_dict(plugin_capability_state)),
                "source_root": str(source_path.resolve()),
            }
        )

        files = _iter_sources(source_path, max_files=max(1000, int(max_files)))
        file_data = _load_file_data(source_path, files)
        touched_files = _parse_patch_touched_files(patch_text)

        include_graph, include_unresolved = _build_include_closure_graph(
            target_id=target_id,
            source_root=source_path,
            file_data=file_data,
            evidence_references=evidence,
        )
        symbol_graph, symbol_unresolved = _build_symbol_dependency_graph(
            target_id=target_id,
            file_data=file_data,
            evidence_references=evidence,
        )
        kconfig_map, subsystem_topology, topology_unresolved = _build_kconfig_map_and_makefile_topology(
            target_id=target_id,
            source_root=source_path,
            file_data=file_data,
            evidence_references=evidence,
        )
        boundary_report, boundary_unresolved = _build_compile_boundary_report(
            target_id=target_id,
            file_data=file_data,
            touched_files=touched_files,
            evidence_references=evidence,
        )
        unresolved_report = _build_unresolved_dependency_report(
            target_id=target_id,
            include_unresolved=include_unresolved,
            symbol_unresolved=symbol_unresolved,
            topology_unresolved=topology_unresolved,
            boundary_unresolved=boundary_unresolved,
            evidence_references=evidence,
        )
        confidence_report = _build_confidence_report(
            target_id=target_id,
            include_graph=include_graph,
            symbol_graph=symbol_graph,
            kconfig_map=kconfig_map,
            subsystem_topology=subsystem_topology,
            boundary_report=boundary_report,
            unresolved_report=unresolved_report,
            evidence_references=evidence,
        )
        governance_report, fail_reasons = _build_governance_escalation(
            target_id=target_id,
            governance_state=governance_state,
            include_graph=include_graph,
            symbol_graph=symbol_graph,
            kconfig_map=kconfig_map,
            subsystem_topology=subsystem_topology,
            boundary_report=boundary_report,
            unresolved_report=unresolved_report,
            confidence_report=confidence_report,
            evidence_references=evidence,
        )
        classification = "FAIL_CLOSED" if fail_reasons else "PASS"

        deterministic_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_compile_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "artifact_fingerprints": {
                "include_closure_graph": str(include_graph.get("deterministic_fingerprint", "")),
                "symbol_dependency_graph": str(symbol_graph.get("deterministic_fingerprint", "")),
                "kconfig_dependency_map": str(kconfig_map.get("deterministic_fingerprint", "")),
                "subsystem_compile_topology": str(subsystem_topology.get("deterministic_fingerprint", "")),
                "compile_boundary_report": str(boundary_report.get("deterministic_fingerprint", "")),
                "unresolved_dependency_report": str(unresolved_report.get("deterministic_fingerprint", "")),
                "compile_confidence_report": str(confidence_report.get("deterministic_fingerprint", "")),
                "compile_governance_escalation": str(governance_report.get("deterministic_fingerprint", "")),
            },
            "replay_signal": {
                "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            "history": [row for row in _as_list(previous_history or []) if isinstance(row, dict)]
            + [
                {
                    "lineage_id": str(lineage_id),
                    "session_id": str(session_id),
                    "classification": classification,
                }
            ],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_replay)

        artifacts = {
            "include_closure_graph": include_graph,
            "symbol_dependency_graph": symbol_graph,
            "kconfig_dependency_map": kconfig_map,
            "compile_boundary_report": boundary_report,
            "unresolved_dependency_report": unresolved_report,
            "compile_governance_escalation": governance_report,
            "deterministic_compile_replay": deterministic_replay,
            "compile_confidence_report": confidence_report,
            "subsystem_compile_topology": subsystem_topology,
        }

        summary = {
            "schema_version": "1.0",
            "report_name": "compile_cognition_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "summary": {
                "files_analyzed": len(files),
                "touched_files": len(touched_files),
                "missing_include_count": int(_as_dict(include_graph.get("summary")).get("missing_edge_count", 0)),
                "unresolved_symbol_count": int(_as_dict(symbol_graph.get("summary")).get("unresolved_call_count", 0))
                + int(_as_dict(symbol_graph.get("summary")).get("unresolved_exported_symbol_count", 0)),
                "kconfig_inconsistency_count": int(_as_dict(kconfig_map.get("summary")).get("unknown_dependency_reference_count", 0))
                + int(_as_dict(kconfig_map.get("summary")).get("impossible_compile_configuration_count", 0)),
                "missing_object_source_count": int(_as_dict(subsystem_topology.get("summary")).get("missing_object_source_count", 0)),
                "confidence_score": _to_float(confidence_report.get("confidence_score"), 0.0),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
        }
        summary["deterministic_fingerprint"] = stable_fingerprint(summary)
        artifacts["compile_cognition_summary"] = summary

        bundle = {
            "schema_version": "1.0",
            "phase": "COMPILE_COGNITION",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "source_root": str(source_path.resolve()),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "artifacts": artifacts,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        bundle["compile_cognition_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "fail_closed_reasons": sorted(set(fail_reasons)),
                "artifact_fingerprints": {
                    key: str(_as_dict(val).get("deterministic_fingerprint", ""))
                    for key, val in sorted(artifacts.items())
                },
            }
        )
        return CompileCognitionResult(compile_bundle=bundle)


class CompileCognitionRegistry:
    """Persistence for compile cognition artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "include_closure_graph": self._output_dir / "include_closure_graph.json",
            "symbol_dependency_graph": self._output_dir / "symbol_dependency_graph.json",
            "kconfig_dependency_map": self._output_dir / "kconfig_dependency_map.json",
            "compile_boundary_report": self._output_dir / "compile_boundary_report.json",
            "unresolved_dependency_report": self._output_dir / "unresolved_dependency_report.json",
            "compile_governance_escalation": self._output_dir / "compile_governance_escalation.json",
            "deterministic_compile_replay": self._output_dir / "deterministic_compile_replay.json",
            "compile_confidence_report": self._output_dir / "compile_confidence_report.json",
            "subsystem_compile_topology": self._output_dir / "subsystem_compile_topology.json",
            "compile_cognition_summary": self._output_dir / "compile_cognition_summary.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        for key in (
            "include_closure_graph",
            "symbol_dependency_graph",
            "kconfig_dependency_map",
            "compile_boundary_report",
            "unresolved_dependency_report",
            "compile_governance_escalation",
            "deterministic_compile_replay",
            "compile_confidence_report",
            "subsystem_compile_topology",
            "compile_cognition_summary",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("compile_cognition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "compile_cognition_fingerprint": str(payload.get("compile_cognition_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
        }
        history.append(entry)
        history = history[-8000:]

        registry["compile_cognition"] = {
            "schema_version": "1.0",
            "latest": dict(payload),
            "history": history,
            "updated_at": _utc_now_iso(),
        }
        registry.setdefault("cognition_lineage", [])
        lineages = [row for row in _as_list(registry.get("cognition_lineage")) if isinstance(row, dict)]
        lineages.append(
            {
                "lineage_id": lineage_id,
                "type": "compile_cognition",
                "recorded_at": _utc_now_iso(),
                "compile_cognition_fingerprint": str(payload.get("compile_cognition_fingerprint", "")),
            }
        )
        registry["cognition_lineage"] = lineages[-32000:]
        registry["updated_at"] = _utc_now_iso()
        self._registry.save(registry)

        return {
            "lineage_id": lineage_id,
            "session_id": entry["session_id"],
            "classification": entry["classification"],
            "fail_closed_reasons": entry["fail_closed_reasons"],
            "compile_cognition_fingerprint": entry["compile_cognition_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("compile_cognition"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        selected: dict[str, Any] | None = None
        if lineage_id:
            for row in reversed(history):
                item = _as_dict(row)
                if str(item.get("lineage_id", "")) == str(lineage_id):
                    selected = item
                    break
        if selected is None and history:
            selected = _as_dict(history[-1])

        replay_payload = {
            "schema_version": "1.0",
            "replay_type": "compile_cognition",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()],
            "compile_cognition_fingerprint": str(_as_dict(selected).get("compile_cognition_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "compile_cognition_fingerprint": str(_as_dict(selected).get("compile_cognition_fingerprint", "")),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        return replay_payload
