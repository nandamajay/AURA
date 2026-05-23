"""Real patch application + governed build validation.

Deterministic, governance-safe build cognition for tiny downstream-to-upstream
transformations on real Qualcomm-style source trees.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*([<"][^>"]+[>"])', re.MULTILINE)
_PATCH_FILE_RE = re.compile(r"^---\s+a/(.+)$")
_PATCH_HUNK_RE = re.compile(r"^@@\s+\-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@")
_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
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
_SAFE_DEBUG_TOKENS = ("pr_debug", "dev_dbg", "pr_info", "dev_info", "pr_err", "dev_err")


@dataclass(frozen=True)
class RealPatchApplicationGovernedBuildResult:
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _extract_includes(text: str) -> list[str]:
    out: list[str] = []
    for match in _INCLUDE_RE.findall(text):
        inc = str(match).strip()
        if not inc:
            continue
        if inc.startswith("<") and inc.endswith(">"):
            out.append(inc[1:-1].strip())
        elif inc.startswith('"') and inc.endswith('"'):
            out.append(inc[1:-1].strip())
    return sorted({v for v in out if v})


def _extract_call(line: str) -> str:
    for token in _CALL_RE.findall(line):
        symbol = str(token).strip()
        if symbol and symbol not in _C_KEYWORDS:
            return symbol
    return ""


def _parse_patch_metadata(patch_text: str) -> dict[str, Any]:
    touched_files: list[str] = []
    changed_lines: list[dict[str, Any]] = []
    replacement_counts: dict[tuple[str, str, str], int] = {}

    current_file = ""
    old_line = 0
    new_line = 0
    removed_calls: list[str] = []
    added_calls: list[str] = []

    def flush_hunk_pairs(file_path: str) -> None:
        if not file_path:
            return
        pairs = min(len(removed_calls), len(added_calls))
        for idx in range(pairs):
            old_sym = str(removed_calls[idx]).strip()
            new_sym = str(added_calls[idx]).strip()
            if not old_sym or not new_sym or old_sym == new_sym:
                continue
            key = (file_path, old_sym, new_sym)
            replacement_counts[key] = int(replacement_counts.get(key, 0)) + 1
        removed_calls.clear()
        added_calls.clear()

    for raw in patch_text.splitlines():
        line = str(raw)
        file_match = _PATCH_FILE_RE.match(line)
        if file_match:
            flush_hunk_pairs(current_file)
            current_file = str(file_match.group(1)).strip()
            if current_file and current_file != "/dev/null":
                touched_files.append(current_file)
            old_line = 0
            new_line = 0
            continue
        hunk_match = _PATCH_HUNK_RE.match(line)
        if hunk_match:
            flush_hunk_pairs(current_file)
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(2))
            continue
        if not current_file:
            continue
        if line.startswith("--- ") or line.startswith("+++ "):
            continue
        if line.startswith("-"):
            sym = _extract_call(line[1:])
            if sym:
                removed_calls.append(sym)
            old_line += 1
            continue
        if line.startswith("+"):
            sym = _extract_call(line[1:])
            if sym:
                added_calls.append(sym)
            changed_lines.append(
                {
                    "file": current_file,
                    "line": new_line,
                    "content": line[1:],
                }
            )
            new_line += 1
            continue
        if line.startswith(" "):
            old_line += 1
            new_line += 1
            continue

    flush_hunk_pairs(current_file)
    replacement_pairs = [
        {
            "file": file_path,
            "old_symbol": old_sym,
            "new_symbol": new_sym,
            "expected_replacements": count,
        }
        for (file_path, old_sym, new_sym), count in sorted(replacement_counts.items())
    ]
    return {
        "touched_files": sorted(set(touched_files)),
        "changed_lines": changed_lines,
        "replacement_pairs": replacement_pairs,
    }


def _prepare_sandbox(source_root: Path, touched_files: list[str]) -> tuple[Path, dict[str, str]]:
    sandbox_root = Path(tempfile.mkdtemp(prefix="aura_build_validation_"))
    baseline: dict[str, str] = {}
    for rel in touched_files:
        src = source_root / rel
        dst = sandbox_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists() and src.is_file():
            shutil.copy2(src, dst)
            baseline[rel] = _read_text(src)
        else:
            dst.write_text("", encoding="utf-8")
            baseline[rel] = ""
    return sandbox_root, baseline


def _run_patch_apply(*, sandbox_root: Path, patch_path: Path) -> dict[str, Any]:
    dry = subprocess.run(
        ["patch", "-p1", "--batch", "--forward", "--dry-run", "-i", str(patch_path.resolve())],
        cwd=str(sandbox_root),
        capture_output=True,
        text=True,
        check=False,
    )
    dry_out = f"{dry.stdout}\n{dry.stderr}".strip()
    fuzz_lines = [line for line in dry_out.splitlines() if "fuzz" in line.lower() or "offset" in line.lower()]
    if dry.returncode != 0:
        return {
            "classification": "FAIL_CLOSED",
            "dry_run_returncode": int(dry.returncode),
            "dry_run_stdout": dry.stdout,
            "dry_run_stderr": dry.stderr,
            "apply_returncode": None,
            "apply_stdout": "",
            "apply_stderr": "",
            "fuzz_observations": fuzz_lines,
            "patch_applied": False,
            "reject_files": [],
            "reason": "dry_run_failed",
        }

    apply = subprocess.run(
        ["patch", "-p1", "--batch", "--forward", "-i", str(patch_path.resolve())],
        cwd=str(sandbox_root),
        capture_output=True,
        text=True,
        check=False,
    )
    apply_out = f"{apply.stdout}\n{apply.stderr}".strip()
    fuzz_lines.extend([line for line in apply_out.splitlines() if "fuzz" in line.lower() or "offset" in line.lower()])
    reject_files = sorted(str(path.relative_to(sandbox_root)).replace("\\", "/") for path in sandbox_root.rglob("*.rej"))
    patch_applied = apply.returncode == 0 and not reject_files

    return {
        "classification": "PASS" if patch_applied else "FAIL_CLOSED",
        "dry_run_returncode": int(dry.returncode),
        "dry_run_stdout": dry.stdout,
        "dry_run_stderr": dry.stderr,
        "apply_returncode": int(apply.returncode),
        "apply_stdout": apply.stdout,
        "apply_stderr": apply.stderr,
        "fuzz_observations": sorted(set(fuzz_lines))[:200],
        "patch_applied": patch_applied,
        "reject_files": reject_files,
        "reason": "applied" if patch_applied else "apply_failed_or_rejects",
    }


def _build_applied_diff(*, baseline: Mapping[str, str], patched: Mapping[str, str]) -> tuple[str, list[str]]:
    out: list[str] = ["# APPLIED PATCH FROM GOVERNED BUILD VALIDATION", "# mode=sandbox_apply"]
    changed: list[str] = []
    for rel in sorted(set(baseline.keys()) | set(patched.keys())):
        before = str(baseline.get(rel, ""))
        after = str(patched.get(rel, ""))
        if before == after:
            continue
        changed.append(rel)
        diff = difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            lineterm="",
        )
        out.extend(list(diff))
        out.append("")
    return "\n".join(out).rstrip() + ("\n" if changed else ""), changed


def _resolve_include(source_root: Path, file_path: Path, include: str) -> str:
    rel = str(include).strip().replace("\\", "/")
    if not rel:
        return ""
    candidates = [
        file_path.parent / rel,
        source_root / rel,
        source_root / "include" / rel,
        source_root / "sound" / rel,
        source_root / "asoc" / rel,
        source_root / "dsp" / rel,
        source_root / "ipc" / rel,
    ]
    for item in candidates:
        if item.exists() and item.is_file():
            try:
                return str(item.relative_to(source_root)).replace("\\", "/")
            except ValueError:
                return str(item.resolve())
    return ""


def _include_closure_report(
    *,
    target_id: str,
    source_root: Path,
    sandbox_root: Path,
    touched_files: list[str],
    evidence_references: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    unresolved_local = 0
    unresolved_external = 0
    for rel in touched_files:
        if not rel.endswith((".c", ".h")):
            continue
        sandbox_file = sandbox_root / rel
        if not sandbox_file.exists():
            continue
        text = _read_text(sandbox_file)
        for include in _extract_includes(text):
            resolved = _resolve_include(source_root, sandbox_file, include)
            unresolved_category = ""
            if not resolved:
                if include.startswith(("linux/", "sound/", "soc/", "uapi/", "asm/")):
                    unresolved_category = "external_kernel_or_system"
                    unresolved_external += 1
                else:
                    unresolved_category = "local_or_project_missing"
                    unresolved_local += 1
            rows.append(
                {
                    "file": rel,
                    "include": include,
                    "status": "resolved" if resolved else "missing",
                    "resolved_to": resolved,
                    "missing_category": unresolved_category,
                }
            )
    classification = "PASS" if unresolved_local == 0 and unresolved_external == 0 else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "include_closure_report",
        "target_id": str(target_id),
        "classification": classification,
        "include_rows": rows[:12000],
        "summary": {
            "checked_include_count": len(rows),
            "unresolved_local_count": unresolved_local,
            "unresolved_external_count": unresolved_external,
            "resolved_count": sum(1 for row in rows if str(_as_dict(row).get("status")) == "resolved"),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _subsystem_for(rel_path: str) -> str:
    path = rel_path.replace("\\", "/").lower()
    if path.startswith("soundwire/") or "soundwire" in path or "swr" in path:
        return "soundwire"
    if path.startswith("asoc/codecs/"):
        return "asoc_codecs"
    if path.startswith("asoc/"):
        return "asoc_machine"
    if path.startswith("dsp/") or "q6" in path or "apr" in path:
        return "dsp"
    if path.startswith("ipc/") or "mailbox" in path:
        return "ipc"
    return "other"


def _touched_object_graph(
    *,
    target_id: str,
    source_root: Path,
    sandbox_root: Path,
    touched_files: list[str],
    include_report: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], list[str]]:
    include_rows = [
        _as_dict(v)
        for v in _as_list(_as_dict(include_report).get("include_rows"))
        if isinstance(v, dict)
    ]
    include_map: dict[str, list[dict[str, Any]]] = {}
    for row in include_rows:
        include_map.setdefault(str(row.get("file", "")), []).append(row)

    compile_targets: list[str] = []
    objects: list[dict[str, Any]] = []
    for rel in touched_files:
        if not rel.endswith(".c"):
            continue
        file_path = sandbox_root / rel
        if not file_path.exists():
            continue
        compile_targets.append(rel)
        row_includes = include_map.get(rel, [])
        objects.append(
            {
                "source_file": rel,
                "object_file": rel[:-2] + ".o",
                "subsystem": _subsystem_for(rel),
                "dependency_includes": [str(_as_dict(row).get("include", "")) for row in row_includes[:250]],
                "resolved_include_count": sum(
                    1 for row in row_includes if str(_as_dict(row).get("status", "")) == "resolved"
                ),
                "missing_include_count": sum(
                    1 for row in row_includes if str(_as_dict(row).get("status", "")) == "missing"
                ),
            }
        )

    payload = {
        "schema_version": "1.0",
        "graph_name": "touched_object_graph",
        "target_id": str(target_id),
        "classification": "PASS" if objects else "FAIL_CLOSED",
        "objects": objects,
        "summary": {
            "object_count": len(objects),
            "subsystem_count": len(sorted({str(_as_dict(v).get("subsystem", "")) for v in objects})),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, compile_targets


def _compile_incremental(
    *,
    target_id: str,
    source_root: Path,
    sandbox_root: Path,
    compile_targets: list[str],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    include_dirs = sorted(
        {
            str(sandbox_root.resolve()),
            str((source_root).resolve()),
            str((source_root / "include").resolve()),
        }
        | {
            str((source_root / Path(rel).parent).resolve())
            for rel in compile_targets
            if Path(rel).parent != Path(".")
        }
    )
    include_flags = [f"-I{item}" for item in include_dirs]

    rows: list[dict[str, Any]] = []
    warning_rows: list[str] = []
    success = 0
    failed = 0
    for rel in compile_targets:
        src = sandbox_root / rel
        cmd = ["cc", "-x", "c", "-std=gnu11", "-fsyntax-only"] + include_flags + [str(src)]
        proc = subprocess.run(cmd, cwd=str(sandbox_root), capture_output=True, text=True, check=False)
        stderr = str(proc.stderr or "")
        stdout = str(proc.stdout or "")
        warnings = [line for line in stderr.splitlines() if "warning:" in line.lower()]
        warning_rows.extend(warnings)
        if proc.returncode == 0:
            success += 1
        else:
            failed += 1
        rows.append(
            {
                "source_file": rel,
                "object_file": rel[:-2] + ".o" if rel.endswith(".c") else rel,
                "returncode": int(proc.returncode),
                "command": " ".join(cmd),
                "stdout": stdout,
                "stderr": stderr,
                "warnings": warnings,
            }
        )

    cluster_map: dict[str, int] = {}
    for warning in warning_rows:
        token = "generic_warning"
        if "warning:" in warning:
            token = warning.split("warning:", 1)[1].strip()
        cluster_map[token] = int(cluster_map.get(token, 0)) + 1

    warning_clusters = {
        "schema_version": "1.0",
        "report_name": "compile_warning_clusters",
        "target_id": str(target_id),
        "classification": "PASS",
        "clusters": [{"warning_signature": sig, "count": cnt} for sig, cnt in sorted(cluster_map.items())],
        "summary": {"warning_count": len(warning_rows), "cluster_count": len(cluster_map)},
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    warning_clusters["deterministic_fingerprint"] = stable_fingerprint(warning_clusters)

    build_report = {
        "schema_version": "1.0",
        "report_name": "incremental_build_report",
        "target_id": str(target_id),
        "classification": "PASS" if failed == 0 else "FAIL_CLOSED",
        "build_mode": "incremental_touched_objects",
        "compile_rows": rows,
        "summary": {
            "objects_compiled": len(rows),
            "compile_success_count": success,
            "compile_failure_count": failed,
            "warning_count": len(warning_rows),
            "include_dir_count": len(include_dirs),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    build_report["deterministic_fingerprint"] = stable_fingerprint(build_report)
    return build_report, warning_clusters


def _count_symbol_calls(text: str, symbol: str) -> int:
    if not symbol:
        return 0
    expr = re.compile(r"\b" + re.escape(symbol) + r"\s*\(")
    return len(expr.findall(text))


def _symbol_resolution_report(
    *,
    target_id: str,
    baseline: Mapping[str, str],
    patched: Mapping[str, str],
    replacement_pairs: list[dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in replacement_pairs:
        pair = _as_dict(row)
        rel = str(pair.get("file", ""))
        old_symbol = str(pair.get("old_symbol", ""))
        new_symbol = str(pair.get("new_symbol", ""))
        expected = int(pair.get("expected_replacements", 0))
        before = str(baseline.get(rel, ""))
        after = str(patched.get(rel, ""))
        before_old = _count_symbol_calls(before, old_symbol)
        after_old = _count_symbol_calls(after, old_symbol)
        after_new = _count_symbol_calls(after, new_symbol)
        actual_replaced = max(0, before_old - after_old)
        ok = actual_replaced >= expected and after_new >= expected
        check = {
            "file": rel,
            "old_symbol": old_symbol,
            "new_symbol": new_symbol,
            "expected_replacements": expected,
            "actual_replaced": actual_replaced,
            "before_old_count": before_old,
            "after_old_count": after_old,
            "after_new_count": after_new,
            "status": "resolved" if ok else "inconsistent",
        }
        checks.append(check)
        if not ok:
            failures.append(check)
    classification = "PASS" if not failures else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "symbol_resolution_report",
        "target_id": str(target_id),
        "classification": classification,
        "checks": checks,
        "summary": {
            "replacement_pair_count": len(checks),
            "failed_pair_count": len(failures),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _runtime_sensitive_compile_report(
    *,
    target_id: str,
    changed_lines: list[dict[str, Any]],
    evidence_references: list[str],
) -> dict[str, Any]:
    impacted: list[dict[str, Any]] = []
    unsafe = 0
    for row in changed_lines:
        item = _as_dict(row)
        rel = str(item.get("file", ""))
        content = str(item.get("content", ""))
        line_no = int(item.get("line", 0))
        low = f"{rel}\n{content}".lower()
        hits = sorted({key for key in _SENSITIVE_KEYWORDS if key in low})
        if not hits:
            continue
        is_safe_debug = any(tok in content for tok in _SAFE_DEBUG_TOKENS)
        state = "safe_debug_only" if is_safe_debug else "unsafe_sensitive_touch"
        if state == "unsafe_sensitive_touch":
            unsafe += 1
        impacted.append(
            {
                "file": rel,
                "line": line_no,
                "content": content[:240],
                "object_file": rel[:-2] + ".o" if rel.endswith(".c") else rel,
                "sensitive_keywords": hits,
                "impact_classification": state,
            }
        )
    classification = "PASS" if unsafe == 0 else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_sensitive_compile_report",
        "target_id": str(target_id),
        "classification": classification,
        "impacted_objects": impacted,
        "summary": {
            "runtime_sensitive_object_count": len(impacted),
            "unsafe_sensitive_impact_count": unsafe,
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
    patch_apply_report: Mapping[str, Any],
    build_report: Mapping[str, Any],
    include_report: Mapping[str, Any],
    symbol_report: Mapping[str, Any],
    runtime_sensitive_report: Mapping[str, Any],
    warning_clusters: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    score = 1.0
    if str(patch_apply_report.get("classification", "")) != "PASS":
        score -= 0.40
    if int(_as_dict(build_report.get("summary")).get("compile_failure_count", 0)) > 0:
        score -= 0.30
    if int(_as_dict(include_report.get("summary")).get("unresolved_local_count", 0)) > 0:
        score -= 0.15
    if int(_as_dict(include_report.get("summary")).get("unresolved_external_count", 0)) > 0:
        score -= 0.10
    if str(symbol_report.get("classification", "")) != "PASS":
        score -= 0.15
    if int(_as_dict(runtime_sensitive_report.get("summary")).get("unsafe_sensitive_impact_count", 0)) > 0:
        score -= 0.15
    if int(_as_dict(warning_clusters.get("summary")).get("warning_count", 0)) > 25:
        score -= 0.05
    score = max(0.0, min(1.0, round(score, 3)))
    classification = "PASS" if score >= 0.75 else "FAIL_CLOSED"
    payload = {
        "schema_version": "1.0",
        "report_name": "build_confidence_report",
        "target_id": str(target_id),
        "classification": classification,
        "confidence_score": score,
        "confidence_threshold": 0.75,
        "inputs": {
            "patch_apply_passed": str(patch_apply_report.get("classification", "")) == "PASS",
            "compile_failure_count": int(_as_dict(build_report.get("summary")).get("compile_failure_count", 0)),
            "unresolved_local_includes": int(_as_dict(include_report.get("summary")).get("unresolved_local_count", 0)),
            "unresolved_external_includes": int(
                _as_dict(include_report.get("summary")).get("unresolved_external_count", 0)
            ),
            "symbol_resolution_passed": str(symbol_report.get("classification", "")) == "PASS",
            "unsafe_runtime_sensitive_impacts": int(
                _as_dict(runtime_sensitive_report.get("summary")).get("unsafe_sensitive_impact_count", 0)
            ),
            "warning_count": int(_as_dict(warning_clusters.get("summary")).get("warning_count", 0)),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _collect_fail_reasons(
    *,
    governance_state: Mapping[str, Any],
    patch_apply_report: Mapping[str, Any],
    build_report: Mapping[str, Any],
    include_report: Mapping[str, Any],
    symbol_report: Mapping[str, Any],
    runtime_sensitive_report: Mapping[str, Any],
    confidence_report: Mapping[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if bool(_as_dict(governance_state).get("autonomous_patching_allowed", False)):
        reasons.append("governance_violation:autonomous_patching_allowed")
    if bool(_as_dict(governance_state).get("autonomous_runtime_mutation_allowed", False)):
        reasons.append("governance_violation:autonomous_runtime_mutation_allowed")
    if bool(_as_dict(governance_state).get("autonomous_topology_rewrite_allowed", False)):
        reasons.append("governance_violation:autonomous_topology_rewrite_allowed")
    if bool(_as_dict(governance_state).get("autonomous_upstream_generation_allowed", False)):
        reasons.append("governance_violation:autonomous_upstream_generation_allowed")

    if str(patch_apply_report.get("classification", "")) != "PASS":
        reasons.append("patch_apply_failed_or_conflicted")
    if int(_as_dict(build_report.get("summary")).get("compile_failure_count", 0)) > 0:
        reasons.append("incremental_compile_failed")
    if str(include_report.get("classification", "")) != "PASS":
        reasons.append("dependency_closure_unresolved")
    if str(symbol_report.get("classification", "")) != "PASS":
        reasons.append("symbol_resolution_incomplete")
    if int(_as_dict(runtime_sensitive_report.get("summary")).get("unsafe_sensitive_impact_count", 0)) > 0:
        reasons.append("runtime_sensitive_compile_regions_impacted_unsafely")
    if str(confidence_report.get("classification", "")) != "PASS":
        reasons.append("build_confidence_below_threshold")
    return sorted(set(reasons))


def _rollback(
    *,
    sandbox_root: Path,
    baseline: Mapping[str, str],
    patched: Mapping[str, str],
    reasons: list[str],
    patch_apply_report: Mapping[str, Any],
    evidence_references: list[str],
    target_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    triggered = bool(reasons) and bool(_as_dict(patch_apply_report).get("patch_applied", False))
    reverted = dict(patched)
    status = "not_required"
    restored_files = 0
    mismatched_after_rollback: list[str] = []
    if triggered:
        for rel, text in baseline.items():
            path = sandbox_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(text), encoding="utf-8")
            reverted[rel] = str(text)
            restored_files += 1
        for rel, text in baseline.items():
            now = _read_text(sandbox_root / rel)
            if now != str(text):
                mismatched_after_rollback.append(rel)
        status = "completed" if not mismatched_after_rollback else "incomplete"

    payload = {
        "schema_version": "1.0",
        "report_name": "rollback_lineage",
        "target_id": str(target_id),
        "classification": "PASS" if status in {"not_required", "completed"} else "FAIL_CLOSED",
        "rollback_triggered": triggered,
        "rollback_status": status,
        "rollback_reason_basis": list(reasons),
        "restored_file_count": restored_files,
        "mismatched_after_rollback": mismatched_after_rollback,
        "before_patch_fingerprint": stable_fingerprint(dict(baseline)),
        "after_patch_fingerprint": stable_fingerprint(dict(patched)),
        "post_rollback_fingerprint": stable_fingerprint(dict(reverted)),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, reverted


def _governance_build_escalation(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    reasons: list[str],
    rollback_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    full_reasons = list(reasons)
    if bool(_as_dict(rollback_report).get("rollback_triggered", False)) and str(
        rollback_report.get("rollback_status", "")
    ) != "completed":
        full_reasons.append("rollback_incomplete")
    full_reasons = sorted(set(full_reasons))
    payload = {
        "schema_version": "1.0",
        "report_name": "governance_build_escalation",
        "target_id": str(target_id),
        "classification": "FAIL_CLOSED" if full_reasons else "PASS",
        "escalation_reasons": full_reasons,
        "governance_state": dict(_as_dict(governance_state)),
        "summary": {
            "reason_count": len(full_reasons),
            "rollback_triggered": bool(_as_dict(rollback_report).get("rollback_triggered", False)),
            "rollback_status": str(rollback_report.get("rollback_status", "")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


class RealPatchApplicationGovernedBuildEngine:
    """Apply real patch in sandbox and run governed incremental build validation."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        source_root: str | Path,
        patch_path: str | Path,
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_history: list[Mapping[str, Any]] | None,
        session_id: str,
        lineage_id: str,
        evidence_references: list[str] | None,
    ) -> RealPatchApplicationGovernedBuildResult:
        source = Path(str(source_root))
        patch = Path(str(patch_path))
        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        if not source.exists() or not source.is_dir():
            fail = {
                "schema_version": "1.0",
                "phase": "REAL_PATCH_APPLICATION_GOVERNED_BUILD",
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
            fail["build_validation_fingerprint"] = stable_fingerprint(fail)
            return RealPatchApplicationGovernedBuildResult(build_bundle=fail)

        if not patch.exists() or not patch.is_file():
            fail = {
                "schema_version": "1.0",
                "phase": "REAL_PATCH_APPLICATION_GOVERNED_BUILD",
                "created_at": _utc_now_iso(),
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["patch_file_missing_or_invalid"],
                "artifacts": {},
                "runtime_truth_precedence": True,
                "advisory_only_behavior": True,
                "evidence_references": evidence,
            }
            fail["build_validation_fingerprint"] = stable_fingerprint(fail)
            return RealPatchApplicationGovernedBuildResult(build_bundle=fail)

        plugin = self._plugins.load_plugin(target_id)
        _ = plugin.capability_provider(
            {
                "target_id": str(target_id),
                "plugin_capability_state": dict(_as_dict(plugin_capability_state)),
                "source_root": str(source.resolve()),
            }
        )

        patch_text = _read_text(patch)
        patch_meta = _parse_patch_metadata(patch_text)
        touched_files = [str(v) for v in _as_list(patch_meta.get("touched_files")) if str(v).strip()]

        sandbox_root, baseline = _prepare_sandbox(source, touched_files)
        patch_apply = _run_patch_apply(sandbox_root=sandbox_root, patch_path=patch)
        patched: dict[str, str] = {
            rel: _read_text(sandbox_root / rel) for rel in touched_files if (sandbox_root / rel).exists()
        }
        applied_diff, changed_files = _build_applied_diff(baseline=baseline, patched=patched)

        include_report = _include_closure_report(
            target_id=target_id,
            source_root=source,
            sandbox_root=sandbox_root,
            touched_files=touched_files,
            evidence_references=evidence,
        )
        object_graph, compile_targets = _touched_object_graph(
            target_id=target_id,
            source_root=source,
            sandbox_root=sandbox_root,
            touched_files=touched_files,
            include_report=include_report,
            evidence_references=evidence,
        )
        build_report, warning_clusters = _compile_incremental(
            target_id=target_id,
            source_root=source,
            sandbox_root=sandbox_root,
            compile_targets=compile_targets,
            evidence_references=evidence,
        )
        symbol_report = _symbol_resolution_report(
            target_id=target_id,
            baseline=baseline,
            patched=patched,
            replacement_pairs=[_as_dict(v) for v in _as_list(patch_meta.get("replacement_pairs")) if isinstance(v, dict)],
            evidence_references=evidence,
        )
        runtime_sensitive_report = _runtime_sensitive_compile_report(
            target_id=target_id,
            changed_lines=[_as_dict(v) for v in _as_list(patch_meta.get("changed_lines")) if isinstance(v, dict)],
            evidence_references=evidence,
        )
        confidence_report = _build_confidence_report(
            target_id=target_id,
            patch_apply_report=patch_apply,
            build_report=build_report,
            include_report=include_report,
            symbol_report=symbol_report,
            runtime_sensitive_report=runtime_sensitive_report,
            warning_clusters=warning_clusters,
            evidence_references=evidence,
        )
        reasons = _collect_fail_reasons(
            governance_state=governance_state,
            patch_apply_report=patch_apply,
            build_report=build_report,
            include_report=include_report,
            symbol_report=symbol_report,
            runtime_sensitive_report=runtime_sensitive_report,
            confidence_report=confidence_report,
        )
        rollback_report, reverted = _rollback(
            sandbox_root=sandbox_root,
            baseline=baseline,
            patched=patched,
            reasons=reasons,
            patch_apply_report=patch_apply,
            evidence_references=evidence,
            target_id=target_id,
        )
        governance_report = _governance_build_escalation(
            target_id=target_id,
            governance_state=governance_state,
            reasons=reasons,
            rollback_report=rollback_report,
            evidence_references=evidence,
        )
        fail_reasons = [str(v) for v in _as_list(governance_report.get("escalation_reasons")) if str(v).strip()]
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
                "patch_apply_report": stable_fingerprint(patch_apply),
                "incremental_build_report": str(build_report.get("deterministic_fingerprint", "")),
                "touched_object_graph": str(object_graph.get("deterministic_fingerprint", "")),
                "symbol_resolution_report": str(symbol_report.get("deterministic_fingerprint", "")),
                "include_closure_report": str(include_report.get("deterministic_fingerprint", "")),
                "runtime_sensitive_compile_report": str(runtime_sensitive_report.get("deterministic_fingerprint", "")),
                "build_confidence_report": str(confidence_report.get("deterministic_fingerprint", "")),
                "rollback_lineage": str(rollback_report.get("deterministic_fingerprint", "")),
                "compile_warning_clusters": str(warning_clusters.get("deterministic_fingerprint", "")),
                "governance_build_escalation": str(governance_report.get("deterministic_fingerprint", "")),
                "applied_patch_diff": stable_fingerprint({"patch_text": applied_diff, "changed_files": changed_files}),
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

        patch_apply_report = {
            "schema_version": "1.0",
            "report_name": "patch_apply_report",
            "target_id": str(target_id),
            "classification": str(patch_apply.get("classification", "FAIL_CLOSED")),
            "patch_applied": bool(patch_apply.get("patch_applied", False)),
            "dry_run_returncode": patch_apply.get("dry_run_returncode"),
            "apply_returncode": patch_apply.get("apply_returncode"),
            "fuzz_observations": _as_list(patch_apply.get("fuzz_observations")),
            "reject_files": _as_list(patch_apply.get("reject_files")),
            "reason": str(patch_apply.get("reason", "")),
            "stdout": {
                "dry_run_stdout": str(patch_apply.get("dry_run_stdout", "")),
                "dry_run_stderr": str(patch_apply.get("dry_run_stderr", "")),
                "apply_stdout": str(patch_apply.get("apply_stdout", "")),
                "apply_stderr": str(patch_apply.get("apply_stderr", "")),
            },
            "summary": {
                "touched_file_count": len(touched_files),
                "changed_file_count": len(changed_files),
                "fuzz_count": len(_as_list(patch_apply.get("fuzz_observations"))),
                "reject_file_count": len(_as_list(patch_apply.get("reject_files"))),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        patch_apply_report["deterministic_fingerprint"] = stable_fingerprint(patch_apply_report)

        summary = {
            "schema_version": "1.0",
            "report_name": "real_patch_validation_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "summary": {
                "files_patched": len(changed_files),
                "objects_compiled": int(_as_dict(build_report.get("summary")).get("objects_compiled", 0)),
                "compile_success_count": int(_as_dict(build_report.get("summary")).get("compile_success_count", 0)),
                "compile_failure_count": int(_as_dict(build_report.get("summary")).get("compile_failure_count", 0)),
                "warnings_detected": int(_as_dict(build_report.get("summary")).get("warning_count", 0)),
                "runtime_sensitive_objects_impacted": int(
                    _as_dict(runtime_sensitive_report.get("summary")).get("runtime_sensitive_object_count", 0)
                ),
                "rollback_triggered": bool(_as_dict(rollback_report).get("rollback_triggered", False)),
                "real_patch_applied_successfully": bool(patch_apply_report.get("patch_applied", False)),
                "real_incremental_compile_succeeded": int(_as_dict(build_report.get("summary")).get("compile_failure_count", 0))
                == 0,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
        }
        summary["deterministic_fingerprint"] = stable_fingerprint(summary)

        artifacts = {
            "applied_patch_diff": {
                "patch_text": applied_diff,
                "changed_files": changed_files,
                "deterministic_fingerprint": stable_fingerprint(
                    {"patch_text": applied_diff, "changed_files": changed_files}
                ),
            },
            "patch_apply_report": patch_apply_report,
            "incremental_build_report": build_report,
            "touched_object_graph": object_graph,
            "symbol_resolution_report": symbol_report,
            "include_closure_report": include_report,
            "runtime_sensitive_compile_report": runtime_sensitive_report,
            "build_confidence_report": confidence_report,
            "rollback_lineage": rollback_report,
            "deterministic_build_replay": deterministic_replay,
            "compile_warning_clusters": warning_clusters,
            "governance_build_escalation": governance_report,
            "real_patch_validation_summary": summary,
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "REAL_PATCH_APPLICATION_GOVERNED_BUILD",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "source_root": str(source.resolve()),
            "patch_path": str(patch.resolve()),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "artifacts": artifacts,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        bundle["build_validation_fingerprint"] = stable_fingerprint(
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
                "reverted_fingerprint": stable_fingerprint(reverted),
            }
        )

        shutil.rmtree(sandbox_root, ignore_errors=True)
        return RealPatchApplicationGovernedBuildResult(build_bundle=bundle)


class RealPatchApplicationGovernedBuildRegistry:
    """Persistence for real patch application/build validation artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "applied_patch_diff": self._output_dir / "applied_patch.diff",
            "patch_apply_report": self._output_dir / "patch_apply_report.json",
            "incremental_build_report": self._output_dir / "incremental_build_report.json",
            "touched_object_graph": self._output_dir / "touched_object_graph.json",
            "symbol_resolution_report": self._output_dir / "symbol_resolution_report.json",
            "include_closure_report": self._output_dir / "include_closure_report.json",
            "runtime_sensitive_compile_report": self._output_dir / "runtime_sensitive_compile_report.json",
            "build_confidence_report": self._output_dir / "build_confidence_report.json",
            "rollback_lineage": self._output_dir / "rollback_lineage.json",
            "deterministic_build_replay": self._output_dir / "deterministic_build_replay.json",
            "compile_warning_clusters": self._output_dir / "compile_warning_clusters.json",
            "governance_build_escalation": self._output_dir / "governance_build_escalation.json",
            "real_patch_validation_summary": self._output_dir / "real_patch_validation_summary.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        patch_payload = _as_dict(artifacts.get("applied_patch_diff"))
        paths["applied_patch_diff"].parent.mkdir(parents=True, exist_ok=True)
        paths["applied_patch_diff"].write_text(str(patch_payload.get("patch_text", "")), encoding="utf-8")

        for key in (
            "patch_apply_report",
            "incremental_build_report",
            "touched_object_graph",
            "symbol_resolution_report",
            "include_closure_report",
            "runtime_sensitive_compile_report",
            "build_confidence_report",
            "rollback_lineage",
            "deterministic_build_replay",
            "compile_warning_clusters",
            "governance_build_escalation",
            "real_patch_validation_summary",
        ):
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("real_patch_application_governed_build"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "build_validation_fingerprint": str(payload.get("build_validation_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "real_patch_applied_successfully": bool(
                _as_dict(_as_dict(artifacts.get("patch_apply_report")).get("summary")).get("changed_file_count", 0) > 0
            ),
            "real_incremental_compile_succeeded": bool(
                int(_as_dict(_as_dict(artifacts.get("incremental_build_report")).get("summary")).get("compile_failure_count", 1))
                == 0
            ),
        }
        history.append(entry)
        history = history[-8000:]

        registry["real_patch_application_governed_build"] = {
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
                "type": "real_patch_application_governed_build",
                "recorded_at": _utc_now_iso(),
                "build_validation_fingerprint": str(payload.get("build_validation_fingerprint", "")),
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
            "build_validation_fingerprint": entry["build_validation_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
            "real_patch_applied_successfully": entry["real_patch_applied_successfully"],
            "real_incremental_compile_succeeded": entry["real_incremental_compile_succeeded"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("real_patch_application_governed_build"))
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
            "replay_type": "real_patch_application_governed_build",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [
                str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()
            ],
            "build_validation_fingerprint": str(_as_dict(selected).get("build_validation_fingerprint", "")),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "real_patch_applied_successfully": bool(_as_dict(selected).get("real_patch_applied_successfully", False)),
            "real_incremental_compile_succeeded": bool(
                _as_dict(selected).get("real_incremental_compile_succeeded", False)
            ),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "build_validation_fingerprint": str(_as_dict(selected).get("build_validation_fingerprint", "")),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        return replay_payload

