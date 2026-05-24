"""Real build execution + compilation governance layer."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.compile_cognition_engine import CompileCognitionEngine
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_OBJ_LINE_RE = re.compile(r"^\s*([A-Za-z0-9_.$()\-+]+)\s*\+?=\s*(.+)$")
_EXPORT_RE = re.compile(r"\bEXPORT_SYMBOL(?:_GPL)?\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)")
_FUNC_RE = re.compile(
    r"(?m)^[ \t]*(?:static\s+)?(?:inline\s+)?(?:const\s+)?"
    r"(?:[A-Za-z_][A-Za-z0-9_]*[\s\*]+)+([A-Za-z_][A-Za-z0-9_]*)\s*"
    r"\(([^;{}]*)\)\s*\{"
)
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"][^>"]+[>"])', re.MULTILINE)

_BUILTINS = {
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
    "pr_debug",
    "pr_info",
    "pr_err",
    "dev_dbg",
    "dev_info",
    "dev_err",
    "ARRAY_SIZE",
    "max",
    "min",
    "memcpy",
    "memset",
    "snprintf",
    "strcmp",
    "strlen",
}

_SENSITIVE_KEYWORDS = (
    "irq",
    "soundwire",
    "swr_",
    "dsp",
    "mailbox",
    "apr",
    "glink",
    "clk",
    "regulator",
    "pcm",
    "dapm",
    "pm_runtime",
    "runtime_pm",
    "suspend",
    "resume",
    "transport",
    "q6",
)


@dataclass(frozen=True)
class BuildExecutionResult:
    build_bundle: dict[str, Any]


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


def _subsystem_for(rel_path: str) -> str:
    low = rel_path.replace("\\", "/").lower()
    if "sound/soc/qcom" in low or low.startswith("asoc/"):
        return "audio_soc"
    if "techpack/audio" in low:
        return "techpack_audio"
    if "drivers/media" in low:
        return "media"
    if "soundwire" in low or "swr" in low:
        return "soundwire"
    if low.startswith("dsp/"):
        return "dsp"
    if low.startswith("ipc/"):
        return "ipc"
    return "other"


def _driver_for(rel_path: str) -> str:
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 3 and parts[0] in {"asoc", "sound"}:
        return "/".join(parts[:3])
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return rel_path


def _is_runtime_sensitive(text: str, rel: str) -> bool:
    low = f"{rel}\n{text}".lower()
    return any(token in low for token in _SENSITIVE_KEYWORDS)


def _extract_calls(text: str) -> list[str]:
    out: set[str] = set()
    for token in _CALL_RE.findall(text):
        sym = str(token).strip()
        if not sym or sym in _BUILTINS:
            continue
        out.add(sym)
    return sorted(out)


def _extract_function_defs(text: str) -> list[str]:
    out: set[str] = set()
    for match in _FUNC_RE.findall(text):
        if isinstance(match, tuple) and len(match) >= 1:
            sym = str(match[0]).strip()
            if sym:
                out.add(sym)
    return sorted(out)


def _extract_exports(text: str) -> list[str]:
    return sorted({str(v).strip() for v in _EXPORT_RE.findall(text) if str(v).strip()})


def _extract_includes(text: str) -> list[str]:
    rows: list[str] = []
    for raw in _INCLUDE_RE.findall(text):
        token = str(raw).strip()
        if token.startswith("<") and token.endswith(">"):
            rows.append(token[1:-1].strip())
        elif token.startswith('"') and token.endswith('"'):
            rows.append(token[1:-1].strip())
    return sorted({v for v in rows if v})


def _iter_makefiles(source_root: Path) -> list[Path]:
    rows: list[Path] = []
    for path in source_root.rglob("Makefile"):
        if path.is_file():
            rows.append(path)
    rows.sort(key=lambda p: str(p))
    return rows


def _parse_makefile_objects(makefile_rel: str, text: str) -> list[dict[str, Any]]:
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
        guard = ""
        if "CONFIG_" in lhs:
            start = lhs.find("CONFIG_")
            end = lhs.find(")", start)
            token = lhs[start:end] if start >= 0 and end > start else ""
            guard = token[len("CONFIG_") :] if token.startswith("CONFIG_") else token
        for part in rhs.replace("\\", " ").split():
            obj = part.strip()
            if not obj.endswith(".o"):
                continue
            order += 1
            rows.append(
                {
                    "makefile": makefile_rel,
                    "lhs": lhs,
                    "object": obj,
                    "guard_config": guard,
                    "order": order,
                }
            )
    return rows


def _resolve_include(source_root: Path, src_path: Path, include: str) -> str:
    rel = str(include).strip().replace("\\", "/")
    if not rel:
        return ""
    candidates = [
        src_path.parent / rel,
        source_root / rel,
        source_root / "include" / rel,
        source_root / "sound" / rel,
        source_root / "asoc" / rel,
        source_root / "dsp" / rel,
        source_root / "ipc" / rel,
        source_root / "techpack" / rel,
        source_root / "drivers" / rel,
    ]
    for path in candidates:
        if path.exists() and path.is_file():
            try:
                return str(path.relative_to(source_root)).replace("\\", "/")
            except ValueError:
                return str(path.resolve())
    return ""


def _collect_sources(source_root: Path, objects: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    data: dict[str, dict[str, Any]] = {}
    for row in objects:
        item = _as_dict(row)
        makefile = str(item.get("makefile", ""))
        obj = str(item.get("object", ""))
        source_candidate = str((Path(makefile).parent / obj).with_suffix(".c")).replace("\\", "/")
        src_path = source_root / source_candidate
        text = _read_text(src_path) if src_path.exists() else ""
        data[source_candidate] = {
            "exists": bool(src_path.exists()),
            "subsystem": _subsystem_for(source_candidate),
            "driver": _driver_for(source_candidate),
            "runtime_sensitive": _is_runtime_sensitive(text, source_candidate),
            "includes": _extract_includes(text),
            "calls": _extract_calls(text),
            "function_defs": _extract_function_defs(text),
            "exported_symbols": _extract_exports(text),
            "line_count": text.count("\n") + 1 if text else 0,
            "text": text,
        }
    return data


def _build_topology_graph(
    *,
    target_id: str,
    source_root: Path,
    objects: list[dict[str, Any]],
    source_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    missing_sources: list[dict[str, Any]] = []
    subsystem_map: dict[str, list[dict[str, Any]]] = {}

    for row in objects:
        item = _as_dict(row)
        makefile = str(item.get("makefile", ""))
        obj = str(item.get("object", ""))
        source_candidate = str((Path(makefile).parent / obj).with_suffix(".c")).replace("\\", "/")
        src = _as_dict(source_data.get(source_candidate))
        subsystem = str(src.get("subsystem", _subsystem_for(source_candidate)))
        exists = bool(src.get("exists", False))
        runtime_sensitive = bool(src.get("runtime_sensitive", False))

        nodes.append(
            {
                "object": obj,
                "source_candidate": source_candidate,
                "makefile": makefile,
                "subsystem": subsystem,
                "source_exists": exists,
                "guard_config": str(item.get("guard_config", "")),
                "runtime_sensitive": runtime_sensitive,
            }
        )
        edges.append({"from": makefile, "to": obj, "type": "makefile_to_object"})
        edges.append({"from": obj, "to": source_candidate, "type": "object_to_source", "status": "resolved" if exists else "missing"})
        if not exists:
            missing_sources.append({"object": obj, "source_candidate": source_candidate, "makefile": makefile, "impact": "high"})
        subsystem_map.setdefault(subsystem, []).append(
            {
                "object": obj,
                "source": source_candidate,
                "makefile": makefile,
                "runtime_sensitive": runtime_sensitive,
                "source_exists": exists,
            }
        )

    topology = {
        "schema_version": "1.0",
        "graph_name": "build_topology_graph",
        "target_id": str(target_id),
        "classification": "PASS" if not missing_sources else "FAIL_CLOSED",
        "nodes": nodes[:50000],
        "edges": edges[:120000],
        "missing_object_sources": missing_sources[:12000],
        "summary": {
            "object_node_count": len(nodes),
            "edge_count": len(edges),
            "missing_object_source_count": len(missing_sources),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    topology["deterministic_fingerprint"] = stable_fingerprint(topology)

    subsystem_rows = [
        {
            "subsystem": name,
            "object_count": len(rows),
            "runtime_sensitive_object_count": sum(1 for row in rows if bool(_as_dict(row).get("runtime_sensitive", False))),
            "missing_source_count": sum(1 for row in rows if not bool(_as_dict(row).get("source_exists", False))),
            "objects": rows[:1200],
        }
        for name, rows in sorted(subsystem_map.items())
    ]
    subsystem_build_map = {
        "schema_version": "1.0",
        "report_name": "subsystem_build_map",
        "target_id": str(target_id),
        "classification": "PASS" if not missing_sources else "FAIL_CLOSED",
        "subsystems": subsystem_rows,
        "summary": {
            "subsystem_count": len(subsystem_rows),
            "runtime_sensitive_subsystem_count": sum(
                1 for row in subsystem_rows if int(_as_dict(row).get("runtime_sensitive_object_count", 0)) > 0
            ),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    subsystem_build_map["deterministic_fingerprint"] = stable_fingerprint(subsystem_build_map)

    lineage_rows: list[dict[str, Any]] = []
    for node in nodes:
        item = _as_dict(node)
        source = str(item.get("source_candidate", ""))
        source_row = _as_dict(source_data.get(source))
        lineage_rows.append(
            {
                "object": str(item.get("object", "")),
                "source_file": source,
                "provider_symbols": sorted(set([str(v) for v in _as_list(source_row.get("function_defs"))] + [str(v) for v in _as_list(source_row.get("exported_symbols"))]))[:300],
                "consumer_symbols": [str(v) for v in _as_list(source_row.get("calls"))][:500],
                "include_deps": [str(v) for v in _as_list(source_row.get("includes"))][:500],
                "runtime_sensitive": bool(source_row.get("runtime_sensitive", False)),
                "subsystem": str(source_row.get("subsystem", "")),
            }
        )
    lineage = {
        "schema_version": "1.0",
        "graph_name": "object_lineage_graph",
        "target_id": str(target_id),
        "classification": "PASS" if not missing_sources else "FAIL_CLOSED",
        "objects": lineage_rows[:50000],
        "summary": {
            "object_count": len(lineage_rows),
            "runtime_sensitive_object_count": sum(1 for row in lineage_rows if bool(_as_dict(row).get("runtime_sensitive", False))),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    lineage["deterministic_fingerprint"] = stable_fingerprint(lineage)
    return topology, subsystem_build_map, lineage


def _build_symbol_closure(
    *,
    target_id: str,
    source_root: Path,
    source_data: Mapping[str, dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    providers: dict[str, set[str]] = {}
    exported: dict[str, set[str]] = {}
    for src, row in sorted(source_data.items()):
        entry = _as_dict(row)
        for sym in [str(v) for v in _as_list(entry.get("function_defs"))]:
            if sym:
                providers.setdefault(sym, set()).add(src)
        for sym in [str(v) for v in _as_list(entry.get("exported_symbols"))]:
            if sym:
                exported.setdefault(sym, set()).add(src)

    dependencies: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    cross_subsystem: list[dict[str, Any]] = []
    include_missing: list[dict[str, Any]] = []

    for src, row in sorted(source_data.items()):
        entry = _as_dict(row)
        source_path = source_root / src
        for include in _as_list(entry.get("includes")):
            inc = str(include)
            resolved = _resolve_include(source_root, source_path, inc)
            if not resolved:
                include_missing.append(
                    {
                        "source_file": src,
                        "include": inc,
                        "severity": "critical" if not inc.startswith(("linux/", "sound/", "soc/", "asm/")) else "high",
                    }
                )
        for call in _as_list(entry.get("calls")):
            sym = str(call).strip()
            if not sym or sym in _BUILTINS:
                continue
            owners = sorted(providers.get(sym, set()))
            if not owners:
                unresolved.append(
                    {
                        "consumer_file": src,
                        "symbol": sym,
                        "subsystem": str(entry.get("subsystem", "")),
                        "runtime_sensitive": bool(entry.get("runtime_sensitive", False)),
                        "impact": "critical" if bool(entry.get("runtime_sensitive", False)) else "high",
                    }
                )
                continue
            dependencies.append({"consumer_file": src, "symbol": sym, "provider_files": owners[:16]})
            for owner in owners[:16]:
                if _subsystem_for(owner) != _subsystem_for(src):
                    cross_subsystem.append(
                        {
                            "symbol": sym,
                            "provider_file": owner,
                            "consumer_file": src,
                            "provider_subsystem": _subsystem_for(owner),
                            "consumer_subsystem": _subsystem_for(src),
                        }
                    )

    exported_unresolved: list[dict[str, Any]] = []
    for sym, owners in sorted(exported.items()):
        if sym not in providers:
            exported_unresolved.append({"symbol": sym, "export_decl_files": sorted(owners), "impact": "critical"})

    report = {
        "schema_version": "1.0",
        "report_name": "symbol_closure_report",
        "target_id": str(target_id),
        "classification": "PASS" if not unresolved and not exported_unresolved else "FAIL_CLOSED",
        "resolved_dependencies": dependencies[:50000],
        "unresolved_symbols": unresolved[:12000],
        "unresolved_exported_symbols": exported_unresolved[:4000],
        "cross_subsystem_symbol_coupling": cross_subsystem[:12000],
        "summary": {
            "resolved_dependency_count": len(dependencies),
            "unresolved_symbol_count": len(unresolved),
            "unresolved_exported_symbol_count": len(exported_unresolved),
            "cross_subsystem_coupling_count": len(cross_subsystem),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    unresolved_payload = {
        "symbol_unresolved": unresolved[:12000],
        "export_unresolved": exported_unresolved[:4000],
        "include_unresolved": include_missing[:12000],
        "symbol_unresolved_count": len(unresolved) + len(exported_unresolved),
        "include_unresolved_count": len(include_missing),
    }
    return report, unresolved_payload


def _runtime_sensitive_regions(
    *,
    target_id: str,
    source_data: Mapping[str, dict[str, Any]],
    command_rows: list[dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_subsystem_failed: set[str] = set()
    for row in command_rows:
        item = _as_dict(row)
        if int(item.get("returncode", 0)) != 0:
            subsystem = str(item.get("subsystem", ""))
            if subsystem:
                by_subsystem_failed.add(subsystem)

    regions: list[dict[str, Any]] = []
    unsafe_count = 0
    for src, row in sorted(source_data.items()):
        entry = _as_dict(row)
        if not bool(entry.get("runtime_sensitive", False)):
            continue
        subsystem = str(entry.get("subsystem", ""))
        state = "unsafe_build_failure" if subsystem in by_subsystem_failed else "observed_stable"
        if state == "unsafe_build_failure":
            unsafe_count += 1
        regions.append(
            {
                "source_file": src,
                "subsystem": subsystem,
                "driver": str(entry.get("driver", "")),
                "impact_classification": state,
                "line_count": int(entry.get("line_count", 0)),
            }
        )

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_sensitive_build_regions",
        "target_id": str(target_id),
        "classification": "PASS" if unsafe_count == 0 else "FAIL_CLOSED",
        "regions": regions[:12000],
        "summary": {
            "region_count": len(regions),
            "unsafe_region_count": unsafe_count,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    unresolved = {
        "runtime_sensitive_unsafe_region_count": unsafe_count,
    }
    return payload, unresolved


def _run_command(cmd: list[str], cwd: Path, timeout_sec: int = 120) -> dict[str, Any]:
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    elapsed_ms = int((time.time() - start) * 1000)
    return {
        "command": " ".join(cmd),
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "elapsed_ms": elapsed_ms,
    }


def _contains_link_or_modpost_error(returncode: int, stdout: str, stderr: str) -> bool:
    low = f"{stdout}\n{stderr}".lower()
    hard_errors = ("undefined reference", "undefined symbol", "ld returned", "collect2: error", "modpost: error")
    if any(token in low for token in hard_errors):
        return True
    linker_markers = ("modpost", "ld: ", "linker")
    return returncode != 0 and any(token in low for token in linker_markers)


def _execute_build_commands(
    *,
    target_id: str,
    source_root: Path,
    output_root: Path,
    subsystems: list[str],
    object_targets: list[str],
    evidence_references: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    command_index = 0

    def append_result(phase: str, subsystem: str, cmd: list[str], res: dict[str, Any]) -> None:
        nonlocal command_index
        command_index += 1
        item = {
            "id": f"cmd_{command_index:04d}",
            "phase": phase,
            "subsystem": subsystem,
            "command": str(res.get("command", " ".join(cmd))),
            "returncode": int(res.get("returncode", 1)),
            "elapsed_ms": int(res.get("elapsed_ms", 0)),
            "stdout": str(res.get("stdout", "")),
            "stderr": str(res.get("stderr", "")),
            "link_or_modpost_error": _contains_link_or_modpost_error(
                int(res.get("returncode", 1)),
                str(res.get("stdout", "")),
                str(res.get("stderr", "")),
            ),
        }
        rows.append(item)

    for subsystem in subsystems:
        cmd_dry = [
            "make",
            "-C",
            str(source_root),
            f"O={output_root}",
            f"M={subsystem}",
            "modules",
            "-n",
        ]
        res_dry = _run_command(cmd_dry, cwd=source_root)
        append_result("dry_run_subsystem", subsystem, cmd_dry, res_dry)

        cmd_exec = [
            "make",
            "-C",
            str(source_root),
            f"O={output_root}",
            f"M={subsystem}",
            "modules",
        ]
        res_exec = _run_command(cmd_exec, cwd=source_root)
        append_result("execute_subsystem", subsystem, cmd_exec, res_exec)

    for obj in object_targets[:12]:
        subsystem = _subsystem_for(obj)
        cmd_obj_dry = ["make", "-C", str(source_root), f"O={output_root}", obj, "-n"]
        res_obj_dry = _run_command(cmd_obj_dry, cwd=source_root)
        append_result("dry_run_object", subsystem, cmd_obj_dry, res_obj_dry)

        cmd_obj_exec = ["make", "-C", str(source_root), f"O={output_root}", obj]
        res_obj_exec = _run_command(cmd_obj_exec, cwd=source_root)
        append_result("execute_object", subsystem, cmd_obj_exec, res_obj_exec)

    success = sum(1 for row in rows if int(_as_dict(row).get("returncode", 1)) == 0)
    failure = len(rows) - success
    link_modpost_failures = sum(1 for row in rows if bool(_as_dict(row).get("link_or_modpost_error", False)))
    incremental_failures = sum(
        1 for row in rows if str(_as_dict(row).get("phase", "")).startswith("execute_object") and int(_as_dict(row).get("returncode", 1)) != 0
    )
    report = {
        "schema_version": "1.0",
        "report_name": "build_execution_commands",
        "target_id": str(target_id),
        "classification": "PASS" if failure == 0 else "FAIL_CLOSED",
        "commands": rows,
        "summary": {
            "command_count": len(rows),
            "success_count": success,
            "failure_count": failure,
            "incremental_failure_count": incremental_failures,
            "link_or_modpost_failure_count": link_modpost_failures,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    report["deterministic_fingerprint"] = stable_fingerprint(report)
    return rows, report


def _build_unresolved_dependency_report(
    *,
    target_id: str,
    compile_unresolved: Mapping[str, Any],
    symbol_unresolved: Mapping[str, Any],
    topology: Mapping[str, Any],
    command_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    missing_topology_sources = len(_as_list(topology.get("missing_object_sources")))
    symbol_unresolved_count = int(symbol_unresolved.get("symbol_unresolved_count", 0))
    include_unresolved_count = int(symbol_unresolved.get("include_unresolved_count", 0))
    compile_missing = int(_as_dict(compile_unresolved.get("include")).get("missing_include_count", 0))
    cmd_failures = int(_as_dict(command_report.get("summary")).get("failure_count", 0))
    total = missing_topology_sources + symbol_unresolved_count + include_unresolved_count + compile_missing + cmd_failures

    payload = {
        "schema_version": "1.0",
        "report_name": "unresolved_dependency_report",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if total > 0 else "PASS",
        "build_topology_missing_sources": _as_list(topology.get("missing_object_sources"))[:3000],
        "symbol_unresolved": _as_list(symbol_unresolved.get("symbol_unresolved"))[:3000],
        "export_unresolved": _as_list(symbol_unresolved.get("export_unresolved"))[:1200],
        "include_unresolved": _as_list(symbol_unresolved.get("include_unresolved"))[:3000],
        "compile_cognition_unresolved": _as_dict(compile_unresolved),
        "failed_build_commands": [row for row in _as_list(command_report.get("commands")) if int(_as_dict(row).get("returncode", 1)) != 0][:1500],
        "summary": {
            "total_unresolved_count": total,
            "build_topology_missing_source_count": missing_topology_sources,
            "symbol_unresolved_count": symbol_unresolved_count,
            "include_unresolved_count": include_unresolved_count,
            "compile_cognition_missing_include_count": compile_missing,
            "failed_build_command_count": cmd_failures,
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
    command_report: Mapping[str, Any],
    compile_cognition: Mapping[str, Any],
    unresolved_report: Mapping[str, Any],
    runtime_sensitive_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    summary = _as_dict(command_report.get("summary"))
    cmd_count = max(1, int(summary.get("command_count", 0)))
    success = int(summary.get("success_count", 0))
    failures = int(summary.get("failure_count", 0))
    success_ratio = round(success / cmd_count, 3)
    link_modpost_fail = int(summary.get("link_or_modpost_failure_count", 0))
    incremental_fail = int(summary.get("incremental_failure_count", 0))

    compile_score = _to_float(_as_dict(compile_cognition.get("compile_confidence_report")).get("confidence_score"), 0.0)
    unresolved_total = int(_as_dict(unresolved_report.get("summary")).get("total_unresolved_count", 0))
    runtime_unsafe = int(_as_dict(runtime_sensitive_report.get("summary")).get("unsafe_region_count", 0))

    score = 1.0
    score -= min(0.5, failures / cmd_count)
    if link_modpost_fail > 0:
        score -= 0.2
    if incremental_fail > 0:
        score -= 0.15
    if unresolved_total > 0:
        score -= 0.25
    if runtime_unsafe > 0:
        score -= 0.2
    score = round(max(0.0, min(1.0, (score * 0.7) + (compile_score * 0.3))), 3)
    classification = "PASS" if score >= 0.78 else "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "build_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "confidence_score": score,
        "confidence_threshold": 0.78,
        "inputs": {
            "command_success_ratio": success_ratio,
            "command_failure_count": failures,
            "link_or_modpost_failure_count": link_modpost_fail,
            "incremental_failure_count": incremental_fail,
            "compile_cognition_confidence_score": compile_score,
            "unresolved_dependency_total": unresolved_total,
            "runtime_sensitive_unsafe_count": runtime_unsafe,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _governance_decision(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    symbol_report: Mapping[str, Any],
    unresolved_report: Mapping[str, Any],
    confidence_report: Mapping[str, Any],
    runtime_sensitive_report: Mapping[str, Any],
    command_report: Mapping[str, Any],
    deterministic_replay_ready: bool,
    evidence_references: list[str],
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    if str(symbol_report.get("classification", "")) != "PASS":
        reasons.append("unresolved_symbol_closure_exists")
    if int(_as_dict(unresolved_report.get("summary")).get("total_unresolved_count", 0)) > 0:
        reasons.append("dependency_graph_inconsistent")
    if str(confidence_report.get("classification", "")) != "PASS":
        reasons.append("compile_confidence_below_threshold")
    if str(runtime_sensitive_report.get("classification", "")) != "PASS":
        reasons.append("runtime_sensitive_regions_unsafe")
    if int(_as_dict(command_report.get("summary")).get("incremental_failure_count", 0)) > 0:
        reasons.append("incremental_rebuild_unsafe")
    if int(_as_dict(command_report.get("summary")).get("link_or_modpost_failure_count", 0)) > 0:
        reasons.append("linker_modpost_instability_detected")
    if not deterministic_replay_ready:
        reasons.append("build_lineage_incomplete")

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
        "report_name": "governance_build_decision",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if reasons else "PASS",
        "governance_reasons": reasons,
        "governance_state": dict(_as_dict(governance_state)),
        "summary": {
            "reason_count": len(reasons),
            "build_promotion_blocked": bool(reasons),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, reasons


class BuildExecutionEngine:
    """Real build execution and compilation governance."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()
        self._compile_engine = CompileCognitionEngine(plugin_loader=self._plugins)

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
        subsystem_targets: list[str] | None = None,
        object_targets: list[str] | None = None,
    ) -> BuildExecutionResult:
        source_path = Path(str(source_root))
        patch = Path(str(patch_path)) if patch_path else None
        evidence = [str(v) for v in (evidence_references or []) if str(v).strip()]

        if not source_path.exists() or not source_path.is_dir():
            fail = {
                "schema_version": "1.0",
                "phase": "BUILD_EXECUTION",
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
            fail["build_execution_fingerprint"] = stable_fingerprint(fail)
            return BuildExecutionResult(build_bundle=fail)

        plugin = self._plugins.load_plugin(target_id)
        _ = plugin.capability_provider(
            {
                "target_id": str(target_id),
                "plugin_capability_state": dict(_as_dict(plugin_capability_state)),
                "source_root": str(source_path.resolve()),
            }
        )

        compile_bundle = self._compile_engine.analyze(
            target_id=target_id,
            source_root=source_path,
            patch_path=patch if patch and patch.exists() else None,
            governance_state=governance_state,
            replay_traces=replay_traces,
            plugin_capability_state=plugin_capability_state,
            previous_history=[],
            session_id=f"{session_id}:compile",
            lineage_id=f"{lineage_id}:compile",
            evidence_references=evidence,
        ).compile_bundle
        compile_artifacts = _as_dict(compile_bundle.get("artifacts"))

        makefiles = _iter_makefiles(source_path)
        object_rows: list[dict[str, Any]] = []
        for mf in makefiles:
            rel = str(mf.relative_to(source_path)).replace("\\", "/")
            object_rows.extend(_parse_makefile_objects(rel, _read_text(mf)))
        source_data = _collect_sources(source_path, object_rows)

        topology_graph, subsystem_build_map, object_lineage = _build_topology_graph(
            target_id=target_id,
            source_root=source_path,
            objects=object_rows,
            source_data=source_data,
            evidence_references=evidence,
        )
        symbol_closure, symbol_unresolved = _build_symbol_closure(
            target_id=target_id,
            source_root=source_path,
            source_data=source_data,
            evidence_references=evidence,
        )

        discovered_subsystems = sorted(
            {
                str(_as_dict(row).get("subsystem", ""))
                for row in _as_list(subsystem_build_map.get("subsystems"))
                if str(_as_dict(row).get("subsystem", "")).strip()
            }
        )
        default_subsystems = ["sound/soc/qcom", "techpack/audio", "drivers/media", "asoc"]
        chosen = [v for v in (subsystem_targets or default_subsystems) if (source_path / v).exists()]
        if not chosen:
            if (source_path / "asoc").exists():
                chosen = ["asoc"]
            elif (source_path / "sound").exists():
                chosen = ["sound"]
            elif discovered_subsystems:
                # map cognition subsystem names to fallback source roots
                chosen = ["asoc"] if "audio_soc" in discovered_subsystems and (source_path / "asoc").exists() else []

        patch_text = _read_text(patch) if patch and patch.exists() else ""
        touched_objects = sorted(
            {
                str(Path(line[6:].strip()).with_suffix(".o")).replace("\\", "/")
                for line in patch_text.splitlines()
                if line.startswith("--- a/") and line[6:].strip().endswith(".c")
            }
        )
        chosen_objects = [str(v) for v in (object_targets or []) if str(v).strip()] or touched_objects
        if not chosen_objects:
            chosen_objects = sorted({str(_as_dict(row).get("source_candidate", "")).replace(".c", ".o") for row in _as_list(object_lineage.get("objects")) if str(_as_dict(row).get("source_file", "")).endswith(".c")})[:8]

        output_root = Path(tempfile.mkdtemp(prefix="aura_build_exec_out_"))
        command_rows, command_report = _execute_build_commands(
            target_id=target_id,
            source_root=source_path,
            output_root=output_root,
            subsystems=chosen,
            object_targets=chosen_objects,
            evidence_references=evidence,
        )
        runtime_sensitive, runtime_unresolved = _runtime_sensitive_regions(
            target_id=target_id,
            source_data=source_data,
            command_rows=command_rows,
            evidence_references=evidence,
        )
        unresolved_report = _build_unresolved_dependency_report(
            target_id=target_id,
            compile_unresolved=_as_dict(compile_artifacts.get("unresolved_dependency_report")),
            symbol_unresolved=symbol_unresolved,
            topology=topology_graph,
            command_report=command_report,
            evidence_references=evidence,
        )
        confidence_report = _build_confidence_report(
            target_id=target_id,
            command_report=command_report,
            compile_cognition={
                "compile_confidence_report": _as_dict(compile_artifacts.get("compile_confidence_report")),
            },
            unresolved_report=unresolved_report,
            runtime_sensitive_report=runtime_sensitive,
            evidence_references=evidence,
        )

        deterministic_replay_ready = len(command_rows) > 0
        governance_decision, fail_reasons = _governance_decision(
            target_id=target_id,
            governance_state=governance_state,
            symbol_report=symbol_closure,
            unresolved_report=unresolved_report,
            confidence_report=confidence_report,
            runtime_sensitive_report=runtime_sensitive,
            command_report=command_report,
            deterministic_replay_ready=deterministic_replay_ready,
            evidence_references=evidence,
        )
        classification = "FAIL_CLOSED" if fail_reasons else "PASS"

        deterministic_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_build_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "artifact_fingerprints": {
                "build_topology_graph": str(topology_graph.get("deterministic_fingerprint", "")),
                "subsystem_build_map": str(subsystem_build_map.get("deterministic_fingerprint", "")),
                "object_lineage_graph": str(object_lineage.get("deterministic_fingerprint", "")),
                "symbol_closure_report": str(symbol_closure.get("deterministic_fingerprint", "")),
                "unresolved_dependency_report": str(unresolved_report.get("deterministic_fingerprint", "")),
                "build_confidence_report": str(confidence_report.get("deterministic_fingerprint", "")),
                "runtime_sensitive_build_regions": str(runtime_sensitive.get("deterministic_fingerprint", "")),
                "governance_build_decision": str(governance_decision.get("deterministic_fingerprint", "")),
                "command_report": str(command_report.get("deterministic_fingerprint", "")),
                "compile_cognition_replay": str(_as_dict(compile_artifacts.get("deterministic_compile_replay")).get("deterministic_fingerprint", "")),
            },
            "command_lineage": [
                {
                    "id": str(_as_dict(row).get("id", "")),
                    "phase": str(_as_dict(row).get("phase", "")),
                    "subsystem": str(_as_dict(row).get("subsystem", "")),
                    "returncode": int(_as_dict(row).get("returncode", 1)),
                    "command_fingerprint": stable_fingerprint(
                        {
                            "command": str(_as_dict(row).get("command", "")),
                            "stdout": str(_as_dict(row).get("stdout", "")),
                            "stderr": str(_as_dict(row).get("stderr", "")),
                        }
                    ),
                }
                for row in command_rows
            ],
            "dependency_snapshot_fingerprint": stable_fingerprint(
                {
                    "object_rows": object_rows,
                    "source_data_subset": {k: _as_dict(v).get("runtime_sensitive", False) for k, v in sorted(source_data.items())},
                }
            ),
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

        summary = {
            "schema_version": "1.0",
            "report_name": "build_execution_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "summary": {
                "command_count": int(_as_dict(command_report.get("summary")).get("command_count", 0)),
                "success_count": int(_as_dict(command_report.get("summary")).get("success_count", 0)),
                "failure_count": int(_as_dict(command_report.get("summary")).get("failure_count", 0)),
                "link_or_modpost_failure_count": int(
                    _as_dict(command_report.get("summary")).get("link_or_modpost_failure_count", 0)
                ),
                "incremental_failure_count": int(_as_dict(command_report.get("summary")).get("incremental_failure_count", 0)),
                "runtime_sensitive_unsafe_count": int(_as_dict(runtime_sensitive.get("summary")).get("unsafe_region_count", 0)),
                "confidence_score": _to_float(confidence_report.get("confidence_score"), 0.0),
                "replay_persistable": deterministic_replay_ready,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
        }
        summary["deterministic_fingerprint"] = stable_fingerprint(summary)

        artifacts = {
            "build_topology_graph": topology_graph,
            "subsystem_build_map": subsystem_build_map,
            "object_lineage_graph": object_lineage,
            "symbol_closure_report": symbol_closure,
            "unresolved_dependency_report": unresolved_report,
            "build_confidence_report": confidence_report,
            "runtime_sensitive_build_regions": runtime_sensitive,
            "deterministic_build_replay": deterministic_replay,
            "build_execution_summary": summary,
            "governance_build_decision": governance_decision,
            "build_execution_commands": command_report,
            "compile_cognition_input": {
                "classification": str(compile_bundle.get("classification", "UNKNOWN")),
                "fail_closed_reasons": [str(v) for v in _as_list(compile_bundle.get("fail_closed_reasons")) if str(v).strip()],
                "compile_confidence_score": _to_float(
                    _as_dict(compile_artifacts.get("compile_confidence_report")).get("confidence_score"),
                    0.0,
                ),
                "deterministic_fingerprint": stable_fingerprint(
                    {
                        "classification": str(compile_bundle.get("classification", "UNKNOWN")),
                        "compile_confidence_report": _as_dict(compile_artifacts.get("compile_confidence_report")),
                    }
                ),
            },
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "BUILD_EXECUTION",
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
        bundle["build_execution_fingerprint"] = stable_fingerprint(
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
        shutil.rmtree(output_root, ignore_errors=True)
        return BuildExecutionResult(build_bundle=bundle)


class BuildExecutionRegistry:
    """Persistence for build execution + governance artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "build_topology_graph": self._output_dir / "build_topology_graph.json",
            "subsystem_build_map": self._output_dir / "subsystem_build_map.json",
            "object_lineage_graph": self._output_dir / "object_lineage_graph.json",
            "symbol_closure_report": self._output_dir / "symbol_closure_report.json",
            "unresolved_dependency_report": self._output_dir / "unresolved_dependency_report.json",
            "build_confidence_report": self._output_dir / "build_confidence_report.json",
            "runtime_sensitive_build_regions": self._output_dir / "runtime_sensitive_build_regions.json",
            "deterministic_build_replay": self._output_dir / "deterministic_build_replay.json",
            "build_execution_summary": self._output_dir / "build_execution_summary.json",
            "governance_build_decision": self._output_dir / "governance_build_decision.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        for key in (
            "build_topology_graph",
            "subsystem_build_map",
            "object_lineage_graph",
            "symbol_closure_report",
            "unresolved_dependency_report",
            "build_confidence_report",
            "runtime_sensitive_build_regions",
            "deterministic_build_replay",
            "build_execution_summary",
            "governance_build_decision",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("build_execution"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "build_execution_fingerprint": str(payload.get("build_execution_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "confidence_score": _to_float(_as_dict(_as_dict(artifacts.get("build_confidence_report"))).get("confidence_score"), 0.0),
        }
        history.append(entry)
        history = history[-8000:]

        registry["build_execution"] = {
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
                "type": "build_execution",
                "recorded_at": _utc_now_iso(),
                "build_execution_fingerprint": str(payload.get("build_execution_fingerprint", "")),
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
            "build_execution_fingerprint": entry["build_execution_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
            "confidence_score": entry["confidence_score"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("build_execution"))
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
            "replay_type": "build_execution",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()],
            "build_execution_fingerprint": str(_as_dict(selected).get("build_execution_fingerprint", "")),
            "confidence_score": _to_float(_as_dict(selected).get("confidence_score"), 0.0),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "build_execution_fingerprint": str(_as_dict(selected).get("build_execution_fingerprint", "")),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        return replay_payload
