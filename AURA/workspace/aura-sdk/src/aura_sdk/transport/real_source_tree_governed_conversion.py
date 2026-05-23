"""Real source-tree governed conversion engine.

Deterministic, governance-safe cognition for Qualcomm downstream audio trees.
This layer ingests real source files, builds dependency/symbol graphs, plans
tiny safe transformations, and emits replay-safe lineage artifacts.
"""

from __future__ import annotations

import difflib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_SOURCE_NAMES = {"kconfig", "makefile"}
_SOURCE_EXTS = {".c", ".h"}
_IGNORE_DIRS = {".git", ".repo", "out", "build", "__pycache__"}

_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"][^>"]+[>"])', re.MULTILINE)
_DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\b", re.MULTILINE)
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_FUNC_RE = re.compile(
    r"(?m)^[ \t]*(?:static\s+)?(?:inline\s+)?(?:const\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*[\s\*]+)+([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\(([^;{}]*)\)\s*\{"
)
_WRAPPER_RE = re.compile(
    r"\b(?:msm|qcom|wcd|swr|lpass|apr|q6|spf)_[A-Za-z0-9_]*"
    r"(?:wrap|wrapper|helper|cap|capability|dbg|debug|log|trace)[A-Za-z0-9_]*\b"
)

_SENSITIVE_KEYWORDS = (
    "irq",
    "mailbox",
    "dsp",
    "apr",
    "glink",
    "soundwire",
    "swr_",
    "pcm",
    "dapm",
    "pm_runtime",
    "runtime_pm",
    "regulator",
    "clk",
    "q6",
)

_C_KEYWORDS = {
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
}


@dataclass(frozen=True)
class RealSourceTreeGovernedConversionResult:
    conversion_bundle: dict[str, Any]


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


def _is_source_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if any(part in _IGNORE_DIRS for part in path.parts):
        return False
    if path.suffix.lower() in _SOURCE_EXTS:
        return True
    return path.name.lower() in _SOURCE_NAMES


def _iter_sources(root: Path, max_files: int) -> list[Path]:
    files: list[Path] = []
    for item in root.rglob("*"):
        if len(files) >= max_files:
            break
        if _is_source_file(item):
            files.append(item)
    files.sort(key=lambda p: str(p))
    return files


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _subsystem_for(rel_path: str) -> str:
    token = rel_path.replace("\\", "/").lower()
    if token.startswith("asoc/codecs/"):
        return "asoc_codecs"
    if token.startswith("asoc/"):
        return "asoc_machine"
    if token.startswith("dsp/"):
        return "dsp"
    if token.startswith("ipc/"):
        return "ipc"
    if token.startswith("soc/"):
        return "soc"
    if token.startswith("include/"):
        return "include"
    if token.startswith("config/"):
        return "config"
    return "other"


def _kind_for(path: Path) -> str:
    low = path.name.lower()
    if low == "kconfig":
        return "kconfig"
    if low == "makefile":
        return "makefile"
    if path.suffix.lower() == ".h":
        return "header"
    if path.suffix.lower() == ".c":
        return "source"
    return "other"


def _extract_includes(text: str) -> list[str]:
    out: list[str] = []
    for item in _INCLUDE_RE.findall(text):
        inc = str(item).strip()
        if not inc:
            continue
        if inc.startswith("<") and inc.endswith(">"):
            out.append(inc[1:-1].strip())
        elif inc.startswith('"') and inc.endswith('"'):
            out.append(inc[1:-1].strip())
    return sorted({row for row in out if row})


def _extract_defines(text: str) -> list[str]:
    return sorted({str(item).strip() for item in _DEFINE_RE.findall(text) if str(item).strip()})


def _extract_calls(text: str) -> list[str]:
    out: set[str] = set()
    for item in _CALL_RE.findall(text):
        call = str(item).strip()
        if not call or call in _C_KEYWORDS:
            continue
        out.add(call)
    return sorted(out)


def _find_functions(text: str) -> list[dict[str, Any]]:
    functions: list[dict[str, Any]] = []
    for match in _FUNC_RE.finditer(text):
        name = str(match.group(1)).strip()
        params = str(match.group(2)).strip()
        if not name:
            continue
        start_off = match.start()
        brace_off = match.end() - 1
        depth = 1
        idx = brace_off + 1
        while idx < len(text) and depth > 0:
            ch = text[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            idx += 1
        end_off = idx
        start_line = text.count("\n", 0, start_off) + 1
        end_line = text.count("\n", 0, end_off) + 1
        body = text[match.start() : end_off]
        functions.append(
            {
                "name": name,
                "params": params,
                "start_line": start_line,
                "end_line": end_line,
                "body": body,
            }
        )
    return functions


def _derive_debug_context(params: str) -> str:
    match = re.search(r"\bstruct\s+platform_device\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\b", params)
    if match:
        return f"&{match.group(1)}->dev"
    match = re.search(r"\bstruct\s+device\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\b", params)
    if match:
        return str(match.group(1))
    match = re.search(r"\bstruct\s+snd_soc_component\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\b", params)
    if match:
        return f"{match.group(1)}->dev"
    match = re.search(r"\bstruct\s+snd_soc_card\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\b", params)
    if match:
        return f"{match.group(1)}->dev"
    match = re.search(r"\bstruct\s+snd_soc_pcm_runtime\s*\*\s*([A-Za-z_][A-Za-z0-9_]*)\b", params)
    if match:
        return f"{match.group(1)}->dev"
    return ""


def _is_sensitive_text(text: str) -> bool:
    low = text.lower()
    return any(keyword in low for keyword in _SENSITIVE_KEYWORDS)


def _resolve_include(source_root: Path, file_path: Path, include: str) -> str:
    rel = str(include).strip().replace("\\", "/")
    if not rel:
        return ""
    candidates = [
        (file_path.parent / rel),
        (source_root / rel),
        (source_root / "include" / rel),
        (source_root / "asoc" / rel),
        (source_root / "dsp" / rel),
        (source_root / "ipc" / rel),
        (source_root / "soc" / rel),
    ]
    for item in candidates:
        if item.exists() and item.is_file():
            try:
                return str(item.relative_to(source_root)).replace("\\", "/")
            except ValueError:
                return str(item.resolve())
    return ""


def _build_source_tree_graph(
    *,
    target_id: str,
    source_root: Path,
    files: list[Path],
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    include_edges: list[dict[str, Any]] = []

    for path in files:
        rel = str(path.relative_to(source_root)).replace("\\", "/")
        entry = _as_dict(file_data.get(rel))
        nodes.append(
            {
                "file": rel,
                "kind": str(entry.get("kind", "")),
                "subsystem": str(entry.get("subsystem", "")),
                "line_count": int(entry.get("line_count", 0)),
                "include_count": len(_as_list(entry.get("includes"))),
                "symbol_define_count": len(_as_list(entry.get("defines"))),
                "symbol_call_count": len(_as_list(entry.get("calls"))),
            }
        )
        for edge in _as_list(entry.get("resolved_includes")):
            row = _as_dict(edge)
            include_edges.append(
                {
                    "from": rel,
                    "to": str(row.get("to", "")),
                    "status": str(row.get("status", "unknown")),
                }
            )

    payload = {
        "schema_version": "1.0",
        "graph_name": "source_tree_graph",
        "target_id": str(target_id),
        "source_root": str(source_root.resolve()),
        "classification": "PASS" if nodes else "FAIL_CLOSED",
        "nodes": nodes,
        "include_edges": include_edges,
        "summary": {
            "file_count": len(nodes),
            "edge_count": len(include_edges),
            "source_files": sum(1 for n in nodes if str(_as_dict(n).get("kind")) == "source"),
            "header_files": sum(1 for n in nodes if str(_as_dict(n).get("kind")) == "header"),
            "kconfig_files": sum(1 for n in nodes if str(_as_dict(n).get("kind")) == "kconfig"),
            "makefile_files": sum(1 for n in nodes if str(_as_dict(n).get("kind")) == "makefile"),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_subsystem_map(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    groups: dict[str, list[str]] = {}
    for rel, item in sorted(file_data.items()):
        subsystem = str(_as_dict(item).get("subsystem", "other"))
        groups.setdefault(subsystem, []).append(rel)
    subsystem_rows = [
        {
            "subsystem": name,
            "files": rows[:300],
            "file_count": len(rows),
            "sensitive": bool(name in {"dsp", "ipc", "soc"}),
        }
        for name, rows in sorted(groups.items())
    ]
    payload = {
        "schema_version": "1.0",
        "report_name": "subsystem_boundary_map",
        "target_id": str(target_id),
        "classification": "PASS" if subsystem_rows else "FAIL_CLOSED",
        "subsystems": subsystem_rows,
        "summary": {
            "subsystem_count": len(subsystem_rows),
            "sensitive_subsystem_count": sum(1 for row in subsystem_rows if bool(_as_dict(row).get("sensitive", False))),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_symbol_dependency_graph(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    defines: dict[str, list[str]] = {}
    calls_by_file: dict[str, list[str]] = {}
    for rel, item in sorted(file_data.items()):
        entry = _as_dict(item)
        calls_by_file[rel] = [str(v) for v in _as_list(entry.get("calls")) if str(v).strip()]
        for symbol in _as_list(entry.get("defines")):
            token = str(symbol).strip()
            if not token:
                continue
            defines.setdefault(token, []).append(rel)

    edges: list[dict[str, Any]] = []
    unresolved_calls: set[str] = set()
    for rel, calls in sorted(calls_by_file.items()):
        for call in calls:
            owners = defines.get(call, [])
            if owners:
                edges.append(
                    {
                        "caller_file": rel,
                        "symbol": call,
                        "owner_files": sorted(set(owners))[:8],
                        "resolution": "resolved",
                    }
                )
            else:
                unresolved_calls.add(call)

    payload = {
        "schema_version": "1.0",
        "graph_name": "symbol_dependency_graph",
        "target_id": str(target_id),
        "classification": "PASS" if edges else "ADVISORY_ONLY",
        "symbol_edges": edges[:5000],
        "unresolved_symbols": sorted(unresolved_calls)[:1500],
        "summary": {
            "resolved_edge_count": len(edges),
            "unresolved_symbol_count": len(unresolved_calls),
            "defined_symbol_count": len(defines),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_wrapper_classification(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    wrappers: dict[str, dict[str, Any]] = {}

    for rel, item in sorted(file_data.items()):
        entry = _as_dict(item)
        text = str(entry.get("text", ""))
        found = sorted(set(_WRAPPER_RE.findall(text)))
        for token in found:
            kind = "vendor_wrapper"
            low = token.lower()
            if "dbg" in low or "log" in low or "debug" in low:
                kind = "debug_wrapper"
            elif "cap" in low or "capability" in low:
                kind = "capability_wrapper"
            elif "helper" in low or "wrap" in low:
                kind = "helper_wrapper"
            row = wrappers.setdefault(
                token,
                {
                    "symbol": token,
                    "kind": kind,
                    "files": [],
                    "occurrences": 0,
                },
            )
            row["files"].append(rel)
            row["occurrences"] = int(row["occurrences"]) + text.count(token)

    wrapper_rows = [
        {
            "symbol": str(row.get("symbol", "")),
            "kind": str(row.get("kind", "")),
            "files": sorted(set(_as_list(row.get("files"))))[:80],
            "occurrences": int(row.get("occurrences", 0)),
        }
        for _, row in sorted(wrappers.items())
    ]

    equivalence_entries = [
        {
            "downstream_construct": "pr_debug",
            "upstream_equivalent": "dev_dbg",
            "equivalence_type": "debug_abstraction_cleanup",
            "equivalence_confidence": 0.86,
            "runtime_sensitive_guard": "blocked_if_sensitive_region",
        },
        {
            "downstream_construct": "pr_err",
            "upstream_equivalent": "dev_err",
            "equivalence_type": "debug_abstraction_cleanup",
            "equivalence_confidence": 0.62,
            "runtime_sensitive_guard": "blocked_if_sensitive_region_or_missing_device_context",
        },
        {
            "downstream_construct": "vendor_capability_wrapper",
            "upstream_equivalent": "standard_kernel_capability_check",
            "equivalence_type": "capability_wrapper_normalization",
            "equivalence_confidence": 0.55,
            "runtime_sensitive_guard": "blocked_without_runtime_backed_equivalence",
        },
    ]

    report = {
        "schema_version": "1.0",
        "report_name": "wrapper_classification_report",
        "target_id": str(target_id),
        "classification": "PASS" if wrapper_rows else "ADVISORY_ONLY",
        "wrappers": wrapper_rows[:2500],
        "summary": {
            "wrapper_count": len(wrapper_rows),
            "debug_wrapper_count": sum(1 for row in wrapper_rows if str(_as_dict(row).get("kind", "")) == "debug_wrapper"),
            "capability_wrapper_count": sum(
                1 for row in wrapper_rows if str(_as_dict(row).get("kind", "")) == "capability_wrapper"
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)

    equivalence_map = {
        "schema_version": "1.0",
        "graph_name": "upstream_equivalence_map",
        "target_id": str(target_id),
        "classification": "PASS",
        "entries": equivalence_entries,
        "summary": {
            "entry_count": len(equivalence_entries),
            "high_confidence_count": sum(1 for row in equivalence_entries if _to_float(_as_dict(row).get("equivalence_confidence"), 0.0) >= 0.75),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    equivalence_map["deterministic_fingerprint"] = stable_fingerprint(equivalence_map)
    return report, equivalence_map


def _index_functions(
    *,
    source_root: Path,
    file_data: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel, item in sorted(file_data.items()):
        if str(_as_dict(item).get("kind")) != "source":
            continue
        text = str(_as_dict(item).get("text", ""))
        subsystem = str(_as_dict(item).get("subsystem", "other"))
        for fn in _find_functions(text):
            row = dict(_as_dict(fn))
            row["file"] = rel
            row["subsystem"] = subsystem
            row["debug_context"] = _derive_debug_context(str(row.get("params", "")))
            row["sensitive"] = _is_sensitive_text(str(row.get("name", "")) + "\n" + str(row.get("body", "")))
            rows.append(row)
    return rows


def _function_for_line(functions: list[dict[str, Any]], file_path: str, line_no: int) -> dict[str, Any]:
    for row in functions:
        item = _as_dict(row)
        if str(item.get("file", "")) != file_path:
            continue
        start = int(item.get("start_line", 0))
        end = int(item.get("end_line", 0))
        if start <= int(line_no) <= end:
            return item
    return {}


def _build_runtime_sensitive_regions(
    *,
    target_id: str,
    functions: list[dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for fn in functions:
        item = _as_dict(fn)
        body = str(item.get("body", ""))
        hits = [key for key in _SENSITIVE_KEYWORDS if key in body.lower() or key in str(item.get("name", "")).lower()]
        if not hits:
            continue
        rows.append(
            {
                "file": str(item.get("file", "")),
                "function": str(item.get("name", "")),
                "line_range": [int(item.get("start_line", 0)), int(item.get("end_line", 0))],
                "subsystem": str(item.get("subsystem", "")),
                "sensitive_keywords": sorted(set(hits)),
            }
        )
    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_sensitive_regions",
        "target_id": str(target_id),
        "classification": "PASS" if rows else "ADVISORY_ONLY",
        "regions": rows,
        "summary": {
            "region_count": len(rows),
            "files_covered": len(sorted({str(_as_dict(row).get("file", "")) for row in rows})),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _plan_transformations(
    *,
    target_id: str,
    file_data: Mapping[str, dict[str, Any]],
    functions: list[dict[str, Any]],
    runtime_sensitive_regions: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    planned: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    by_file: dict[str, list[dict[str, Any]]] = {}

    sensitive_lookup: set[tuple[str, str]] = {
        (str(_as_dict(row).get("file", "")), str(_as_dict(row).get("function", "")))
        for row in _as_list(_as_dict(runtime_sensitive_regions).get("regions"))
        if isinstance(row, dict)
    }

    for rel, item in sorted(file_data.items()):
        if str(_as_dict(item).get("kind")) != "source":
            continue
        lines = str(_as_dict(item).get("text", "")).splitlines()
        for idx, raw in enumerate(lines, start=1):
            if "pr_debug(" not in raw:
                continue
            fn = _function_for_line(functions, rel, idx)
            fn_name = str(fn.get("name", ""))
            ctx = str(fn.get("debug_context", ""))
            is_sensitive = bool((rel, fn_name) in sensitive_lookup) or _is_sensitive_text(raw)
            reason: list[str] = []
            if not ctx:
                reason.append("missing_device_context")
            if is_sensitive:
                reason.append("runtime_sensitive_region")
            if "/*" in raw or raw.strip().startswith("//"):
                reason.append("comment_line")

            trans_id = f"{rel}:{idx}:pr_debug_to_dev_dbg"
            if reason:
                blocked.append(
                    {
                        "transformation_id": trans_id,
                        "file": rel,
                        "line": idx,
                        "function": fn_name,
                        "from": "pr_debug",
                        "to": "dev_dbg",
                        "reasons": reason,
                        "subsystem": str(_as_dict(item).get("subsystem", "")),
                        "risk": "HIGH" if is_sensitive else "MEDIUM",
                        "evidence_references": evidence_references,
                    }
                )
                continue

            updated = raw.replace("pr_debug(", f"dev_dbg({ctx}, ", 1)
            row = {
                "transformation_id": trans_id,
                "file": rel,
                "line": idx,
                "function": fn_name,
                "from": "pr_debug",
                "to": "dev_dbg",
                "replacement_preview": updated.strip(),
                "subsystem": str(_as_dict(item).get("subsystem", "")),
                "risk": "LOW",
                "runtime_safety": "guarded_non_sensitive_context",
                "evidence_references": evidence_references,
            }
            planned.append(row)
            by_file.setdefault(rel, []).append(row)

    # Capability wrapper normalization classification (advisory unless explicit mapping found)
    cap_tokens: list[dict[str, Any]] = []
    cap_re = re.compile(r"\b(?:msm|qcom)_[A-Za-z0-9_]*(?:cap|capability)[A-Za-z0-9_]*\b")
    for rel, item in sorted(file_data.items()):
        text = str(_as_dict(item).get("text", ""))
        for token in sorted(set(cap_re.findall(text))):
            cap_tokens.append({"file": rel, "token": token})
    for row in cap_tokens[:120]:
        blocked.append(
            {
                "transformation_id": f"{row['file']}:capability:{row['token']}",
                "file": row["file"],
                "line": 0,
                "function": "",
                "from": str(row["token"]),
                "to": "standard_kernel_capability_check",
                "reasons": ["runtime_equivalence_not_verified"],
                "subsystem": _subsystem_for(str(row["file"])),
                "risk": "MEDIUM",
                "evidence_references": evidence_references,
            }
        )

    ordered = sorted(planned, key=lambda r: (str(_as_dict(r).get("file", "")), int(_as_dict(r).get("line", 0))))
    blocked = sorted(blocked, key=lambda r: (str(_as_dict(r).get("file", "")), int(_as_dict(r).get("line", 0))))

    plan = {
        "schema_version": "1.0",
        "report_name": "governed_conversion_plan",
        "target_id": str(target_id),
        "classification": "PASS" if ordered else "FAIL_CLOSED",
        "approved_transformations": ordered[:400],
        "blocked_transformations": blocked[:1000],
        "summary": {
            "approved_count": len(ordered),
            "blocked_count": len(blocked),
            "subsystems_touched": sorted({str(_as_dict(row).get("subsystem", "")) for row in ordered}),
            "transformation_scope": "tiny_controlled",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    plan["deterministic_fingerprint"] = stable_fingerprint(plan)
    return plan, by_file


def _apply_transformations(
    *,
    source_root: Path,
    file_data: Mapping[str, dict[str, Any]],
    approved_by_file: Mapping[str, list[dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, str], list[dict[str, Any]]]:
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    applied: list[dict[str, Any]] = []
    for rel, item in sorted(file_data.items()):
        text = str(_as_dict(item).get("text", ""))
        before[rel] = text
        if rel not in approved_by_file:
            after[rel] = text
            continue
        rows = sorted(
            [_as_dict(row) for row in _as_list(approved_by_file.get(rel)) if isinstance(row, dict)],
            key=lambda r: int(_as_dict(r).get("line", 0)),
            reverse=True,
        )
        lines = text.splitlines()
        for row in rows:
            line_no = int(row.get("line", 0))
            if line_no <= 0 or line_no > len(lines):
                continue
            original = lines[line_no - 1]
            updated = original.replace("pr_debug(", "dev_dbg(", 1)
            # We stored preview with injected context, preserve exactly.
            preview = str(row.get("replacement_preview", ""))
            if preview:
                updated = preview
            lines[line_no - 1] = updated
            applied.append(
                {
                    "transformation_id": str(row.get("transformation_id", "")),
                    "file": rel,
                    "line": line_no,
                    "before": original.strip(),
                    "after": updated.strip(),
                }
            )
        after[rel] = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    return before, after, sorted(applied, key=lambda r: (str(_as_dict(r).get("file", "")), int(_as_dict(r).get("line", 0))))


def _build_patch(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    changed_files: list[str] = []
    for path in sorted(before.keys()):
        a = str(before.get(path, ""))
        b = str(after.get(path, ""))
        if a == b:
            continue
        changed_files.append(path)
        diff = difflib.unified_diff(
            a.splitlines(keepends=True),
            b.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=3,
        )
        chunks.append("".join(diff))
    patch_text = "# REAL SOURCE-TREE GOVERNED CONVERSION PATCH\n# mode=proposal\n\n" + "\n".join(chunks)
    return patch_text, changed_files


def _find_compiler() -> str:
    for candidate in ("cc", "gcc", "clang"):
        proc = subprocess.run(["bash", "-lc", f"command -v {candidate}"], check=False, capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return candidate
    return ""


def _compile_validation(
    *,
    source_root: Path,
    changed_sources: Mapping[str, str],
) -> dict[str, Any]:
    compiler = _find_compiler()
    if not compiler:
        return {
            "compile_attempted": False,
            "classification": "UNCERTAIN",
            "reason": "compiler_not_found",
            "files_checked": len(_as_dict(changed_sources)),
            "failed_files": [],
            "command": "",
        }

    failures: list[dict[str, Any]] = []
    checked = 0
    include_flags = [
        f"-I{source_root}",
        f"-I{source_root / 'include'}",
        f"-I{source_root / 'asoc'}",
        f"-I{source_root / 'dsp'}",
        f"-I{source_root / 'ipc'}",
        f"-I{source_root / 'soc'}",
    ]

    with tempfile.TemporaryDirectory(prefix="aura_real_tree_compile_") as td:
        tmp = Path(td)
        for idx, (path, content) in enumerate(sorted(_as_dict(changed_sources).items()), start=1):
            checked += 1
            src = tmp / f"changed_{idx}.c"
            src.write_text(str(content), encoding="utf-8")
            cmd = [compiler, "-x", "c", "-std=gnu11", "-fsyntax-only", *include_flags, str(src)]
            proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
            if proc.returncode != 0:
                failures.append(
                    {
                        "file": str(path),
                        "stderr": proc.stderr.strip()[:2000],
                        "stdout": proc.stdout.strip()[:1000],
                    }
                )

    classification = "PASS" if checked > 0 and not failures else ("FAIL_CLOSED" if checked > 0 else "UNCERTAIN")
    return {
        "compile_attempted": True,
        "classification": classification,
        "reason": "" if classification == "PASS" else ("compile_errors_detected" if failures else "no_changed_files"),
        "files_checked": checked,
        "failed_files": failures[:120],
        "command": f"{compiler} -x c -std=gnu11 -fsyntax-only -I<source_root> ... <file>",
    }


def _build_compile_validation_report(
    *,
    target_id: str,
    source_root: Path,
    file_data: Mapping[str, dict[str, Any]],
    applied: list[dict[str, Any]],
    changed_after: Mapping[str, str],
    evidence_references: list[str],
) -> dict[str, Any]:
    include_missing: list[dict[str, Any]] = []
    include_total = 0
    for rel, item in sorted(file_data.items()):
        for edge in _as_list(_as_dict(item).get("resolved_includes")):
            row = _as_dict(edge)
            include_total += 1
            if str(row.get("status", "")) == "missing":
                include_missing.append({"file": rel, "include": str(row.get("include", ""))})

    symbol_consistency: list[dict[str, Any]] = []
    symbol_ok = True
    for row in applied:
        item = _as_dict(row)
        old_line = str(item.get("before", ""))
        new_line = str(item.get("after", ""))
        ok = "pr_debug(" in old_line and "dev_dbg(" in new_line
        symbol_ok = symbol_ok and ok
        symbol_consistency.append(
            {
                "transformation_id": str(item.get("transformation_id", "")),
                "file": str(item.get("file", "")),
                "line": int(item.get("line", 0)),
                "symbol_lineage_valid": bool(ok),
            }
        )

    macro_mutations = [
        row
        for row in applied
        if str(_as_dict(row).get("before", "")).lstrip().startswith("#define")
        or str(_as_dict(row).get("after", "")).lstrip().startswith("#define")
    ]

    ordering_hazards = []
    touched = sorted({str(_as_dict(row).get("file", "")) for row in applied})
    if len(touched) > 6:
        ordering_hazards.append("wide_transform_scope")

    changed_sources = {path: text for path, text in changed_after.items() if path in touched}
    compile_result = _compile_validation(source_root=source_root, changed_sources=changed_sources)

    classification = "PASS"
    if include_missing:
        classification = "FAIL_CLOSED"
    if not symbol_ok:
        classification = "FAIL_CLOSED"
    if macro_mutations:
        classification = "FAIL_CLOSED"
    if str(compile_result.get("classification", "")) != "PASS":
        classification = "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "compile_validation_report",
        "target_id": str(target_id),
        "classification": classification,
        "include_dependency_validation": {
            "total_includes_checked": include_total,
            "missing_include_count": len(include_missing),
            "missing_includes": include_missing[:500],
        },
        "symbol_consistency_validation": {
            "checked_transformations": len(symbol_consistency),
            "symbol_lineage_consistent": bool(symbol_ok),
            "details": symbol_consistency,
        },
        "macro_integrity_validation": {
            "macro_mutation_count": len(macro_mutations),
            "macro_integrity_ok": len(macro_mutations) == 0,
        },
        "ordering_hazard_validation": {
            "ordering_hazard_count": len(ordering_hazards),
            "ordering_hazards": ordering_hazards,
        },
        "compile_oriented_validation": compile_result,
        "summary": {
            "applied_transformation_count": len(applied),
            "changed_file_count": len(touched),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_transformation_confidence(
    *,
    target_id: str,
    plan: Mapping[str, Any],
    compile_report: Mapping[str, Any],
    runtime_sensitive_regions: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    approved = int(_as_dict(plan.get("summary")).get("approved_count", 0))
    blocked = int(_as_dict(plan.get("summary")).get("blocked_count", 0))
    sensitive_regions = int(_as_dict(runtime_sensitive_regions.get("summary")).get("region_count", 0))
    compile_class = str(compile_report.get("classification", "UNKNOWN"))
    include_missing = int(_as_dict(compile_report.get("include_dependency_validation")).get("missing_include_count", 0))
    symbol_ok = bool(_as_dict(compile_report.get("symbol_consistency_validation")).get("symbol_lineage_consistent", False))

    confidence = 0.88
    confidence -= min(0.3, blocked * 0.0025)
    confidence -= 0.18 if compile_class != "PASS" else 0.0
    confidence -= 0.12 if include_missing > 0 else 0.0
    confidence -= 0.14 if not symbol_ok else 0.0
    confidence -= 0.05 if approved == 0 else 0.0
    confidence -= min(0.12, sensitive_regions * 0.001)
    confidence = round(max(0.0, min(1.0, confidence)), 3)

    classification = "PASS" if confidence >= 0.72 else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "transformation_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "runtime_confidence": confidence,
        "drivers": {
            "approved_transformations": approved,
            "blocked_transformations": blocked,
            "compile_classification": compile_class,
            "missing_include_count": include_missing,
            "symbol_lineage_consistent": symbol_ok,
            "runtime_sensitive_region_count": sensitive_regions,
        },
        "summary": {
            "confidence_threshold": 0.72,
            "confidence_delta_from_threshold": round(confidence - 0.72, 3),
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
    plan: Mapping[str, Any],
    compile_report: Mapping[str, Any],
    confidence_report: Mapping[str, Any],
    runtime_sensitive_regions: Mapping[str, Any],
    applied: list[dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    reasons: list[str] = []
    if bool(_as_dict(governance_state).get("autonomous_patching_allowed", False)):
        reasons.append("governance_violation:autonomous_patching_allowed")
    if bool(_as_dict(governance_state).get("autonomous_runtime_mutation_allowed", False)):
        reasons.append("governance_violation:autonomous_runtime_mutation_allowed")
    if bool(_as_dict(governance_state).get("autonomous_topology_rewrite_allowed", False)):
        reasons.append("governance_violation:autonomous_topology_rewrite_allowed")
    if bool(_as_dict(governance_state).get("autonomous_upstream_generation_allowed", False)):
        reasons.append("governance_violation:autonomous_upstream_generation_allowed")

    compile_class = str(compile_report.get("classification", "UNKNOWN"))
    if compile_class != "PASS":
        reasons.append("compile_integrity_uncertain_or_failed")
    if int(_as_dict(compile_report.get("include_dependency_validation")).get("missing_include_count", 0)) > 0:
        reasons.append("dependency_graph_inconsistent")
    if not bool(_as_dict(compile_report.get("symbol_consistency_validation")).get("symbol_lineage_consistent", False)):
        reasons.append("symbol_lineage_incomplete")

    sensitive_lookup = {
        (str(_as_dict(row).get("file", "")), str(_as_dict(row).get("function", "")))
        for row in _as_list(_as_dict(runtime_sensitive_regions).get("regions"))
        if isinstance(row, dict)
    }
    sensitive_touches = [
        row
        for row in applied
        if (str(_as_dict(row).get("file", "")), str(_as_dict(row).get("function", ""))) in sensitive_lookup
    ]
    if sensitive_touches:
        reasons.append("runtime_sensitive_regions_affected")

    if str(confidence_report.get("classification", "")) != "PASS":
        reasons.append("runtime_confidence_dropped_below_threshold")

    if int(_as_dict(plan.get("summary")).get("approved_count", 0)) == 0:
        reasons.append("no_safe_transformations_available")

    reasons = sorted(set(reasons))
    classification = "FAIL_CLOSED" if reasons else "PASS"
    payload = {
        "schema_version": "1.0",
        "report_name": "governance_escalation_report",
        "target_id": str(target_id),
        "classification": classification,
        "escalation_reasons": reasons,
        "sensitive_touches": [
            {
                "file": str(_as_dict(row).get("file", "")),
                "line": int(_as_dict(row).get("line", 0)),
                "function": str(_as_dict(row).get("function", "")),
            }
            for row in sensitive_touches[:120]
        ],
        "summary": {
            "reason_count": len(reasons),
            "approved_transformations": int(_as_dict(plan.get("summary")).get("approved_count", 0)),
        },
        "governance_state": dict(_as_dict(governance_state)),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class RealSourceTreeGovernedConversionEngine:
    """Real source-tree governed conversion with deterministic lineage."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        source_root: str | Path,
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_history: list[Mapping[str, Any]] | None,
        session_id: str,
        lineage_id: str,
        evidence_references: list[str] | None,
        max_files: int = 7000,
    ) -> RealSourceTreeGovernedConversionResult:
        source_path = Path(str(source_root))
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        if not source_path.exists() or not source_path.is_dir():
            fail = {
                "schema_version": "1.0",
                "phase": "REAL_SOURCE_TREE_GOVERNED_CONVERSION",
                "created_at": _utc_now_iso(),
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["source_root_missing_or_invalid"],
                "source_root": str(source_path),
                "artifacts": {},
                "runtime_truth_precedence": True,
                "advisory_only_behavior": True,
                "evidence_references": evidence,
            }
            fail["conversion_fingerprint"] = stable_fingerprint(fail)
            return RealSourceTreeGovernedConversionResult(conversion_bundle=fail)

        plugin = self._plugins.load_plugin(target_id)
        _ = plugin.capability_provider(
            {
                "target_id": str(target_id),
                "plugin_capability_state": dict(_as_dict(plugin_capability_state)),
                "source_root": str(source_path.resolve()),
            }
        )

        files = _iter_sources(source_path, max_files=max(500, int(max_files)))
        file_data: dict[str, dict[str, Any]] = {}
        for path in files:
            rel = str(path.relative_to(source_path)).replace("\\", "/")
            text = _read_text(path)
            includes = _extract_includes(text)
            resolved = []
            for include in includes:
                target = _resolve_include(source_path, path, include)
                resolved.append(
                    {
                        "include": include,
                        "to": target,
                        "status": "resolved" if target else "missing",
                    }
                )
            file_data[rel] = {
                "text": text,
                "kind": _kind_for(path),
                "subsystem": _subsystem_for(rel),
                "line_count": text.count("\n") + 1 if text else 0,
                "includes": includes,
                "resolved_includes": resolved,
                "defines": _extract_defines(text),
                "calls": _extract_calls(text),
            }

        source_tree_graph = _build_source_tree_graph(
            target_id=target_id,
            source_root=source_path,
            files=files,
            file_data=file_data,
            evidence_references=evidence,
        )
        subsystem_map = _build_subsystem_map(
            target_id=target_id,
            file_data=file_data,
            evidence_references=evidence,
        )
        symbol_graph = _build_symbol_dependency_graph(
            target_id=target_id,
            file_data=file_data,
            evidence_references=evidence,
        )
        wrapper_report, equivalence_map = _build_wrapper_classification(
            target_id=target_id,
            file_data=file_data,
            evidence_references=evidence,
        )

        functions = _index_functions(source_root=source_path, file_data=file_data)
        runtime_sensitive_regions = _build_runtime_sensitive_regions(
            target_id=target_id,
            functions=functions,
            evidence_references=evidence,
        )
        conversion_plan, approved_by_file = _plan_transformations(
            target_id=target_id,
            file_data=file_data,
            functions=functions,
            runtime_sensitive_regions=runtime_sensitive_regions,
            evidence_references=evidence,
        )

        before, after, applied = _apply_transformations(
            source_root=source_path,
            file_data=file_data,
            approved_by_file=approved_by_file,
        )
        patch_text, changed_files = _build_patch(before, after)

        compile_report = _build_compile_validation_report(
            target_id=target_id,
            source_root=source_path,
            file_data=file_data,
            applied=applied,
            changed_after=after,
            evidence_references=evidence,
        )

        confidence_report = _build_transformation_confidence(
            target_id=target_id,
            plan=conversion_plan,
            compile_report=compile_report,
            runtime_sensitive_regions=runtime_sensitive_regions,
            evidence_references=evidence,
        )

        governance_report = _build_governance_escalation(
            target_id=target_id,
            governance_state=governance_state,
            plan=conversion_plan,
            compile_report=compile_report,
            confidence_report=confidence_report,
            runtime_sensitive_regions=runtime_sensitive_regions,
            applied=applied,
            evidence_references=evidence,
        )

        fail_reasons = [str(item) for item in _as_list(governance_report.get("escalation_reasons")) if str(item).strip()]
        classification = "FAIL_CLOSED" if fail_reasons else "PASS"

        deterministic_driver_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_driver_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "artifact_fingerprints": {
                "source_tree_graph": str(source_tree_graph.get("deterministic_fingerprint", "")),
                "subsystem_boundary_map": str(subsystem_map.get("deterministic_fingerprint", "")),
                "symbol_dependency_graph": str(symbol_graph.get("deterministic_fingerprint", "")),
                "wrapper_classification_report": str(wrapper_report.get("deterministic_fingerprint", "")),
                "governed_conversion_plan": str(conversion_plan.get("deterministic_fingerprint", "")),
                "compile_validation_report": str(compile_report.get("deterministic_fingerprint", "")),
                "runtime_sensitive_regions": str(runtime_sensitive_regions.get("deterministic_fingerprint", "")),
                "governance_escalation_report": str(governance_report.get("deterministic_fingerprint", "")),
                "transformation_confidence_report": str(confidence_report.get("deterministic_fingerprint", "")),
                "upstream_equivalence_map": str(equivalence_map.get("deterministic_fingerprint", "")),
                "downstream_to_upstream_patch": stable_fingerprint(
                    {"patch_text": patch_text, "changed_files": changed_files}
                ),
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
        deterministic_driver_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_driver_replay)

        artifacts = {
            "source_tree_graph": source_tree_graph,
            "subsystem_boundary_map": subsystem_map,
            "symbol_dependency_graph": symbol_graph,
            "wrapper_classification_report": wrapper_report,
            "governed_conversion_plan": conversion_plan,
            "compile_validation_report": compile_report,
            "runtime_sensitive_regions": runtime_sensitive_regions,
            "governance_escalation_report": governance_report,
            "deterministic_driver_replay": deterministic_driver_replay,
            "transformation_confidence_report": confidence_report,
            "upstream_equivalence_map": equivalence_map,
            "downstream_to_upstream_patch": {
                "patch_text": patch_text,
                "changed_files": changed_files,
                "real_patch_generated": bool(changed_files and "# mode=proposal" in patch_text),
                "applied_transformations": applied,
                "deterministic_fingerprint": stable_fingerprint(
                    {"patch_text": patch_text, "changed_files": changed_files, "applied": applied}
                ),
            },
        }

        summary = {
            "schema_version": "1.0",
            "report_name": "real_driver_conversion_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "summary": {
                "drivers_analyzed": int(_as_dict(subsystem_map.get("summary")).get("subsystem_count", 0)),
                "files_parsed": int(_as_dict(source_tree_graph.get("summary")).get("file_count", 0)),
                "transformations_attempted": int(_as_dict(conversion_plan.get("summary")).get("approved_count", 0))
                + int(_as_dict(conversion_plan.get("summary")).get("blocked_count", 0)),
                "runtime_sensitive_regions_detected": int(_as_dict(runtime_sensitive_regions.get("summary")).get("region_count", 0)),
                "changed_file_count": len(changed_files),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
        }
        summary["deterministic_fingerprint"] = stable_fingerprint(summary)
        artifacts["real_driver_conversion_summary"] = summary

        bundle = {
            "schema_version": "1.0",
            "phase": "REAL_SOURCE_TREE_GOVERNED_CONVERSION",
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
        bundle["conversion_fingerprint"] = stable_fingerprint(
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
        return RealSourceTreeGovernedConversionResult(conversion_bundle=bundle)


class RealSourceTreeGovernedConversionRegistry:
    """Persistence for real source-tree governed conversion artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "source_tree_graph": self._output_dir / "source_tree_graph.json",
            "subsystem_boundary_map": self._output_dir / "subsystem_boundary_map.json",
            "symbol_dependency_graph": self._output_dir / "symbol_dependency_graph.json",
            "wrapper_classification_report": self._output_dir / "wrapper_classification_report.json",
            "governed_conversion_plan": self._output_dir / "governed_conversion_plan.json",
            "compile_validation_report": self._output_dir / "compile_validation_report.json",
            "runtime_sensitive_regions": self._output_dir / "runtime_sensitive_regions.json",
            "governance_escalation_report": self._output_dir / "governance_escalation_report.json",
            "deterministic_driver_replay": self._output_dir / "deterministic_driver_replay.json",
            "transformation_confidence_report": self._output_dir / "transformation_confidence_report.json",
            "upstream_equivalence_map": self._output_dir / "upstream_equivalence_map.json",
            "downstream_to_upstream_patch": self._output_dir / "downstream_to_upstream.patch",
            "real_driver_conversion_summary": self._output_dir / "real_driver_conversion_summary.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        patch_payload = _as_dict(artifacts.get("downstream_to_upstream_patch"))
        paths["downstream_to_upstream_patch"].parent.mkdir(parents=True, exist_ok=True)
        paths["downstream_to_upstream_patch"].write_text(str(patch_payload.get("patch_text", "")), encoding="utf-8")

        for key in (
            "source_tree_graph",
            "subsystem_boundary_map",
            "symbol_dependency_graph",
            "wrapper_classification_report",
            "governed_conversion_plan",
            "compile_validation_report",
            "runtime_sensitive_regions",
            "governance_escalation_report",
            "deterministic_driver_replay",
            "transformation_confidence_report",
            "upstream_equivalence_map",
            "real_driver_conversion_summary",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("real_source_tree_governed_conversion"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "conversion_fingerprint": str(payload.get("conversion_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "real_patch_generated": bool(_as_dict(artifacts.get("downstream_to_upstream_patch")).get("real_patch_generated", False)),
        }
        history.append(entry)
        history = history[-8000:]

        registry["real_source_tree_governed_conversion"] = {
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
                "type": "real_source_tree_governed_conversion",
                "recorded_at": _utc_now_iso(),
                "conversion_fingerprint": str(payload.get("conversion_fingerprint", "")),
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
            "conversion_fingerprint": entry["conversion_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
            "real_patch_generated": entry["real_patch_generated"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("real_source_tree_governed_conversion"))
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
            "replay_type": "real_source_tree_governed_conversion",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()],
            "conversion_fingerprint": str(_as_dict(selected).get("conversion_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "real_patch_generated": bool(_as_dict(selected).get("real_patch_generated", False)),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "conversion_fingerprint": str(_as_dict(selected).get("conversion_fingerprint", "")),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        _save_json(self._output_dir / "deterministic_driver_replay.json", replay_payload)
        return replay_payload
