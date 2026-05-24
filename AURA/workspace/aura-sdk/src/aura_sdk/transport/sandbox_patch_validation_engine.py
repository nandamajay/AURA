"""Real patch application + sandbox build validation governance."""

from __future__ import annotations

import hashlib
import json
import os
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


_PATCH_FILE_RE = re.compile(r"^---\s+a/(.+)$")
_SENSITIVE_KEYWORDS = (
    "irq",
    "dsp",
    "mailbox",
    "apr",
    "soundwire",
    "swr_",
    "pcm",
    "dapm",
    "clk",
    "regulator",
    "pm_runtime",
    "runtime_pm",
    "suspend",
    "resume",
    "transport",
    "q6",
)


@dataclass(frozen=True)
class SandboxPatchValidationResult:
    validation_bundle: dict[str, Any]


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


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _path_fingerprint(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return _sha256_text(_read_text(path))


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


def _subsystem_for(rel_path: str) -> str:
    low = rel_path.replace("\\", "/").lower()
    if low.startswith("sound/soc/qcom/"):
        return "sound_soc_qcom"
    if low.startswith("techpack/audio/"):
        return "techpack_audio"
    if low.startswith("drivers/media/"):
        return "drivers_media"
    if low.startswith("asoc/codecs/"):
        return "asoc_codecs"
    if low.startswith("asoc/"):
        return "asoc_machine"
    if "soundwire" in low or "swr" in low:
        return "soundwire"
    if low.startswith("dsp/"):
        return "dsp"
    if low.startswith("ipc/"):
        return "ipc"
    return "other"


def _is_runtime_sensitive(rel_path: str, text: str) -> bool:
    low = f"{rel_path}\n{text}".lower()
    return any(token in low for token in _SENSITIVE_KEYWORDS)


def _build_deterministic_sandbox_root(*, lineage_id: str, source_root: Path, patch_text: str) -> Path:
    base = Path(tempfile.gettempdir()) / "aura_sandbox_patch_validation"
    base.mkdir(parents=True, exist_ok=True)
    token = stable_fingerprint(
        {
            "lineage_id": str(lineage_id),
            "source_root": str(source_root.resolve()),
            "patch_fingerprint": stable_fingerprint({"patch_text": patch_text}),
        }
    )[:16]
    root = base / f"{lineage_id}_{token}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _run_cmd(cmd: list[str], cwd: Path, timeout_sec: int = 180) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec,
    )
    return {
        "command": " ".join(cmd),
        "returncode": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _prepare_sandbox(
    *,
    source_root: Path,
    patch_text: str,
    lineage_id: str,
    evidence_references: list[str],
    target_id: str,
) -> tuple[dict[str, Any], Path, Path, dict[str, Any]]:
    sandbox_root = _build_deterministic_sandbox_root(
        lineage_id=str(lineage_id),
        source_root=source_root,
        patch_text=patch_text,
    )
    sandbox_src = sandbox_root / "src"
    sandbox_out = sandbox_root / "out"
    sandbox_out.mkdir(parents=True, exist_ok=True)

    mode = "copytree"
    prepare_trace: list[dict[str, Any]] = []
    is_git_repo = bool((source_root / ".git").exists())
    if is_git_repo:
        cmd = ["git", "-C", str(source_root), "worktree", "add", "--detach", str(sandbox_src)]
        res = _run_cmd(cmd, cwd=source_root)
        prepare_trace.append({"step": "git_worktree_add", **res})
        if int(res.get("returncode", 1)) == 0 and sandbox_src.exists():
            mode = "git_worktree"
        else:
            # fallback to copy mode if worktree failed
            if sandbox_src.exists():
                shutil.rmtree(sandbox_src, ignore_errors=True)
            sandbox_src.mkdir(parents=True, exist_ok=True)
            cp = _run_cmd(["cp", "-a", "--reflink=auto", str(source_root / "."), str(sandbox_src)], cwd=sandbox_root)
            prepare_trace.append({"step": "copytree_fallback", **cp})
            if int(cp.get("returncode", 1)) != 0:
                # final fallback: python copytree
                shutil.rmtree(sandbox_src, ignore_errors=True)
                shutil.copytree(source_root, sandbox_src, symlinks=True)
                prepare_trace.append(
                    {
                        "step": "python_copytree_fallback",
                        "command": "shutil.copytree",
                        "returncode": 0,
                        "stdout": "",
                        "stderr": "",
                        "elapsed_ms": 0,
                    }
                )
    else:
        sandbox_src.mkdir(parents=True, exist_ok=True)
        cp = _run_cmd(["cp", "-a", "--reflink=auto", str(source_root / "."), str(sandbox_src)], cwd=sandbox_root)
        prepare_trace.append({"step": "copytree", **cp})
        if int(cp.get("returncode", 1)) != 0:
            shutil.rmtree(sandbox_src, ignore_errors=True)
            shutil.copytree(source_root, sandbox_src, symlinks=True)
            prepare_trace.append(
                {
                    "step": "python_copytree_fallback",
                    "command": "shutil.copytree",
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "elapsed_ms": 0,
                }
            )

    manifest = {
        "schema_version": "1.0",
        "report_name": "sandbox_workspace_manifest",
        "target_id": str(target_id),
        "classification": "PASS" if sandbox_src.exists() else "FAIL_CLOSED",
        "source_root": str(source_root.resolve()),
        "sandbox_root": str(sandbox_root.resolve()),
        "sandbox_source_root": str(sandbox_src.resolve()),
        "sandbox_output_root": str(sandbox_out.resolve()),
        "workspace_mode": mode,
        "isolation_policy": {
            "source_tree_immutable": True,
            "artifact_isolation": True,
            "rollback_safe_execution": True,
            "disposable_workspace": True,
        },
        "prepare_trace": prepare_trace,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    manifest["deterministic_fingerprint"] = stable_fingerprint(manifest)
    return manifest, sandbox_src, sandbox_out, {"workspace_mode": mode, "sandbox_root": sandbox_root}


def _patch_apply_sequence(
    *,
    sandbox_src: Path,
    patch_paths: list[Path],
    workspace_mode: str,
    target_id: str,
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any], list[str], bool]:
    trace_rows: list[dict[str, Any]] = []
    all_touched: set[str] = set()
    patch_applied = True
    any_partial_failure = False

    for idx, patch in enumerate(patch_paths, start=1):
        patch_text = _read_text(patch)
        touched = _parse_patch_touched_files(patch_text)
        all_touched.update(touched)

        if workspace_mode == "git_worktree" or (sandbox_src / ".git").exists():
            dry_cmd = ["git", "-C", str(sandbox_src), "apply", "--check", str(patch.resolve())]
            apply_cmd = ["git", "-C", str(sandbox_src), "apply", str(patch.resolve())]
        else:
            dry_cmd = ["patch", "-p1", "--batch", "--forward", "--dry-run", "-i", str(patch.resolve())]
            apply_cmd = ["patch", "-p1", "--batch", "--forward", "-i", str(patch.resolve())]

        dry = _run_cmd(dry_cmd, cwd=sandbox_src)
        apply = {"command": "not_run", "returncode": 1, "stdout": "", "stderr": "", "elapsed_ms": 0}
        if int(dry.get("returncode", 1)) == 0:
            apply = _run_cmd(apply_cmd, cwd=sandbox_src)

        succeeded = int(dry.get("returncode", 1)) == 0 and int(apply.get("returncode", 1)) == 0
        if not succeeded:
            patch_applied = False
            any_partial_failure = True

        trace_rows.append(
            {
                "patch_index": idx,
                "patch_path": str(patch.resolve()),
                "touched_files": touched,
                "dry_run": dry,
                "apply": apply,
                "status": "applied" if succeeded else "failed",
            }
        )

    patch_application_trace = {
        "schema_version": "1.0",
        "report_name": "patch_application_trace",
        "target_id": str(target_id),
        "classification": "PASS" if patch_applied else "FAIL_CLOSED",
        "patch_steps": trace_rows,
        "summary": {
            "patch_count": len(patch_paths),
            "applied_patch_count": sum(1 for row in trace_rows if str(_as_dict(row).get("status", "")) == "applied"),
            "failed_patch_count": sum(1 for row in trace_rows if str(_as_dict(row).get("status", "")) == "failed"),
            "touched_file_count": len(all_touched),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    patch_application_trace["deterministic_fingerprint"] = stable_fingerprint(patch_application_trace)

    touched_objects = sorted({str(Path(rel).with_suffix(".o")).replace("\\", "/") for rel in all_touched if rel.endswith(".c")})
    subsystem_boundaries = sorted({_subsystem_for(rel) for rel in all_touched})
    applied_patch_lineage = {
        "schema_version": "1.0",
        "report_name": "applied_patch_lineage",
        "target_id": str(target_id),
        "classification": "PASS" if patch_applied else "FAIL_CLOSED",
        "patch_order": [str(path.resolve()) for path in patch_paths],
        "touched_files": sorted(all_touched),
        "touched_objects": touched_objects,
        "subsystem_boundaries": subsystem_boundaries,
        "summary": {
            "touched_file_count": len(all_touched),
            "touched_object_count": len(touched_objects),
            "subsystem_boundary_count": len(subsystem_boundaries),
            "partial_failure_detected": any_partial_failure,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    applied_patch_lineage["deterministic_fingerprint"] = stable_fingerprint(applied_patch_lineage)
    return applied_patch_lineage, patch_application_trace, sorted(all_touched), patch_applied


def _collect_runtime_sensitive_patch_impact(
    *,
    target_id: str,
    sandbox_src: Path,
    touched_files: list[str],
    command_rows: list[dict[str, Any]],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    failed_subsystems = {
        str(_as_dict(row).get("subsystem", ""))
        for row in command_rows
        if int(_as_dict(row).get("returncode", 0)) != 0
    }
    impacts: list[dict[str, Any]] = []
    unsafe = 0
    for rel in touched_files:
        text = _read_text(sandbox_src / rel)
        if not _is_runtime_sensitive(rel, text):
            continue
        subsystem = _subsystem_for(rel)
        state = "unsafe_build_failure" if subsystem in failed_subsystems else "stable"
        if state != "stable":
            unsafe += 1
        impacts.append(
            {
                "file": rel,
                "subsystem": subsystem,
                "impact_state": state,
                "runtime_sensitive_keywords": sorted({k for k in _SENSITIVE_KEYWORDS if k in f'{rel}\\n{text}'.lower()})[:20],
            }
        )
    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_sensitive_patch_impact",
        "target_id": str(target_id),
        "classification": "PASS" if unsafe == 0 else "FAIL_CLOSED",
        "impacts": impacts,
        "summary": {
            "runtime_sensitive_touched_count": len(impacts),
            "unsafe_runtime_sensitive_count": unsafe,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, {"unsafe_runtime_sensitive_count": unsafe}


def _execute_sandbox_builds(
    *,
    target_id: str,
    sandbox_src: Path,
    sandbox_out: Path,
    subsystem_targets: list[str],
    object_targets: list[str],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    object_rows: list[dict[str, Any]] = []

    def append_row(phase: str, subsystem: str, cmd: list[str], result: dict[str, Any]) -> None:
        rows.append(
            {
                "phase": phase,
                "subsystem": subsystem,
                "command": str(result.get("command", " ".join(cmd))),
                "returncode": int(result.get("returncode", 1)),
                "stdout": str(result.get("stdout", "")),
                "stderr": str(result.get("stderr", "")),
                "elapsed_ms": int(result.get("elapsed_ms", 0)),
            }
        )

    for subsystem in subsystem_targets:
        dry = _run_cmd(
            ["make", "-C", str(sandbox_src), f"O={sandbox_out}", f"M={subsystem}", "modules", "-n"],
            cwd=sandbox_src,
        )
        append_row("dry_run_subsystem", subsystem, [], dry)
        exe = _run_cmd(
            ["make", "-C", str(sandbox_src), f"O={sandbox_out}", f"M={subsystem}", "modules"],
            cwd=sandbox_src,
        )
        append_row("execute_subsystem", subsystem, [], exe)

    for obj in object_targets[:20]:
        subsystem = _subsystem_for(obj)
        dry = _run_cmd(
            ["make", "-C", str(sandbox_src), f"O={sandbox_out}", obj, "-n"],
            cwd=sandbox_src,
        )
        append_row("dry_run_object", subsystem, [], dry)
        exe = _run_cmd(
            ["make", "-C", str(sandbox_src), f"O={sandbox_out}", obj],
            cwd=sandbox_src,
        )
        append_row("execute_object", subsystem, [], exe)

        built_obj = sandbox_out / obj
        object_rows.append(
            {
                "object": obj,
                "subsystem": subsystem,
                "build_returncode": int(exe.get("returncode", 1)),
                "exists_in_output": bool(built_obj.exists()),
                "output_path": str(built_obj.resolve()),
            }
        )

    success = sum(1 for row in rows if int(_as_dict(row).get("returncode", 1)) == 0)
    failure = len(rows) - success
    build_report = {
        "schema_version": "1.0",
        "report_name": "subsystem_build_validation",
        "target_id": str(target_id),
        "classification": "PASS" if failure == 0 else "FAIL_CLOSED",
        "commands": rows,
        "summary": {
            "command_count": len(rows),
            "success_count": success,
            "failure_count": failure,
            "subsystem_target_count": len(subsystem_targets),
            "object_target_count": len(object_targets[:20]),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    build_report["deterministic_fingerprint"] = stable_fingerprint(build_report)

    object_lineage = {
        "schema_version": "1.0",
        "report_name": "object_rebuild_lineage",
        "target_id": str(target_id),
        "classification": "PASS" if all(bool(_as_dict(v).get("build_returncode", 1)) == 0 for v in object_rows) else "FAIL_CLOSED",
        "objects": object_rows,
        "summary": {
            "object_count": len(object_rows),
            "successful_object_count": sum(1 for row in object_rows if int(_as_dict(row).get("build_returncode", 1)) == 0),
            "generated_object_count": sum(1 for row in object_rows if bool(_as_dict(row).get("exists_in_output", False))),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    object_lineage["deterministic_fingerprint"] = stable_fingerprint(object_lineage)

    modpost_issues: list[dict[str, Any]] = []
    linker_issues: list[dict[str, Any]] = []
    for row in rows:
        item = _as_dict(row)
        text = f"{item.get('stdout', '')}\n{item.get('stderr', '')}".lower()
        if "modpost" in text and ("error" in text or int(item.get("returncode", 0)) != 0):
            modpost_issues.append(
                {
                    "phase": str(item.get("phase", "")),
                    "subsystem": str(item.get("subsystem", "")),
                    "command": str(item.get("command", "")),
                    "excerpt": (str(item.get("stdout", "")) + "\n" + str(item.get("stderr", "")))[:600],
                }
            )
        linker_markers = ("undefined reference", "undefined symbol", "ld: ", "collect2: error")
        if any(token in text for token in linker_markers):
            linker_issues.append(
                {
                    "phase": str(item.get("phase", "")),
                    "subsystem": str(item.get("subsystem", "")),
                    "command": str(item.get("command", "")),
                    "excerpt": (str(item.get("stdout", "")) + "\n" + str(item.get("stderr", "")))[:600],
                }
            )

    modpost_report = {
        "schema_version": "1.0",
        "report_name": "modpost_validation_report",
        "target_id": str(target_id),
        "classification": "PASS" if not modpost_issues else "FAIL_CLOSED",
        "issues": modpost_issues[:2000],
        "summary": {"issue_count": len(modpost_issues)},
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    modpost_report["deterministic_fingerprint"] = stable_fingerprint(modpost_report)

    linker_report = {
        "schema_version": "1.0",
        "report_name": "linker_closure_report",
        "target_id": str(target_id),
        "classification": "PASS" if not linker_issues else "FAIL_CLOSED",
        "issues": linker_issues[:2000],
        "summary": {"issue_count": len(linker_issues)},
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    linker_report["deterministic_fingerprint"] = stable_fingerprint(linker_report)

    return build_report, object_lineage, rows, modpost_report, linker_report


def _symbol_regression_report(
    *,
    target_id: str,
    baseline_files: Mapping[str, str],
    transformed_files: Mapping[str, str],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    def extract_functions(text: str) -> set[str]:
        out: set[str] = set()
        for match in re.findall(r"(?m)^[ \t]*(?:static\s+)?(?:inline\s+)?(?:const\s+)?(?:[A-Za-z_][A-Za-z0-9_]*[\s\*]+)+([A-Za-z_][A-Za-z0-9_]*)\s*\(", text):
            sym = str(match).strip()
            if sym:
                out.add(sym)
        return out

    rows: list[dict[str, Any]] = []
    removed_total = 0
    added_total = 0
    for rel in sorted(set(baseline_files.keys()) | set(transformed_files.keys())):
        before = str(baseline_files.get(rel, ""))
        after = str(transformed_files.get(rel, ""))
        b = extract_functions(before)
        a = extract_functions(after)
        removed = sorted(b - a)
        added = sorted(a - b)
        removed_total += len(removed)
        added_total += len(added)
        if removed or added:
            rows.append(
                {
                    "file": rel,
                    "removed_symbols": removed,
                    "added_symbols": added,
                }
            )
    payload = {
        "schema_version": "1.0",
        "report_name": "symbol_regression_report",
        "target_id": str(target_id),
        "classification": "PASS" if removed_total == 0 else "FAIL_CLOSED",
        "deltas": rows,
        "summary": {
            "file_delta_count": len(rows),
            "removed_symbol_count": removed_total,
            "added_symbol_count": added_total,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    unresolved = {
        "removed_symbol_count": removed_total,
    }
    return payload, unresolved


def _build_fingerprint_diff_and_equivalence(
    *,
    target_id: str,
    touched_files: list[str],
    baseline_files: Mapping[str, str],
    transformed_files: Mapping[str, str],
    compile_baseline: Mapping[str, Any],
    compile_transformed: Mapping[str, Any],
    build_report: Mapping[str, Any],
    runtime_sensitive_impact: Mapping[str, Any],
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    file_deltas: list[dict[str, Any]] = []
    for rel in touched_files:
        before = str(baseline_files.get(rel, ""))
        after = str(transformed_files.get(rel, ""))
        file_deltas.append(
            {
                "file": rel,
                "before_fingerprint": _sha256_text(before),
                "after_fingerprint": _sha256_text(after),
                "changed": before != after,
            }
        )

    b_conf = _to_float(_as_dict(_as_dict(compile_baseline.get("artifacts")).get("compile_confidence_report")).get("confidence_score"), 0.0)
    t_conf = _to_float(_as_dict(_as_dict(compile_transformed.get("artifacts")).get("compile_confidence_report")).get("confidence_score"), 0.0)
    b_unres = int(_as_dict(_as_dict(compile_baseline.get("artifacts")).get("unresolved_dependency_report")).get("summary", {}).get("total_unresolved_count", 0))
    t_unres = int(_as_dict(_as_dict(compile_transformed.get("artifacts")).get("unresolved_dependency_report")).get("summary", {}).get("total_unresolved_count", 0))
    cmd_fail = int(_as_dict(build_report.get("summary")).get("failure_count", 0))
    runtime_unsafe = int(_as_dict(runtime_sensitive_impact.get("summary")).get("unsafe_runtime_sensitive_count", 0))

    diff = {
        "schema_version": "1.0",
        "report_name": "build_fingerprint_diff",
        "target_id": str(target_id),
        "classification": "PASS" if cmd_fail == 0 else "FAIL_CLOSED",
        "file_fingerprints": file_deltas,
        "compile_confidence_delta": round(t_conf - b_conf, 3),
        "unresolved_dependency_delta": int(t_unres - b_unres),
        "command_failure_count": cmd_fail,
        "runtime_sensitive_unsafe_count": runtime_unsafe,
        "summary": {
            "changed_file_count": sum(1 for row in file_deltas if bool(_as_dict(row).get("changed", False))),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    diff["deterministic_fingerprint"] = stable_fingerprint(diff)

    drift_exceeds = (t_unres - b_unres) > 10 or (b_conf - t_conf) > 0.2
    equivalence = {
        "schema_version": "1.0",
        "report_name": "transformation_equivalence_report",
        "target_id": str(target_id),
        "classification": "PASS" if not drift_exceeds and cmd_fail == 0 and runtime_unsafe == 0 else "FAIL_CLOSED",
        "equivalence_inputs": {
            "baseline_compile_confidence": b_conf,
            "transformed_compile_confidence": t_conf,
            "confidence_delta": round(t_conf - b_conf, 3),
            "baseline_unresolved_dependencies": b_unres,
            "transformed_unresolved_dependencies": t_unres,
            "unresolved_dependency_delta": int(t_unres - b_unres),
            "command_failure_count": cmd_fail,
            "runtime_sensitive_unsafe_count": runtime_unsafe,
        },
        "summary": {
            "dependency_drift_exceeds_threshold": drift_exceeds,
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    equivalence["deterministic_fingerprint"] = stable_fingerprint(equivalence)
    unresolved = {
        "dependency_drift_exceeds_threshold": drift_exceeds,
    }
    return diff, equivalence, unresolved


def _rollback(
    *,
    target_id: str,
    sandbox_src: Path,
    workspace_mode: str,
    touched_files: list[str],
    baseline_files: Mapping[str, str],
    reasons: list[str],
    patch_applied: bool,
    evidence_references: list[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    triggered = bool(reasons) and bool(patch_applied)
    restored = dict(baseline_files)
    status = "not_required"
    mismatched: list[str] = []

    if triggered:
        if workspace_mode == "git_worktree" or (sandbox_src / ".git").exists():
            res = _run_cmd(["git", "-C", str(sandbox_src), "reset", "--hard", "HEAD"], cwd=sandbox_src)
            status = "completed" if int(res.get("returncode", 1)) == 0 else "incomplete"
        else:
            for rel in touched_files:
                (sandbox_src / rel).parent.mkdir(parents=True, exist_ok=True)
                (sandbox_src / rel).write_text(str(baseline_files.get(rel, "")), encoding="utf-8")
            status = "completed"

        for rel in touched_files:
            current = _read_text(sandbox_src / rel)
            if current != str(baseline_files.get(rel, "")):
                mismatched.append(rel)
        if mismatched:
            status = "incomplete"

    post: dict[str, str] = {}
    for rel in touched_files:
        post[rel] = _read_text(sandbox_src / rel)

    payload = {
        "schema_version": "1.0",
        "report_name": "rollback_lineage_report",
        "target_id": str(target_id),
        "classification": "PASS" if status in {"not_required", "completed"} else "FAIL_CLOSED",
        "rollback_triggered": triggered,
        "rollback_status": status,
        "rollback_reason_basis": sorted(set(reasons)),
        "mismatched_after_rollback": mismatched,
        "before_patch_fingerprint": stable_fingerprint(dict(baseline_files)),
        "post_rollback_fingerprint": stable_fingerprint(dict(post)),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload, post


def _runtime_promotion_eligibility(
    *,
    target_id: str,
    governance_reasons: list[str],
    confidence_score: float,
    linker_report: Mapping[str, Any],
    modpost_report: Mapping[str, Any],
    runtime_sensitive_report: Mapping[str, Any],
    deterministic_ready: bool,
    rollback_report: Mapping[str, Any],
    evidence_references: list[str],
) -> dict[str, Any]:
    eligible = (
        not governance_reasons
        and confidence_score >= 0.78
        and str(linker_report.get("classification", "")) == "PASS"
        and str(modpost_report.get("classification", "")) == "PASS"
        and str(runtime_sensitive_report.get("classification", "")) == "PASS"
        and deterministic_ready
        and str(rollback_report.get("classification", "")) == "PASS"
    )
    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_promotion_eligibility",
        "target_id": str(target_id),
        "classification": "PASS" if eligible else "FAIL_CLOSED",
        "eligible": bool(eligible),
        "inputs": {
            "governance_reason_count": len(governance_reasons),
            "confidence_score": round(confidence_score, 3),
            "linker_state": str(linker_report.get("classification", "")),
            "modpost_state": str(modpost_report.get("classification", "")),
            "runtime_sensitive_state": str(runtime_sensitive_report.get("classification", "")),
            "deterministic_replay_ready": bool(deterministic_ready),
            "rollback_safety_state": str(rollback_report.get("classification", "")),
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": evidence_references,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _cleanup_sandbox(source_root: Path, sandbox_src: Path, sandbox_root: Path, workspace_mode: str) -> dict[str, Any]:
    trace = {"workspace_mode": workspace_mode, "cleanup_steps": []}
    if workspace_mode == "git_worktree":
        res = _run_cmd(["git", "-C", str(source_root), "worktree", "remove", "--force", str(sandbox_src)], cwd=source_root)
        trace["cleanup_steps"].append({"step": "git_worktree_remove", **res})
    shutil.rmtree(sandbox_root, ignore_errors=True)
    trace["cleanup_steps"].append(
        {
            "step": "sandbox_directory_remove",
            "command": f"rm -rf {sandbox_root}",
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "elapsed_ms": 0,
        }
    )
    return trace


class SandboxPatchValidationEngine:
    """Real patch application and sandbox build validation."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()
        self._compile = CompileCognitionEngine(plugin_loader=self._plugins)

    def analyze(
        self,
        *,
        target_id: str,
        source_root: str | Path,
        patch_paths: list[str | Path],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        previous_history: list[Mapping[str, Any]] | None,
        session_id: str,
        lineage_id: str,
        evidence_references: list[str] | None,
        subsystem_targets: list[str] | None = None,
        object_targets: list[str] | None = None,
    ) -> SandboxPatchValidationResult:
        source_path = Path(str(source_root))
        evidence = [str(v) for v in (evidence_references or []) if str(v).strip()]
        patch_list = [Path(str(v)) for v in patch_paths if str(v).strip()]

        if not source_path.exists() or not source_path.is_dir():
            fail = {
                "schema_version": "1.0",
                "phase": "SANDBOX_PATCH_VALIDATION",
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
            fail["sandbox_patch_validation_fingerprint"] = stable_fingerprint(fail)
            return SandboxPatchValidationResult(validation_bundle=fail)

        if not patch_list or any(not p.exists() or not p.is_file() for p in patch_list):
            fail = {
                "schema_version": "1.0",
                "phase": "SANDBOX_PATCH_VALIDATION",
                "created_at": _utc_now_iso(),
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": "FAIL_CLOSED",
                "fail_closed_reasons": ["patch_path_missing_or_invalid"],
                "artifacts": {},
                "runtime_truth_precedence": True,
                "advisory_only_behavior": True,
                "evidence_references": evidence,
            }
            fail["sandbox_patch_validation_fingerprint"] = stable_fingerprint(fail)
            return SandboxPatchValidationResult(validation_bundle=fail)

        plugin = self._plugins.load_plugin(target_id)
        _ = plugin.capability_provider(
            {
                "target_id": str(target_id),
                "plugin_capability_state": dict(_as_dict(plugin_capability_state)),
                "source_root": str(source_path.resolve()),
            }
        )

        patch_text_all = "\n".join(_read_text(path) for path in patch_list)
        workspace_manifest, sandbox_src, sandbox_out, sandbox_meta = _prepare_sandbox(
            source_root=source_path,
            patch_text=patch_text_all,
            lineage_id=str(lineage_id),
            evidence_references=evidence,
            target_id=str(target_id),
        )
        workspace_mode = str(_as_dict(sandbox_meta).get("workspace_mode", "copytree"))
        sandbox_root = Path(str(_as_dict(sandbox_meta).get("sandbox_root", sandbox_src.parent)))

        applied_lineage, patch_trace, touched_files, patch_applied = _patch_apply_sequence(
            sandbox_src=sandbox_src,
            patch_paths=patch_list,
            workspace_mode=workspace_mode,
            target_id=str(target_id),
            evidence_references=evidence,
        )

        baseline_files = {rel: _read_text(source_path / rel) for rel in touched_files}
        transformed_files = {rel: _read_text(sandbox_src / rel) for rel in touched_files}

        baseline_compile = self._compile.analyze(
            target_id=target_id,
            source_root=source_path,
            patch_path=patch_list[0],
            governance_state=governance_state,
            replay_traces=replay_traces,
            plugin_capability_state=plugin_capability_state,
            previous_history=[],
            session_id=f"{session_id}:baseline_compile",
            lineage_id=f"{lineage_id}:baseline_compile",
            evidence_references=evidence,
        ).compile_bundle
        transformed_compile = self._compile.analyze(
            target_id=target_id,
            source_root=sandbox_src,
            patch_path=patch_list[0],
            governance_state=governance_state,
            replay_traces=replay_traces,
            plugin_capability_state=plugin_capability_state,
            previous_history=[],
            session_id=f"{session_id}:transformed_compile",
            lineage_id=f"{lineage_id}:transformed_compile",
            evidence_references=evidence,
        ).compile_bundle

        patch_touched_objects = [str(v) for v in _as_list(applied_lineage.get("touched_objects")) if str(v).strip()]
        selected_object_targets = [str(v) for v in (object_targets or []) if str(v).strip()] or patch_touched_objects
        if not selected_object_targets:
            selected_object_targets = ["asoc/test.o"]

        default_subsystems = ["sound/soc/qcom", "techpack/audio", "asoc", "drivers/media"]
        selected_subsystems = [str(v) for v in (subsystem_targets or default_subsystems) if (sandbox_src / str(v)).exists()]
        if not selected_subsystems and (sandbox_src / "asoc").exists():
            selected_subsystems = ["asoc"]

        build_report, object_lineage, command_rows, modpost_report, linker_report = _execute_sandbox_builds(
            target_id=str(target_id),
            sandbox_src=sandbox_src,
            sandbox_out=sandbox_out,
            subsystem_targets=selected_subsystems,
            object_targets=selected_object_targets,
            evidence_references=evidence,
        )

        runtime_sensitive_impact, runtime_unresolved = _collect_runtime_sensitive_patch_impact(
            target_id=str(target_id),
            sandbox_src=sandbox_src,
            touched_files=touched_files,
            command_rows=command_rows,
            evidence_references=evidence,
        )

        symbol_regression, symbol_regression_unresolved = _symbol_regression_report(
            target_id=str(target_id),
            baseline_files=baseline_files,
            transformed_files=transformed_files,
            evidence_references=evidence,
        )

        build_fingerprint_diff, transformation_equivalence, equivalence_unresolved = _build_fingerprint_diff_and_equivalence(
            target_id=str(target_id),
            touched_files=touched_files,
            baseline_files=baseline_files,
            transformed_files=transformed_files,
            compile_baseline=baseline_compile,
            compile_transformed=transformed_compile,
            build_report=build_report,
            runtime_sensitive_impact=runtime_sensitive_impact,
            evidence_references=evidence,
        )

        unresolved_dependency_report = {
            "schema_version": "1.0",
            "report_name": "unresolved_dependency_report",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED",
            "compile_baseline": _as_dict(_as_dict(baseline_compile.get("artifacts")).get("unresolved_dependency_report")),
            "compile_transformed": _as_dict(_as_dict(transformed_compile.get("artifacts")).get("unresolved_dependency_report")),
            "build_failures": [row for row in command_rows if int(_as_dict(row).get("returncode", 1)) != 0][:2000],
            "symbol_regression": symbol_regression_unresolved,
            "equivalence_unresolved": equivalence_unresolved,
            "summary": {
                "total_unresolved_count": int(
                    _as_dict(_as_dict(transformed_compile.get("artifacts")).get("unresolved_dependency_report")).get("summary", {}).get(
                        "total_unresolved_count", 0
                    )
                )
                + int(_as_dict(build_report.get("summary")).get("failure_count", 0))
                + int(symbol_regression_unresolved.get("removed_symbol_count", 0)),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        unresolved_dependency_report["deterministic_fingerprint"] = stable_fingerprint(unresolved_dependency_report)

        confidence_score = (
            (_to_float(_as_dict(_as_dict(transformed_compile.get("artifacts")).get("compile_confidence_report")).get("confidence_score"), 0.0) * 0.5)
            + (1.0 - min(1.0, int(_as_dict(build_report.get("summary")).get("failure_count", 0)) / max(1, int(_as_dict(build_report.get("summary")).get("command_count", 1))))) * 0.3
            + (1.0 - min(1.0, int(_as_dict(runtime_sensitive_impact.get("summary")).get("unsafe_runtime_sensitive_count", 0)))) * 0.2
        )
        confidence_score = round(max(0.0, min(1.0, confidence_score)), 3)
        build_confidence_report = {
            "schema_version": "1.0",
            "report_name": "build_confidence_report",
            "target_id": str(target_id),
            "classification": "PASS" if confidence_score >= 0.78 else "FAIL_CLOSED",
            "confidence_score": confidence_score,
            "confidence_threshold": 0.78,
            "inputs": {
                "transformed_compile_confidence": _to_float(
                    _as_dict(_as_dict(transformed_compile.get("artifacts")).get("compile_confidence_report")).get("confidence_score"),
                    0.0,
                ),
                "build_failure_count": int(_as_dict(build_report.get("summary")).get("failure_count", 0)),
                "runtime_sensitive_unsafe_count": int(_as_dict(runtime_sensitive_impact.get("summary")).get("unsafe_runtime_sensitive_count", 0)),
                "symbol_removed_count": int(symbol_regression_unresolved.get("removed_symbol_count", 0)),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        build_confidence_report["deterministic_fingerprint"] = stable_fingerprint(build_confidence_report)

        fail_reasons: list[str] = []
        if not patch_applied:
            fail_reasons.append("patch_application_partially_failed")
        if str(build_report.get("classification", "")) != "PASS":
            fail_reasons.append("compile_integrity_uncertain")
        if str(linker_report.get("classification", "")) != "PASS":
            fail_reasons.append("linker_closure_incomplete")
        if str(modpost_report.get("classification", "")) != "PASS":
            fail_reasons.append("modpost_integrity_failed")
        if str(runtime_sensitive_impact.get("classification", "")) != "PASS":
            fail_reasons.append("runtime_sensitive_regions_unstable")
        if bool(_as_dict(equivalence_unresolved).get("dependency_drift_exceeds_threshold", False)):
            fail_reasons.append("dependency_drift_exceeds_threshold")
        if str(build_confidence_report.get("classification", "")) != "PASS":
            fail_reasons.append("compile_confidence_below_threshold")
        if int(_as_dict(unresolved_dependency_report.get("summary")).get("total_unresolved_count", 0)) > 0:
            fail_reasons.append("unresolved_symbols_or_dependencies_exist")

        rollback_report, post_rollback_files = _rollback(
            target_id=str(target_id),
            sandbox_src=sandbox_src,
            workspace_mode=workspace_mode,
            touched_files=touched_files,
            baseline_files=baseline_files,
            reasons=fail_reasons,
            patch_applied=patch_applied,
            evidence_references=evidence,
        )
        if str(rollback_report.get("classification", "")) != "PASS":
            fail_reasons.append("rollback_unsafe")

        deterministic_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_patch_validation_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "patch_application_order": [str(path.resolve()) for path in patch_list],
            "build_commands": [
                {
                    "phase": str(_as_dict(row).get("phase", "")),
                    "command": str(_as_dict(row).get("command", "")),
                    "returncode": int(_as_dict(row).get("returncode", 1)),
                }
                for row in command_rows
            ],
            "sandbox_fingerprint": str(workspace_manifest.get("deterministic_fingerprint", "")),
            "lineage_fingerprints": {
                "applied_patch_lineage": str(applied_lineage.get("deterministic_fingerprint", "")),
                "patch_application_trace": str(patch_trace.get("deterministic_fingerprint", "")),
                "subsystem_build_validation": str(build_report.get("deterministic_fingerprint", "")),
                "object_rebuild_lineage": str(object_lineage.get("deterministic_fingerprint", "")),
                "modpost_validation_report": str(modpost_report.get("deterministic_fingerprint", "")),
                "linker_closure_report": str(linker_report.get("deterministic_fingerprint", "")),
                "symbol_regression_report": str(symbol_regression.get("deterministic_fingerprint", "")),
                "build_fingerprint_diff": str(build_fingerprint_diff.get("deterministic_fingerprint", "")),
                "transformation_equivalence_report": str(transformation_equivalence.get("deterministic_fingerprint", "")),
                "runtime_sensitive_patch_impact": str(runtime_sensitive_impact.get("deterministic_fingerprint", "")),
                "rollback_lineage_report": str(rollback_report.get("deterministic_fingerprint", "")),
            },
            "replay_signal": {
                "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            "history": [row for row in _as_list(previous_history or []) if isinstance(row, dict)]
            + [{"lineage_id": str(lineage_id), "session_id": str(session_id), "classification": "FAIL_CLOSED" if fail_reasons else "PASS"}],
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_replay["deterministic_fingerprint"] = stable_fingerprint(deterministic_replay)

        governance_decision = {
            "schema_version": "1.0",
            "report_name": "governance_patch_validation_decision",
            "target_id": str(target_id),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "governance_reasons": sorted(set(fail_reasons)),
            "governance_state": dict(_as_dict(governance_state)),
            "summary": {
                "reason_count": len(sorted(set(fail_reasons))),
                "build_promotion_blocked": bool(fail_reasons),
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        governance_decision["deterministic_fingerprint"] = stable_fingerprint(governance_decision)

        runtime_promotion = _runtime_promotion_eligibility(
            target_id=str(target_id),
            governance_reasons=sorted(set(fail_reasons)),
            confidence_score=confidence_score,
            linker_report=linker_report,
            modpost_report=modpost_report,
            runtime_sensitive_report=runtime_sensitive_impact,
            deterministic_ready=True,
            rollback_report=rollback_report,
            evidence_references=evidence,
        )

        summary = {
            "schema_version": "1.0",
            "report_name": "sandbox_patch_validation_summary",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "summary": {
                "patch_applied": bool(patch_applied),
                "command_count": int(_as_dict(build_report.get("summary")).get("command_count", 0)),
                "build_failure_count": int(_as_dict(build_report.get("summary")).get("failure_count", 0)),
                "modpost_issue_count": int(_as_dict(modpost_report.get("summary")).get("issue_count", 0)),
                "linker_issue_count": int(_as_dict(linker_report.get("summary")).get("issue_count", 0)),
                "runtime_sensitive_unsafe_count": int(
                    _as_dict(runtime_sensitive_impact.get("summary")).get("unsafe_runtime_sensitive_count", 0)
                ),
                "confidence_score": confidence_score,
                "rollback_status": str(rollback_report.get("rollback_status", "")),
                "runtime_promotion_eligible": bool(runtime_promotion.get("eligible", False)),
                "replay_persistable": True,
            },
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
        }
        summary["deterministic_fingerprint"] = stable_fingerprint(summary)

        cleanup_trace = _cleanup_sandbox(
            source_root=source_path,
            sandbox_src=sandbox_src,
            sandbox_root=sandbox_root,
            workspace_mode=workspace_mode,
        )
        workspace_manifest["cleanup_trace"] = cleanup_trace
        workspace_manifest["deterministic_fingerprint"] = stable_fingerprint(workspace_manifest)

        artifacts = {
            "sandbox_workspace_manifest": workspace_manifest,
            "applied_patch_lineage": applied_lineage,
            "patch_application_trace": patch_trace,
            "subsystem_build_validation": build_report,
            "object_rebuild_lineage": object_lineage,
            "modpost_validation_report": modpost_report,
            "linker_closure_report": linker_report,
            "symbol_regression_report": symbol_regression,
            "build_fingerprint_diff": build_fingerprint_diff,
            "transformation_equivalence_report": transformation_equivalence,
            "runtime_promotion_eligibility": runtime_promotion,
            "rollback_lineage_report": rollback_report,
            "deterministic_patch_validation_replay": deterministic_replay,
            "runtime_sensitive_patch_impact": runtime_sensitive_impact,
            "sandbox_patch_validation_summary": summary,
            "governance_patch_validation_decision": governance_decision,
            "build_confidence_report": build_confidence_report,
            "unresolved_dependency_report": unresolved_dependency_report,
            "compile_baseline_summary": _as_dict(_as_dict(baseline_compile.get("artifacts")).get("compile_cognition_summary")),
            "compile_transformed_summary": _as_dict(_as_dict(transformed_compile.get("artifacts")).get("compile_cognition_summary")),
            "post_rollback_fingerprint": {
                "files": [
                    {"file": rel, "fingerprint": _sha256_text(str(post_rollback_files.get(rel, "")))}
                    for rel in sorted(post_rollback_files.keys())
                ],
                "deterministic_fingerprint": stable_fingerprint(
                    {rel: _sha256_text(str(post_rollback_files.get(rel, ""))) for rel in sorted(post_rollback_files.keys())}
                ),
            },
        }

        bundle = {
            "schema_version": "1.0",
            "phase": "SANDBOX_PATCH_VALIDATION",
            "created_at": _utc_now_iso(),
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "source_root": str(source_path.resolve()),
            "classification": "FAIL_CLOSED" if fail_reasons else "PASS",
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "artifacts": artifacts,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        bundle["sandbox_patch_validation_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": str(bundle.get("classification", "UNKNOWN")),
                "fail_closed_reasons": sorted(set(fail_reasons)),
                "artifact_fingerprints": {
                    key: str(_as_dict(val).get("deterministic_fingerprint", ""))
                    for key, val in sorted(artifacts.items())
                    if isinstance(val, dict)
                },
            }
        )
        return SandboxPatchValidationResult(validation_bundle=bundle)


class SandboxPatchValidationRegistry:
    """Persistence for sandbox patch validation artifacts."""

    def __init__(self, *, cognition_registry_path: str | Path, output_dir: str | Path):
        self._registry = AURACognitionRegistry(cognition_registry_path)
        self._output_dir = Path(output_dir)

    def _artifact_paths(self) -> dict[str, Path]:
        return {
            "sandbox_workspace_manifest": self._output_dir / "sandbox_workspace_manifest.json",
            "applied_patch_lineage": self._output_dir / "applied_patch_lineage.json",
            "patch_application_trace": self._output_dir / "patch_application_trace.json",
            "subsystem_build_validation": self._output_dir / "subsystem_build_validation.json",
            "object_rebuild_lineage": self._output_dir / "object_rebuild_lineage.json",
            "modpost_validation_report": self._output_dir / "modpost_validation_report.json",
            "linker_closure_report": self._output_dir / "linker_closure_report.json",
            "symbol_regression_report": self._output_dir / "symbol_regression_report.json",
            "build_fingerprint_diff": self._output_dir / "build_fingerprint_diff.json",
            "transformation_equivalence_report": self._output_dir / "transformation_equivalence_report.json",
            "runtime_promotion_eligibility": self._output_dir / "runtime_promotion_eligibility.json",
            "rollback_lineage_report": self._output_dir / "rollback_lineage_report.json",
            "deterministic_patch_validation_replay": self._output_dir / "deterministic_patch_validation_replay.json",
            "runtime_sensitive_patch_impact": self._output_dir / "runtime_sensitive_patch_impact.json",
            "sandbox_patch_validation_summary": self._output_dir / "sandbox_patch_validation_summary.json",
            "governance_patch_validation_decision": self._output_dir / "governance_patch_validation_decision.json",
            "build_confidence_report": self._output_dir / "build_confidence_report.json",
            "unresolved_dependency_report": self._output_dir / "unresolved_dependency_report.json",
        }

    def persist(self, bundle: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(bundle)
        artifacts = _as_dict(payload.get("artifacts"))
        lineage_id = str(payload.get("lineage_id", "")).strip() or stable_fingerprint(payload)
        paths = self._artifact_paths()

        for key in paths:
            _save_json(paths[key], _as_dict(artifacts.get(key)))

        registry = self._registry.load()
        state = _as_dict(registry.get("sandbox_patch_validation"))
        history = [row for row in _as_list(state.get("history")) if isinstance(row, dict)]
        entry = {
            "lineage_id": lineage_id,
            "recorded_at": _utc_now_iso(),
            "target_id": str(payload.get("target_id", "")),
            "session_id": str(payload.get("session_id", "")),
            "classification": str(payload.get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(payload.get("fail_closed_reasons")) if str(v).strip()],
            "sandbox_patch_validation_fingerprint": str(payload.get("sandbox_patch_validation_fingerprint", "")),
            "artifact_paths": {name: str(path.resolve()) for name, path in paths.items()},
            "runtime_promotion_eligible": bool(_as_dict(_as_dict(artifacts.get("runtime_promotion_eligibility"))).get("eligible", False)),
            "confidence_score": _to_float(_as_dict(_as_dict(artifacts.get("build_confidence_report"))).get("confidence_score"), 0.0),
        }
        history.append(entry)
        history = history[-8000:]

        registry["sandbox_patch_validation"] = {
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
                "type": "sandbox_patch_validation",
                "recorded_at": _utc_now_iso(),
                "sandbox_patch_validation_fingerprint": str(payload.get("sandbox_patch_validation_fingerprint", "")),
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
            "sandbox_patch_validation_fingerprint": entry["sandbox_patch_validation_fingerprint"],
            "artifact_paths": entry["artifact_paths"],
            "runtime_promotion_eligible": entry["runtime_promotion_eligible"],
            "confidence_score": entry["confidence_score"],
        }

    def replay(self, *, lineage_id: str | None = None) -> dict[str, Any]:
        registry = self._registry.load()
        state = _as_dict(registry.get("sandbox_patch_validation"))
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
            "replay_type": "sandbox_patch_validation",
            "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
            "session_id": str(_as_dict(selected).get("session_id", "")),
            "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
            "fail_closed_reasons": [str(v) for v in _as_list(_as_dict(selected).get("fail_closed_reasons")) if str(v).strip()],
            "sandbox_patch_validation_fingerprint": str(
                _as_dict(selected).get("sandbox_patch_validation_fingerprint", "")
            ),
            "runtime_promotion_eligible": bool(_as_dict(selected).get("runtime_promotion_eligible", False)),
            "confidence_score": _to_float(_as_dict(selected).get("confidence_score"), 0.0),
            "artifact_paths": _as_dict(selected).get("artifact_paths", {}),
            "deterministic_replay_fingerprint": stable_fingerprint(
                {
                    "lineage_id": str(_as_dict(selected).get("lineage_id", "")),
                    "session_id": str(_as_dict(selected).get("session_id", "")),
                    "classification": str(_as_dict(selected).get("classification", "UNKNOWN")),
                    "sandbox_patch_validation_fingerprint": str(
                        _as_dict(selected).get("sandbox_patch_validation_fingerprint", "")
                    ),
                }
            ),
            "replayed_at": _utc_now_iso(),
        }
        return replay_payload

