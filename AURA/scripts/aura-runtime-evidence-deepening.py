#!/usr/bin/env python3
"""P1.5 runtime evidence deepening on top of existing fail-closed AURA runtime truth framework.

Scope:
- audit current stable modules/parsers/assumptions/gaps
- expand direct runtime evidence capture (DAPM, PCM lifecycle, hw_params, FE/BE, SoundWire)
- add deterministic timing intelligence and strict fail-closed governance scoring

No architecture/orchestration redesign is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


VOLATILE_KEYS = {
    "generated_at",
    "started_at",
    "finished_at",
    "timestamp",
    "deterministic_fingerprint",
    "runtime_fingerprint",
}


@dataclass(frozen=True)
class TraceRow:
    command: str
    stdout: str
    stderr: str
    exit_code: int
    execution_status: str
    started_at: str
    finished_at: str
    response_path: str
    request_id: str
    phase: str


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_workspace_path(path: Path) -> Path:
    text = str(path)
    if path.exists():
        return path
    local_prefix = "/local/mnt/workspace/AURA_V1"
    workspace_prefix = "/workspace"
    if text.startswith(local_prefix):
        candidate = Path(workspace_prefix + text[len(local_prefix):])
        if candidate.exists():
            return candidate
    if text.startswith(workspace_prefix):
        candidate = Path(local_prefix + text[len(workspace_prefix):])
        if candidate.exists():
            return candidate
    return path


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(path: Path) -> dict[str, Any]:
    raw = _read_text(path)
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _trim_lines(text: str, limit: int = 12000) -> list[str]:
    return [line.rstrip("\n") for line in text.replace("\r", "").splitlines()[:limit] if line.strip()]


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _sanitize_ls_entries(text: str) -> list[str]:
    entries: list[str] = []
    for line in _trim_lines(text, limit=5000):
        chunks = [chunk.strip() for chunk in re.split(r"\s+", line.strip()) if chunk.strip()]
        multi_column = len(chunks) > 1
        for token in chunks:
            if not re.fullmatch(r"[A-Za-z0-9:._-]+", token):
                continue
            if token.isdigit():
                continue
            if multi_column and not re.search(r"[-._:]", token):
                continue
            entries.append(token)
    return sorted(set(entries))


def _to_epoch(ts: str) -> float:
    text = str(ts or "").strip()
    if not text:
        return 0.0
    match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$",
        text,
    )
    if match:
        base = str(match.group(1))
        frac = str(match.group(2) or "")
        tz = str(match.group(3) or "Z")
        frac = (frac[:6]).ljust(6, "0") if frac else ""
        if tz == "Z":
            tz = "+00:00"
        elif re.fullmatch(r"[+-]\d{4}", tz):
            tz = tz[:3] + ":" + tz[3:]
        try:
            if frac:
                return datetime.fromisoformat(f"{base}.{frac}{tz}").timestamp()
            return datetime.fromisoformat(f"{base}{tz}").timestamp()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _canonical_without_volatile(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _canonical_without_volatile(v)
            for k, v in sorted(value.items())
            if k not in VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_canonical_without_volatile(v) for v in value]
    return value


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(_canonical_without_volatile(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_subprocess(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _run_bridge_submit(
    *,
    submit_script: Path,
    bridge_root: Path,
    output_dir: Path,
    commands: list[str],
    timeout_seconds: int,
    execution_mode: str,
    allow_write_ops: bool,
    phase: str,
) -> dict[str, Any]:
    if not commands:
        return {
            "phase": phase,
            "return_code": 0,
            "summary": {
                "classification": "SKIPPED",
                "reason": "no_commands",
            },
            "response": {},
            "commands": [],
        }

    cmd = [
        "bash",
        str(submit_script),
        "--bridge-root",
        str(bridge_root),
        "--output-dir",
        str(output_dir),
        "--timeout-seconds",
        str(timeout_seconds),
        "--execution-mode",
        execution_mode,
    ]
    if allow_write_ops:
        cmd.append("--allow-write-ops")
    for command in commands:
        cmd.extend(["--command", command])

    rc, stdout, stderr = _run_subprocess(cmd, timeout=max(360, timeout_seconds + 180))
    if stdout:
        try:
            summary = json.loads(stdout)
        except json.JSONDecodeError:
            summary = {
                "classification": "INVALID",
                "reason": "submit_non_json_stdout",
                "raw_stdout": stdout,
                "raw_stderr": stderr,
            }
    else:
        summary = {
            "classification": "INVALID",
            "reason": "submit_empty_stdout",
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }

    response = _read_json(Path(str(_as_dict(summary).get("response", ""))))
    return {
        "phase": phase,
        "return_code": rc,
        "summary": summary,
        "response": response,
        "commands": list(commands),
        "execution_mode": execution_mode,
        "allow_write_ops": allow_write_ops,
    }


def _chunked_submit(
    *,
    submit_script: Path,
    bridge_root: Path,
    output_dir: Path,
    commands: list[str],
    timeout_seconds: int,
    chunk_size: int,
    phase_prefix: str,
) -> list[dict[str, Any]]:
    phases: list[dict[str, Any]] = []
    for idx in range(0, len(commands), chunk_size):
        batch = commands[idx : idx + chunk_size]
        phase = _run_bridge_submit(
            submit_script=submit_script,
            bridge_root=bridge_root,
            output_dir=output_dir,
            commands=batch,
            timeout_seconds=timeout_seconds,
            execution_mode="governed_read_only",
            allow_write_ops=False,
            phase=f"{phase_prefix}_{(idx // chunk_size) + 1}",
        )
        phases.append(phase)
    return phases


def _extract_trace_rows(response: Mapping[str, Any], *, response_path: str, phase: str) -> list[TraceRow]:
    rows: list[TraceRow] = []
    request_id = str(_as_dict(response).get("request_id", ""))
    for item in _as_list(_as_dict(response).get("executor_command_trace")):
        row = _as_dict(item)
        rows.append(
            TraceRow(
                command=str(row.get("normalized_command", "")).strip(),
                stdout=str(row.get("stdout", "")),
                stderr=str(row.get("stderr", "")),
                exit_code=_to_int(row.get("exit_code"), default=-1),
                execution_status=str(row.get("execution_status", "")),
                started_at=str(row.get("started_at", "")),
                finished_at=str(row.get("finished_at", "")),
                response_path=response_path,
                request_id=request_id,
                phase=phase,
            )
        )
    return rows


def _collect_rows_from_phases(phases: Iterable[Mapping[str, Any]]) -> list[TraceRow]:
    rows: list[TraceRow] = []
    for phase in phases:
        summary = _as_dict(phase).get("summary")
        response_path = str(_as_dict(summary).get("response", ""))
        phase_name = str(_as_dict(phase).get("phase", ""))
        response = _as_dict(_as_dict(phase).get("response"))
        rows.extend(_extract_trace_rows(response, response_path=response_path, phase=phase_name))
    return sorted(rows, key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id))


def _latest_by_command(rows: Iterable[TraceRow]) -> dict[str, TraceRow]:
    latest: dict[str, TraceRow] = {}
    for row in sorted(rows, key=lambda item: (_to_epoch(item.finished_at), item.command, item.request_id), reverse=True):
        if row.command and row.command not in latest:
            latest[row.command] = row
    return latest


def _parse_proc_pcm_rows(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"^(\d+)-(\d+):\s*(.*?)\s*:\s*(.*?)\s*:\s*(playback|capture)\s+(\d+)\s*$", re.IGNORECASE)
    for line in _trim_lines(raw, limit=4000):
        match = pattern.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "card_index": int(match.group(1)),
                "device_index": int(match.group(2)),
                "pcm_id": f"{int(match.group(1))}-{int(match.group(2))}",
                "name": match.group(3).strip(),
                "interface": match.group(4).strip(),
                "direction": match.group(5).strip().lower(),
                "substreams": int(match.group(6)),
            }
        )
    return sorted(rows, key=lambda row: (int(row["card_index"]), int(row["device_index"]), str(row["direction"])))


def _parse_proc_cards(raw: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*(\d+)\s+\[(.+?)\s*\]:\s*(.+)$")
    for line in _trim_lines(raw, limit=4000):
        match = pattern.match(line)
        if not match:
            continue
        rows.append(
            {
                "card_index": int(match.group(1)),
                "card_id": match.group(2).strip(),
                "descriptor": match.group(3).strip(),
            }
        )
    return sorted(rows, key=lambda row: int(row["card_index"]))


def _parse_interrupt_rows(raw: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in _trim_lines(raw, limit=8000):
        text = line.strip()
        if not text or text.startswith("CPU"):
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", text)
        if not match:
            continue
        irq_id = match.group(1)
        tokens = match.group(2).split()
        counts: list[int] = []
        idx = 0
        while idx < len(tokens) and tokens[idx].isdigit():
            counts.append(int(tokens[idx]))
            idx += 1
        rows[irq_id] = {
            "irq_id": irq_id,
            "total": int(sum(counts)),
            "label": " ".join(tokens[idx:]).strip(),
        }
    return rows


def _irq_delta(before: str, after: str) -> dict[str, Any]:
    b_rows = _parse_interrupt_rows(before)
    a_rows = _parse_interrupt_rows(after)
    audio_tokens = ("snd", "audio", "wcd", "swr", "soundwire", "lpass", "adsp", "q6", "mi2s")
    delta_rows: list[dict[str, Any]] = []
    for irq_id in sorted(set(b_rows.keys()) | set(a_rows.keys())):
        b = _as_dict(b_rows.get(irq_id))
        a = _as_dict(a_rows.get(irq_id))
        b_total = int(b.get("total", 0))
        a_total = int(a.get("total", 0))
        diff = a_total - b_total
        if diff == 0:
            continue
        label = str(a.get("label", b.get("label", "")))
        lowered = f"{irq_id} {label}".lower()
        delta_rows.append(
            {
                "irq_id": irq_id,
                "before_total": b_total,
                "after_total": a_total,
                "delta": diff,
                "label": label,
                "audio_related": any(token in lowered for token in audio_tokens),
            }
        )
    audio_rows = [row for row in delta_rows if bool(row.get("audio_related", False))]
    return {
        "rows": delta_rows,
        "audio_rows": audio_rows,
        "audio_delta_count": len(audio_rows),
        "irq_active": bool(audio_rows),
    }


def _parse_dapm_line(line: str) -> dict[str, Any]:
    text = str(line).strip()
    if not text:
        return {}

    name = text
    if ":" in text:
        name = text.split(":", 1)[0].strip()

    lowered = text.lower()
    status = "UNKNOWN"
    if "[on]" in lowered or re.search(r"\bon\b", lowered):
        status = "ON"
    elif "[off]" in lowered or re.search(r"\boff\b", lowered):
        status = "OFF"

    in_count = -1
    out_count = -1
    in_match = re.search(r"\bin\s+(\d+)\b", lowered)
    out_match = re.search(r"\bout\s+(\d+)\b", lowered)
    if in_match:
        in_count = int(in_match.group(1))
    if out_match:
        out_count = int(out_match.group(1))

    widget_type = ""
    wt_match = re.search(r"widget-type\s+([A-Za-z0-9._-]+)", text)
    if wt_match:
        widget_type = wt_match.group(1)

    name = re.sub(r"\[(?:on|off)\]", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\b(?:on|off)\b", "", name, flags=re.IGNORECASE).strip()

    if not name:
        return {}
    return {
        "widget": name,
        "status": status,
        "in_count": in_count,
        "out_count": out_count,
        "widget_type": widget_type,
        "raw": text,
    }


def _parse_dapm_snapshot(raw: str) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for line in _trim_lines(raw, limit=20000):
        parsed = _parse_dapm_line(line)
        if not parsed:
            continue
        state[str(parsed["widget"])] = parsed
    return state


def _parse_substream_status(raw: str) -> dict[str, Any]:
    out: dict[str, Any] = {"state": "", "owner_pid": "", "trigger_tstamp": ""}
    for line in _trim_lines(raw, limit=1200):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        k = key.strip().lower().replace(" ", "_")
        v = value.strip()
        if k in {"state", "owner_pid", "trigger_tstamp", "appl_ptr", "hw_ptr", "avail", "avail_max", "delay"}:
            out[k] = v
    return out


def _parse_hw_params(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        return {"status": "MISSING"}
    if text.lower() == "closed":
        return {"status": "CLOSED"}

    kv: dict[str, str] = {}
    for line in _trim_lines(text, limit=1200):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().upper()
        value = value.strip()
        if key:
            kv[key] = value

    def _interval(s: str) -> dict[str, int]:
        match = re.search(r"[\[(]\s*([0-9]+)\s+([0-9]+)\s*[\])]", s)
        if match:
            return {"min": int(match.group(1)), "max": int(match.group(2))}
        vals = [int(v) for v in re.findall(r"\b([0-9]+)\b", s)]
        if len(vals) == 1:
            return {"min": vals[0], "max": vals[0]}
        if len(vals) >= 2:
            return {"min": min(vals), "max": max(vals)}
        return {}

    return {
        "status": "AVAILABLE",
        "channels": _interval(kv.get("CHANNELS", "")),
        "rates": _interval(kv.get("RATE", "")),
        "formats": sorted(set(kv.get("FORMAT", "").replace(",", " ").split())),
        "raw_keys": sorted(kv.keys()),
    }


def _parse_soundwire_rows(rows: Iterable[TraceRow]) -> dict[str, Any]:
    masters: set[str] = set()
    debugfs_entries: dict[str, list[str]] = {}
    endpoint_files: list[dict[str, Any]] = []
    bus_devices: set[str] = set()

    for row in rows:
        cmd = row.command
        if cmd == "ls /sys/kernel/debug/soundwire":
            masters.update(_sanitize_ls_entries(row.stdout))
        elif cmd.startswith("ls /sys/kernel/debug/soundwire/"):
            master = cmd.split("/sys/kernel/debug/soundwire/", 1)[1]
            debugfs_entries[master] = _sanitize_ls_entries(row.stdout)
        elif cmd.startswith("cat /sys/kernel/debug/soundwire/"):
            rel = cmd.split("cat /sys/kernel/debug/soundwire/", 1)[1]
            if "/" in rel:
                master, name = rel.split("/", 1)
                endpoint_files.append(
                    {
                        "master": master,
                        "name": name,
                        "status": row.execution_status,
                        "exit_code": row.exit_code,
                        "stdout_sample": _trim_lines(row.stdout, limit=20),
                    }
                )
        elif cmd == "ls /sys/bus/soundwire/devices":
            bus_devices.update(_sanitize_ls_entries(row.stdout))
        elif cmd.startswith("cat /sys/bus/soundwire/devices/"):
            rel = cmd.split("cat /sys/bus/soundwire/devices/", 1)[1]
            parts = rel.split("/")
            if len(parts) == 2:
                bus_devices.add(parts[0])

    active_endpoints = [
        item
        for item in endpoint_files
        if any(token in "\n".join(item.get("stdout_sample", [])).lower() for token in ("active", "enable", "on", "attached", "up"))
    ]
    return {
        "masters": sorted(masters),
        "debugfs_entries": {k: sorted(v) for k, v in sorted(debugfs_entries.items())},
        "bus_devices": sorted(bus_devices),
        "endpoint_files": sorted(endpoint_files, key=lambda item: (str(item.get("master", "")), str(item.get("name", "")))),
        "active_endpoint_count": len(active_endpoints),
        "active_endpoints": active_endpoints[:80],
    }


def _classify_fe_be(pcm_rows: list[dict[str, Any]], dapm_widgets: list[str]) -> dict[str, Any]:
    fe_rows: list[dict[str, Any]] = []
    be_rows: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []

    for row in pcm_rows:
        name = str(row.get("name", ""))
        iface = str(row.get("interface", ""))
        text = f"{name} {iface}".lower()
        roles: set[str] = set()
        if any(token in text for token in ("multimedia", "frontend", "fe", "hostless", "voip")):
            roles.add("frontend")
        if any(token in text for token in ("backend", "be", "wsa", "rx_macro", "tx_macro", "mi2s", "slim", "swr", "soundwire", "aif")):
            roles.add("backend")
        if not roles:
            roles.add("unknown")

        mapped = {
            "pcm_id": str(row.get("pcm_id", "")),
            "card_index": int(row.get("card_index", -1)),
            "device_index": int(row.get("device_index", -1)),
            "direction": str(row.get("direction", "")),
            "name": name,
            "interface": iface,
            "roles": sorted(roles),
        }
        if "frontend" in roles:
            fe_rows.append(mapped)
        if "backend" in roles:
            be_rows.append(mapped)

    widget_lower = [w.lower() for w in dapm_widgets]
    for fe in fe_rows:
        f_tokens = [tok for tok in re.findall(r"[a-z0-9_]+", f"{fe.get('name', '')} {fe.get('interface', '')}".lower()) if len(tok) > 2]
        for be in be_rows:
            b_tokens = [tok for tok in re.findall(r"[a-z0-9_]+", f"{be.get('name', '')} {be.get('interface', '')}".lower()) if len(tok) > 2]
            shared = sorted(set(f_tokens).intersection(b_tokens))
            widget_hits = 0
            for tok in set((f_tokens + b_tokens)[:12]):
                widget_hits += sum(1 for lw in widget_lower if tok in lw)
            if shared or widget_hits > 0:
                links.append(
                    {
                        "frontend_pcm_id": str(fe.get("pcm_id", "")),
                        "backend_pcm_id": str(be.get("pcm_id", "")),
                        "shared_tokens": shared[:20],
                        "widget_hit_count": int(widget_hits),
                    }
                )

    return {
        "frontend_candidates": sorted(fe_rows, key=lambda row: str(row.get("pcm_id", ""))),
        "backend_candidates": sorted(be_rows, key=lambda row: str(row.get("pcm_id", ""))),
        "fe_be_links": sorted(links, key=lambda row: (str(row.get("frontend_pcm_id", "")), str(row.get("backend_pcm_id", ""))))[:600],
    }


def _module_audit(scripts_dir: Path, repo_root: Path) -> dict[str, Any]:
    modules = [
        ("runtime_launcher", scripts_dir / "aura_runtime_launcher.sh"),
        ("bridge_worker", scripts_dir / "windows-bridge-worker.ps1"),
        ("container_runtime", scripts_dir / "aura_container_exec.sh"),
        ("orchestration_flow", scripts_dir / "aura-golden-playback-capture.py"),
        ("governance_engine", scripts_dir / "aura-runtime-governance.py"),
        ("replay_engine", scripts_dir / "aura-runtime-equivalence.py"),
        ("certification_engine", scripts_dir / "aura-runtime-truth-consolidation.py"),
        ("playback_semantic_intelligence", scripts_dir / "aura-playback-semantic-intelligence.py"),
        ("evidence_ingestion_pipeline", scripts_dir / "aura-runtime-evidence-ingestion.py"),
        ("alsa_reasoning_layer", scripts_dir / "aura-playback-semantic-intelligence.py"),
    ]

    rows: list[dict[str, Any]] = []
    for name, path in modules:
        text = _read_text(path)
        exists = path.exists()
        has_stable_fp = "stable_fingerprint(" in text
        has_sorted = "sorted(" in text or "sort_keys=True" in text
        has_fail_closed = "FAIL_CLOSED" in text or "fail_closed" in text.lower()
        has_fallback = "fallback" in text.lower() or "heuristic" in text.lower()

        git_state = "unknown"
        try:
            rc, stdout, _ = _run_subprocess(["git", "-C", str(repo_root), "status", "--porcelain", "--", str(path)], timeout=30)
            if rc == 0:
                git_state = "modified_or_untracked" if stdout.strip() else "clean"
        except Exception:
            git_state = "unknown"

        if not exists:
            stability = "missing"
            architecture_status = "missing"
            deterministic_status = "unknown"
            blockers = ["module_file_missing"]
        else:
            architecture_status = "present"
            deterministic_status = "deterministic_controls_present" if has_stable_fp and has_sorted else "partial_determinism"
            if has_stable_fp and has_sorted and has_fail_closed and not has_fallback:
                stability = "production_stable"
            elif has_stable_fp and has_sorted:
                stability = "stable_with_heuristics"
            else:
                stability = "experimental"
            blockers = []
            if not has_fail_closed:
                blockers.append("fail_closed_marker_not_detected")
            if has_fallback:
                blockers.append("fallback_or_heuristic_paths_present")

        rows.append(
            {
                "module": name,
                "file": str(path),
                "architecture_status": architecture_status,
                "stability_level": stability,
                "merged_pushed_status": git_state,
                "deterministic_status": deterministic_status,
                "known_blockers": blockers,
                "redesign_risk_level": "low" if stability.startswith("production") else "medium" if stability.startswith("stable") else "high",
            }
        )

    return {
        "artifact_name": "P15_FOUNDATION_AUDIT",
        "generated_at": _utc_now_iso(),
        "modules": rows,
        "summary": {
            "module_count": len(rows),
            "production_stable": len([r for r in rows if str(r.get("stability_level", "")) == "production_stable"]),
            "stable_with_heuristics": len([r for r in rows if str(r.get("stability_level", "")) == "stable_with_heuristics"]),
            "experimental_or_missing": len([r for r in rows if str(r.get("stability_level", "")) in {"experimental", "missing"}]),
        },
    }


def _reusable_parsers(scripts_dir: Path) -> dict[str, Any]:
    parser_files = [
        scripts_dir / "aura-runtime-evidence-ingestion.py",
        scripts_dir / "aura-golden-playback-capture.py",
        scripts_dir / "aura-playback-semantic-intelligence.py",
        scripts_dir / "aura-runtime-truth-consolidation.py",
    ]
    rows: list[dict[str, Any]] = []
    for path in parser_files:
        text = _read_text(path)
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            match = re.match(r"^def\s+(_parse_[A-Za-z0-9_]+)\s*\(", line.strip())
            if not match:
                continue
            name = match.group(1)
            category = "generic"
            lname = name.lower()
            if "dapm" in lname:
                category = "dapm"
            elif "irq" in lname or "interrupt" in lname:
                category = "irq"
            elif "pcm" in lname:
                category = "pcm"
            elif "soundwire" in lname or "swr" in lname:
                category = "soundwire"
            elif "amixer" in lname or "tinymix" in lname or "mixer" in lname:
                category = "mixer"
            rows.append(
                {
                    "parser": name,
                    "category": category,
                    "file": str(path),
                    "line": idx,
                }
            )

    return {
        "artifact_name": "P15_REUSABLE_RUNTIME_PARSERS",
        "generated_at": _utc_now_iso(),
        "parsers": sorted(rows, key=lambda row: (str(row.get("category", "")), str(row.get("parser", "")), str(row.get("file", "")))),
        "summary": {
            "parser_count": len(rows),
            "categories": sorted(set(str(row.get("category", "")) for row in rows)),
        },
    }


def _brittle_assumptions(scripts_dir: Path) -> dict[str, Any]:
    files = [
        scripts_dir / "aura-golden-playback-capture.py",
        scripts_dir / "aura-playback-semantic-intelligence.py",
        scripts_dir / "aura-runtime-truth-consolidation.py",
        scripts_dir / "linux-bridge-submit.sh",
        scripts_dir / "windows-bridge-worker.ps1",
    ]
    patterns = {
        "board_specific_token": r"\b(rb3|rb3gen2|qcs6490|shikra)\b",
        "hardcoded_pcm": r"\b(?:plughw|hw):\d+,\d+\b",
        "fixed_card_index": r"\bcard0\b|\b-c\s*0\b",
        "wildcard_dapm_only": r"/sys/kernel/debug/asoc/\*/dapm",
        "fallback_heuristic_path": r"\bfallback\b|\bheuristic\b|inferred_dapm_converged",
    }

    findings: list[dict[str, Any]] = []
    for path in files:
        text = _read_text(path)
        if not text:
            continue
        for idx, line in enumerate(text.splitlines(), start=1):
            for category, pattern in patterns.items():
                if re.search(pattern, line, flags=re.IGNORECASE):
                    findings.append(
                        {
                            "file": str(path),
                            "line": idx,
                            "category": category,
                            "snippet": line.strip()[:220],
                        }
                    )

    return {
        "artifact_name": "P15_BRITTLE_ASSUMPTIONS",
        "generated_at": _utc_now_iso(),
        "findings": sorted(findings, key=lambda row: (str(row.get("category", "")), str(row.get("file", "")), int(row.get("line", 0)))),
        "summary": {
            "finding_count": len(findings),
            "board_specific_count": len([f for f in findings if str(f.get("category", "")) == "board_specific_token"]),
            "fallback_path_count": len([f for f in findings if str(f.get("category", "")) == "fallback_heuristic_path"]),
        },
    }


def _runtime_assumption_findings(rows: list[TraceRow]) -> list[dict[str, Any]]:
    patterns: list[tuple[str, str, str]] = [
        ("hardcoded_pcm_literal", r"\b(?:hw|plughw):\d+,\d+\b", "medium"),
        ("fixed_card0_path", r"/proc/asound/card0/", "medium"),
        ("fixed_substream0_path", r"/sub0/(?:status|hw_params|info|sw_params)\b", "low"),
        ("board_token_literal", r"\b(?:qcs6490|rb3|rb3gen2|shikra)\b", "high"),
    ]
    findings: list[dict[str, Any]] = []
    for row in rows:
        command = str(row.command or "")
        if not command:
            continue
        for category, pattern, risk in patterns:
            if re.search(pattern, command, flags=re.IGNORECASE):
                findings.append(
                    {
                        "category": category,
                        "risk_level": risk,
                        "command": command,
                        "phase": row.phase,
                        "timestamp": row.finished_at,
                    }
                )
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings:
        key = (str(finding.get("category", "")), str(finding.get("command", "")))
        if key not in unique:
            unique[key] = finding
    return sorted(unique.values(), key=lambda row: (str(row.get("category", "")), str(row.get("command", ""))))


def _kernel_sensitive_logic(path: Path) -> list[dict[str, Any]]:
    text = _read_text(path)
    if not text:
        return []
    patterns: list[tuple[str, str, str]] = [
        ("debugfs_asoc_dependency", r"/sys/kernel/debug/asoc", "medium"),
        ("debugfs_soundwire_dependency", r"/sys/kernel/debug/soundwire", "medium"),
        ("soundwire_bus_dependency", r"/sys/bus/soundwire/devices", "medium"),
        ("procfs_substream_dependency", r"/proc/asound/card\d+/pcm\d+[pc]/sub\d+", "medium"),
        ("interrupts_dependency", r"/proc/interrupts", "low"),
        ("irq_label_token_heuristic", r"audio_tokens\s*=", "medium"),
    ]
    findings: list[dict[str, Any]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for category, pattern, sensitivity in patterns:
            if re.search(pattern, line):
                findings.append(
                    {
                        "category": category,
                        "line": idx,
                        "sensitivity": sensitivity,
                        "snippet": line.strip()[:220],
                    }
                )
    return sorted(findings, key=lambda row: (str(row.get("category", "")), int(row.get("line", 0))))


def _build_board_specific_assumptions(
    *,
    scripts_dir: Path,
    brittle_assumptions: Mapping[str, Any],
    reusable_parsers: Mapping[str, Any],
    combined_rows: list[TraceRow],
) -> dict[str, Any]:
    code_findings = [
        _as_dict(item)
        for item in _as_list(_as_dict(brittle_assumptions).get("findings"))
        if str(_as_dict(item).get("category", "")) in {"board_specific_token", "hardcoded_pcm", "fixed_card_index", "wildcard_dapm_only"}
    ]
    runtime_findings = _runtime_assumption_findings(combined_rows)
    kernel_sensitive = _kernel_sensitive_logic(scripts_dir / "aura-runtime-evidence-deepening.py")

    parser_rows = [_as_dict(item) for item in _as_list(_as_dict(reusable_parsers).get("parsers"))]
    parser_categories: dict[str, int] = {}
    for row in parser_rows:
        category = str(row.get("category", "generic"))
        parser_categories[category] = int(parser_categories.get(category, 0)) + 1

    code_category_count = len(set(str(_as_dict(item).get("category", "")) for item in code_findings))
    runtime_category_count = len(set(str(_as_dict(item).get("category", "")) for item in runtime_findings))
    kernel_category_count = len(set(str(_as_dict(item).get("category", "")) for item in kernel_sensitive))

    code_risk_units = code_category_count * 6 + min(len(code_findings), 12)
    runtime_risk_units = runtime_category_count * 4 + min(len(runtime_findings), 12)
    kernel_risk_units = kernel_category_count * 3
    total_risk_units = code_risk_units + runtime_risk_units + kernel_risk_units
    portability_score = round(max(0.0, 1.0 - min(1.0, total_risk_units / 100.0)), 3)
    classification = (
        "LOW_RISK"
        if portability_score >= 0.8
        else "MEDIUM_RISK"
        if portability_score >= 0.6
        else "HIGH_RISK"
    )

    payload = {
        "artifact_name": "BOARD_SPECIFIC_ASSUMPTIONS",
        "generated_at": _utc_now_iso(),
        "classification": classification,
        "portability_score": portability_score,
        "code_level_assumptions": code_findings[:2000],
        "runtime_level_assumptions": runtime_findings[:2000],
        "kernel_version_sensitive_logic": kernel_sensitive[:1200],
        "generalized_parser_coverage": {
            "parser_total": len(parser_rows),
            "categories": dict(sorted(parser_categories.items())),
        },
        "summary": {
            "code_assumption_count": len(code_findings),
            "runtime_assumption_count": len(runtime_findings),
            "kernel_sensitive_count": len(kernel_sensitive),
            "code_category_count": code_category_count,
            "runtime_category_count": runtime_category_count,
            "kernel_category_count": kernel_category_count,
            "risk_units": total_risk_units,
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _capability_confidence(
    *,
    command_count: int,
    executed_count: int,
    nonempty_count: int,
    timeout_count: int,
    failed_count: int,
) -> str:
    if command_count <= 0:
        return "NONE"
    if executed_count <= 0:
        return "LOW"
    if nonempty_count > 0 and timeout_count == 0 and failed_count == 0:
        return "HIGH"
    if nonempty_count > 0:
        return "MEDIUM"
    return "LOW"


def _capability_entry(
    *,
    source_id: str,
    rows: list[TraceRow],
    command_filter: Callable[[str], bool],
    parse_signal: Callable[[TraceRow], bool] | None = None,
    direct_default: bool = True,
) -> dict[str, Any]:
    matched = [row for row in rows if command_filter(row.command)]
    executed = [row for row in matched if row.execution_status == "executed" and int(row.exit_code) == 0]
    failed = [row for row in matched if row.execution_status == "failed" or int(row.exit_code) != 0]
    timeouts = [row for row in matched if row.execution_status == "timeout"]
    nonempty = [row for row in executed if str(row.stdout).strip()]
    parse_hits = [row for row in executed if parse_signal(row)] if parse_signal else []
    signal_detected = bool(parse_hits) if parse_signal else bool(nonempty)
    confidence = _capability_confidence(
        command_count=len(matched),
        executed_count=len(executed),
        nonempty_count=len(nonempty),
        timeout_count=len(timeouts),
        failed_count=len(failed),
    )
    reproducibility_quality = (
        "high"
        if len(executed) >= 2 and len(timeouts) == 0
        else "medium"
        if len(executed) >= 1
        else "low"
        if len(matched) >= 1
        else "none"
    )
    determinism_quality = (
        "high"
        if len(nonempty) >= 2
        else "medium"
        if len(nonempty) >= 1
        else "low"
        if len(matched) >= 1
        else "none"
    )
    return {
        "source_id": source_id,
        "available": bool(executed),
        "direct_evidence": bool(signal_detected and direct_default),
        "confidence_level": confidence,
        "reproducibility_quality": reproducibility_quality,
        "determinism_quality": determinism_quality,
        "command_count": len(matched),
        "executed_count": len(executed),
        "failed_count": len(failed),
        "timeout_count": len(timeouts),
        "nonempty_stdout_count": len(nonempty),
        "signal_detected": signal_detected,
        "sample_commands": sorted(set(row.command for row in matched))[:8],
    }


def _build_runtime_capability_matrix(
    *,
    combined_rows: list[TraceRow],
    pcm_rows: list[dict[str, Any]],
    fe_be_map: Mapping[str, Any],
    soundwire_runtime_activation: Mapping[str, Any],
    temporal_signal_index: Mapping[str, Any],
) -> dict[str, Any]:
    capability_rows: list[dict[str, Any]] = [
        _capability_entry(
            source_id="proc_asound_cards",
            rows=combined_rows,
            command_filter=lambda c: c == "cat /proc/asound/cards",
        ),
        _capability_entry(
            source_id="proc_asound_pcm",
            rows=combined_rows,
            command_filter=lambda c: c == "cat /proc/asound/pcm",
            parse_signal=lambda row: len(_parse_proc_pcm_rows(row.stdout)) > 0,
        ),
        _capability_entry(
            source_id="pcm_substream_status",
            rows=combined_rows,
            command_filter=lambda c: c.endswith("/status") and "/proc/asound/card" in c,
            parse_signal=lambda row: bool(str(_parse_substream_status(row.stdout).get("state", "")).strip()),
        ),
        _capability_entry(
            source_id="pcm_substream_hw_params",
            rows=combined_rows,
            command_filter=lambda c: c.endswith("/hw_params") and "/proc/asound/card" in c,
            parse_signal=lambda row: str(_parse_hw_params(row.stdout).get("status", "")) in {"AVAILABLE", "CLOSED"},
        ),
        _capability_entry(
            source_id="playback_stream_metadata",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("AURA_PLAYBACK_APLAY "),
            parse_signal=lambda row: bool(_parse_aplay_stream_line(f"{row.stdout}\n{row.stderr}").get("observed", False)),
        ),
        _capability_entry(
            source_id="irq_interrupts",
            rows=combined_rows,
            command_filter=lambda c: c == "head -n 200 /proc/interrupts",
            parse_signal=lambda row: len(_parse_interrupt_rows(row.stdout)) > 0,
        ),
        _capability_entry(
            source_id="dapm_debugfs",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in c,
            parse_signal=lambda row: len(_parse_dapm_snapshot(row.stdout)) > 0,
        ),
        _capability_entry(
            source_id="codec_debugfs",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and c.endswith("/codecs"),
        ),
        _capability_entry(
            source_id="dai_links_debugfs",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and c.endswith("/dai_links"),
        ),
        _capability_entry(
            source_id="amixer_cli",
            rows=combined_rows,
            command_filter=lambda c: c == "amixer",
        ),
        _capability_entry(
            source_id="tinymix_cli",
            rows=combined_rows,
            command_filter=lambda c: c == "tinymix",
        ),
        _capability_entry(
            source_id="soundwire_debugfs",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("ls /sys/kernel/debug/soundwire") or c.startswith("cat /sys/kernel/debug/soundwire/"),
        ),
        _capability_entry(
            source_id="soundwire_bus",
            rows=combined_rows,
            command_filter=lambda c: c.startswith("ls /sys/bus/soundwire/devices") or c.startswith("cat /sys/bus/soundwire/devices/"),
        ),
        _capability_entry(
            source_id="dmesg_tail",
            rows=combined_rows,
            command_filter=lambda c: c == "dmesg | tail -200" or c == "dmesg",
        ),
    ]

    slimbus_detected = any(
        "slim" in f"{row.command}\n{row.stdout}\n{row.stderr}".lower()
        for row in combined_rows
    )
    capability_rows.append(
        {
            "source_id": "slimbus_indicator",
            "available": bool(slimbus_detected),
            "direct_evidence": bool(slimbus_detected),
            "confidence_level": "MEDIUM" if slimbus_detected else "NONE",
            "reproducibility_quality": "medium" if slimbus_detected else "none",
            "determinism_quality": "medium" if slimbus_detected else "none",
            "command_count": 0,
            "executed_count": 0,
            "failed_count": 0,
            "timeout_count": 0,
            "nonempty_stdout_count": 0,
            "signal_detected": bool(slimbus_detected),
            "sample_commands": [],
        }
    )

    capability_map = {str(row.get("source_id", "")): row for row in capability_rows}
    mandatory = {
        "proc_asound_cards",
        "proc_asound_pcm",
        "irq_interrupts",
        "dapm_debugfs",
        "playback_stream_metadata",
    }
    optional = set(capability_map.keys()) - mandatory
    mandatory_available = len([sid for sid in mandatory if bool(_as_dict(capability_map.get(sid)).get("available", False))])
    optional_available = len([sid for sid in optional if bool(_as_dict(capability_map.get(sid)).get("available", False))])
    portability_score = round(
        (mandatory_available / float(max(1, len(mandatory)))) * 0.75
        + (optional_available / float(max(1, len(optional)))) * 0.25,
        3,
    )

    payload = {
        "artifact_name": "RUNTIME_CAPABILITY_MATRIX",
        "generated_at": _utc_now_iso(),
        "capabilities": sorted(capability_rows, key=lambda row: str(row.get("source_id", ""))),
        "topology_summary": {
            "pcm_count": len(pcm_rows),
            "frontend_count": len(_as_list(_as_dict(fe_be_map).get("frontend_candidates"))),
            "backend_count": len(_as_list(_as_dict(fe_be_map).get("backend_candidates"))),
            "fe_be_link_count": len(_as_list(_as_dict(fe_be_map).get("fe_be_links"))),
        },
        "bus_summary": {
            "soundwire_master_count": len(_as_list(_as_dict(soundwire_runtime_activation).get("masters"))),
            "soundwire_bus_device_count": len(_as_list(_as_dict(soundwire_runtime_activation).get("bus_devices"))),
            "slimbus_detected": bool(slimbus_detected),
        },
        "temporal_signal_coverage": {
            key: bool(_as_dict(value).get("observed", False))
            for key, value in sorted(_as_dict(temporal_signal_index).items())
        },
        "portability_score": portability_score,
        "classification": "PORTABLE_READY" if portability_score >= 0.75 else "PORTABLE_LIMITED",
        "summary": {
            "mandatory_available": mandatory_available,
            "mandatory_total": len(mandatory),
            "optional_available": optional_available,
            "optional_total": len(optional),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_evidence_source_negotiation(
    *,
    capability_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    capability_rows = [_as_dict(item) for item in _as_list(_as_dict(capability_matrix).get("capabilities"))]
    source_by_id = {str(row.get("source_id", "")): row for row in capability_rows}
    signal_source_preferences: dict[str, list[str]] = {
        "playback_invoked": ["playback_stream_metadata"],
        "pcm_lifecycle": ["pcm_substream_status", "playback_stream_metadata"],
        "hw_params": ["pcm_substream_hw_params", "playback_stream_metadata"],
        "dapm_transition": ["dapm_debugfs"],
        "irq_correlation": ["irq_interrupts"],
        "fe_be_layout": ["proc_asound_pcm", "dai_links_debugfs"],
        "codec_discovery": ["codec_debugfs", "proc_asound_cards"],
        "bus_activity": ["soundwire_bus", "soundwire_debugfs", "slimbus_indicator"],
    }

    negotiated: list[dict[str, Any]] = []
    missing_required: list[str] = []
    required_signals = {"playback_invoked", "pcm_lifecycle", "hw_params", "dapm_transition", "irq_correlation"}
    for signal, options in sorted(signal_source_preferences.items()):
        selected = ""
        reason = "no_available_source"
        selected_confidence = "NONE"
        selected_direct = False
        for source_id in options:
            source = _as_dict(source_by_id.get(source_id))
            if not source:
                continue
            if bool(source.get("available", False)):
                selected = source_id
                selected_confidence = str(source.get("confidence_level", "NONE"))
                selected_direct = bool(source.get("direct_evidence", False))
                reason = "selected_first_available"
                break
        if not selected and signal in required_signals:
            missing_required.append(signal)
        negotiated.append(
            {
                "signal": signal,
                "options": options,
                "selected_source": selected,
                "selected_confidence_level": selected_confidence,
                "selected_direct_evidence": selected_direct,
                "status": "selected" if selected else "missing",
                "reason": reason,
                "required": signal in required_signals,
            }
        )

    confidence_points = {"HIGH": 1.0, "MEDIUM": 0.75, "LOW": 0.4, "NONE": 0.0}
    required_rows = [row for row in negotiated if bool(row.get("required", False))]
    confidence_score = round(
        sum(confidence_points.get(str(row.get("selected_confidence_level", "NONE")), 0.0) for row in required_rows)
        / float(max(1, len(required_rows))),
        3,
    )

    payload = {
        "artifact_name": "EVIDENCE_SOURCE_NEGOTIATION",
        "generated_at": _utc_now_iso(),
        "required_signals": sorted(required_signals),
        "negotiated_sources": negotiated,
        "missing_required_signals": sorted(missing_required),
        "negotiation_confidence_score": confidence_score,
        "classification": "PASS" if not missing_required else "FAIL_CLOSED",
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_adaptive_capture_strategy(
    *,
    capability_matrix: Mapping[str, Any],
    evidence_negotiation: Mapping[str, Any],
) -> dict[str, Any]:
    capability_rows = [_as_dict(item) for item in _as_list(_as_dict(capability_matrix).get("capabilities"))]
    source_by_id = {str(row.get("source_id", "")): row for row in capability_rows}
    selected_by_signal = {
        str(_as_dict(item).get("signal", "")): str(_as_dict(item).get("selected_source", ""))
        for item in _as_list(_as_dict(evidence_negotiation).get("negotiated_sources"))
    }

    amixer_available = bool(_as_dict(source_by_id.get("amixer_cli")).get("available", False))
    tinymix_available = bool(_as_dict(source_by_id.get("tinymix_cli")).get("available", False))
    soundwire_available = bool(
        _as_dict(source_by_id.get("soundwire_bus")).get("available", False)
        or _as_dict(source_by_id.get("soundwire_debugfs")).get("available", False)
    )
    slimbus_detected = bool(_as_dict(source_by_id.get("slimbus_indicator")).get("available", False))

    base_phase = [
        "cat /proc/asound/cards",
        "cat /proc/asound/pcm",
        "head -n 200 /proc/interrupts",
        "dmesg | tail -200",
    ]
    topology_phase = ["ls /sys/kernel/debug/asoc", "cat /sys/kernel/debug/asoc/<card>/dai_links", "cat /sys/kernel/debug/asoc/<card>/codecs"]
    dapm_phase = ["cat /sys/kernel/debug/asoc/<card>/dapm/*"] if selected_by_signal.get("dapm_transition") == "dapm_debugfs" else []
    pcm_phase = [
        "cat /proc/asound/card<card>/pcm<dev>p/sub0/status",
        "cat /proc/asound/card<card>/pcm<dev>p/sub0/hw_params",
    ]
    mixer_phase = ["amixer"] + (["tinymix"] if tinymix_available else [])
    bus_phase: list[str] = []
    if soundwire_available:
        bus_phase.extend(["ls /sys/bus/soundwire/devices", "cat /sys/bus/soundwire/devices/<dev>/status"])
    elif slimbus_detected:
        bus_phase.extend(["dmesg | tail -200"])

    missing_required = _as_list(_as_dict(evidence_negotiation).get("missing_required_signals"))
    fail_closed_reasons: list[str] = []
    if missing_required:
        fail_closed_reasons.append("required_signal_source_unavailable")
    if not amixer_available and not tinymix_available:
        fail_closed_reasons.append("no_mixer_cli_available")

    payload = {
        "artifact_name": "ADAPTIVE_CAPTURE_STRATEGY",
        "generated_at": _utc_now_iso(),
        "strategy_profile": (
            "ASOC_SOUNDWIRE"
            if soundwire_available
            else "ASOC_SLIMBUS"
            if slimbus_detected
            else "ASOC_GENERIC"
        ),
        "phase_plan": [
            {"phase": "baseline_capture", "commands": base_phase},
            {"phase": "topology_capture", "commands": topology_phase},
            {"phase": "dapm_capture", "commands": dapm_phase},
            {"phase": "pcm_lifecycle_capture", "commands": pcm_phase},
            {"phase": "mixer_capture", "commands": mixer_phase},
            {"phase": "bus_capture", "commands": bus_phase},
        ],
        "selected_signal_sources": selected_by_signal,
        "fallback_policies": {
            "hw_params": ["pcm_substream_hw_params", "playback_stream_metadata"],
            "pcm_lifecycle": ["pcm_substream_status", "playback_stream_metadata"],
            "bus_activity": ["soundwire_bus", "soundwire_debugfs", "slimbus_indicator"],
        },
        "fail_closed_reasons": sorted(set(fail_closed_reasons)),
        "classification": "PASS" if not fail_closed_reasons else "FAIL_CLOSED",
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


SEMANTIC_SCOPE_CLASSES = {
    "UNIVERSAL",
    "CODEC_FAMILY",
    "PLATFORM_SPECIFIC",
    "DOWNSTREAM_ONLY",
    "TEMPORAL_RUNTIME_ONLY",
    "UNKNOWN_UNSAFE",
}


def _deterministic_proof_state(*, key_seed: str, evidence_sources: list[str]) -> dict[str, Any]:
    sources = sorted(set(str(item).strip() for item in evidence_sources if str(item).strip()))
    proof_payload = {
        "key_seed": str(key_seed),
        "evidence_sources": sources,
    }
    return {
        "deterministic": True,
        "evidence_count": len(sources),
        "proof_key": stable_fingerprint(proof_payload),
    }


def _classify_semantic_scope(category: str, text: str) -> str:
    cat = str(category or "").lower()
    blob = f"{cat} {text}".lower()
    if any(token in blob for token in ("proc_asound", "interrupts_dependency", "universal")):
        return "UNIVERSAL"
    if any(token in blob for token in ("rx_cdc", "soundwire", "slim", "codec_family", "pcm0_rx", "pcm_rx")):
        return "CODEC_FAMILY"
    if any(token in blob for token in ("board_specific_token", "board_token_literal", "hardcoded_pcm", "fixed_card0", "card0")):
        return "PLATFORM_SPECIFIC"
    if any(token in blob for token in ("debugfs", "wildcard_dapm", "downstream", "kernel/debug")):
        return "DOWNSTREAM_ONLY"
    if any(token in blob for token in ("sub0", "temporal", "runtime_only", "fixed_substream0")):
        return "TEMPORAL_RUNTIME_ONLY"
    return "UNKNOWN_UNSAFE"


def _confidence_score(*, evidence_count: int, direct: bool, penalty: float = 0.0) -> float:
    base = 0.45 + min(0.35, max(0, evidence_count) * 0.07)
    if direct:
        base += 0.2
    score = max(0.0, min(1.0, base - max(0.0, penalty)))
    return round(score, 3)


def _normalize_semantic_alias(alias: str) -> dict[str, Any]:
    token = str(alias or "").strip()
    lowered = token.lower()
    if re.fullmatch(r"(?:hw|plughw):(\d+),(\d+)", lowered):
        match = re.fullmatch(r"(?:hw|plughw):(\d+),(\d+)", lowered)
        card = int(match.group(1)) if match else -1
        dev = int(match.group(2)) if match else -1
        return {
            "canonical_semantic_identity": f"ALSA_PCM_CARD{card}_DEV{dev}",
            "semantic_scope": "UNIVERSAL",
            "semantic_type": "alsa_device_alias",
            "fallback_reason": "",
        }
    if lowered in {"default", "sysdefault"}:
        return {
            "canonical_semantic_identity": "ALSA_PCM_DEFAULT_DEVICE",
            "semantic_scope": "UNIVERSAL",
            "semantic_type": "alsa_default_device",
            "fallback_reason": "",
        }
    mm = re.search(r"multimedia\s*([0-9]+)", lowered)
    if mm:
        return {
            "canonical_semantic_identity": f"PLAYBACK_FE_MULTIMEDIA_{int(mm.group(1))}",
            "semantic_scope": "PLATFORM_SPECIFIC",
            "semantic_type": "platform_fe_alias",
            "fallback_reason": "",
        }
    pcm_rx = re.search(r"pcm\s*([0-9]+)_rx", lowered)
    if pcm_rx or "rx_cdc_dma_rx" in lowered:
        idx = int(pcm_rx.group(1)) if pcm_rx else 0
        return {
            "canonical_semantic_identity": f"CODEC_RX_PATH_{idx}",
            "semantic_scope": "CODEC_FAMILY",
            "semantic_type": "codec_rx_alias",
            "fallback_reason": "",
        }
    if "speaker" in lowered and "playback" in lowered:
        return {
            "canonical_semantic_identity": "PLAYBACK_SINK_SPEAKER",
            "semantic_scope": "UNIVERSAL",
            "semantic_type": "playback_intent_alias",
            "fallback_reason": "",
        }
    if "jack" in lowered:
        return {
            "canonical_semantic_identity": "ENDPOINT_JACK",
            "semantic_scope": "UNIVERSAL",
            "semantic_type": "endpoint_alias",
            "fallback_reason": "",
        }
    sanitized = re.sub(r"[^A-Za-z0-9]+", "_", token.upper()).strip("_")
    sanitized = sanitized if sanitized else "UNKNOWN_ALIAS"
    return {
        "canonical_semantic_identity": f"UNCLASSIFIED_{sanitized}",
        "semantic_scope": "UNKNOWN_UNSAFE",
        "semantic_type": "unknown_alias",
        "fallback_reason": "unknown_alias_pattern",
    }


def _collect_semantic_alias_candidates(
    *,
    combined_rows: list[TraceRow],
    pcm_rows: list[dict[str, Any]],
    fe_be_map: Mapping[str, Any],
    direct_dapm_runtime_state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence: dict[str, set[str]] = {}

    def add(alias: str, source: str) -> None:
        key = str(alias or "").strip()
        if not key:
            return
        evidence.setdefault(key, set()).add(str(source))

    for row in combined_rows:
        command = str(row.command or "")
        if command.startswith("AURA_PLAYBACK_APLAY "):
            parts = command.split()
            if len(parts) >= 2:
                add(parts[1], command)
        elif command == "amixer":
            for line in _trim_lines(row.stdout, limit=20000):
                match = re.search(r"Simple mixer control '([^']+)'", line)
                if match:
                    add(match.group(1), command)

    for row in pcm_rows:
        card = _to_int(_as_dict(row).get("card_index"), default=-1)
        dev = _to_int(_as_dict(row).get("device_index"), default=-1)
        direction = str(_as_dict(row).get("direction", ""))
        if card >= 0 and dev >= 0 and direction == "playback":
            add(f"hw:{card},{dev}", "cat /proc/asound/pcm")
            add(f"plughw:{card},{dev}", "cat /proc/asound/pcm")
        name = str(_as_dict(row).get("name", "")).strip()
        iface = str(_as_dict(row).get("interface", "")).strip()
        if name:
            add(name, "cat /proc/asound/pcm")
        if iface:
            add(iface, "cat /proc/asound/pcm")

    for key in ("frontend_candidates", "backend_candidates"):
        for row in _as_list(_as_dict(fe_be_map).get(key)):
            item = _as_dict(row)
            for token in (str(item.get("name", "")).strip(), str(item.get("interface", "")).strip()):
                if token:
                    add(token, "fe_be_transition_map")

    widget_rows = _as_list(_as_dict(direct_dapm_runtime_state).get("widgets"))
    for row in widget_rows[:800]:
        widget = str(_as_dict(row).get("widget", "")).strip()
        if widget and (re.search(r"[A-Z0-9_]{4,}", widget) or "Jack" in widget or "jack" in widget):
            add(widget, "direct_dapm_runtime_state")

    result = [
        {
            "alias": alias,
            "evidence_sources": sorted(list(sources)),
        }
        for alias, sources in sorted(evidence.items(), key=lambda item: item[0].lower())
    ]
    return result


def _build_semantic_alias_registry(
    *,
    combined_rows: list[TraceRow],
    pcm_rows: list[dict[str, Any]],
    fe_be_map: Mapping[str, Any],
    direct_dapm_runtime_state: Mapping[str, Any],
) -> dict[str, Any]:
    candidates = _collect_semantic_alias_candidates(
        combined_rows=combined_rows,
        pcm_rows=pcm_rows,
        fe_be_map=fe_be_map,
        direct_dapm_runtime_state=direct_dapm_runtime_state,
    )
    mappings: list[dict[str, Any]] = []
    for item in candidates:
        alias = str(_as_dict(item).get("alias", ""))
        evidence_sources = [str(v) for v in _as_list(_as_dict(item).get("evidence_sources"))]
        normalized = _normalize_semantic_alias(alias)
        scope = str(_as_dict(normalized).get("semantic_scope", "UNKNOWN_UNSAFE"))
        penalty = 0.25 if scope == "UNKNOWN_UNSAFE" else 0.0
        confidence = _confidence_score(
            evidence_count=len(evidence_sources),
            direct=(scope != "UNKNOWN_UNSAFE"),
            penalty=penalty,
        )
        mapping = {
            "alias": alias,
            "canonical_semantic_identity": str(_as_dict(normalized).get("canonical_semantic_identity", "")),
            "semantic_scope": scope if scope in SEMANTIC_SCOPE_CLASSES else "UNKNOWN_UNSAFE",
            "semantic_type": str(_as_dict(normalized).get("semantic_type", "")),
            "evidence_sources": evidence_sources,
            "confidence": confidence,
            "fallback_reason": str(_as_dict(normalized).get("fallback_reason", "")),
        }
        mapping["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"alias:{alias}",
            evidence_sources=evidence_sources,
        )
        mappings.append(mapping)

    scope_counts: dict[str, int] = {}
    for row in mappings:
        scope = str(_as_dict(row).get("semantic_scope", "UNKNOWN_UNSAFE"))
        scope_counts[scope] = int(scope_counts.get(scope, 0)) + 1

    payload = {
        "artifact_name": "SEMANTIC_ALIAS_REGISTRY",
        "generated_at": _utc_now_iso(),
        "alias_mappings": sorted(mappings, key=lambda row: (str(row.get("semantic_scope", "")), str(row.get("alias", "")[:180])))[:4000],
        "summary": {
            "mapping_count": len(mappings),
            "scope_counts": dict(sorted(scope_counts.items())),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_portability_blocker_registry(
    *,
    board_specific_assumptions: Mapping[str, Any],
    runtime_capability_matrix: Mapping[str, Any],
    fe_be_map: Mapping[str, Any],
    combined_rows: list[TraceRow],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []

    def add_blocker(
        *,
        blocker_key: str,
        hazard_type: str,
        severity: str,
        evidence_sources: list[str],
        raw_category: str,
        description: str,
        fallback_reason: str,
    ) -> None:
        scope = _classify_semantic_scope(raw_category, f"{hazard_type} {description}")
        confidence = _confidence_score(evidence_count=len(evidence_sources), direct=True, penalty=0.05 if severity == "high" else 0.0)
        row = {
            "blocker_key": blocker_key,
            "hazard_type": hazard_type,
            "severity": severity,
            "semantic_scope": scope,
            "raw_category": raw_category,
            "description": description,
            "evidence_sources": sorted(set(evidence_sources)),
            "confidence": confidence,
            "fallback_reason": fallback_reason,
        }
        row["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"blocker:{blocker_key}",
            evidence_sources=row["evidence_sources"],
        )
        blockers.append(row)

    code_findings = _as_list(_as_dict(board_specific_assumptions).get("code_level_assumptions"))
    runtime_findings = _as_list(_as_dict(board_specific_assumptions).get("runtime_level_assumptions"))
    kernel_findings = _as_list(_as_dict(board_specific_assumptions).get("kernel_version_sensitive_logic"))

    for idx, item in enumerate(code_findings, start=1):
        row = _as_dict(item)
        category = str(row.get("category", ""))
        if category == "board_specific_token":
            add_blocker(
                blocker_key=f"board_specific_token_{idx}",
                hazard_type="board_specific_token",
                severity="high",
                evidence_sources=[str(row.get("file", "")), str(row.get("snippet", ""))],
                raw_category=category,
                description="Board-local semantic identifiers are embedded in source logic.",
                fallback_reason="requires runtime-discovered topology aliasing",
            )
        elif category == "hardcoded_pcm":
            add_blocker(
                blocker_key=f"hardcoded_pcm_{idx}",
                hazard_type="hardcoded_pcm",
                severity="medium",
                evidence_sources=[str(row.get("file", "")), str(row.get("snippet", ""))],
                raw_category=category,
                description="Hardcoded ALSA PCM literal assumptions in code.",
                fallback_reason="replace with semantic alias resolution",
            )
        elif category == "wildcard_dapm_only":
            add_blocker(
                blocker_key=f"downstream_debugfs_{idx}",
                hazard_type="downstream_debugfs_assumption",
                severity="high",
                evidence_sources=[str(row.get("file", "")), str(row.get("snippet", ""))],
                raw_category=category,
                description="Relies on downstream debugfs DAPM exposure pattern.",
                fallback_reason="negotiate evidence source alternatives",
            )

    for idx, item in enumerate(runtime_findings, start=1):
        row = _as_dict(item)
        category = str(row.get("category", ""))
        cmd = str(row.get("command", ""))
        if category == "fixed_card0_path":
            add_blocker(
                blocker_key=f"fixed_card_path_{idx}",
                hazard_type="hardcoded_card_paths",
                severity="high",
                evidence_sources=[cmd],
                raw_category=category,
                description="Runtime capture currently touches fixed card0 path assumptions.",
                fallback_reason="resolve card/device dynamically from proc/asound",
            )
        elif category == "hardcoded_pcm_literal":
            add_blocker(
                blocker_key=f"fixed_pcm_literal_{idx}",
                hazard_type="hardcoded_pcm",
                severity="medium",
                evidence_sources=[cmd],
                raw_category=category,
                description="Runtime commands include fixed hw/plughw literals.",
                fallback_reason="normalize via canonical semantic identities",
            )
        elif category == "fixed_substream0_path":
            add_blocker(
                blocker_key=f"fixed_substream_{idx}",
                hazard_type="static_topology_coupling",
                severity="medium",
                evidence_sources=[cmd],
                raw_category=category,
                description="Substream0-only assumptions may miss runtime topology variants.",
                fallback_reason="enumerate substreams dynamically",
            )

    for idx, item in enumerate(kernel_findings, start=1):
        row = _as_dict(item)
        category = str(row.get("category", ""))
        if category in {"debugfs_asoc_dependency", "debugfs_soundwire_dependency", "soundwire_bus_dependency"}:
            add_blocker(
                blocker_key=f"kernel_sensitive_{idx}",
                hazard_type="downstream_debugfs_assumption",
                severity="medium",
                evidence_sources=[str(row.get("snippet", ""))],
                raw_category=category,
                description="Kernel/debugfs layout dependency may vary across upstream/downstream builds.",
                fallback_reason="negotiate fallback evidence path",
            )

    sw_exact_cmds = sorted(
        {
            row.command
            for row in combined_rows
            if "/sys/bus/soundwire/devices/sdw:" in str(row.command)
        }
    )
    if sw_exact_cmds:
        add_blocker(
            blocker_key="fixed_soundwire_endpoint_assumptions",
            hazard_type="fixed_soundwire_endpoint_assumptions",
            severity="medium",
            evidence_sources=sw_exact_cmds[:20],
            raw_category="soundwire_endpoint_literal",
            description="Runtime path references exact SoundWire endpoint IDs.",
            fallback_reason="normalize endpoint aliases by bus role",
        )

    if len(_as_list(_as_dict(fe_be_map).get("fe_be_links"))) == 0:
        add_blocker(
            blocker_key="static_topology_coupling_missing_fe_be_links",
            hazard_type="static_topology_coupling",
            severity="high",
            evidence_sources=["fe_be_transition_map"],
            raw_category="fe_be_unresolved",
            description="No FE/BE semantic links discovered under current naming/layout.",
            fallback_reason="require richer topology semantic inference",
        )

    capability_rows = _as_list(_as_dict(runtime_capability_matrix).get("capabilities"))
    tinymix_cap = next((c for c in capability_rows if str(_as_dict(c).get("source_id", "")) == "tinymix_cli"), {})
    if not bool(_as_dict(tinymix_cap).get("available", False)):
        add_blocker(
            blocker_key="board_local_mixer_naming",
            hazard_type="board_local_mixer_names",
            severity="medium",
            evidence_sources=["runtime_capability_matrix:tinymix_cli_unavailable"],
            raw_category="mixer_cli_variation",
            description="Mixer semantic names may vary and tinymix path is unavailable.",
            fallback_reason="retain amixer-first semantic normalization",
        )

    blockers = sorted(blockers, key=lambda row: (str(row.get("severity", "")), str(row.get("hazard_type", "")), str(row.get("blocker_key", ""))))
    unique: dict[str, dict[str, Any]] = {}
    for row in blockers:
        key = str(_as_dict(row).get("blocker_key", ""))
        if key and key not in unique:
            unique[key] = row
    deduped = list(unique.values())

    severity_counts: dict[str, int] = {}
    hazard_counts: dict[str, int] = {}
    for row in deduped:
        sev = str(_as_dict(row).get("severity", "unknown"))
        hz = str(_as_dict(row).get("hazard_type", "unknown"))
        severity_counts[sev] = int(severity_counts.get(sev, 0)) + 1
        hazard_counts[hz] = int(hazard_counts.get(hz, 0)) + 1

    payload = {
        "artifact_name": "PORTABILITY_BLOCKER_REGISTRY",
        "generated_at": _utc_now_iso(),
        "blockers": deduped[:4000],
        "summary": {
            "blocker_count": len(deduped),
            "severity_counts": dict(sorted(severity_counts.items())),
            "hazard_counts": dict(sorted(hazard_counts.items())),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_semantic_assumption_matrix(
    *,
    board_specific_assumptions: Mapping[str, Any],
    portability_blockers: Mapping[str, Any],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    def add_row(assumption_id: str, raw_category: str, evidence_sources: list[str], text: str, inferred: bool) -> None:
        scope = _classify_semantic_scope(raw_category, text)
        penalty = 0.0 if scope != "UNKNOWN_UNSAFE" else 0.3
        confidence = _confidence_score(evidence_count=len(evidence_sources), direct=not inferred, penalty=penalty)
        entry = {
            "assumption_id": assumption_id,
            "raw_category": raw_category,
            "semantic_scope_class": scope if scope in SEMANTIC_SCOPE_CLASSES else "UNKNOWN_UNSAFE",
            "evidence_sources": sorted(set(evidence_sources)),
            "confidence": confidence,
            "fallback_reason": "" if scope != "UNKNOWN_UNSAFE" else "assumption_scope_not_resolved",
        }
        entry["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"assumption:{assumption_id}",
            evidence_sources=entry["evidence_sources"],
        )
        rows.append(entry)

    for idx, item in enumerate(_as_list(_as_dict(board_specific_assumptions).get("code_level_assumptions")), start=1):
        row = _as_dict(item)
        add_row(
            assumption_id=f"code_{idx}",
            raw_category=str(row.get("category", "")),
            evidence_sources=[str(row.get("file", "")), str(row.get("snippet", ""))],
            text=str(row.get("snippet", "")),
            inferred=False,
        )

    for idx, item in enumerate(_as_list(_as_dict(board_specific_assumptions).get("runtime_level_assumptions")), start=1):
        row = _as_dict(item)
        add_row(
            assumption_id=f"runtime_{idx}",
            raw_category=str(row.get("category", "")),
            evidence_sources=[str(row.get("command", ""))],
            text=str(row.get("command", "")),
            inferred=False,
        )

    for idx, item in enumerate(_as_list(_as_dict(board_specific_assumptions).get("kernel_version_sensitive_logic")), start=1):
        row = _as_dict(item)
        add_row(
            assumption_id=f"kernel_{idx}",
            raw_category=str(row.get("category", "")),
            evidence_sources=[str(row.get("snippet", ""))],
            text=str(row.get("snippet", "")),
            inferred=True,
        )

    for idx, item in enumerate(_as_list(_as_dict(portability_blockers).get("blockers")), start=1):
        row = _as_dict(item)
        add_row(
            assumption_id=f"blocker_{idx}",
            raw_category=str(row.get("raw_category", "")),
            evidence_sources=[str(v) for v in _as_list(row.get("evidence_sources"))],
            text=str(row.get("description", "")),
            inferred=True,
        )

    class_counts: dict[str, int] = {key: 0 for key in sorted(SEMANTIC_SCOPE_CLASSES)}
    for row in rows:
        cls = str(_as_dict(row).get("semantic_scope_class", "UNKNOWN_UNSAFE"))
        class_counts[cls] = int(class_counts.get(cls, 0)) + 1

    payload = {
        "artifact_name": "SEMANTIC_ASSUMPTION_MATRIX",
        "generated_at": _utc_now_iso(),
        "assumptions": sorted(rows, key=lambda row: (str(row.get("semantic_scope_class", "")), str(row.get("assumption_id", ""))))[:8000],
        "summary": {
            "assumption_count": len(rows),
            "class_counts": class_counts,
            "unknown_unsafe_count": int(class_counts.get("UNKNOWN_UNSAFE", 0)),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_board_specific_dependency_graph(
    *,
    portability_blockers: Mapping[str, Any],
    evidence_source_negotiation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers = [_as_dict(item) for item in _as_list(_as_dict(portability_blockers).get("blockers"))]
    negotiated_sources = [_as_dict(item) for item in _as_list(_as_dict(evidence_source_negotiation).get("negotiated_sources"))]

    signal_nodes = sorted(set(str(row.get("signal", "")) for row in negotiated_sources if str(row.get("signal", ""))))
    nodes: list[dict[str, Any]] = []
    for sig in signal_nodes:
        nodes.append({"id": f"signal:{sig}", "type": "signal", "label": sig})
    for row in blockers:
        key = str(row.get("blocker_key", ""))
        if key:
            nodes.append(
                {
                    "id": f"blocker:{key}",
                    "type": "blocker",
                    "label": str(row.get("hazard_type", "")),
                    "severity": str(row.get("severity", "")),
                    "semantic_scope": str(row.get("semantic_scope", "")),
                }
            )

    impact_map = {
        "hardcoded_card_paths": ["pcm_lifecycle", "hw_params"],
        "hardcoded_pcm": ["playback_invoked", "pcm_lifecycle"],
        "board_local_mixer_names": ["pcm_lifecycle"],
        "downstream_debugfs_assumption": ["dapm_transition", "codec_discovery"],
        "fixed_soundwire_endpoint_assumptions": ["bus_activity"],
        "static_topology_coupling": ["fe_be_layout", "dapm_transition"],
        "board_specific_token": ["codec_discovery", "fe_be_layout"],
    }

    edges: list[dict[str, Any]] = []
    for row in blockers:
        blocker_id = str(row.get("blocker_key", ""))
        hazard = str(row.get("hazard_type", ""))
        targets = impact_map.get(hazard, [])
        for sig in targets:
            evidence_sources = [str(v) for v in _as_list(row.get("evidence_sources"))]
            edge = {
                "from": f"blocker:{blocker_id}",
                "to": f"signal:{sig}",
                "relationship": "may_reduce_portability_confidence",
                "confidence": _confidence_score(evidence_count=len(evidence_sources), direct=True, penalty=0.1),
                "fallback_reason": "impact_inferred_from_hazard_category",
                "evidence_sources": evidence_sources[:12],
            }
            edge["deterministic_proof_state"] = _deterministic_proof_state(
                key_seed=f"dependency:{blocker_id}:{sig}",
                evidence_sources=edge["evidence_sources"],
            )
            edges.append(edge)

    payload = {
        "artifact_name": "BOARD_SPECIFIC_DEPENDENCY_GRAPH",
        "generated_at": _utc_now_iso(),
        "nodes": sorted(nodes, key=lambda row: str(row.get("id", ""))),
        "edges": sorted(edges, key=lambda row: (str(row.get("from", "")), str(row.get("to", "")))),
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "blocker_node_count": len([n for n in nodes if str(_as_dict(n).get("type", "")) == "blocker"]),
            "signal_node_count": len([n for n in nodes if str(_as_dict(n).get("type", "")) == "signal"]),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_pcm_role_registry(
    *,
    pcm_rows: list[dict[str, Any]],
    fe_be_map: Mapping[str, Any],
    semantic_alias_registry: Mapping[str, Any],
) -> dict[str, Any]:
    fe_ids = set(str(_as_dict(item).get("pcm_id", "")) for item in _as_list(_as_dict(fe_be_map).get("frontend_candidates")))
    be_ids = set(str(_as_dict(item).get("pcm_id", "")) for item in _as_list(_as_dict(fe_be_map).get("backend_candidates")))
    alias_rows = [_as_dict(item) for item in _as_list(_as_dict(semantic_alias_registry).get("alias_mappings"))]
    alias_by_canonical: dict[str, list[str]] = {}
    for row in alias_rows:
        canonical = str(row.get("canonical_semantic_identity", ""))
        alias = str(row.get("alias", ""))
        if canonical and alias:
            alias_by_canonical.setdefault(canonical, []).append(alias)

    entries: list[dict[str, Any]] = []
    for row in pcm_rows:
        item = _as_dict(row)
        card = _to_int(item.get("card_index"), default=-1)
        dev = _to_int(item.get("device_index"), default=-1)
        direction = str(item.get("direction", "unknown"))
        pcm_id = str(item.get("pcm_id", ""))
        role = "FRONTEND" if pcm_id in fe_ids else "BACKEND" if pcm_id in be_ids else "PCM_ENDPOINT"
        canonical = f"PCM_CARD{card}_DEV{dev}_{direction.upper()}"
        aliases = sorted(
            set(
                alias_by_canonical.get(canonical, [])
                + (
                    [f"hw:{card},{dev}", f"plughw:{card},{dev}"]
                    if card >= 0 and dev >= 0 and direction == "playback"
                    else []
                )
            )
        )
        fallback_reason = "" if role in {"FRONTEND", "BACKEND"} else "role_inferred_from_direction"
        entry = {
            "pcm_id": pcm_id,
            "card_index": card,
            "device_index": dev,
            "direction": direction,
            "name": str(item.get("name", "")),
            "interface": str(item.get("interface", "")),
            "semantic_role": role,
            "canonical_semantic_identity": canonical,
            "aliases": aliases,
            "evidence_sources": ["cat /proc/asound/pcm"],
            "confidence": _confidence_score(evidence_count=1, direct=True, penalty=0.0 if role in {"FRONTEND", "BACKEND"} else 0.15),
            "fallback_reason": fallback_reason,
        }
        entry["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"pcm_role:{pcm_id}",
            evidence_sources=entry["evidence_sources"] + aliases[:4],
        )
        entries.append(entry)

    role_counts: dict[str, int] = {}
    for row in entries:
        role = str(_as_dict(row).get("semantic_role", "UNKNOWN"))
        role_counts[role] = int(role_counts.get(role, 0)) + 1

    payload = {
        "artifact_name": "PCM_ROLE_REGISTRY",
        "generated_at": _utc_now_iso(),
        "pcm_roles": sorted(entries, key=lambda row: (str(row.get("semantic_role", "")), str(row.get("pcm_id", "")))),
        "summary": {
            "pcm_count": len(entries),
            "role_counts": dict(sorted(role_counts.items())),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_frontend_backend_semantic_map(
    *,
    fe_be_map: Mapping[str, Any],
    pcm_role_registry: Mapping[str, Any],
) -> dict[str, Any]:
    role_rows = [_as_dict(item) for item in _as_list(_as_dict(pcm_role_registry).get("pcm_roles"))]
    role_by_pcm = {str(row.get("pcm_id", "")): row for row in role_rows}
    links = [_as_dict(item) for item in _as_list(_as_dict(fe_be_map).get("fe_be_links"))]
    link_map: dict[str, list[dict[str, Any]]] = {}
    for row in links:
        fe = str(row.get("frontend_pcm_id", ""))
        link_map.setdefault(fe, []).append(row)

    mappings: list[dict[str, Any]] = []
    fe_rows = [_as_dict(item) for item in _as_list(_as_dict(fe_be_map).get("frontend_candidates"))]
    for fe in fe_rows:
        fe_pcm = str(fe.get("pcm_id", ""))
        link_rows = link_map.get(fe_pcm, [])
        backends = [str(_as_dict(item).get("backend_pcm_id", "")) for item in link_rows if str(_as_dict(item).get("backend_pcm_id", ""))]
        resolved = bool(backends)
        evidence_sources = ["cat /proc/asound/pcm"] + (["cat /sys/kernel/debug/asoc/<card>/dai_links"] if resolved else [])
        mapping = {
            "frontend_pcm_id": fe_pcm,
            "frontend_semantic_identity": str(_as_dict(role_by_pcm.get(fe_pcm)).get("canonical_semantic_identity", "")),
            "backend_pcm_ids": sorted(set(backends)),
            "backend_semantic_identities": sorted(
                set(str(_as_dict(role_by_pcm.get(pid)).get("canonical_semantic_identity", "")) for pid in backends if pid in role_by_pcm)
            ),
            "resolved": resolved,
            "evidence_sources": evidence_sources,
            "confidence": _confidence_score(evidence_count=len(evidence_sources), direct=resolved, penalty=0.2 if not resolved else 0.0),
            "fallback_reason": "" if resolved else "backend_candidates_unavailable_or_unlinked",
        }
        mapping["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"fe_be:{fe_pcm}",
            evidence_sources=evidence_sources + mapping["backend_pcm_ids"][:6],
        )
        mappings.append(mapping)

    payload = {
        "artifact_name": "FRONTEND_BACKEND_SEMANTIC_MAP",
        "generated_at": _utc_now_iso(),
        "mappings": sorted(mappings, key=lambda row: str(row.get("frontend_pcm_id", ""))),
        "summary": {
            "frontend_count": len(mappings),
            "resolved_count": len([row for row in mappings if bool(_as_dict(row).get("resolved", False))]),
            "unresolved_count": len([row for row in mappings if not bool(_as_dict(row).get("resolved", False))]),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_semantic_topology_graph(
    *,
    cards: list[dict[str, Any]],
    pcm_role_registry: Mapping[str, Any],
    direct_dapm_runtime_state: Mapping[str, Any],
    soundwire_runtime_activation: Mapping[str, Any],
    frontend_backend_semantic_map: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for card in cards:
        row = _as_dict(card)
        card_index = _to_int(row.get("card_index"), default=-1)
        card_id = str(row.get("card_id", ""))
        node_id = f"card:{card_index}"
        nodes.append(
            {
                "id": node_id,
                "type": "alsa_card",
                "label": card_id if card_id else node_id,
            }
        )

    pcm_rows = [_as_dict(item) for item in _as_list(_as_dict(pcm_role_registry).get("pcm_roles"))]
    for row in pcm_rows:
        pcm_id = str(row.get("pcm_id", ""))
        card_index = _to_int(row.get("card_index"), default=-1)
        node_id = f"pcm:{pcm_id}"
        nodes.append(
            {
                "id": node_id,
                "type": "pcm_endpoint",
                "label": str(row.get("canonical_semantic_identity", node_id)),
                "semantic_role": str(row.get("semantic_role", "")),
            }
        )
        evidence_sources = [str(v) for v in _as_list(row.get("evidence_sources"))]
        edge = {
            "from": f"card:{card_index}",
            "to": node_id,
            "relationship": "owns_pcm",
            "evidence_sources": evidence_sources,
            "confidence": _confidence_score(evidence_count=len(evidence_sources), direct=True),
            "fallback_reason": "",
        }
        edge["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"card_pcm:{card_index}:{pcm_id}",
            evidence_sources=evidence_sources,
        )
        edges.append(edge)

    widgets = [_as_dict(item) for item in _as_list(_as_dict(direct_dapm_runtime_state).get("widgets"))]
    cluster_counts: dict[tuple[str, str], int] = {}
    for row in widgets[:4000]:
        card = str(row.get("card", "UNKNOWN_CARD"))
        widget = str(row.get("widget", ""))
        lowered = widget.lower()
        cluster = "MISC"
        if "jack" in lowered:
            cluster = "JACK_ENDPOINT"
        elif "mic" in lowered:
            cluster = "MIC_PATH"
        elif re.search(r"\brx\b", lowered):
            cluster = "RX_PATH"
        elif re.search(r"\btx\b", lowered):
            cluster = "TX_PATH"
        cluster_counts[(card, cluster)] = int(cluster_counts.get((card, cluster), 0)) + 1

    for (card, cluster), count in sorted(cluster_counts.items()):
        node_id = f"dapm_cluster:{card}:{cluster}"
        nodes.append(
            {
                "id": node_id,
                "type": "dapm_cluster",
                "label": cluster,
                "card": card,
                "widget_count": count,
            }
        )
        evidence_sources = ["direct_dapm_runtime_state"]
        edge = {
            "from": f"card:{card}",
            "to": node_id,
            "relationship": "hosts_dapm_cluster",
            "evidence_sources": evidence_sources,
            "confidence": _confidence_score(evidence_count=1, direct=True),
            "fallback_reason": "",
        }
        edge["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"card_dapm:{card}:{cluster}",
            evidence_sources=evidence_sources,
        )
        edges.append(edge)

    sw_masters = [str(item) for item in _as_list(_as_dict(soundwire_runtime_activation).get("masters")) if str(item).strip()]
    sw_devices = [str(item) for item in _as_list(_as_dict(soundwire_runtime_activation).get("bus_devices")) if str(item).strip()]
    for master in sw_masters:
        nodes.append({"id": f"soundwire_master:{master}", "type": "soundwire_master", "label": master})
    for dev in sw_devices:
        nodes.append({"id": f"soundwire_device:{dev}", "type": "soundwire_device", "label": dev})
        for master in sw_masters:
            evidence_sources = ["ls /sys/bus/soundwire/devices", "ls /sys/kernel/debug/soundwire"]
            edge = {
                "from": f"soundwire_master:{master}",
                "to": f"soundwire_device:{dev}",
                "relationship": "enumerates_device",
                "evidence_sources": evidence_sources,
                "confidence": _confidence_score(evidence_count=len(evidence_sources), direct=True),
                "fallback_reason": "",
            }
            edge["deterministic_proof_state"] = _deterministic_proof_state(
                key_seed=f"soundwire:{master}:{dev}",
                evidence_sources=evidence_sources,
            )
            edges.append(edge)

    for mapping in _as_list(_as_dict(frontend_backend_semantic_map).get("mappings")):
        row = _as_dict(mapping)
        fe_pcm = str(row.get("frontend_pcm_id", ""))
        if not fe_pcm:
            continue
        for be_pcm in _as_list(row.get("backend_pcm_ids")):
            be = str(be_pcm)
            evidence_sources = [str(v) for v in _as_list(row.get("evidence_sources"))]
            edge = {
                "from": f"pcm:{fe_pcm}",
                "to": f"pcm:{be}",
                "relationship": "semantic_fe_be_link",
                "evidence_sources": evidence_sources,
                "confidence": float(row.get("confidence", 0.0) or 0.0),
                "fallback_reason": str(row.get("fallback_reason", "")),
            }
            edge["deterministic_proof_state"] = _deterministic_proof_state(
                key_seed=f"fe_be_link:{fe_pcm}:{be}",
                evidence_sources=evidence_sources,
            )
            edges.append(edge)

    nodes = sorted({str(_as_dict(node).get("id", "")): node for node in nodes if str(_as_dict(node).get("id", ""))}.values(), key=lambda row: str(_as_dict(row).get("id", "")))
    edges = sorted(edges, key=lambda row: (str(row.get("from", "")), str(row.get("to", "")), str(row.get("relationship", ""))))
    payload = {
        "artifact_name": "SEMANTIC_TOPOLOGY_GRAPH",
        "generated_at": _utc_now_iso(),
        "nodes": nodes,
        "edges": edges[:12000],
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "pcm_node_count": len([n for n in nodes if str(_as_dict(n).get("type", "")) == "pcm_endpoint"]),
            "dapm_cluster_count": len([n for n in nodes if str(_as_dict(n).get("type", "")) == "dapm_cluster"]),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_route_semantic_clusters(
    *,
    activation_order_graph: Mapping[str, Any],
    runtime_transition_timeline: Mapping[str, Any],
    playback_convergence_timeline: Mapping[str, Any],
    runtime_causality_chain: Mapping[str, Any],
    alsa_runtime_lifecycle: Mapping[str, Any],
    soundwire_runtime_activation: Mapping[str, Any],
    frontend_backend_semantic_map: Mapping[str, Any],
) -> dict[str, Any]:
    observed_nodes = [
        _as_dict(node)
        for node in _as_list(_as_dict(activation_order_graph).get("nodes"))
        if bool(_as_dict(node).get("observed", False))
    ]
    observed_nodes = sorted(observed_nodes, key=lambda node: (_to_epoch(str(_as_dict(node).get("timestamp", ""))), str(_as_dict(node).get("id", ""))))
    invoke_sequence = [str(_as_dict(node).get("id", "")) for node in observed_nodes if str(_as_dict(node).get("id", ""))]

    convergence = _as_dict(playback_convergence_timeline)
    lifecycle = _as_dict(alsa_runtime_lifecycle)
    fe_be_summary = _as_dict(frontend_backend_semantic_map).get("summary", {})
    causal_summary = _as_dict(runtime_causality_chain).get("summary", {})

    clusters: list[dict[str, Any]] = []

    def add_cluster(cluster_id: str, description: str, evidence_sources: list[str], confidence: float, fallback_reason: str, semantics: Mapping[str, Any]) -> None:
        row = {
            "cluster_id": cluster_id,
            "description": description,
            "evidence_sources": sorted(set(evidence_sources)),
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
            "fallback_reason": fallback_reason,
            "semantics": dict(semantics),
        }
        row["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"cluster:{cluster_id}",
            evidence_sources=row["evidence_sources"],
        )
        clusters.append(row)

    add_cluster(
        "playback_invoke_sequence",
        "Observed playback invocation and subsequent runtime activation sequence.",
        ["activation_order_graph", "runtime_transition_timeline"],
        _confidence_score(evidence_count=len(invoke_sequence), direct=True),
        "" if invoke_sequence else "observed_sequence_empty",
        {
            "ordered_nodes": invoke_sequence,
            "event_count": len(_as_list(_as_dict(runtime_transition_timeline).get("events"))),
        },
    )

    resolved_count = _to_int(_as_dict(fe_be_summary).get("resolved_count"), default=0)
    unresolved_count = _to_int(_as_dict(fe_be_summary).get("unresolved_count"), default=0)
    add_cluster(
        "fe_be_activation_order",
        "Frontend/backend semantic activation relation inferred from runtime topology evidence.",
        ["frontend_backend_semantic_map", "runtime_topology_inference"],
        _confidence_score(evidence_count=max(1, resolved_count + unresolved_count), direct=resolved_count > 0, penalty=0.2 if resolved_count == 0 else 0.0),
        "" if resolved_count > 0 else "backend_links_not_observed",
        {
            "resolved_count": resolved_count,
            "unresolved_count": unresolved_count,
        },
    )

    irq_corr = _as_dict(lifecycle.get("irq_window_correlation"))
    add_cluster(
        "irq_propagation_pattern",
        "IRQ propagation around playback window.",
        ["alsa_runtime_lifecycle", "playback_convergence_timeline"],
        _confidence_score(
            evidence_count=_to_int(irq_corr.get("any_delta_count"), default=0),
            direct=_to_int(irq_corr.get("any_delta_count"), default=0) > 0,
        ),
        "" if _to_int(irq_corr.get("any_delta_count"), default=0) > 0 else "irq_delta_not_observed",
        {
            "audio_delta_count": _to_int(irq_corr.get("audio_delta_count"), default=0),
            "any_delta_count": _to_int(irq_corr.get("any_delta_count"), default=0),
        },
    )

    dapm_timing = _as_dict(lifecycle.get("dapm_propagation_timing"))
    add_cluster(
        "dapm_transition_lifecycle",
        "DAPM transition lifecycle observed around playback window.",
        ["alsa_runtime_lifecycle", "direct_dapm_runtime_state"],
        _confidence_score(
            evidence_count=_to_int(dapm_timing.get("transition_count"), default=0) + (1 if bool(dapm_timing.get("snapshot_pair_observed", False)) else 0),
            direct=bool(dapm_timing.get("snapshot_pair_observed", False)),
        ),
        "" if bool(dapm_timing.get("snapshot_pair_observed", False)) else "dapm_snapshot_pair_not_observed",
        {
            "transition_count": _to_int(dapm_timing.get("transition_count"), default=0),
            "snapshot_pair_observed": bool(dapm_timing.get("snapshot_pair_observed", False)),
        },
    )

    sw = _as_dict(soundwire_runtime_activation)
    add_cluster(
        "soundwire_activation_semantics",
        "SoundWire runtime activation semantics from bus/debugfs evidence.",
        ["soundwire_runtime_activation", "runtime_capability_matrix"],
        _confidence_score(
            evidence_count=len(_as_list(sw.get("bus_devices"))) + len(_as_list(sw.get("masters"))),
            direct=bool(_as_list(sw.get("bus_devices")) or _as_list(sw.get("masters"))),
        ),
        "" if bool(_as_list(sw.get("bus_devices")) or _as_list(sw.get("masters"))) else "soundwire_not_detected",
        {
            "master_count": len(_as_list(sw.get("masters"))),
            "bus_device_count": len(_as_list(sw.get("bus_devices"))),
            "active_endpoint_count": _to_int(sw.get("active_endpoint_count"), default=0),
            "causal_confidence": float(_as_dict(causal_summary).get("causal_confidence", 0.0) or 0.0),
            "convergence_certainty": str(convergence.get("convergence_certainty", "")),
        },
    )

    payload = {
        "artifact_name": "ROUTE_SEMANTIC_CLUSTERS",
        "generated_at": _utc_now_iso(),
        "clusters": sorted(clusters, key=lambda row: str(row.get("cluster_id", ""))),
        "summary": {
            "cluster_count": len(clusters),
            "high_confidence_clusters": len([row for row in clusters if float(_as_dict(row).get("confidence", 0.0) or 0.0) >= 0.8]),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_semantic_runtime_capability_map(
    *,
    runtime_capability_matrix: Mapping[str, Any],
    evidence_source_negotiation: Mapping[str, Any],
    semantic_alias_registry: Mapping[str, Any],
    pcm_role_registry: Mapping[str, Any],
    route_semantic_clusters: Mapping[str, Any],
) -> dict[str, Any]:
    capability_rows = [_as_dict(item) for item in _as_list(_as_dict(runtime_capability_matrix).get("capabilities"))]
    cap_by_id = {str(row.get("source_id", "")): row for row in capability_rows}
    negotiated_rows = [_as_dict(item) for item in _as_list(_as_dict(evidence_source_negotiation).get("negotiated_sources"))]
    selected_by_signal = {str(row.get("signal", "")): str(row.get("selected_source", "")) for row in negotiated_rows}

    alias_rows = [_as_dict(item) for item in _as_list(_as_dict(semantic_alias_registry).get("alias_mappings"))]
    pcm_rows = [_as_dict(item) for item in _as_list(_as_dict(pcm_role_registry).get("pcm_roles"))]
    cluster_rows = [_as_dict(item) for item in _as_list(_as_dict(route_semantic_clusters).get("clusters"))]

    semantic_entries: list[dict[str, Any]] = []

    def add_entry(name: str, signal: str, extra_sources: list[str], semantics: Mapping[str, Any], fallback_reason: str = "") -> None:
        selected = selected_by_signal.get(signal, "")
        cap = _as_dict(cap_by_id.get(selected))
        evidence_sources = [selected] + extra_sources if selected else extra_sources
        evidence_sources = [str(src) for src in evidence_sources if str(src).strip()]
        conf = float(cap.get("confidence_level", "NONE") == "HIGH") * 0.9 + float(cap.get("confidence_level", "NONE") == "MEDIUM") * 0.75 + float(cap.get("confidence_level", "NONE") == "LOW") * 0.45
        if conf == 0.0:
            conf = _confidence_score(evidence_count=len(evidence_sources), direct=False, penalty=0.3)
        row = {
            "semantic_capability": name,
            "signal": signal,
            "selected_source": selected,
            "evidence_sources": sorted(set(evidence_sources)),
            "confidence": round(float(conf), 3),
            "fallback_reason": fallback_reason,
            "semantics": dict(semantics),
        }
        row["deterministic_proof_state"] = _deterministic_proof_state(
            key_seed=f"semantic_capability:{name}",
            evidence_sources=row["evidence_sources"],
        )
        semantic_entries.append(row)

    add_entry(
        "playback_identity_normalization",
        "playback_invoked",
        ["semantic_alias_registry"],
        {
            "alias_mapping_count": len(alias_rows),
            "canonical_alias_count": len(set(str(_as_dict(row).get("canonical_semantic_identity", "")) for row in alias_rows)),
        },
        fallback_reason="" if alias_rows else "alias_mappings_missing",
    )
    add_entry(
        "pcm_role_semantics",
        "pcm_lifecycle",
        ["pcm_role_registry", "frontend_backend_semantic_map"],
        {
            "pcm_role_count": len(pcm_rows),
            "frontend_count": len([row for row in pcm_rows if str(_as_dict(row).get("semantic_role", "")) == "FRONTEND"]),
            "backend_count": len([row for row in pcm_rows if str(_as_dict(row).get("semantic_role", "")) == "BACKEND"]),
        },
        fallback_reason="" if pcm_rows else "pcm_role_registry_missing",
    )
    add_entry(
        "dapm_semantics",
        "dapm_transition",
        ["route_semantic_clusters"],
        {
            "cluster_present": any(str(_as_dict(row).get("cluster_id", "")) == "dapm_transition_lifecycle" for row in cluster_rows),
        },
        fallback_reason="" if any(str(_as_dict(row).get("cluster_id", "")) == "dapm_transition_lifecycle" for row in cluster_rows) else "dapm_cluster_missing",
    )
    add_entry(
        "irq_semantics",
        "irq_correlation",
        ["route_semantic_clusters"],
        {
            "cluster_present": any(str(_as_dict(row).get("cluster_id", "")) == "irq_propagation_pattern" for row in cluster_rows),
        },
        fallback_reason="" if any(str(_as_dict(row).get("cluster_id", "")) == "irq_propagation_pattern" for row in cluster_rows) else "irq_cluster_missing",
    )
    add_entry(
        "bus_activation_semantics",
        "bus_activity",
        ["route_semantic_clusters"],
        {
            "cluster_present": any(str(_as_dict(row).get("cluster_id", "")) == "soundwire_activation_semantics" for row in cluster_rows),
        },
        fallback_reason="" if any(str(_as_dict(row).get("cluster_id", "")) == "soundwire_activation_semantics" for row in cluster_rows) else "bus_cluster_missing",
    )

    payload = {
        "artifact_name": "SEMANTIC_RUNTIME_CAPABILITY_MAP",
        "generated_at": _utc_now_iso(),
        "semantic_capabilities": sorted(semantic_entries, key=lambda row: str(row.get("semantic_capability", ""))),
        "summary": {
            "capability_count": len(semantic_entries),
            "high_confidence_capabilities": len([row for row in semantic_entries if float(_as_dict(row).get("confidence", 0.0) or 0.0) >= 0.8]),
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_runtime_portability_matrix(
    *,
    strict_runtime_governance_score: Mapping[str, Any],
    runtime_capability_matrix: Mapping[str, Any],
    evidence_source_negotiation: Mapping[str, Any],
    adaptive_capture_strategy: Mapping[str, Any],
    semantic_assumption_matrix: Mapping[str, Any],
    portability_blocker_registry: Mapping[str, Any],
) -> dict[str, Any]:
    strict_pass = str(_as_dict(strict_runtime_governance_score).get("classification", "")) == "PASS"
    strict_score = float(_as_dict(strict_runtime_governance_score).get("strict_score", 0.0) or 0.0)
    capability_score = float(_as_dict(runtime_capability_matrix).get("portability_score", 0.0) or 0.0)
    negotiation_pass = str(_as_dict(evidence_source_negotiation).get("classification", "")) == "PASS"
    adaptive_pass = str(_as_dict(adaptive_capture_strategy).get("classification", "")) == "PASS"

    class_counts = _as_dict(_as_dict(semantic_assumption_matrix).get("summary")).get("class_counts", {})
    unknown_unsafe = _to_int(_as_dict(class_counts).get("UNKNOWN_UNSAFE"), default=0)
    platform_specific = _to_int(_as_dict(class_counts).get("PLATFORM_SPECIFIC"), default=0)
    downstream_only = _to_int(_as_dict(class_counts).get("DOWNSTREAM_ONLY"), default=0)

    blocker_rows = [_as_dict(item) for item in _as_list(_as_dict(portability_blocker_registry).get("blockers"))]
    high_blockers = len([row for row in blocker_rows if str(row.get("severity", "")) == "high"])
    medium_blockers = len([row for row in blocker_rows if str(row.get("severity", "")) == "medium"])

    portability_debt = min(1.0, (high_blockers * 0.06 + medium_blockers * 0.03 + unknown_unsafe * 0.02))
    portability_maturity_score = round(max(0.0, ((strict_score * 0.45) + (capability_score * 0.35) + (0.2 if negotiation_pass and adaptive_pass else 0.0)) - portability_debt), 3)

    if strict_pass and capability_score >= 0.9 and negotiation_pass and adaptive_pass:
        if portability_maturity_score >= 0.75 and high_blockers <= 4:
            maturity = "P1_6_SEMANTIC_PORTABILITY_READY"
        else:
            maturity = "P1_6_RUNTIME_PORTABLE_WITH_ASSUMPTION_DEBT"
    else:
        maturity = "P1_6_NOT_READY"

    blockers_cross_board = sorted(
        {
            str(row.get("hazard_type", ""))
            for row in blocker_rows
            if str(row.get("severity", "")) in {"high", "medium"}
        }
    )

    payload = {
        "artifact_name": "RUNTIME_PORTABILITY_MATRIX",
        "generated_at": _utc_now_iso(),
        "portability_maturity": maturity,
        "portability_maturity_score": portability_maturity_score,
        "axes": {
            "strict_runtime_governance_score": strict_score,
            "runtime_capability_score": capability_score,
            "negotiation_pass": negotiation_pass,
            "adaptive_capture_pass": adaptive_pass,
            "unknown_unsafe_assumptions": unknown_unsafe,
            "platform_specific_assumptions": platform_specific,
            "downstream_only_assumptions": downstream_only,
            "high_severity_blockers": high_blockers,
            "medium_severity_blockers": medium_blockers,
        },
        "blockers_preventing_cross_board_portability": blockers_cross_board,
        "classification": "PASS" if strict_pass and negotiation_pass and adaptive_pass else "FAIL_CLOSED",
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_topology_portability_report(
    *,
    semantic_topology_graph: Mapping[str, Any],
    frontend_backend_semantic_map: Mapping[str, Any],
    pcm_role_registry: Mapping[str, Any],
    route_semantic_clusters: Mapping[str, Any],
    runtime_portability_matrix: Mapping[str, Any],
) -> dict[str, Any]:
    topo_summary = _as_dict(semantic_topology_graph).get("summary", {})
    fe_be_summary = _as_dict(frontend_backend_semantic_map).get("summary", {})
    pcm_summary = _as_dict(pcm_role_registry).get("summary", {})
    cluster_summary = _as_dict(route_semantic_clusters).get("summary", {})

    unresolved_fe_be = _to_int(_as_dict(fe_be_summary).get("unresolved_count"), default=0)
    blockers: list[str] = []
    if unresolved_fe_be > 0:
        blockers.append("frontend_backend_links_unresolved")
    if _to_int(_as_dict(topo_summary).get("dapm_cluster_count"), default=0) == 0:
        blockers.append("dapm_clusters_missing")
    if _to_int(_as_dict(cluster_summary).get("high_confidence_clusters"), default=0) < 3:
        blockers.append("insufficient_high_confidence_route_clusters")

    score = round(
        max(
            0.0,
            min(
                1.0,
                float(_as_dict(runtime_portability_matrix).get("portability_maturity_score", 0.0) or 0.0)
                - (0.08 * len(blockers)),
            ),
        ),
        3,
    )
    payload = {
        "artifact_name": "TOPOLOGY_PORTABILITY_REPORT",
        "generated_at": _utc_now_iso(),
        "topology_summary": {
            "node_count": _to_int(_as_dict(topo_summary).get("node_count"), default=0),
            "edge_count": _to_int(_as_dict(topo_summary).get("edge_count"), default=0),
            "pcm_node_count": _to_int(_as_dict(topo_summary).get("pcm_node_count"), default=0),
            "dapm_cluster_count": _to_int(_as_dict(topo_summary).get("dapm_cluster_count"), default=0),
            "pcm_role_count": _to_int(_as_dict(pcm_summary).get("pcm_count"), default=0),
            "resolved_fe_be_count": _to_int(_as_dict(fe_be_summary).get("resolved_count"), default=0),
            "unresolved_fe_be_count": unresolved_fe_be,
            "route_cluster_count": _to_int(_as_dict(cluster_summary).get("cluster_count"), default=0),
        },
        "classification": "PASS" if not blockers else "FAIL_CLOSED",
        "portability_score": score,
        "portability_blockers": blockers,
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _build_semantic_abstraction_summary(
    *,
    runtime_portability_matrix: Mapping[str, Any],
    board_specific_assumptions: Mapping[str, Any],
    portability_blocker_registry: Mapping[str, Any],
    route_semantic_clusters: Mapping[str, Any],
    topology_portability_report: Mapping[str, Any],
) -> dict[str, Any]:
    blocker_rows = [_as_dict(item) for item in _as_list(_as_dict(portability_blocker_registry).get("blockers"))]
    high_or_medium = [row for row in blocker_rows if str(row.get("severity", "")) in {"high", "medium"}]
    remaining_hardcoded = sorted(
        set(
            str(row.get("hazard_type", ""))
            for row in high_or_medium
            if str(row.get("hazard_type", "")).strip()
        )
    )
    clusters = [_as_dict(item) for item in _as_list(_as_dict(route_semantic_clusters).get("clusters"))]
    reusable_patterns = [
        {
            "pattern": str(row.get("cluster_id", "")),
            "confidence": float(row.get("confidence", 0.0) or 0.0),
            "evidence_sources": [str(v) for v in _as_list(row.get("evidence_sources"))],
            "fallback_reason": str(row.get("fallback_reason", "")),
            "deterministic_proof_state": _as_dict(row.get("deterministic_proof_state")),
        }
        for row in clusters
    ]

    maturity = str(_as_dict(runtime_portability_matrix).get("portability_maturity", "UNKNOWN"))
    next_phase = (
        "P1.7 Cross-Board Semantic Equivalence Validation"
        if maturity == "P1_6_SEMANTIC_PORTABILITY_READY"
        else "P1.6.1 Assumption Debt Reduction and FE/BE Link Expansion"
    )

    payload = {
        "artifact_name": "SEMANTIC_ABSTRACTION_SUMMARY",
        "generated_at": _utc_now_iso(),
        "current_portability_maturity": maturity,
        "remaining_hardcoded_assumptions": remaining_hardcoded,
        "reusable_semantic_patterns_discovered": reusable_patterns[:80],
        "blockers_preventing_cross_board_portability": sorted(
            set([str(row.get("hazard_type", "")) for row in high_or_medium] + [str(v) for v in _as_list(_as_dict(topology_portability_report).get("portability_blockers"))])
        ),
        "recommended_next_phase": next_phase,
        "assumption_summary": _as_dict(board_specific_assumptions).get("summary", {}),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _load_bridge_history_rows(bridge_root: Path, max_files: int = 100000) -> list[TraceRow]:
    responses_dir = bridge_root / "responses"
    if not responses_dir.exists():
        return []
    files = sorted([p for p in responses_dir.glob("*.json") if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)[:max_files]
    rows: list[TraceRow] = []
    for path in files:
        payload = _read_json(path)
        rows.extend(_extract_trace_rows(payload, response_path=str(path), phase="history"))
    return sorted(rows, key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id))


def _find_latest_successful_playback(rows: list[TraceRow]) -> TraceRow | None:
    candidates = [
        row
        for row in rows
        if row.command.startswith("AURA_PLAYBACK_APLAY ")
        and row.execution_status == "executed"
        and int(row.exit_code) == 0
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda row: _to_epoch(row.finished_at), reverse=True)
    return candidates[0]


def _ordered_unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _parse_aplay_wrapper_command(command: str) -> dict[str, str]:
    parts = str(command or "").strip().split()
    if len(parts) < 3:
        return {"device": "", "target_path": ""}
    if parts[0] != "AURA_PLAYBACK_APLAY":
        return {"device": "", "target_path": ""}
    return {"device": parts[1].strip(), "target_path": parts[2].strip()}


def _extract_asoc_cards(raw_ls_asoc: str) -> list[str]:
    blocked = {"components", "dais", "dapm_pop_time"}
    cards = []
    for token in _sanitize_ls_entries(raw_ls_asoc):
        if token.lower() in blocked:
            continue
        cards.append(token)
    return _ordered_unique(cards)


def _parse_aplay_stream_line(text: str) -> dict[str, Any]:
    lines = _trim_lines(text, limit=200)
    for line in lines:
        lowered = line.lower()
        if "playing wave" not in lowered:
            continue
        rate_match = re.search(r"rate\s+([0-9]+)\s*hz", line, flags=re.IGNORECASE)
        bit_match = re.search(r"([0-9]+)\s*bit", line, flags=re.IGNORECASE)
        channels = "Stereo" if "stereo" in lowered else "Mono" if "mono" in lowered else ""
        return {
            "observed": True,
            "line": line,
            "rate_hz": int(rate_match.group(1)) if rate_match else 0,
            "sample_bits": int(bit_match.group(1)) if bit_match else 0,
            "channels": channels,
        }
    return {"observed": False, "line": "", "rate_hz": 0, "sample_bits": 0, "channels": ""}


def _build_playback_candidates(
    *,
    pcm_rows: list[dict[str, Any]],
    history_rows: list[TraceRow],
    playback_device_prefix: str,
    fallback_target_path: str,
    candidate_limit: int,
) -> dict[str, Any]:
    latest = _find_latest_successful_playback(history_rows)
    latest_device = ""
    latest_target = ""
    if latest:
        parsed = _parse_aplay_wrapper_command(latest.command)
        latest_device = str(parsed.get("device", ""))
        latest_target = str(parsed.get("target_path", ""))

    target_path = latest_target or str(fallback_target_path).strip()
    if not target_path:
        target_path = "/data/local/tmp/aura/audio/speaker_validation_48k_stereo.wav"

    preferred = "plughw" if str(playback_device_prefix).strip() == "plughw" else "hw"
    secondary = "hw" if preferred == "plughw" else "plughw"

    candidates: list[str] = []
    if latest_device:
        candidates.append(latest_device)
        if latest_device.startswith("hw:"):
            candidates.append("plughw:" + latest_device.split(":", 1)[1])
        if latest_device.startswith("plughw:"):
            candidates.append("hw:" + latest_device.split(":", 1)[1])

    playback_entries = [
        _as_dict(row)
        for row in pcm_rows
        if str(_as_dict(row).get("direction", "")) == "playback"
    ]
    for row in playback_entries:
        card = _to_int(row.get("card_index"), default=-1)
        dev = _to_int(row.get("device_index"), default=-1)
        if card < 0 or dev < 0:
            continue
        suffix = f"{card},{dev}"
        candidates.append(f"{preferred}:{suffix}")
        candidates.append(f"{secondary}:{suffix}")

    candidates.extend(["default", "sysdefault"])
    candidates = _ordered_unique(candidates)[: max(1, int(candidate_limit))]
    return {
        "latest_successful_playback_command": latest.command if latest else "",
        "target_path": target_path,
        "candidates": candidates,
    }


def _build_window_snapshot_commands(
    *,
    asoc_nodes: list[str],
    pcm_rows: list[dict[str, Any]],
    sw_masters: list[str],
    sw_bus_devices: list[str],
) -> list[str]:
    commands: list[str] = [
        "cat /proc/asound/cards",
        "cat /proc/asound/pcm",
        "head -n 200 /proc/interrupts",
        "dmesg | tail -200",
        "amixer",
        "tinymix",
        "ls /sys/kernel/debug/asoc",
        "ls /sys/kernel/debug/soundwire",
        "ls /sys/bus/soundwire/devices",
    ]
    for card in asoc_nodes[:6]:
        commands.extend(
            [
                f"ls /sys/kernel/debug/asoc/{card}",
                f"cat /sys/kernel/debug/asoc/{card}/dapm/*",
                f"cat /sys/kernel/debug/asoc/{card}/dai_links",
                f"cat /sys/kernel/debug/asoc/{card}/codecs",
            ]
        )
    for row in pcm_rows[:10]:
        card = _to_int(_as_dict(row).get("card_index"), default=-1)
        dev = _to_int(_as_dict(row).get("device_index"), default=-1)
        direction = str(_as_dict(row).get("direction", ""))
        if card < 0 or dev < 0 or direction not in {"playback", "capture"}:
            continue
        suffix = "p" if direction == "playback" else "c"
        commands.extend(
            [
                f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/status",
                f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/hw_params",
                f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/info",
                f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/sw_params",
            ]
        )
    for master in sw_masters[:8]:
        commands.append(f"ls /sys/kernel/debug/soundwire/{master}")
    for dev in sw_bus_devices[:12]:
        commands.extend(
            [
                f"cat /sys/bus/soundwire/devices/{dev}/status",
                f"cat /sys/bus/soundwire/devices/{dev}/name",
                f"cat /sys/bus/soundwire/devices/{dev}/power/control",
            ]
        )
    return _ordered_unique(commands)


def _build_window_critical_commands(
    *,
    asoc_nodes: list[str],
    pcm_rows: list[dict[str, Any]],
) -> list[str]:
    commands: list[str] = [
        "head -n 200 /proc/interrupts",
        "cat /proc/asound/pcm",
    ]
    for card in asoc_nodes[:3]:
        commands.append(f"cat /sys/kernel/debug/asoc/{card}/dapm/*")
    for row in pcm_rows[:12]:
        card = _to_int(_as_dict(row).get("card_index"), default=-1)
        dev = _to_int(_as_dict(row).get("device_index"), default=-1)
        direction = str(_as_dict(row).get("direction", ""))
        if card < 0 or dev < 0 or direction != "playback":
            continue
        commands.extend(
            [
                f"cat /proc/asound/card{card}/pcm{dev}p/sub0/status",
                f"cat /proc/asound/card{card}/pcm{dev}p/sub0/hw_params",
            ]
        )
    return _ordered_unique(commands)


def _nearest_before(rows: list[TraceRow], *, command_filter: callable, anchor_epoch: float) -> TraceRow | None:
    candidates = [row for row in rows if command_filter(row.command) and _to_epoch(row.finished_at) <= anchor_epoch]
    if not candidates:
        return None
    candidates.sort(key=lambda row: _to_epoch(row.finished_at), reverse=True)
    return candidates[0]


def _nearest_after(rows: list[TraceRow], *, command_filter: callable, anchor_epoch: float) -> TraceRow | None:
    candidates = [row for row in rows if command_filter(row.command) and _to_epoch(row.finished_at) >= anchor_epoch]
    if not candidates:
        return None
    candidates.sort(key=lambda row: _to_epoch(row.finished_at))
    return candidates[0]


def _build_timing_capture_audit(rows: list[TraceRow], *, label: str) -> dict[str, Any]:
    latest = _find_latest_successful_playback(rows)
    playback_count = len([row for row in rows if row.command.startswith("AURA_PLAYBACK_APLAY ")])
    successful_count = len(
        [
            row
            for row in rows
            if row.command.startswith("AURA_PLAYBACK_APLAY ") and row.execution_status == "executed" and row.exit_code == 0
        ]
    )
    has_hw_params = any("/hw_params" in row.command and row.execution_status in {"executed", "failed"} for row in rows)
    has_pcm_status = any("/status" in row.command and "/proc/asound/card" in row.command for row in rows)
    has_dapm = any("/dapm" in row.command and row.command.startswith("cat /sys/kernel/debug/asoc/") for row in rows)
    has_irq = any(row.command == "head -n 200 /proc/interrupts" for row in rows)

    missing: list[str] = []
    race_conditions: list[str] = []
    uncertainties: list[str] = []

    pre_irq = None
    post_irq = None
    pre_dapm = None
    post_dapm = None
    if latest:
        start = _to_epoch(latest.started_at)
        end = _to_epoch(latest.finished_at)
        pre_irq = _nearest_before(rows, command_filter=lambda c: c == "head -n 200 /proc/interrupts", anchor_epoch=start)
        post_irq = _nearest_after(rows, command_filter=lambda c: c == "head -n 200 /proc/interrupts", anchor_epoch=end)
        pre_dapm = _nearest_before(rows, command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in c, anchor_epoch=start)
        post_dapm = _nearest_after(rows, command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in c, anchor_epoch=end)
        if pre_irq and post_irq:
            gap_ms = int(max(0.0, _to_epoch(post_irq.finished_at) - _to_epoch(pre_irq.finished_at)) * 1000.0)
            if gap_ms > 120000:
                race_conditions.append("irq_pre_post_gap_gt_120s")
        else:
            missing.append("irq_pre_post_pair_missing_near_playback")
        if pre_dapm and post_dapm:
            gap_ms = int(max(0.0, _to_epoch(post_dapm.finished_at) - _to_epoch(pre_dapm.finished_at)) * 1000.0)
            if gap_ms > 120000:
                race_conditions.append("dapm_pre_post_gap_gt_120s")
        else:
            missing.append("dapm_pre_post_pair_missing_near_playback")
    else:
        missing.append("successful_playback_trace_missing")

    if not has_hw_params:
        missing.append("hw_params_signal_missing")
    if not has_pcm_status:
        missing.append("pcm_status_signal_missing")
    if not has_dapm:
        missing.append("dapm_signal_missing")
    if not has_irq:
        missing.append("irq_signal_missing")

    if has_dapm and has_irq and not latest:
        uncertainties.append("signals_present_but_not_time_anchored_to_playback")
    if successful_count > 1:
        uncertainties.append("multiple_successful_playback_windows_present")
    if any(row.execution_status == "timeout" for row in rows):
        race_conditions.append("timeout_commands_present")

    payload = {
        "label": label,
        "generated_at": _utc_now_iso(),
        "playback_trace_count": playback_count,
        "successful_playback_count": successful_count,
        "has_hw_params_signal": has_hw_params,
        "has_pcm_status_signal": has_pcm_status,
        "has_dapm_signal": has_dapm,
        "has_irq_signal": has_irq,
        "has_pre_post_irq_pair_near_latest": bool(pre_irq and post_irq),
        "has_pre_post_dapm_pair_near_latest": bool(pre_dapm and post_dapm),
        "missing_temporal_signals": sorted(set(missing)),
        "race_conditions": sorted(set(race_conditions)),
        "convergence_uncertainty_sources": sorted(set(uncertainties)),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _command_kind(command: str) -> str:
    text = str(command or "")
    if text.startswith("AURA_PLAYBACK_APLAY "):
        return "playback"
    if text == "head -n 200 /proc/interrupts":
        return "irq"
    if text == "cat /proc/asound/pcm":
        return "pcm_catalog"
    if "/proc/asound/card" in text and text.endswith("/status"):
        return "pcm_status"
    if "/proc/asound/card" in text and text.endswith("/hw_params"):
        return "hw_params"
    if text.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in text:
        return "dapm"
    if text == "amixer" or text == "tinymix":
        return "mixer"
    if text.startswith("ls /sys/kernel/debug/soundwire") or text.startswith("cat /sys/kernel/debug/soundwire/"):
        return "soundwire_debugfs"
    if text.startswith("ls /sys/bus/soundwire/devices") or text.startswith("cat /sys/bus/soundwire/devices/"):
        return "soundwire_bus"
    if text.startswith("dmesg"):
        return "dmesg"
    if text.startswith("ls /sys/kernel/debug/asoc"):
        return "asoc_debugfs"
    return "other"


def _text_line_delta(before: str, after: str, *, sample_limit: int = 120) -> dict[str, Any]:
    def _normalize(text: str) -> set[str]:
        rows: set[str] = set()
        for line in _trim_lines(text, limit=30000):
            token = " ".join(line.strip().split())
            if token:
                rows.add(token)
        return rows

    b = _normalize(before)
    a = _normalize(after)
    added = sorted(a - b)
    removed = sorted(b - a)
    return {
        "changed": bool(added or removed),
        "added_count": len(added),
        "removed_count": len(removed),
        "added_sample": added[:sample_limit],
        "removed_sample": removed[:sample_limit],
    }


def _phase_bounds(rows: list[TraceRow], prefix: str) -> dict[str, str]:
    subset = [row for row in rows if str(row.phase).startswith(prefix)]
    if not subset:
        return {"started_at": "", "finished_at": ""}
    ordered = sorted(subset, key=lambda row: _to_epoch(row.started_at))
    return {
        "started_at": ordered[0].started_at,
        "finished_at": ordered[-1].finished_at,
    }


def _nearest_window_pair(
    *,
    window_rows: list[TraceRow],
    fallback_rows: list[TraceRow],
    command_filter: Callable[[str], bool],
    start_epoch: float,
    end_epoch: float,
) -> tuple[TraceRow | None, TraceRow | None]:
    pre = _nearest_before(window_rows, command_filter=command_filter, anchor_epoch=start_epoch)
    post = _nearest_after(window_rows, command_filter=command_filter, anchor_epoch=end_epoch)
    if pre is None:
        pre = _nearest_before(fallback_rows, command_filter=command_filter, anchor_epoch=start_epoch)
    if post is None:
        post = _nearest_after(fallback_rows, command_filter=command_filter, anchor_epoch=end_epoch)
    return pre, post


def _build_temporal_artifacts(
    *,
    window_rows: list[TraceRow],
    combined_rows: list[TraceRow],
    session_id: str,
    lineage_id: str,
    target_id: str,
) -> dict[str, dict[str, Any]]:
    source_rows = window_rows if window_rows else combined_rows
    latest_playback = _find_latest_successful_playback(source_rows)
    if latest_playback is None:
        latest_playback = _find_latest_successful_playback(combined_rows)

    playback_start = _to_epoch(latest_playback.started_at) if latest_playback else 0.0
    playback_end = _to_epoch(latest_playback.finished_at) if latest_playback else 0.0
    around_start = playback_start - 90.0 if playback_start > 0 else 0.0
    around_end = playback_end + 180.0 if playback_end > 0 else 0.0

    pre_irq, post_irq = _nearest_window_pair(
        window_rows=window_rows,
        fallback_rows=combined_rows,
        command_filter=lambda c: c == "head -n 200 /proc/interrupts",
        start_epoch=playback_start,
        end_epoch=playback_end,
    )
    pre_dapm, post_dapm = _nearest_window_pair(
        window_rows=window_rows,
        fallback_rows=combined_rows,
        command_filter=lambda c: c.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in c,
        start_epoch=playback_start,
        end_epoch=playback_end,
    )
    pre_amixer, post_amixer = _nearest_window_pair(
        window_rows=window_rows,
        fallback_rows=combined_rows,
        command_filter=lambda c: c == "amixer",
        start_epoch=playback_start,
        end_epoch=playback_end,
    )
    pre_tinymix, post_tinymix = _nearest_window_pair(
        window_rows=window_rows,
        fallback_rows=combined_rows,
        command_filter=lambda c: c == "tinymix",
        start_epoch=playback_start,
        end_epoch=playback_end,
    )
    pre_pcm, post_pcm = _nearest_window_pair(
        window_rows=window_rows,
        fallback_rows=combined_rows,
        command_filter=lambda c: c == "cat /proc/asound/pcm",
        start_epoch=playback_start,
        end_epoch=playback_end,
    )

    irq_delta = _irq_delta(pre_irq.stdout, post_irq.stdout) if (pre_irq and post_irq) else {"rows": [], "audio_rows": [], "audio_delta_count": 0, "irq_active": False}
    irq_any_active = len(_as_list(irq_delta.get("rows"))) > 0
    irq_audio_active = bool(_as_dict(irq_delta).get("irq_active", False))

    dapm_transitions: list[dict[str, Any]] = []
    dapm_raw_delta = {"changed": False, "added_count": 0, "removed_count": 0, "added_sample": [], "removed_sample": []}
    dapm_snapshot_pair_observed = False
    if pre_dapm and post_dapm:
        b_state = _parse_dapm_snapshot(pre_dapm.stdout)
        a_state = _parse_dapm_snapshot(post_dapm.stdout)
        dapm_snapshot_pair_observed = bool(b_state or a_state)
        for widget in sorted(set(b_state.keys()) | set(a_state.keys())):
            b_status = str(_as_dict(b_state.get(widget)).get("status", "UNKNOWN"))
            a_status = str(_as_dict(a_state.get(widget)).get("status", "UNKNOWN"))
            if b_status != a_status:
                dapm_transitions.append(
                    {
                        "widget": widget,
                        "before_status": b_status,
                        "after_status": a_status,
                        "transition": f"{b_status}->{a_status}",
                        "post_timestamp": post_dapm.finished_at,
                    }
                )
        dapm_raw_delta = _text_line_delta(pre_dapm.stdout, post_dapm.stdout)
        if not dapm_transitions and bool(dapm_raw_delta.get("changed", False)):
            dapm_transitions.append(
                {
                    "widget": "DAPM_RAW_DELTA",
                    "before_status": "UNKNOWN",
                    "after_status": "UNKNOWN",
                    "transition": "raw_line_delta",
                    "post_timestamp": post_dapm.finished_at,
                }
            )
        if not dapm_transitions and dapm_snapshot_pair_observed:
            dapm_transitions.append(
                {
                    "widget": "DAPM_SNAPSHOT_PAIR",
                    "before_status": "OBSERVED",
                    "after_status": "OBSERVED",
                    "transition": "snapshot_pair_observed_no_delta",
                    "post_timestamp": post_dapm.finished_at,
                }
            )

    amixer_delta = _text_line_delta(pre_amixer.stdout, post_amixer.stdout) if (pre_amixer and post_amixer) else {"changed": False, "added_count": 0, "removed_count": 0, "added_sample": [], "removed_sample": []}
    tinymix_delta = _text_line_delta(pre_tinymix.stdout, post_tinymix.stdout) if (pre_tinymix and post_tinymix) else {"changed": False, "added_count": 0, "removed_count": 0, "added_sample": [], "removed_sample": []}

    fe_before = _classify_fe_be(_parse_proc_pcm_rows(pre_pcm.stdout), [row.get("widget", "") for row in dapm_transitions]) if pre_pcm else {"frontend_candidates": [], "backend_candidates": [], "fe_be_links": []}
    fe_after = _classify_fe_be(_parse_proc_pcm_rows(post_pcm.stdout), [row.get("widget", "") for row in dapm_transitions]) if post_pcm else {"frontend_candidates": [], "backend_candidates": [], "fe_be_links": []}
    fe_delta = {
        "frontend_delta": len(_as_list(fe_after.get("frontend_candidates"))) - len(_as_list(fe_before.get("frontend_candidates"))),
        "backend_delta": len(_as_list(fe_after.get("backend_candidates"))) - len(_as_list(fe_before.get("backend_candidates"))),
        "link_delta": len(_as_list(fe_after.get("fe_be_links"))) - len(_as_list(fe_before.get("fe_be_links"))),
    }

    status_rows = [
        row
        for row in combined_rows
        if _command_kind(row.command) in {"pcm_status", "hw_params"}
        and (around_start <= _to_epoch(row.finished_at) <= around_end if latest_playback else True)
    ]
    status_rows = sorted(status_rows, key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id))

    pcm_running_event: dict[str, Any] | None = None
    hw_params_event: dict[str, Any] | None = None
    runtime_pcm_activation_events: list[dict[str, Any]] = []
    for row in status_rows:
        kind = _command_kind(row.command)
        if kind == "pcm_status":
            parsed = _parse_substream_status(row.stdout)
            state = str(parsed.get("state", "")).upper()
            runtime_pcm_activation_events.append(
                {
                    "timestamp": row.finished_at,
                    "command": row.command,
                    "kind": kind,
                    "state": state,
                    "owner_pid": str(parsed.get("owner_pid", "")),
                    "phase": row.phase,
                }
            )
            if pcm_running_event is None and latest_playback and state in {"RUNNING", "PREPARED", "XRUN"} and _to_epoch(row.finished_at) >= playback_start:
                pcm_running_event = {"timestamp": row.finished_at, "command": row.command, "state": state}
        elif kind == "hw_params":
            parsed = _parse_hw_params(row.stdout)
            status = str(parsed.get("status", "MISSING"))
            runtime_pcm_activation_events.append(
                {
                    "timestamp": row.finished_at,
                    "command": row.command,
                    "kind": kind,
                    "status": status,
                    "phase": row.phase,
                }
            )
            if hw_params_event is None and latest_playback and status == "AVAILABLE" and _to_epoch(row.finished_at) >= playback_start:
                hw_params_event = {"timestamp": row.finished_at, "command": row.command, "status": status}

    playback_stream = _parse_aplay_stream_line(f"{latest_playback.stdout}\n{latest_playback.stderr}") if latest_playback else {"observed": False}
    if pcm_running_event is None and latest_playback and bool(playback_stream.get("observed", False)) and playback_end > playback_start:
        pcm_running_event = {
            "timestamp": latest_playback.started_at,
            "command": latest_playback.command,
            "state": "RUNNING",
            "source": "playback_stream_line",
        }
        runtime_pcm_activation_events.append(
            {
                "timestamp": latest_playback.started_at,
                "command": latest_playback.command,
                "kind": "pcm_status",
                "state": "RUNNING",
                "owner_pid": "",
                "phase": latest_playback.phase,
                "source": "playback_stream_line",
            }
        )
    if hw_params_event is None and latest_playback and bool(playback_stream.get("observed", False)):
        hw_params_event = {
            "timestamp": latest_playback.started_at,
            "command": latest_playback.command,
            "status": "AVAILABLE",
            "source": "playback_stream_line",
            "rate_hz": int(playback_stream.get("rate_hz", 0) or 0),
            "sample_bits": int(playback_stream.get("sample_bits", 0) or 0),
            "channels": str(playback_stream.get("channels", "")),
        }
        runtime_pcm_activation_events.append(
            {
                "timestamp": latest_playback.started_at,
                "command": latest_playback.command,
                "kind": "hw_params",
                "status": "AVAILABLE",
                "phase": latest_playback.phase,
                "source": "playback_stream_line",
                "rate_hz": int(playback_stream.get("rate_hz", 0) or 0),
                "sample_bits": int(playback_stream.get("sample_bits", 0) or 0),
                "channels": str(playback_stream.get("channels", "")),
            }
        )

    soundwire_rows = [
        row
        for row in combined_rows
        if _command_kind(row.command) in {"soundwire_debugfs", "soundwire_bus"}
        and (around_start <= _to_epoch(row.finished_at) <= around_end if latest_playback else True)
    ]
    soundwire_rows = sorted(soundwire_rows, key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id))
    soundwire_activation_event: dict[str, Any] | None = None
    for row in soundwire_rows:
        text = f"{row.stdout}\n{row.stderr}".lower()
        if any(token in text for token in ("active", "enable", "attached", "up")):
            soundwire_activation_event = {"timestamp": row.finished_at, "command": row.command}
            break

    dapm_transition_event = None
    if (dapm_transitions or bool(dapm_raw_delta.get("changed", False)) or dapm_snapshot_pair_observed) and post_dapm:
        dapm_transition_event = {"timestamp": post_dapm.finished_at, "command": post_dapm.command}

    mixer_change_event = None
    if amixer_delta.get("changed") and post_amixer:
        mixer_change_event = {"timestamp": post_amixer.finished_at, "command": post_amixer.command}
    elif tinymix_delta.get("changed") and post_tinymix:
        mixer_change_event = {"timestamp": post_tinymix.finished_at, "command": post_tinymix.command}

    fe_be_event = None
    if post_pcm:
        fe_be_event = {"timestamp": post_pcm.finished_at, "command": post_pcm.command}

    signal_index: dict[str, dict[str, Any]] = {
        "playback_invoked": {
            "label": "Playback Command Executed",
            "observed": bool(latest_playback),
            "timestamp": latest_playback.started_at if latest_playback else "",
            "command": latest_playback.command if latest_playback else "",
        },
        "pcm_running": {
            "label": "PCM Lifecycle Activated",
            "observed": bool(pcm_running_event),
            "timestamp": str(_as_dict(pcm_running_event).get("timestamp", "")),
            "command": str(_as_dict(pcm_running_event).get("command", "")),
        },
        "hw_params_available": {
            "label": "hw_params Negotiation Observed",
            "observed": bool(hw_params_event),
            "timestamp": str(_as_dict(hw_params_event).get("timestamp", "")),
            "command": str(_as_dict(hw_params_event).get("command", "")),
        },
        "dapm_transition": {
            "label": "DAPM Widget Transition Observed",
            "observed": bool(dapm_transition_event),
            "timestamp": str(_as_dict(dapm_transition_event).get("timestamp", "")),
            "command": str(_as_dict(dapm_transition_event).get("command", "")),
        },
        "irq_audio_delta": {
            "label": "IRQ Audio Delta Observed",
            "observed": bool(irq_audio_active or irq_any_active),
            "timestamp": post_irq.finished_at if post_irq else "",
            "command": post_irq.command if post_irq else "",
            "evidence_type": "audio_or_runtime_irq_delta",
        },
        "mixer_state_change": {
            "label": "Mixer State Delta Observed",
            "observed": bool(amixer_delta.get("changed", False) or tinymix_delta.get("changed", False)),
            "timestamp": str(_as_dict(mixer_change_event).get("timestamp", "")),
            "command": str(_as_dict(mixer_change_event).get("command", "")),
        },
        "fe_be_observed": {
            "label": "FE/BE Correlation Observed",
            "observed": bool(
                fe_be_event
                and (
                    len(_as_list(fe_after.get("fe_be_links"))) > 0
                    or (
                        len(_as_list(fe_after.get("frontend_candidates"))) > 0
                        and len(_as_list(fe_after.get("backend_candidates"))) > 0
                    )
                )
            ),
            "timestamp": str(_as_dict(fe_be_event).get("timestamp", "")),
            "command": str(_as_dict(fe_be_event).get("command", "")),
        },
        "soundwire_activation": {
            "label": "SoundWire Runtime Activity Observed",
            "observed": bool(soundwire_activation_event),
            "timestamp": str(_as_dict(soundwire_activation_event).get("timestamp", "")),
            "command": str(_as_dict(soundwire_activation_event).get("command", "")),
        },
    }

    observed_nodes = [
        {"id": signal_id, **payload}
        for signal_id, payload in signal_index.items()
        if bool(_as_dict(payload).get("observed", False)) and str(_as_dict(payload).get("timestamp", "")).strip()
    ]
    observed_nodes.sort(key=lambda row: (_to_epoch(str(row.get("timestamp", ""))), str(row.get("id", ""))))
    activation_edges: list[dict[str, Any]] = []
    for idx in range(1, len(observed_nodes)):
        prev_node = _as_dict(observed_nodes[idx - 1])
        node = _as_dict(observed_nodes[idx])
        activation_edges.append(
            {
                "from": str(prev_node.get("id", "")),
                "to": str(node.get("id", "")),
                "relation": "precedes",
                "lag_ms": int(max(0.0, _to_epoch(str(node.get("timestamp", ""))) - _to_epoch(str(prev_node.get("timestamp", "")))) * 1000.0),
            }
        )

    activation_order_graph = {
        "artifact_name": "ACTIVATION_ORDER_GRAPH",
        "session_id": session_id,
        "lineage_id": lineage_id,
        "target_id": target_id,
        "generated_at": _utc_now_iso(),
        "nodes": sorted(
            [{"id": signal_id, **payload} for signal_id, payload in signal_index.items()],
            key=lambda row: str(row.get("id", "")),
        ),
        "edges": activation_edges,
        "summary": {
            "observed_node_count": len(observed_nodes),
            "edge_count": len(activation_edges),
        },
    }
    activation_order_graph["deterministic_fingerprint"] = stable_fingerprint(activation_order_graph)

    transition_events = [
        {
            "timestamp": row.finished_at,
            "phase": row.phase,
            "command": row.command,
            "command_kind": _command_kind(row.command),
            "execution_status": row.execution_status,
            "exit_code": row.exit_code,
            "duration_ms": int(max(0.0, _to_epoch(row.finished_at) - _to_epoch(row.started_at)) * 1000.0),
            "relative_to_playback_ms": (
                int((_to_epoch(row.finished_at) - playback_start) * 1000.0)
                if latest_playback
                else 0
            ),
        }
        for row in sorted(combined_rows, key=lambda item: (_to_epoch(item.finished_at), item.command, item.request_id))
        if (around_start <= _to_epoch(row.finished_at) <= around_end if latest_playback else True)
        and _command_kind(row.command) != "other"
    ]
    transition_events = transition_events[:4000]

    runtime_transition_timeline = {
        "artifact_name": "RUNTIME_TRANSITION_TIMELINE",
        "session_id": session_id,
        "lineage_id": lineage_id,
        "target_id": target_id,
        "generated_at": _utc_now_iso(),
        "playback_anchor": {
            "command": latest_playback.command if latest_playback else "",
            "started_at": latest_playback.started_at if latest_playback else "",
            "finished_at": latest_playback.finished_at if latest_playback else "",
        },
        "events": transition_events,
        "summary": {
            "event_count": len(transition_events),
            "window_rows_used": len(window_rows),
            "history_rows_used": len(combined_rows) - len(window_rows),
        },
    }
    runtime_transition_timeline["deterministic_fingerprint"] = stable_fingerprint(runtime_transition_timeline)

    required_signals = ("playback_invoked", "pcm_running", "hw_params_available", "dapm_transition", "irq_audio_delta")
    required_ok = len([sid for sid in required_signals if bool(_as_dict(signal_index.get(sid)).get("observed", False))])
    missing_required = sorted([sid for sid in required_signals if not bool(_as_dict(signal_index.get(sid)).get("observed", False))])

    ordering_chain = ["playback_invoked", "pcm_running", "hw_params_available", "dapm_transition", "irq_audio_delta"]
    propagation_delays_ms: list[dict[str, Any]] = []
    ordering_violation = False
    for idx in range(1, len(ordering_chain)):
        prev = _as_dict(signal_index.get(ordering_chain[idx - 1]))
        cur = _as_dict(signal_index.get(ordering_chain[idx]))
        if not (bool(prev.get("observed", False)) and bool(cur.get("observed", False))):
            continue
        prev_ts = _to_epoch(str(prev.get("timestamp", "")))
        cur_ts = _to_epoch(str(cur.get("timestamp", "")))
        lag_ms = int((cur_ts - prev_ts) * 1000.0)
        propagation_delays_ms.append({"from": ordering_chain[idx - 1], "to": ordering_chain[idx], "lag_ms": lag_ms})
        if lag_ms < 0:
            ordering_violation = True

    delayed_edges = [row for row in propagation_delays_ms if int(row.get("lag_ms", 0)) > 15000]
    widget_transition_counts: dict[str, int] = {}
    for row in dapm_transitions:
        widget = str(_as_dict(row).get("widget", ""))
        if not widget:
            continue
        widget_transition_counts[widget] = int(widget_transition_counts.get(widget, 0)) + 1
    oscillating_widgets = sorted(
        [
            widget
            for widget, count in widget_transition_counts.items()
            if count > 1 and widget not in {"DAPM_RAW_DELTA", "DAPM_SNAPSHOT_PAIR"}
        ]
    )

    race_conditions: list[str] = []
    if any(str(_as_dict(event).get("execution_status", "")) == "timeout" for event in transition_events):
        race_conditions.append("timeout_detected_in_playback_window")
    if ordering_violation:
        race_conditions.append("temporal_ordering_violation_detected")
    if not (pre_irq and post_irq):
        race_conditions.append("missing_irq_pre_post_pair")
    if not (pre_dapm and post_dapm):
        race_conditions.append("missing_dapm_pre_post_pair")

    if missing_required:
        convergence_certainty = "incomplete_convergence"
    elif oscillating_widgets:
        convergence_certainty = "oscillating_convergence"
    elif delayed_edges:
        convergence_certainty = "delayed_convergence"
    else:
        convergence_certainty = "stable_convergence"

    certainty_factor = {
        "stable_convergence": 1.0,
        "delayed_convergence": 0.85,
        "oscillating_convergence": 0.6,
        "incomplete_convergence": 0.3,
    }
    convergence_score = round(
        (required_ok / float(len(required_signals))) * float(certainty_factor.get(convergence_certainty, 0.0)),
        3,
    )
    convergence_classification = "PASS" if convergence_certainty in {"stable_convergence", "delayed_convergence"} else "FAIL_CLOSED"

    playback_convergence_timeline = {
        "artifact_name": "PLAYBACK_CONVERGENCE_TIMELINE",
        "session_id": session_id,
        "lineage_id": lineage_id,
        "target_id": target_id,
        "generated_at": _utc_now_iso(),
        "window_bounds": {
            "pre_window": _phase_bounds(window_rows, "p15_window_pre"),
            "live_window": _phase_bounds(window_rows, "p15_window_live"),
            "post_window": _phase_bounds(window_rows, "p15_window_post"),
        },
        "signals": [
            {
                "signal": sid,
                "observed": bool(_as_dict(payload).get("observed", False)),
                "timestamp": str(_as_dict(payload).get("timestamp", "")),
                "command": str(_as_dict(payload).get("command", "")),
            }
            for sid, payload in sorted(signal_index.items())
        ],
        "deltas": {
            "irq_audio_delta_count": int(_as_dict(irq_delta).get("audio_delta_count", 0)),
            "irq_any_delta_count": len(_as_list(irq_delta.get("rows"))),
            "dapm_transition_count": len(dapm_transitions),
            "dapm_raw_delta_changed": bool(dapm_raw_delta.get("changed", False)),
            "dapm_snapshot_pair_observed": bool(dapm_snapshot_pair_observed),
            "amixer_changed": bool(amixer_delta.get("changed", False)),
            "tinymix_changed": bool(tinymix_delta.get("changed", False)),
            "fe_be_delta": fe_delta,
        },
        "classification": convergence_classification,
        "convergence_certainty": convergence_certainty,
        "convergence_score": convergence_score,
        "missing_required_signals": missing_required,
        "oscillating_widgets": oscillating_widgets,
        "propagation_delays_ms": propagation_delays_ms,
        "delayed_edges": delayed_edges,
        "race_conditions": sorted(set(race_conditions)),
    }
    playback_convergence_timeline["deterministic_fingerprint"] = stable_fingerprint(playback_convergence_timeline)

    causal_steps = [
        ("playback_invoked", "pcm_running", "Playback invocation should activate PCM lifecycle."),
        ("pcm_running", "hw_params_available", "PCM activation should surface negotiated hw_params."),
        ("hw_params_available", "dapm_transition", "Negotiated stream should trigger DAPM route power transition."),
        ("dapm_transition", "irq_audio_delta", "Powered route should correlate with IRQ runtime activity."),
        ("irq_audio_delta", "soundwire_activation", "Audio IRQ activity should align with transport activation when present."),
    ]
    chain: list[dict[str, Any]] = []
    supported_edges = 0
    for src, dst, rationale in causal_steps:
        src_node = _as_dict(signal_index.get(src))
        dst_node = _as_dict(signal_index.get(dst))
        supported = bool(src_node.get("observed", False)) and bool(dst_node.get("observed", False))
        if supported:
            supported_edges += 1
        chain.append(
            {
                "from": src,
                "to": dst,
                "supported": supported,
                "from_timestamp": str(src_node.get("timestamp", "")),
                "to_timestamp": str(dst_node.get("timestamp", "")),
                "lag_ms": int(max(0.0, _to_epoch(str(dst_node.get("timestamp", ""))) - _to_epoch(str(src_node.get("timestamp", "")))) * 1000.0)
                if supported
                else -1,
                "rationale": rationale,
            }
        )

    runtime_causality_chain = {
        "artifact_name": "RUNTIME_CAUSALITY_CHAIN",
        "session_id": session_id,
        "lineage_id": lineage_id,
        "target_id": target_id,
        "generated_at": _utc_now_iso(),
        "chain": chain,
        "summary": {
            "edge_count": len(chain),
            "supported_edges": supported_edges,
            "causal_confidence": round(supported_edges / float(len(chain)), 3) if chain else 0.0,
            "classification": "PASS" if supported_edges == len(chain) else "FAIL_CLOSED",
        },
        "supporting_evidence": {
            "irq_delta": irq_delta,
            "dapm_transitions": dapm_transitions[:1200],
            "dapm_raw_delta": dapm_raw_delta,
            "amixer_delta": amixer_delta,
            "tinymix_delta": tinymix_delta,
            "playback_stream": playback_stream,
            "runtime_pcm_events": runtime_pcm_activation_events[:2400],
            "race_conditions": sorted(set(race_conditions)),
        },
    }
    runtime_causality_chain["deterministic_fingerprint"] = stable_fingerprint(runtime_causality_chain)

    alsa_runtime_lifecycle = {
        "artifact_name": "ALSA_RUNTIME_LIFECYCLE",
        "session_id": session_id,
        "lineage_id": lineage_id,
        "target_id": target_id,
        "generated_at": _utc_now_iso(),
        "playback_anchor": {
            "command": latest_playback.command if latest_playback else "",
            "started_at": latest_playback.started_at if latest_playback else "",
            "finished_at": latest_playback.finished_at if latest_playback else "",
            "duration_ms": int(max(0.0, playback_end - playback_start) * 1000.0) if latest_playback else 0,
        },
        "direct_stream_params": playback_stream,
        "hw_params_transitions": [row for row in runtime_pcm_activation_events if str(_as_dict(row).get("kind", "")) == "hw_params"][:1200],
        "pcm_lifecycle_transitions": [row for row in runtime_pcm_activation_events if str(_as_dict(row).get("kind", "")) == "pcm_status"][:1200],
        "fe_be_activation_ordering": {
            "before": {
                "frontend_count": len(_as_list(fe_before.get("frontend_candidates"))),
                "backend_count": len(_as_list(fe_before.get("backend_candidates"))),
                "link_count": len(_as_list(fe_before.get("fe_be_links"))),
            },
            "after": {
                "frontend_count": len(_as_list(fe_after.get("frontend_candidates"))),
                "backend_count": len(_as_list(fe_after.get("backend_candidates"))),
                "link_count": len(_as_list(fe_after.get("fe_be_links"))),
            },
            "delta": fe_delta,
        },
        "dapm_propagation_timing": {
            "pre_timestamp": pre_dapm.finished_at if pre_dapm else "",
            "post_timestamp": post_dapm.finished_at if post_dapm else "",
            "transition_count": len(dapm_transitions),
            "snapshot_pair_observed": bool(dapm_snapshot_pair_observed),
            "raw_delta": dapm_raw_delta,
        },
        "irq_window_correlation": {
            "pre_timestamp": pre_irq.finished_at if pre_irq else "",
            "post_timestamp": post_irq.finished_at if post_irq else "",
            "audio_delta_count": int(_as_dict(irq_delta).get("audio_delta_count", 0)),
            "any_delta_count": len(_as_list(irq_delta.get("rows"))),
        },
        "propagation_delays_ms": propagation_delays_ms,
        "race_conditions": sorted(set(race_conditions)),
        "convergence_certainty": convergence_certainty,
    }
    alsa_runtime_lifecycle["deterministic_fingerprint"] = stable_fingerprint(alsa_runtime_lifecycle)

    return {
        "activation_order_graph": activation_order_graph,
        "runtime_transition_timeline": runtime_transition_timeline,
        "playback_convergence_timeline": playback_convergence_timeline,
        "runtime_causality_chain": runtime_causality_chain,
        "alsa_runtime_lifecycle": alsa_runtime_lifecycle,
        "signal_index": signal_index,
    }


def _run_self_tests() -> dict[str, Any]:
    tests: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        tests.append({"test": name, "ok": bool(ok), "detail": detail})

    pcm = _parse_proc_pcm_rows("0-0: MultiMedia1 : MultiMedia1 Playback : playback 1")
    check("parse_proc_pcm_rows", len(pcm) == 1 and pcm[0]["card_index"] == 0, json.dumps(pcm[:1], sort_keys=True))

    dapm = _parse_dapm_line("RX0: On  in 1 out 2  widget-type mixer")
    check(
        "parse_dapm_line",
        bool(dapm) and dapm.get("widget") == "RX0" and dapm.get("status") == "ON" and dapm.get("in_count") == 1,
        json.dumps(dapm, sort_keys=True),
    )

    hw = _parse_hw_params("closed")
    check("parse_hw_params_closed", str(hw.get("status")) == "CLOSED", json.dumps(hw, sort_keys=True))

    status = _parse_substream_status("state: RUNNING\nowner_pid   : 123\n")
    check("parse_substream_status", status.get("state") == "RUNNING", json.dumps(status, sort_keys=True))

    sw = _sanitize_ls_entries("master-1-0\nmaster 1\n")
    check("sanitize_ls_entries", sw == ["master-1-0"], json.dumps(sw, sort_keys=True))

    passed = len([t for t in tests if bool(t.get("ok", False))])
    payload = {
        "artifact_name": "P15_SELF_TESTS",
        "generated_at": _utc_now_iso(),
        "tests": tests,
        "summary": {
            "total": len(tests),
            "passed": passed,
            "failed": len(tests) - passed,
            "classification": "PASS" if passed == len(tests) else "FAIL_CLOSED",
        },
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="P1.5 runtime evidence deepening")
    parser.add_argument("--bridge-root", default=str((REPO_ROOT.parent / "bridge").resolve()))
    parser.add_argument("--output-dir", default=str((REPO_ROOT.parent / "docs/operations/transport").resolve()))
    parser.add_argument("--scripts-dir", default=str((REPO_ROOT / "scripts").resolve()))
    parser.add_argument("--target-id", default="UNKNOWN_TARGET")
    parser.add_argument("--session-id", default="p15_runtime_evidence_deepening_v1")
    parser.add_argument("--lineage-id", default="p15_runtime_evidence_deepening_lineage_v1")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--chunk-size", type=int, default=18)
    parser.add_argument("--enable-playback-window-capture", action="store_true")
    parser.add_argument("--playback-window-candidate-limit", type=int, default=4)
    parser.add_argument("--playback-device-prefix", default="plughw")
    parser.add_argument("--target-playback-path", default="/data/local/tmp/aura/audio/speaker_validation_48k_stereo.wav")
    parser.add_argument("--playback-window-timeout-seconds", type=int, default=180)
    parser.add_argument("--skip-capture", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    bridge_root = _resolve_workspace_path(Path(args.bridge_root).expanduser())
    output_dir = _resolve_workspace_path(Path(args.output_dir).expanduser())
    scripts_dir = _resolve_workspace_path(Path(args.scripts_dir).expanduser())
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        payload = _run_self_tests()
        _write_json(output_dir / "p15_self_tests.json", payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if str(_as_dict(payload.get("summary")).get("classification", "")) == "PASS" else 2

    submit_script = scripts_dir / "linux-bridge-submit.sh"

    self_tests = _run_self_tests()

    foundation_audit = _module_audit(scripts_dir, REPO_ROOT.parent)
    foundation_audit.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    foundation_audit["deterministic_fingerprint"] = stable_fingerprint(foundation_audit)

    reusable_parsers = _reusable_parsers(scripts_dir)
    reusable_parsers.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    reusable_parsers["deterministic_fingerprint"] = stable_fingerprint(reusable_parsers)

    brittle_assumptions = _brittle_assumptions(scripts_dir)
    brittle_assumptions.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    brittle_assumptions["deterministic_fingerprint"] = stable_fingerprint(brittle_assumptions)

    history_rows_before_capture = _load_bridge_history_rows(bridge_root)
    timing_capture_audit_pre = _build_timing_capture_audit(history_rows_before_capture, label="pre_capture_history")
    timing_capture_audit_pre.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    timing_capture_audit_pre["deterministic_fingerprint"] = stable_fingerprint(timing_capture_audit_pre)

    capture_phases: list[dict[str, Any]] = []
    capture_rows: list[TraceRow] = []
    window_rows: list[TraceRow] = []
    window_capture_metadata: dict[str, Any] = {
        "artifact_name": "PLAYBACK_WINDOW_CAPTURE_METADATA",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "target_id": args.target_id,
        "requested": bool(args.enable_playback_window_capture),
        "enabled": bool(args.enable_playback_window_capture and (not args.skip_capture)),
        "candidate_devices": [],
        "playback_attempts": [],
        "selected_playback_command": "",
        "selected_playback_device": "",
        "target_playback_path": str(args.target_playback_path).strip(),
        "pre_phase_count": 0,
        "live_phase_count": 0,
        "post_phase_count": 0,
        "classification": "NOT_REQUESTED" if not args.enable_playback_window_capture else "PENDING",
    }

    if not args.skip_capture:
        phase1_commands = [
            "cat /proc/asound/cards",
            "cat /proc/asound/pcm",
            "head -n 200 /proc/interrupts",
            "dmesg | tail -200",
            "amixer",
            "tinymix",
            "ls /sys/kernel/debug",
            "ls /sys/kernel/debug/asoc",
            "ls /sys/kernel/debug/soundwire",
            "ls /sys/bus/soundwire/devices",
        ]
        phase1 = _run_bridge_submit(
            submit_script=submit_script,
            bridge_root=bridge_root,
            output_dir=output_dir,
            commands=phase1_commands,
            timeout_seconds=args.timeout_seconds,
            execution_mode="governed_read_only",
            allow_write_ops=False,
            phase="p15_phase1_baseline",
        )
        capture_phases.append(phase1)
        rows_phase1 = _collect_rows_from_phases([phase1])
        latest_phase1 = _latest_by_command(rows_phase1)

        asoc_row = latest_phase1.get("ls /sys/kernel/debug/asoc")
        pcm_row = latest_phase1.get("cat /proc/asound/pcm")
        sw_master_row = latest_phase1.get("ls /sys/kernel/debug/soundwire")
        sw_bus_row = latest_phase1.get("ls /sys/bus/soundwire/devices")
        asoc_nodes = _extract_asoc_cards(asoc_row.stdout if isinstance(asoc_row, TraceRow) else "")[:6]
        pcm_rows = _parse_proc_pcm_rows(pcm_row.stdout if isinstance(pcm_row, TraceRow) else "")[:10]
        sw_masters = _sanitize_ls_entries(sw_master_row.stdout if isinstance(sw_master_row, TraceRow) else "")[:6]
        sw_bus_devices = _sanitize_ls_entries(sw_bus_row.stdout if isinstance(sw_bus_row, TraceRow) else "")[:10]

        phase2_commands: list[str] = []
        for card in asoc_nodes:
            phase2_commands.extend(
                [
                    f"ls /sys/kernel/debug/asoc/{card}",
                    f"ls /sys/kernel/debug/asoc/{card}/dapm",
                    f"cat /sys/kernel/debug/asoc/{card}/dapm/*",
                    f"cat /sys/kernel/debug/asoc/{card}/dai_links",
                    f"cat /sys/kernel/debug/asoc/{card}/codecs",
                ]
            )

        for entry in pcm_rows:
            card = int(_as_dict(entry).get("card_index", -1))
            dev = int(_as_dict(entry).get("device_index", -1))
            direction = str(_as_dict(entry).get("direction", ""))
            if direction not in {"playback", "capture"}:
                continue
            suffix = "p" if direction == "playback" else "c"
            phase2_commands.extend(
                [
                    f"cat /proc/asound/card{card}/pcm{dev}{suffix}/info",
                    f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/status",
                    f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/hw_params",
                    f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/info",
                    f"cat /proc/asound/card{card}/pcm{dev}{suffix}/sub0/sw_params",
                ]
            )

        for master in sw_masters:
            phase2_commands.append(f"ls /sys/kernel/debug/soundwire/{master}")

        for dev in sw_bus_devices:
            phase2_commands.extend(
                [
                    f"cat /sys/bus/soundwire/devices/{dev}/modalias",
                    f"cat /sys/bus/soundwire/devices/{dev}/name",
                    f"cat /sys/bus/soundwire/devices/{dev}/status",
                    f"cat /sys/bus/soundwire/devices/{dev}/power/control",
                ]
            )

        phase2_commands = sorted(dict.fromkeys(phase2_commands))
        phase2_batches = _chunked_submit(
            submit_script=submit_script,
            bridge_root=bridge_root,
            output_dir=output_dir,
            commands=phase2_commands,
            timeout_seconds=args.timeout_seconds,
            chunk_size=args.chunk_size,
            phase_prefix="p15_phase2_dynamic",
        )
        capture_phases.extend(phase2_batches)

        rows_phase2 = _collect_rows_from_phases(phase2_batches)
        latest_phase2 = _latest_by_command(rows_phase2)

        phase3_commands: list[str] = []
        for master in sw_masters:
            ls_cmd = f"ls /sys/kernel/debug/soundwire/{master}"
            ls_row = latest_phase2.get(ls_cmd)
            if not ls_row:
                continue
            names = _sanitize_ls_entries(ls_row.stdout)[:8]
            for name in names:
                phase3_commands.append(f"cat /sys/kernel/debug/soundwire/{master}/{name}")

        phase3_commands = sorted(dict.fromkeys(phase3_commands))
        phase3_batches = _chunked_submit(
            submit_script=submit_script,
            bridge_root=bridge_root,
            output_dir=output_dir,
            commands=phase3_commands,
            timeout_seconds=args.timeout_seconds,
            chunk_size=args.chunk_size,
            phase_prefix="p15_phase3_soundwire",
        )
        capture_phases.extend(phase3_batches)
        rows_phase3 = _collect_rows_from_phases(phase3_batches)

        if args.enable_playback_window_capture:
            playback_seed_rows = sorted(
                history_rows_before_capture + rows_phase1 + rows_phase2 + rows_phase3,
                key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id),
            )
            playback_plan = _build_playback_candidates(
                pcm_rows=pcm_rows,
                history_rows=playback_seed_rows,
                playback_device_prefix=str(args.playback_device_prefix).strip(),
                fallback_target_path=str(args.target_playback_path).strip(),
                candidate_limit=max(1, int(args.playback_window_candidate_limit)),
            )
            candidate_devices = _as_list(playback_plan.get("candidates"))
            target_path = str(args.target_playback_path).strip() or str(playback_plan.get("target_path", "")).strip()
            if not target_path:
                target_path = "/data/local/tmp/aura/audio/speaker_validation_48k_stereo.wav"
            window_capture_metadata["candidate_devices"] = candidate_devices
            window_capture_metadata["target_playback_path"] = target_path

            snapshot_commands = _build_window_snapshot_commands(
                asoc_nodes=asoc_nodes,
                pcm_rows=pcm_rows,
                sw_masters=sw_masters,
                sw_bus_devices=sw_bus_devices,
            )
            critical_commands = _build_window_critical_commands(asoc_nodes=asoc_nodes, pcm_rows=pcm_rows)

            pre_critical = _run_bridge_submit(
                submit_script=submit_script,
                bridge_root=bridge_root,
                output_dir=output_dir,
                commands=critical_commands,
                timeout_seconds=args.timeout_seconds,
                execution_mode="governed_read_only",
                allow_write_ops=False,
                phase="p15_window_pre_critical",
            )
            capture_phases.append(pre_critical)

            pre_batches = _chunked_submit(
                submit_script=submit_script,
                bridge_root=bridge_root,
                output_dir=output_dir,
                commands=snapshot_commands,
                timeout_seconds=args.timeout_seconds,
                chunk_size=args.chunk_size,
                phase_prefix="p15_window_pre_full",
            )
            capture_phases.extend(pre_batches)
            window_capture_metadata["pre_phase_count"] = 1 + len(pre_batches)

            live_count = 0
            for idx, device in enumerate(candidate_devices, start=1):
                playback_command = f"AURA_PLAYBACK_APLAY {device} {target_path}"
                live_phase = _run_bridge_submit(
                    submit_script=submit_script,
                    bridge_root=bridge_root,
                    output_dir=output_dir,
                    commands=[playback_command],
                    timeout_seconds=max(args.timeout_seconds, args.playback_window_timeout_seconds),
                    execution_mode="governed_write_approved",
                    allow_write_ops=True,
                    phase=f"p15_window_live_{idx}",
                )
                capture_phases.append(live_phase)
                live_count += 1
                live_rows = _collect_rows_from_phases([live_phase])
                playback_row = next((row for row in live_rows if row.command.startswith("AURA_PLAYBACK_APLAY ")), None)
                success = bool(playback_row and playback_row.execution_status == "executed" and int(playback_row.exit_code) == 0)
                window_capture_metadata["playback_attempts"].append(
                    {
                        "attempt_index": idx,
                        "command": playback_command,
                        "success": success,
                        "execution_status": playback_row.execution_status if playback_row else "",
                        "exit_code": int(playback_row.exit_code) if playback_row else -1,
                        "response_path": playback_row.response_path if playback_row else "",
                    }
                )
                if success:
                    window_capture_metadata["selected_playback_command"] = playback_command
                    window_capture_metadata["selected_playback_device"] = str(device)
                    break
            window_capture_metadata["live_phase_count"] = live_count

            post_critical = _run_bridge_submit(
                submit_script=submit_script,
                bridge_root=bridge_root,
                output_dir=output_dir,
                commands=critical_commands,
                timeout_seconds=args.timeout_seconds,
                execution_mode="governed_read_only",
                allow_write_ops=False,
                phase="p15_window_post_critical",
            )
            capture_phases.append(post_critical)

            post_batches = _chunked_submit(
                submit_script=submit_script,
                bridge_root=bridge_root,
                output_dir=output_dir,
                commands=snapshot_commands,
                timeout_seconds=args.timeout_seconds,
                chunk_size=args.chunk_size,
                phase_prefix="p15_window_post_full",
            )
            capture_phases.extend(post_batches)
            window_capture_metadata["post_phase_count"] = 1 + len(post_batches)

            window_capture_metadata["classification"] = (
                "CAPTURE_READY" if str(window_capture_metadata.get("selected_playback_command", "")).strip() else "FAIL_CLOSED"
            )

    capture_rows = _collect_rows_from_phases(capture_phases)
    window_rows = [row for row in capture_rows if str(row.phase).startswith("p15_window_")]
    history_rows = _load_bridge_history_rows(bridge_root)
    combined_rows = sorted(capture_rows + history_rows, key=lambda row: (_to_epoch(row.finished_at), row.command, row.request_id))

    board_specific_assumptions = _build_board_specific_assumptions(
        scripts_dir=scripts_dir,
        brittle_assumptions=brittle_assumptions,
        reusable_parsers=reusable_parsers,
        combined_rows=combined_rows,
    )
    board_specific_assumptions.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    board_specific_assumptions["deterministic_fingerprint"] = stable_fingerprint(board_specific_assumptions)

    timing_capture_audit_post = _build_timing_capture_audit(combined_rows, label="post_capture_combined")
    timing_capture_audit_post.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    timing_capture_audit_post["deterministic_fingerprint"] = stable_fingerprint(timing_capture_audit_post)

    playback_window_capture_audit = {
        "artifact_name": "PLAYBACK_WINDOW_CAPTURE_AUDIT",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "target_id": args.target_id,
        "generated_at": _utc_now_iso(),
        "pre_capture_audit": timing_capture_audit_pre,
        "post_capture_audit": timing_capture_audit_post,
        "window_capture_metadata": window_capture_metadata,
    }
    playback_window_capture_audit["deterministic_fingerprint"] = stable_fingerprint(playback_window_capture_audit)

    latest = _latest_by_command(combined_rows)

    cards_raw = str(latest.get("cat /proc/asound/cards").stdout if latest.get("cat /proc/asound/cards") else "")
    pcm_raw = str(latest.get("cat /proc/asound/pcm").stdout if latest.get("cat /proc/asound/pcm") else "")
    cards = _parse_proc_cards(cards_raw)
    pcm_rows = _parse_proc_pcm_rows(pcm_raw)

    dapm_rows = [row for row in combined_rows if row.command.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in row.command]
    dapm_snapshots: list[dict[str, Any]] = []
    for row in sorted(dapm_rows, key=lambda item: (_to_epoch(item.finished_at), item.command)):
        match = re.search(r"/sys/kernel/debug/asoc/([^/]+)/", row.command)
        card = match.group(1) if match else "UNKNOWN_CARD"
        state = _parse_dapm_snapshot(row.stdout)
        dapm_snapshots.append(
            {
                "card": card,
                "command": row.command,
                "timestamp": row.finished_at,
                "widget_count": len(state),
                "on_count": len([v for v in state.values() if str(_as_dict(v).get("status", "")) == "ON"]),
                "off_count": len([v for v in state.values() if str(_as_dict(v).get("status", "")) == "OFF"]),
                "state": state,
            }
        )

    widget_rows: list[dict[str, Any]] = []
    for snap in dapm_snapshots:
        card = str(_as_dict(snap).get("card", ""))
        ts = str(_as_dict(snap).get("timestamp", ""))
        command = str(_as_dict(snap).get("command", ""))
        for widget, payload in sorted(_as_dict(snap).get("state", {}).items()):
            row = _as_dict(payload)
            widget_rows.append(
                {
                    "card": card,
                    "timestamp": ts,
                    "command": command,
                    "widget": widget,
                    "status": str(row.get("status", "UNKNOWN")),
                    "in_count": _to_int(row.get("in_count"), default=-1),
                    "out_count": _to_int(row.get("out_count"), default=-1),
                    "widget_type": str(row.get("widget_type", "")),
                    "raw": str(row.get("raw", "")),
                }
            )

    direct_dapm_runtime_state = {
        "artifact_name": "DIRECT_DAPM_RUNTIME_STATE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "target_id": args.target_id,
        "generated_at": _utc_now_iso(),
        "cards_discovered": sorted(set(str(row.get("card", "")) for row in widget_rows if str(row.get("card", "")))),
        "snapshot_count": len(dapm_snapshots),
        "widgets": sorted(widget_rows, key=lambda row: (str(row.get("card", "")), str(row.get("widget", "")), str(row.get("timestamp", ""))))[:12000],
        "summary": {
            "widget_total": len(widget_rows),
            "on_total": len([row for row in widget_rows if str(row.get("status", "")) == "ON"]),
            "off_total": len([row for row in widget_rows if str(row.get("status", "")) == "OFF"]),
            "direct_observed": bool(widget_rows),
        },
    }
    direct_dapm_runtime_state["deterministic_fingerprint"] = stable_fingerprint(direct_dapm_runtime_state)

    route_activation_timeline = {
        "artifact_name": "ROUTE_ACTIVATION_TIMELINE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "events": [
            {
                "timestamp": str(snap.get("timestamp", "")),
                "card": str(snap.get("card", "")),
                "command": str(snap.get("command", "")),
                "on_count": int(snap.get("on_count", 0) or 0),
                "off_count": int(snap.get("off_count", 0) or 0),
                "widget_count": int(snap.get("widget_count", 0) or 0),
            }
            for snap in sorted(dapm_snapshots, key=lambda row: (str(row.get("timestamp", "")), str(row.get("card", ""))))
        ],
    }
    route_activation_timeline["deterministic_fingerprint"] = stable_fingerprint(route_activation_timeline)

    power_graph_nodes: dict[str, dict[str, Any]] = {}
    power_graph_edges: list[dict[str, Any]] = []
    snapshots_by_card: dict[str, list[dict[str, Any]]] = {}
    for snap in dapm_snapshots:
        snapshots_by_card.setdefault(str(_as_dict(snap).get("card", "UNKNOWN")), []).append(_as_dict(snap))
    for card, snaps in sorted(snapshots_by_card.items()):
        ordered = sorted(snaps, key=lambda row: _to_epoch(str(_as_dict(row).get("timestamp", ""))))
        prev_state: dict[str, dict[str, Any]] = {}
        for snap in ordered:
            state = _as_dict(snap.get("state"))
            for widget, payload in state.items():
                wid = f"{card}:{widget}"
                power_graph_nodes[wid] = {
                    "id": wid,
                    "card": card,
                    "widget": widget,
                    "status": str(_as_dict(payload).get("status", "UNKNOWN")),
                }
                old = _as_dict(prev_state.get(widget))
                old_status = str(old.get("status", "UNKNOWN"))
                new_status = str(_as_dict(payload).get("status", "UNKNOWN"))
                if old and old_status != new_status:
                    power_graph_edges.append(
                        {
                            "from": f"{wid}:{old_status}",
                            "to": f"{wid}:{new_status}",
                            "timestamp": str(_as_dict(snap).get("timestamp", "")),
                            "relation": "state_transition",
                        }
                    )
            prev_state = state

    runtime_widget_power_graph = {
        "artifact_name": "RUNTIME_WIDGET_POWER_GRAPH",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "nodes": sorted(power_graph_nodes.values(), key=lambda row: str(row.get("id", ""))),
        "edges": sorted(power_graph_edges, key=lambda row: (str(row.get("timestamp", "")), str(row.get("from", "")), str(row.get("to", "")))),
    }
    runtime_widget_power_graph["deterministic_fingerprint"] = stable_fingerprint(runtime_widget_power_graph)

    pcm_lifecycle_rows: list[dict[str, Any]] = []
    sub_pattern = re.compile(r"^cat /proc/asound/card(\d+)/pcm(\d+)([pc])/sub(\d+)/(status|hw_params|info|sw_params)$")
    sub_map: dict[tuple[int, int, str, int], dict[str, Any]] = {}
    for row in combined_rows:
        match = sub_pattern.match(row.command)
        if not match:
            continue
        card = int(match.group(1))
        dev = int(match.group(2))
        direction = "playback" if match.group(3) == "p" else "capture"
        sub = int(match.group(4))
        kind = match.group(5)
        key = (card, dev, direction, sub)
        obj = sub_map.setdefault(
            key,
            {
                "card_index": card,
                "device_index": dev,
                "direction": direction,
                "substream": sub,
                "status": {},
                "hw_params": {},
                "info": "",
                "sw_params": "",
                "last_update": "",
            },
        )
        if kind == "status":
            obj["status"] = _parse_substream_status(row.stdout)
        elif kind == "hw_params":
            obj["hw_params"] = _parse_hw_params(row.stdout)
        elif kind == "info":
            obj["info"] = row.stdout
        elif kind == "sw_params":
            obj["sw_params"] = row.stdout
        obj["last_update"] = max(str(obj.get("last_update", "")), str(row.finished_at))

    for key in sorted(sub_map.keys()):
        entry = _as_dict(sub_map[key])
        pcm_lifecycle_rows.append(entry)

    runtime_pcm_lifecycle = {
        "artifact_name": "RUNTIME_PCM_LIFECYCLE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "pcm_entries": pcm_rows,
        "substreams": pcm_lifecycle_rows,
        "summary": {
            "pcm_count": len(pcm_rows),
            "substream_count": len(pcm_lifecycle_rows),
            "hw_params_available": len([row for row in pcm_lifecycle_rows if str(_as_dict(row.get("hw_params")).get("status", "")) == "AVAILABLE"]),
            "hw_params_closed": len([row for row in pcm_lifecycle_rows if str(_as_dict(row.get("hw_params")).get("status", "")) == "CLOSED"]),
        },
    }
    runtime_pcm_lifecycle["deterministic_fingerprint"] = stable_fingerprint(runtime_pcm_lifecycle)

    soundwire_runtime_activation = {
        "artifact_name": "SOUNDWIRE_RUNTIME_ACTIVATION",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        **_parse_soundwire_rows(combined_rows),
    }
    soundwire_runtime_activation["deterministic_fingerprint"] = stable_fingerprint(soundwire_runtime_activation)

    fe_be_map = _classify_fe_be(pcm_rows, [str(row.get("widget", "")) for row in widget_rows])
    fe_be_transition_map = {
        "artifact_name": "FE_BE_TRANSITION_MAP",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        **fe_be_map,
    }
    fe_be_transition_map["deterministic_fingerprint"] = stable_fingerprint(fe_be_transition_map)

    runtime_topology_inference = {
        "artifact_name": "RUNTIME_TOPOLOGY_INFERENCE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "cards": cards,
        "pcm": pcm_rows,
        "fe_be": {
            "frontend_count": len(_as_list(fe_be_map.get("frontend_candidates"))),
            "backend_count": len(_as_list(fe_be_map.get("backend_candidates"))),
            "link_count": len(_as_list(fe_be_map.get("fe_be_links"))),
        },
        "dapm": {
            "card_count": len(_as_list(direct_dapm_runtime_state.get("cards_discovered"))),
            "widget_total": int(_as_dict(direct_dapm_runtime_state.get("summary")).get("widget_total", 0)),
            "on_total": int(_as_dict(direct_dapm_runtime_state.get("summary")).get("on_total", 0)),
        },
        "soundwire": {
            "master_count": len(_as_list(soundwire_runtime_activation.get("masters"))),
            "bus_device_count": len(_as_list(soundwire_runtime_activation.get("bus_devices"))),
            "active_endpoint_count": int(soundwire_runtime_activation.get("active_endpoint_count", 0) or 0),
        },
    }
    runtime_topology_inference["deterministic_fingerprint"] = stable_fingerprint(runtime_topology_inference)

    temporal_artifacts = _build_temporal_artifacts(
        window_rows=window_rows,
        combined_rows=combined_rows,
        session_id=args.session_id,
        lineage_id=args.lineage_id,
        target_id=args.target_id,
    )
    activation_order_graph = _as_dict(temporal_artifacts.get("activation_order_graph"))
    runtime_transition_timeline = _as_dict(temporal_artifacts.get("runtime_transition_timeline"))
    playback_convergence_timeline = _as_dict(temporal_artifacts.get("playback_convergence_timeline"))
    runtime_causality_chain = _as_dict(temporal_artifacts.get("runtime_causality_chain"))
    alsa_runtime_lifecycle = _as_dict(temporal_artifacts.get("alsa_runtime_lifecycle"))
    temporal_signal_index = _as_dict(temporal_artifacts.get("signal_index"))

    runtime_capability_matrix = _build_runtime_capability_matrix(
        combined_rows=combined_rows,
        pcm_rows=pcm_rows,
        fe_be_map=fe_be_map,
        soundwire_runtime_activation=soundwire_runtime_activation,
        temporal_signal_index=temporal_signal_index,
    )
    runtime_capability_matrix.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    runtime_capability_matrix["deterministic_fingerprint"] = stable_fingerprint(runtime_capability_matrix)

    evidence_source_negotiation = _build_evidence_source_negotiation(capability_matrix=runtime_capability_matrix)
    evidence_source_negotiation.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    evidence_source_negotiation["deterministic_fingerprint"] = stable_fingerprint(evidence_source_negotiation)

    adaptive_capture_strategy = _build_adaptive_capture_strategy(
        capability_matrix=runtime_capability_matrix,
        evidence_negotiation=evidence_source_negotiation,
    )
    adaptive_capture_strategy.update({"session_id": args.session_id, "lineage_id": args.lineage_id, "target_id": args.target_id})
    adaptive_capture_strategy["deterministic_fingerprint"] = stable_fingerprint(adaptive_capture_strategy)

    latest_playback = _find_latest_successful_playback(combined_rows)
    playback_epoch_start = _to_epoch(latest_playback.started_at) if latest_playback else 0.0
    playback_epoch_end = _to_epoch(latest_playback.finished_at) if latest_playback else 0.0

    dapm_before = None
    dapm_after = None
    irq_before = None
    irq_after = None
    if latest_playback:
        for row in combined_rows:
            if row.command.startswith("cat /sys/kernel/debug/asoc/") and "/dapm" in row.command:
                t = _to_epoch(row.finished_at)
                if t <= playback_epoch_start:
                    dapm_before = row
                elif t >= playback_epoch_end and dapm_after is None:
                    dapm_after = row
            if row.command == "head -n 200 /proc/interrupts":
                t = _to_epoch(row.finished_at)
                if t <= playback_epoch_start:
                    irq_before = row
                elif t >= playback_epoch_end and irq_after is None:
                    irq_after = row

    delayed_widgets: list[str] = []
    dapm_delta = {"rows": [], "audio_rows": [], "audio_delta_count": 0, "irq_active": False}
    if dapm_before and dapm_after:
        b_state = _parse_dapm_snapshot(dapm_before.stdout)
        a_state = _parse_dapm_snapshot(dapm_after.stdout)
        for widget in sorted(set(b_state.keys()) | set(a_state.keys())):
            b_status = str(_as_dict(b_state.get(widget)).get("status", "UNKNOWN"))
            a_status = str(_as_dict(a_state.get(widget)).get("status", "UNKNOWN"))
            if b_status != "ON" and a_status == "ON":
                delayed_widgets.append(widget)

    if irq_before and irq_after:
        dapm_delta = _irq_delta(irq_before.stdout, irq_after.stdout)

    timing_events = [
        {
            "timestamp": row.finished_at,
            "command": row.command,
            "execution_status": row.execution_status,
            "exit_code": row.exit_code,
            "duration_ms": int(max(0.0, (_to_epoch(row.finished_at) - _to_epoch(row.started_at))) * 1000.0),
            "phase": row.phase,
        }
        for row in combined_rows
        if row.command
    ]
    timing_events = sorted(timing_events, key=lambda row: (str(row.get("timestamp", "")), str(row.get("command", ""))))[-1200:]

    runtime_timing_intelligence = {
        "artifact_name": "RUNTIME_TIMING_INTELLIGENCE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "latest_successful_playback": {
            "command": latest_playback.command if latest_playback else "",
            "started_at": latest_playback.started_at if latest_playback else "",
            "finished_at": latest_playback.finished_at if latest_playback else "",
            "duration_ms": int(max(0.0, playback_epoch_end - playback_epoch_start) * 1000.0) if latest_playback else 0,
        },
        "activation_ordering": timing_events,
        "convergence_timing": {
            "playback_to_post_dapm_ms": int(max(0.0, _to_epoch(dapm_after.finished_at) - playback_epoch_end) * 1000.0) if latest_playback and dapm_after else -1,
            "playback_to_post_irq_ms": int(max(0.0, _to_epoch(irq_after.finished_at) - playback_epoch_end) * 1000.0) if latest_playback and irq_after else -1,
        },
        "delayed_widget_enable_detection": {
            "detected": bool(delayed_widgets),
            "widget_count": len(delayed_widgets),
            "widgets": delayed_widgets[:200],
        },
        "irq_runtime_correlation": dapm_delta,
    }
    runtime_timing_intelligence["deterministic_fingerprint"] = stable_fingerprint(runtime_timing_intelligence)

    window_required = bool(window_capture_metadata.get("enabled", False))
    strict_checks = {
        "direct_dapm_runtime_observed": bool(_as_dict(direct_dapm_runtime_state.get("summary")).get("direct_observed", False)),
        "direct_pcm_lifecycle_observed": bool(_as_dict(runtime_pcm_lifecycle.get("summary")).get("substream_count", 0)),
        "direct_hw_params_observed": bool(_as_dict(_as_dict(temporal_signal_index.get("hw_params_available"))).get("observed", False)),
        "direct_soundwire_runtime_observed": (
            bool(_as_dict(_as_dict(temporal_signal_index.get("soundwire_activation"))).get("observed", False))
            or len(_as_list(soundwire_runtime_activation.get("masters"))) > 0
            or len(_as_list(soundwire_runtime_activation.get("bus_devices"))) > 0
        ),
        "direct_irq_playback_delta_observed": bool(_as_dict(_as_dict(temporal_signal_index.get("irq_audio_delta"))).get("observed", False)),
        "activation_ordering_observed": (
            bool(_as_dict(_as_dict(temporal_signal_index.get("playback_invoked"))).get("observed", False))
            and bool(_as_dict(_as_dict(temporal_signal_index.get("pcm_running"))).get("observed", False))
            and bool(_as_dict(_as_dict(temporal_signal_index.get("dapm_transition"))).get("observed", False))
        ),
        "playback_window_pre_snapshot_observed": (not window_required) or int(window_capture_metadata.get("pre_phase_count", 0)) > 0,
        "playback_window_live_observed": (not window_required) or bool(str(window_capture_metadata.get("selected_playback_command", "")).strip()),
        "playback_window_post_snapshot_observed": (not window_required) or int(window_capture_metadata.get("post_phase_count", 0)) > 0,
        "temporal_artifacts_generated": bool(_as_list(activation_order_graph.get("nodes"))) and bool(_as_list(runtime_transition_timeline.get("events"))),
        "playback_convergence_observed": str(playback_convergence_timeline.get("classification", "FAIL_CLOSED")) == "PASS",
        "evidence_source_negotiation_pass": str(evidence_source_negotiation.get("classification", "FAIL_CLOSED")) == "PASS",
        "adaptive_capture_strategy_pass": str(adaptive_capture_strategy.get("classification", "FAIL_CLOSED")) == "PASS",
    }
    strict_failed = [key for key, value in strict_checks.items() if not bool(value)]
    strict_score = round(
        float(len([v for v in strict_checks.values() if bool(v)])) / float(len(strict_checks)),
        3,
    )

    strict_runtime_governance_score = {
        "artifact_name": "STRICT_RUNTIME_GOVERNANCE_SCORE",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "target_id": args.target_id,
        "generated_at": _utc_now_iso(),
        "classification": "PASS" if not strict_failed else "FAIL_CLOSED",
        "fail_closed": bool(strict_failed),
        "strict_score": strict_score,
        "checks": strict_checks,
        "blocking_gaps": strict_failed,
    }
    strict_runtime_governance_score["deterministic_fingerprint"] = stable_fingerprint(strict_runtime_governance_score)

    semantic_alias_registry = _build_semantic_alias_registry(
        combined_rows=combined_rows,
        pcm_rows=pcm_rows,
        fe_be_map=fe_be_map,
        direct_dapm_runtime_state=direct_dapm_runtime_state,
    )
    portability_blocker_registry = _build_portability_blocker_registry(
        board_specific_assumptions=board_specific_assumptions,
        runtime_capability_matrix=runtime_capability_matrix,
        fe_be_map=fe_be_map,
        combined_rows=combined_rows,
    )
    semantic_assumption_matrix = _build_semantic_assumption_matrix(
        board_specific_assumptions=board_specific_assumptions,
        portability_blockers=portability_blocker_registry,
    )
    board_specific_dependency_graph = _build_board_specific_dependency_graph(
        portability_blockers=portability_blocker_registry,
        evidence_source_negotiation=evidence_source_negotiation,
    )
    pcm_role_registry = _build_pcm_role_registry(
        pcm_rows=pcm_rows,
        fe_be_map=fe_be_map,
        semantic_alias_registry=semantic_alias_registry,
    )
    frontend_backend_semantic_map = _build_frontend_backend_semantic_map(
        fe_be_map=fe_be_map,
        pcm_role_registry=pcm_role_registry,
    )
    semantic_topology_graph = _build_semantic_topology_graph(
        cards=cards,
        pcm_role_registry=pcm_role_registry,
        direct_dapm_runtime_state=direct_dapm_runtime_state,
        soundwire_runtime_activation=soundwire_runtime_activation,
        frontend_backend_semantic_map=frontend_backend_semantic_map,
    )
    route_semantic_clusters = _build_route_semantic_clusters(
        activation_order_graph=activation_order_graph,
        runtime_transition_timeline=runtime_transition_timeline,
        playback_convergence_timeline=playback_convergence_timeline,
        runtime_causality_chain=runtime_causality_chain,
        alsa_runtime_lifecycle=alsa_runtime_lifecycle,
        soundwire_runtime_activation=soundwire_runtime_activation,
        frontend_backend_semantic_map=frontend_backend_semantic_map,
    )
    semantic_runtime_capability_map = _build_semantic_runtime_capability_map(
        runtime_capability_matrix=runtime_capability_matrix,
        evidence_source_negotiation=evidence_source_negotiation,
        semantic_alias_registry=semantic_alias_registry,
        pcm_role_registry=pcm_role_registry,
        route_semantic_clusters=route_semantic_clusters,
    )
    runtime_portability_matrix = _build_runtime_portability_matrix(
        strict_runtime_governance_score=strict_runtime_governance_score,
        runtime_capability_matrix=runtime_capability_matrix,
        evidence_source_negotiation=evidence_source_negotiation,
        adaptive_capture_strategy=adaptive_capture_strategy,
        semantic_assumption_matrix=semantic_assumption_matrix,
        portability_blocker_registry=portability_blocker_registry,
    )
    topology_portability_report = _build_topology_portability_report(
        semantic_topology_graph=semantic_topology_graph,
        frontend_backend_semantic_map=frontend_backend_semantic_map,
        pcm_role_registry=pcm_role_registry,
        route_semantic_clusters=route_semantic_clusters,
        runtime_portability_matrix=runtime_portability_matrix,
    )
    semantic_abstraction_summary = _build_semantic_abstraction_summary(
        runtime_portability_matrix=runtime_portability_matrix,
        board_specific_assumptions=board_specific_assumptions,
        portability_blocker_registry=portability_blocker_registry,
        route_semantic_clusters=route_semantic_clusters,
        topology_portability_report=topology_portability_report,
    )

    p16_artifacts = [
        semantic_alias_registry,
        portability_blocker_registry,
        semantic_assumption_matrix,
        board_specific_dependency_graph,
        pcm_role_registry,
        frontend_backend_semantic_map,
        semantic_topology_graph,
        route_semantic_clusters,
        semantic_runtime_capability_map,
        runtime_portability_matrix,
        topology_portability_report,
        semantic_abstraction_summary,
    ]
    for artifact in p16_artifacts:
        artifact.update(
            {
                "session_id": args.session_id,
                "lineage_id": args.lineage_id,
                "target_id": args.target_id,
            }
        )
        artifact["deterministic_fingerprint"] = stable_fingerprint(artifact)

    previous_gap = _read_json(output_dir / "strict_runtime_truth_certification.json")
    prior_blockers = [str(item) for item in _as_list(previous_gap.get("blocking_gaps"))] if previous_gap else []
    p15_evidence_gap_report = {
        "artifact_name": "P15_EVIDENCE_GAP_REPORT",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "previous_blocking_gaps": prior_blockers,
        "current_blocking_gaps": strict_failed,
        "resolved_gaps": sorted(set(prior_blockers) - set(strict_failed)),
        "new_gaps": sorted(set(strict_failed) - set(prior_blockers)),
    }
    p15_evidence_gap_report["deterministic_fingerprint"] = stable_fingerprint(p15_evidence_gap_report)

    artifact_map = {
        "p15_self_tests.json": self_tests,
        "p15_foundation_audit.json": foundation_audit,
        "p15_reusable_runtime_parsers.json": reusable_parsers,
        "p15_brittle_assumptions.json": brittle_assumptions,
        "board_specific_assumptions.json": board_specific_assumptions,
        "runtime_capability_matrix.json": runtime_capability_matrix,
        "adaptive_capture_strategy.json": adaptive_capture_strategy,
        "evidence_source_negotiation.json": evidence_source_negotiation,
        "p15_evidence_gap_report.json": p15_evidence_gap_report,
        "timing_capture_audit_pre.json": timing_capture_audit_pre,
        "timing_capture_audit_post.json": timing_capture_audit_post,
        "playback_window_capture_audit.json": playback_window_capture_audit,
        "direct_dapm_runtime_state.json": direct_dapm_runtime_state,
        "route_activation_timeline.json": route_activation_timeline,
        "runtime_widget_power_graph.json": runtime_widget_power_graph,
        "runtime_pcm_lifecycle.json": runtime_pcm_lifecycle,
        "fe_be_transition_map.json": fe_be_transition_map,
        "soundwire_runtime_activation.json": soundwire_runtime_activation,
        "runtime_topology_inference.json": runtime_topology_inference,
        "runtime_timing_intelligence.json": runtime_timing_intelligence,
        "activation_order_graph.json": activation_order_graph,
        "runtime_transition_timeline.json": runtime_transition_timeline,
        "playback_convergence_timeline.json": playback_convergence_timeline,
        "runtime_causality_chain.json": runtime_causality_chain,
        "alsa_runtime_lifecycle.json": alsa_runtime_lifecycle,
        "strict_runtime_governance_score.json": strict_runtime_governance_score,
        "semantic_alias_registry.json": semantic_alias_registry,
        "portability_blocker_registry.json": portability_blocker_registry,
        "semantic_assumption_matrix.json": semantic_assumption_matrix,
        "board_specific_dependency_graph.json": board_specific_dependency_graph,
        "pcm_role_registry.json": pcm_role_registry,
        "frontend_backend_semantic_map.json": frontend_backend_semantic_map,
        "semantic_topology_graph.json": semantic_topology_graph,
        "route_semantic_clusters.json": route_semantic_clusters,
        "semantic_runtime_capability_map.json": semantic_runtime_capability_map,
        "runtime_portability_matrix.json": runtime_portability_matrix,
        "topology_portability_report.json": topology_portability_report,
        "semantic_abstraction_summary.json": semantic_abstraction_summary,
    }

    current_hashes = {name: _canonical_sha256(payload) for name, payload in sorted(artifact_map.items())}
    prev_matrix = _read_json(output_dir / "p15_runtime_reproducibility_matrix.json")
    prev_hashes = _as_dict(prev_matrix.get("artifact_hashes"))

    reproducibility = {
        "artifact_name": "P15_RUNTIME_REPRODUCIBILITY_MATRIX",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "generated_at": _utc_now_iso(),
        "artifact_hashes": current_hashes,
        "comparison_with_previous": {
            name: {
                "previous": str(prev_hashes.get(name, "")),
                "current": current_hashes[name],
                "unchanged": str(prev_hashes.get(name, "")) == current_hashes[name] and bool(str(prev_hashes.get(name, ""))),
            }
            for name in sorted(current_hashes.keys())
        },
    }
    reproducibility["deterministic_fingerprint"] = stable_fingerprint(reproducibility)

    for name, payload in artifact_map.items():
        _write_json(output_dir / name, payload)
    _write_json(output_dir / "p15_runtime_reproducibility_matrix.json", reproducibility)

    validation_summary = {
        "artifact_name": "P15_RUNTIME_VALIDATION_SUMMARY",
        "session_id": args.session_id,
        "lineage_id": args.lineage_id,
        "target_id": args.target_id,
        "generated_at": _utc_now_iso(),
        "capture_phase_count": len(capture_phases),
        "capture_trace_count": len(capture_rows),
        "history_trace_count": len(history_rows),
        "combined_trace_count": len(combined_rows),
        "self_tests": _as_dict(self_tests.get("summary")),
        "strict_governance": {
            "classification": str(strict_runtime_governance_score.get("classification", "UNKNOWN")),
            "strict_score": float(strict_runtime_governance_score.get("strict_score", 0.0) or 0.0),
            "blocking_gaps": strict_failed,
        },
        "portability": {
            "classification": str(board_specific_assumptions.get("classification", "UNKNOWN")),
            "portability_score": float(board_specific_assumptions.get("portability_score", 0.0) or 0.0),
            "runtime_capability_classification": str(runtime_capability_matrix.get("classification", "UNKNOWN")),
            "runtime_capability_score": float(runtime_capability_matrix.get("portability_score", 0.0) or 0.0),
            "negotiation_classification": str(evidence_source_negotiation.get("classification", "UNKNOWN")),
            "adaptive_strategy_classification": str(adaptive_capture_strategy.get("classification", "UNKNOWN")),
            "p16_portability_maturity": str(runtime_portability_matrix.get("portability_maturity", "UNKNOWN")),
            "p16_portability_maturity_score": float(runtime_portability_matrix.get("portability_maturity_score", 0.0) or 0.0),
            "p16_topology_portability_classification": str(topology_portability_report.get("classification", "UNKNOWN")),
            "p16_topology_portability_score": float(topology_portability_report.get("portability_score", 0.0) or 0.0),
            "p16_remaining_hardcoded_assumptions": len(
                _as_list(semantic_abstraction_summary.get("remaining_hardcoded_assumptions"))
            ),
            "p16_cross_board_blocker_count": len(
                _as_list(semantic_abstraction_summary.get("blockers_preventing_cross_board_portability"))
            ),
        },
        "output_paths": {name: str((output_dir / name).resolve()) for name in sorted(list(artifact_map.keys()) + ["p15_runtime_reproducibility_matrix.json"])},
    }
    validation_summary["deterministic_fingerprint"] = stable_fingerprint(validation_summary)
    _write_json(output_dir / "p15_runtime_validation_summary.json", validation_summary)

    print(json.dumps(validation_summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
