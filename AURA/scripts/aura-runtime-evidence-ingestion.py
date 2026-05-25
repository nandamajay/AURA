#!/usr/bin/env python3
"""Real Runtime Evidence Ingestion Layer runner."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.runtime_evidence_ingestor import RuntimeEvidenceIngestor
from aura_sdk.transport.runtime_session_registry import RuntimeSessionRegistry


def _repo_root() -> Path:
    env_root = str(os.getenv("AURA_REPO_ROOT", "")).strip()
    if env_root:
        path = Path(env_root)
        if path.exists():
            return path
    here = Path(__file__).resolve()
    return here.parents[2]


def _default_output_dir() -> str:
    return str((_repo_root() / "docs/operations/transport").resolve())


def _default_registry_path() -> str:
    return str((_repo_root() / "docs/operations/transport/aura_cognition_registry.json").resolve())


def _default_bridge_root() -> str:
    return str((_repo_root() / "bridge").resolve())


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _load_lines(path: Path, limit: int = 1200) -> list[str]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[:limit]
    except Exception:
        return []
    return [line.rstrip("\n") for line in lines if line.strip()]


def _find_payload(output_dir: Path, candidates: list[str]) -> dict[str, Any]:
    for name in candidates:
        path = output_dir / name
        if not path.exists():
            continue
        if path.suffix.lower() == ".json":
            maybe_json = _read_json(path)
            if isinstance(maybe_json.get("events"), list):
                return {"events": maybe_json.get("events", [])}
            if isinstance(maybe_json.get("lines"), list):
                return {"lines": [str(item) for item in maybe_json.get("lines", [])]}
        lines = _load_lines(path)
        if lines:
            return {"lines": lines}
    return {}


_CARD_LINE_RE = re.compile(r"^\s*\d+\s+\[(.+?)\]\s*:\s*(.+)$")
_PCM_LINE_RE = re.compile(r"^\s*([0-9]+-[0-9]+)\s*:\s*(.+)$")


def _run_command(cmd: list[str], timeout_s: float = 3.0) -> list[str]:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
    except Exception:
        return []
    output = proc.stdout if proc.stdout.strip() else proc.stderr
    return [line.strip() for line in output.splitlines() if line.strip()]


def _safe_read_lines(path: Path, limit: int = 400, max_bytes: int = 256 * 1024) -> list[str]:
    try:
        if not path.exists():
            return []
    except Exception:
        return []
    try:
        raw = path.read_bytes()[:max_bytes]
    except Exception:
        return []
    text = raw.decode("utf-8", errors="ignore")
    return [line.strip() for line in text.splitlines()[:limit] if line.strip()]


def _read_device_tree_value(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        raw = path.read_bytes()
    except Exception:
        return ""
    text = raw.decode("utf-8", errors="ignore").replace("\x00", ",").strip(" ,\n\t")
    return text


def _collect_tree_lines(root: Path, *, max_files: int = 80, max_lines_per_file: int = 20) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        if not root.exists():
            return [], []
    except Exception:
        return [], []

    files = []
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            dirnames.sort()
            for filename in sorted(filenames):
                if len(files) >= max_files:
                    break
                path = Path(dirpath) / filename
                try:
                    if path.is_symlink() or not path.is_file():
                        continue
                except Exception:
                    continue
                files.append(path)
            if len(files) >= max_files:
                break
    except Exception:
        return [], []

    combined_lines: list[str] = []
    samples: list[dict[str, Any]] = []
    for path in files:
        rel = str(path)
        lines = _safe_read_lines(path, limit=max_lines_per_file)
        if not lines:
            continue
        samples.append(
            {
                "path": rel,
                "sample_count": len(lines),
            }
        )
        for line in lines:
            combined_lines.append(f"{rel}: {line}")

    return combined_lines, samples


def _discover_toolchain(capture_root: Path, bridge_root: Path, output_dir: Path) -> dict[str, Any]:
    bridge_state = _bridge_evidence(bridge_root, output_dir)
    tool_meta = [
        ("tinymix", "critical", "install tinyalsa"),
        ("tinyplay", "recommended", "install tinyalsa"),
        ("tinycap", "recommended", "install tinyalsa"),
        ("amixer", "critical", "install alsa-utils"),
        ("alsactl", "recommended", "install alsa-utils"),
        ("trace-cmd", "critical", "install trace-cmd"),
        ("perf", "optional", "install linux-tools package"),
        ("arecord", "critical", "install alsa-utils"),
        ("aplay", "critical", "install alsa-utils"),
    ]

    tools = []
    in_container = str(os.getenv("AURA_RUNTIME_EXECUTION_MODE", "")).strip().lower() == "container"
    for name, importance, recommendation in tool_meta:
        path = shutil.which(name)
        bridge_status, bridge_reason = _tool_status_from_bridge(name, bridge_state)

        if bridge_status == "AVAILABLE":
            status = "AVAILABLE"
            available = True
            source = bridge_reason
        elif bridge_status == "MISSING":
            status = "MISSING"
            available = False
            source = bridge_reason
        elif not in_container and path:
            status = "AVAILABLE"
            available = True
            source = "local_runtime_binary"
        elif not in_container and not path:
            status = "MISSING"
            available = False
            source = "local_runtime_binary_missing"
        else:
            status = "UNKNOWN"
            available = False
            source = bridge_reason if bridge_reason else "container_runtime_no_board_evidence"

        tools.append(
            {
                "name": name,
                "status": status,
                "available": available,
                "path": path or "",
                "importance": importance,
                "evidence_source": source,
                "install_recommendation": recommendation if status == "MISSING" else "",
            }
        )

    tracing_path = capture_root / "sys/kernel/tracing"
    debug_tracing_path = capture_root / "sys/kernel/debug/tracing"
    trace_available = _path_exists(tracing_path) or _path_exists(debug_tracing_path)
    trace_status = "AVAILABLE" if trace_available else ("MISSING" if not in_container else "UNKNOWN")
    tools.append(
        {
            "name": "ftrace/debugfs",
            "status": trace_status,
            "available": trace_available,
            "path": str(tracing_path if _path_exists(tracing_path) else debug_tracing_path),
            "importance": "critical",
            "evidence_source": "local_sysfs",
            "install_recommendation": "mount tracefs/debugfs and enable tracing support" if trace_status == "MISSING" else "",
        }
    )

    return {
        "tools": tools,
        "bridge_command_evidence_count": len(_as_dict(bridge_state.get("commands"))),
    }


def _parse_sound_cards(lines: list[str]) -> list[str]:
    cards = []
    for line in lines:
        match = _CARD_LINE_RE.match(line)
        if not match:
            continue
        cards.append(f"{match.group(1).strip()}:{match.group(2).strip()}")
    return sorted(set(cards))


def _parse_pcm_devices(lines: list[str]) -> list[str]:
    devices = []
    for line in lines:
        match = _PCM_LINE_RE.match(line)
        if not match:
            continue
        devices.append(f"{match.group(1).strip()}:{match.group(2).strip()}")
    return sorted(set(devices))


def _extract_component_tokens(lines: list[str], pattern: re.Pattern[str]) -> list[str]:
    out = []
    for line in lines:
        for match in pattern.findall(line):
            token = str(match).strip()
            if token:
                out.append(token)
    return sorted(set(out))


def _bridge_response_paths(bridge_root: Path, output_dir: Path, max_files: int = 320) -> list[Path]:
    candidates: dict[str, Path] = {}
    for root in (bridge_root / "responses", output_dir):
        if not _path_exists(root):
            continue
        pattern = "*.json" if root == (bridge_root / "responses") else "bridge_response_*.json"
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            candidates[str(path.resolve())] = path

    ordered = sorted(candidates.values(), key=lambda p: p.stat().st_mtime, reverse=True)
    return ordered[:max_files]


def _bridge_evidence(bridge_root: Path, output_dir: Path) -> dict[str, Any]:
    entries: dict[str, dict[str, Any]] = {}
    lines_by_command: dict[str, list[str]] = {}
    all_lines: list[str] = []

    for path in _bridge_response_paths(bridge_root, output_dir):
        payload = _read_json(path)
        if not payload:
            continue
        for trace in _as_list(payload.get("executor_command_trace")):
            item = _as_dict(trace)
            cmd = str(item.get("normalized_command", "")).strip()
            if not cmd:
                continue

            status = str(item.get("execution_status", "")).strip().lower()
            stdout = str(item.get("stdout", ""))
            stderr = str(item.get("stderr", ""))
            exit_code = int(item.get("exit_code", -9999) or -9999)
            out_lines = [line.strip() for line in stdout.replace("\r", "").splitlines() if line.strip()]
            err_lines = [line.strip() for line in stderr.replace("\r", "").splitlines() if line.strip()]
            command_lines = out_lines + err_lines

            previous = _as_dict(entries.get(cmd))
            prev_rank = int(previous.get("rank", -1) or -1)
            rank = 3 if status in {"executed", "success", "completed"} else 2 if "not found" in stdout.lower() or "not found" in stderr.lower() else 1 if status == "timeout" else 0
            if rank >= prev_rank:
                entries[cmd] = {
                    "command": cmd,
                    "status": status,
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "path": str(path),
                    "rank": rank,
                }

            existing = lines_by_command.setdefault(cmd, [])
            for line in command_lines:
                if len(existing) >= 2400:
                    break
                existing.append(line)
            for line in command_lines:
                if len(all_lines) >= 8000:
                    break
                all_lines.append(line)

    return {
        "commands": {cmd: {k: v for k, v in data.items() if k != "rank"} for cmd, data in sorted(entries.items())},
        "lines_by_command": {cmd: lines[:2400] for cmd, lines in sorted(lines_by_command.items())},
        "all_lines": all_lines[:8000],
    }


def _tool_status_from_bridge(tool_name: str, bridge_state: Mapping[str, Any]) -> tuple[str, str]:
    commands = _as_dict(bridge_state.get("commands"))
    all_lines = [str(line).lower() for line in _as_list(bridge_state.get("all_lines"))]

    if tool_name in {"amixer", "tinymix"}:
        cmd = _as_dict(commands.get(tool_name))
        if cmd:
            stdout = str(cmd.get("stdout", "")).lower()
            stderr = str(cmd.get("stderr", "")).lower()
            status = str(cmd.get("status", "")).lower()
            if "not found" in stdout or "not found" in stderr:
                return "MISSING", f"bridge:{tool_name}:not_found"
            if status in {"executed", "success", "completed"}:
                return "AVAILABLE", f"bridge:{tool_name}:executed"
            if status == "timeout":
                return "UNKNOWN", f"bridge:{tool_name}:timeout"
            return "UNKNOWN", f"bridge:{tool_name}:{status or 'unknown'}"

    if tool_name in {"aplay", "arecord"}:
        usage_marker = f"usage: {tool_name}"
        if any(usage_marker in line for line in all_lines):
            return "AVAILABLE", f"bridge:{tool_name}:usage_banner"
        for cmd in commands.values():
            item = _as_dict(cmd)
            invoc = str(item.get("command", "")).lower() + " " + str(item.get("stdout", "")).lower() + " " + str(item.get("stderr", "")).lower()
            if f"{tool_name} " in invoc:
                if "not found" in invoc:
                    return "MISSING", f"bridge:{tool_name}:not_found"
                if str(item.get("status", "")).lower() in {"executed", "failed", "success", "completed"}:
                    return "AVAILABLE", f"bridge:{tool_name}:invocation_seen"

    if tool_name == "trace-cmd":
        cmd = _as_dict(commands.get("trace-cmd report"))
        if cmd:
            status = str(cmd.get("status", "")).lower()
            if status in {"executed", "success", "completed"}:
                return "AVAILABLE", "bridge:trace-cmd:executed"
            return "UNKNOWN", f"bridge:trace-cmd:{status or 'unknown'}"

    if tool_name == "perf":
        for cmd_name, cmd in commands.items():
            if not str(cmd_name).startswith("perf"):
                continue
            item = _as_dict(cmd)
            status = str(item.get("status", "")).lower()
            if status in {"executed", "success", "completed"}:
                return "AVAILABLE", "bridge:perf:executed"
            if "not found" in str(item.get("stdout", "")).lower() or "not found" in str(item.get("stderr", "")).lower():
                return "MISSING", "bridge:perf:not_found"
        return "UNKNOWN", "bridge:perf:no_signal"

    return "UNKNOWN", f"bridge:{tool_name}:no_signal"


def _discover_runtime_environment(capture_root: Path, output_dir: Path, bridge_root: Path) -> dict[str, Any]:
    kernel_uname = os.uname()
    bridge_state = _bridge_evidence(bridge_root, output_dir)
    bridge_lines_by_command = _as_dict(bridge_state.get("lines_by_command"))
    soc = _read_device_tree_value(capture_root / "proc/device-tree/compatible")
    board_model = _read_device_tree_value(capture_root / "proc/device-tree/model")

    proc_asound_root = capture_root / "proc/asound"
    proc_asound_lines, proc_asound_samples = _collect_tree_lines(proc_asound_root, max_files=120, max_lines_per_file=25)
    cards_lines = _safe_read_lines(proc_asound_root / "cards", limit=200)
    pcm_lines = _safe_read_lines(proc_asound_root / "pcm", limit=300)
    if not cards_lines:
        cards_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("cat /proc/asound/cards"))][:220]
    if not pcm_lines:
        pcm_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("cat /proc/asound/pcm"))][:340]
    if not proc_asound_lines:
        proc_asound_lines = cards_lines + pcm_lines

    debug_asoc_root = capture_root / "sys/kernel/debug/asoc"
    debug_asoc_lines, debug_asoc_samples = _collect_tree_lines(debug_asoc_root, max_files=140, max_lines_per_file=25)
    if not debug_asoc_lines:
        debug_asoc_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("ls /sys/kernel/debug/asoc"))]
    if not debug_asoc_lines:
        debug_asoc_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("cat /sys/kernel/debug/asoc/*/dapm"))]

    soundwire_root = capture_root / "sys/bus/soundwire"
    soundwire_lines, soundwire_samples = _collect_tree_lines(soundwire_root, max_files=80, max_lines_per_file=20)

    dmesg_lines = _run_command(["dmesg", "--color=never"], timeout_s=4.0)
    if not dmesg_lines:
        dmesg_lines = _load_lines(output_dir / "runtime_dmesg.log", limit=1800)
    if not dmesg_lines:
        dmesg_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("dmesg"))][:2000]
    if not dmesg_lines:
        dmesg_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("dmesg | tail -200"))][:2000]

    modules_lines = _safe_read_lines(capture_root / "proc/modules", limit=600)
    if not modules_lines:
        modules_lines = _run_command(["lsmod"], timeout_s=2.0)
    if not modules_lines:
        modules_lines = [str(line) for line in _as_list(bridge_lines_by_command.get("lsmod"))][:600]

    interrupts_lines = _safe_read_lines(capture_root / "proc/interrupts", limit=1500)
    if not interrupts_lines:
        bridge_interrupt_lines: list[str] = []
        for cmd, lines in bridge_lines_by_command.items():
            normalized = str(cmd).strip()
            if "/proc/interrupts" in normalized:
                bridge_interrupt_lines.extend([str(line) for line in _as_list(lines)])
        interrupts_lines = bridge_interrupt_lines[:1500]

    softirq_lines = _safe_read_lines(capture_root / "proc/softirqs", limit=1000)
    if not softirq_lines:
        bridge_softirq_lines: list[str] = []
        for cmd, lines in bridge_lines_by_command.items():
            normalized = str(cmd).strip()
            if "/proc/softirqs" in normalized:
                bridge_softirq_lines.extend([str(line) for line in _as_list(lines)])
        softirq_lines = bridge_softirq_lines[:1000]

    dts_compatible = [item for item in soc.split(",") if item.strip()] if soc else []
    sound_cards = _parse_sound_cards(cards_lines)
    pcm_devices = _parse_pcm_devices(pcm_lines)

    codec_pattern = re.compile(r"\b(?:wcd[0-9a-z_]+|wsa[0-9a-z_]+|codec[0-9a-z_./-]*)\b", re.IGNORECASE)
    amp_pattern = re.compile(r"\b(?:tas[0-9a-z_]+|max[0-9a-z_]+|amp(?:lifier)?[0-9a-z_./-]*)\b", re.IGNORECASE)
    dai_pattern = re.compile(r"\b(?:fe[0-9]+|be[0-9]+|multimedia[0-9]+|mi2s[0-9a-z_]*)\b", re.IGNORECASE)
    swr_pattern = re.compile(r"\b(?:swr[0-9a-z_:-]+|soundwire[0-9a-z_:-]+)\b", re.IGNORECASE)
    slimbus_pattern = re.compile(r"\bslim(?:bus)?[0-9a-z_:-]*\b", re.IGNORECASE)
    dapm_pattern = re.compile(r"\b(?:dapm|widget|mixer|mux|route)\b.*", re.IGNORECASE)

    combined_component_lines = proc_asound_lines + debug_asoc_lines + soundwire_lines + dmesg_lines
    codecs = _extract_component_tokens(combined_component_lines, codec_pattern)
    amplifiers = _extract_component_tokens(combined_component_lines, amp_pattern)
    dai_links = _extract_component_tokens(combined_component_lines, dai_pattern)
    soundwire_devices = _extract_component_tokens(combined_component_lines, swr_pattern)
    slimbus_devices = _extract_component_tokens(combined_component_lines, slimbus_pattern)
    dapm_widgets = _extract_component_tokens(debug_asoc_lines, dapm_pattern)
    routing_paths = [line for line in debug_asoc_lines if "->" in line][:500]

    fe_dais = sorted(set([item for item in dai_links if item.lower().startswith(("fe", "multimedia"))]))
    be_dais = sorted(set([item for item in dai_links if item.lower().startswith("be")]))

    availability = [
        {
            "source": "proc_asound",
            "path": str(proc_asound_root),
            "available": _path_exists(proc_asound_root) or bool(cards_lines) or bool(pcm_lines),
            "sample_count": len(proc_asound_lines),
        },
        {
            "source": "debug_asoc",
            "path": str(debug_asoc_root),
            "available": _path_exists(debug_asoc_root) or bool(debug_asoc_lines),
            "sample_count": len(debug_asoc_lines),
        },
        {
            "source": "soundwire_sysbus",
            "path": str(soundwire_root),
            "available": _path_exists(soundwire_root),
            "sample_count": len(soundwire_lines),
        },
        {
            "source": "dmesg",
            "path": "dmesg",
            "available": bool(dmesg_lines),
            "sample_count": len(dmesg_lines),
        },
    ]

    return {
        "kernel": {
            "release": kernel_uname.release,
            "version": kernel_uname.version,
            "machine": kernel_uname.machine,
        },
        "soc": dts_compatible[0] if dts_compatible else "",
        "board_model": board_model,
        "dts_compatible": dts_compatible[:20],
        "components": {
            "sound_cards": sound_cards,
            "pcm_devices": pcm_devices,
            "dai_links": dai_links[:400],
            "fe_dais": fe_dais[:200],
            "be_dais": be_dais[:200],
            "codecs": codecs[:200],
            "amplifiers": amplifiers[:200],
            "soundwire_devices": soundwire_devices[:200],
            "slimbus_devices": slimbus_devices[:200],
            "dapm_widgets": dapm_widgets[:400],
            "routing_paths": routing_paths[:600],
        },
        "source_availability": availability,
        "raw_samples": {
            "proc_asound": proc_asound_samples[:120],
            "debug_asoc": debug_asoc_samples[:140],
            "soundwire": soundwire_samples[:80],
            "modules_sample": modules_lines[:120],
        },
        "runtime_lines": {
            "dmesg": dmesg_lines[:2000],
            "proc_asound": proc_asound_lines[:2000],
            "debug_asoc": debug_asoc_lines[:2500],
            "soundwire": soundwire_lines[:1200],
            "interrupts": interrupts_lines[:1500],
            "softirqs": softirq_lines[:1000],
            "modules": modules_lines[:600],
            "cards": cards_lines[:200],
            "pcm": pcm_lines[:300],
        },
        "bridge_evidence": {
            "command_count": len(_as_dict(bridge_state.get("commands"))),
            "commands": _as_dict(bridge_state.get("commands")),
        },
    }


def _build_live_source_payloads(runtime_discovery: dict[str, Any], toolchain: dict[str, Any], capture_root: Path) -> dict[str, Any]:
    runtime_lines = _as_dict(runtime_discovery.get("runtime_lines"))
    bridge_commands = _as_dict(_as_dict(runtime_discovery.get("bridge_evidence")).get("commands"))
    tools = {str(_as_dict(item).get("name", "")): _as_dict(item) for item in _as_list(toolchain.get("tools"))}
    soundwire_lines = _as_list(runtime_lines.get("soundwire"))
    interrupts_lines = [str(line).strip() for line in _as_list(runtime_lines.get("interrupts")) if str(line).strip()]
    softirq_lines = [str(line).strip() for line in _as_list(runtime_lines.get("softirqs")) if str(line).strip()]

    payloads = {
        "dmesg": {"lines": _as_list(runtime_lines.get("dmesg"))},
        "ftrace": {},
        "trace_cmd": {},
        "perf": {},
        "tinymix_state": {},
        "procfs_runtime": {"lines": _as_list(runtime_lines.get("proc_asound"))},
        "debugfs_runtime": {"lines": _as_list(runtime_lines.get("debug_asoc"))},
        "soundwire_runtime": {"lines": soundwire_lines} if soundwire_lines else {},
        "dsp_mailbox": {},
        "irq_runtime": {},
    }

    trace_path = capture_root / "sys/kernel/tracing/trace"
    if not _path_exists(trace_path):
        trace_path = capture_root / "sys/kernel/debug/tracing/trace"
    trace_lines = _safe_read_lines(trace_path, limit=2000)
    if trace_lines:
        payloads["ftrace"] = {"lines": trace_lines}

    if bool(_as_dict(tools.get("trace-cmd")).get("available", False)):
        trace_cmd_lines = _run_command(["trace-cmd", "report"], timeout_s=2.0)
        if trace_cmd_lines:
            payloads["trace_cmd"] = {"lines": trace_cmd_lines[:2000]}

    if bool(_as_dict(tools.get("perf")).get("available", False)):
        perf_lines = _run_command(["perf", "list"], timeout_s=2.0)
        if perf_lines:
            payloads["perf"] = {"lines": perf_lines[:1000]}

    tinymix_lines: list[str] = []
    if bool(_as_dict(tools.get("tinymix")).get("available", False)):
        tinymix_lines = _run_command(["tinymix"], timeout_s=3.0)
    if not tinymix_lines and bool(_as_dict(tools.get("amixer")).get("available", False)):
        tinymix_lines = _run_command(["amixer", "-c", "0", "scontents"], timeout_s=3.0)
    if tinymix_lines:
        payloads["tinymix_state"] = {"lines": tinymix_lines[:2500]}

    irq_lines = [
        line
        for line in interrupts_lines
        if any(token in line.lower() for token in ("snd", "audio", "wcd", "swr", "dsp", "apr", "q6", "lpass", "mi2s", "soundwire"))
    ]
    if not irq_lines:
        irq_lines = [line for line in interrupts_lines if re.match(r"^\s*\d+\s*:", line)][:400]
    if not irq_lines and softirq_lines:
        irq_lines = [line for line in softirq_lines if re.search(r"\b(?:HI|TIMER|NET_TX|NET_RX|BLOCK|IRQ_POLL|TASKLET|SCHED|HRTIMER|RCU)\b", line)]
        if not irq_lines:
            irq_lines = softirq_lines[:400]
    if irq_lines:
        payloads["irq_runtime"] = {"lines": irq_lines}

    mailbox_lines = [
        line
        for line in _as_list(runtime_lines.get("dmesg"))
        if any(token in str(line).lower() for token in ("mailbox", "apr", "adsp", "dsp", "glink", "rpmsg"))
    ]
    mailbox_lines.extend(
        [
            line
            for line in _as_list(runtime_lines.get("debug_asoc"))
            if any(token in str(line).lower() for token in ("mailbox", "apr", "adsp", "dsp"))
        ]
    )
    if mailbox_lines:
        payloads["dsp_mailbox"] = {"lines": mailbox_lines[:1500]}

    if not _as_dict(payloads.get("soundwire_runtime")):
        swr_lines = []
        for source in ("debug_asoc", "proc_asound", "dmesg"):
            for line in _as_list(runtime_lines.get(source)):
                text = str(line).strip()
                low = text.lower()
                if "soundwire" in low or "swr" in low or "slimbus" in low:
                    swr_lines.append(text)
        if not swr_lines:
            for cmd_data in bridge_commands.values():
                item = _as_dict(cmd_data)
                blob = (str(item.get("stdout", "")) + "\n" + str(item.get("stderr", ""))).replace("\r", "")
                for line in blob.splitlines():
                    text = line.strip()
                    low = text.lower()
                    if not text:
                        continue
                    if "soundwire" in low or "swr" in low or "slimbus" in low:
                        swr_lines.append(text)
        if swr_lines:
            payloads["soundwire_runtime"] = {"lines": swr_lines[:1500]}

    if not _as_dict(payloads.get("irq_runtime")):
        proc_interrupts = _as_dict(bridge_commands.get("cat /proc/interrupts"))
        if not proc_interrupts:
            for cmd, data in bridge_commands.items():
                normalized = str(cmd).strip()
                if "/proc/interrupts" in normalized:
                    proc_interrupts = _as_dict(data)
                    break
        proc_interrupt_lines = [
            line.strip()
            for line in (str(proc_interrupts.get("stdout", "")) + "\n" + str(proc_interrupts.get("stderr", ""))).replace("\r", "").splitlines()
            if line.strip()
        ]
        if proc_interrupt_lines:
            irq_fallback = [
                line
                for line in proc_interrupt_lines
                if any(token in line.lower() for token in ("snd", "audio", "wcd", "swr", "dsp", "apr", "q6", "lpass", "mi2s", "soundwire"))
            ]
            if not irq_fallback:
                irq_fallback = [line for line in proc_interrupt_lines if re.match(r"^\s*\d+\s*:", line)][:400]
        else:
            irq_fallback = []

        if not irq_fallback:
            proc_softirqs = _as_dict(bridge_commands.get("cat /proc/softirqs"))
            proc_softirq_lines = [
                line.strip()
                for line in (str(proc_softirqs.get("stdout", "")) + "\n" + str(proc_softirqs.get("stderr", ""))).replace("\r", "").splitlines()
                if line.strip()
            ]
            if proc_softirq_lines:
                irq_fallback = [
                    line
                    for line in proc_softirq_lines
                    if re.search(r"\b(?:HI|TIMER|NET_TX|NET_RX|BLOCK|IRQ_POLL|TASKLET|SCHED|HRTIMER|RCU)\b", line)
                ]
                if not irq_fallback:
                    irq_fallback = proc_softirq_lines[:400]

        irq_fallback = [
            str(line).strip()
            for line in _as_list(runtime_lines.get("dmesg"))
            if "irq" in str(line).lower() or "interrupt" in str(line).lower()
        ] if not irq_fallback else irq_fallback
        if not irq_fallback:
            for cmd_data in bridge_commands.values():
                item = _as_dict(cmd_data)
                blob = (str(item.get("stdout", "")) + "\n" + str(item.get("stderr", ""))).replace("\r", "")
                for line in blob.splitlines():
                    text = line.strip()
                    if text and ("irq" in text.lower() or "interrupt" in text.lower()):
                        irq_fallback.append(text)
        if irq_fallback:
            payloads["irq_runtime"] = {"lines": irq_fallback[:1000]}

    return payloads


def _load_source_payloads(output_dir: Path, live_payloads: Mapping[str, Any] | None = None) -> dict[str, Any]:
    payloads = {
        "dmesg": _as_dict(_as_dict(live_payloads).get("dmesg")) if live_payloads else {},
        "ftrace": _as_dict(_as_dict(live_payloads).get("ftrace")) if live_payloads else {},
        "trace_cmd": _as_dict(_as_dict(live_payloads).get("trace_cmd")) if live_payloads else {},
        "perf": _as_dict(_as_dict(live_payloads).get("perf")) if live_payloads else {},
        "tinymix_state": _as_dict(_as_dict(live_payloads).get("tinymix_state")) if live_payloads else {},
        "procfs_runtime": _as_dict(_as_dict(live_payloads).get("procfs_runtime")) if live_payloads else {},
        "debugfs_runtime": _as_dict(_as_dict(live_payloads).get("debugfs_runtime")) if live_payloads else {},
        "soundwire_runtime": _as_dict(_as_dict(live_payloads).get("soundwire_runtime")) if live_payloads else {},
        "dsp_mailbox": _as_dict(_as_dict(live_payloads).get("dsp_mailbox")) if live_payloads else {},
        "irq_runtime": _as_dict(_as_dict(live_payloads).get("irq_runtime")) if live_payloads else {},
    }

    file_fallbacks = {
        "dmesg": ["runtime_dmesg.log", "dmesg.log", "kernel.log"],
        "ftrace": ["runtime_ftrace.log", "ftrace.log"],
        "trace_cmd": ["trace_cmd.json", "runtime_trace_cmd.json", "trace_cmd.log"],
        "perf": ["perf_trace.json", "perf_trace.log", "runtime_perf.log"],
        "tinymix_state": ["tinymix_dump.txt", "tinyalsa_dump.txt", "tinymix_state.log"],
        "procfs_runtime": ["procfs_sysfs_runtime.txt", "runtime_procfs_sysfs.txt", "alsa_procfs_state.txt"],
        "debugfs_runtime": ["debugfs_runtime.txt", "runtime_debugfs.txt", "asoc_debugfs.txt"],
        "soundwire_runtime": ["soundwire_debugfs.txt", "runtime_soundwire_debugfs.txt", "soundwire_runtime.log"],
        "dsp_mailbox": ["mailbox_trace.log", "dsp_response.log", "runtime_dsp_response.log"],
        "irq_runtime": ["irq_trace.log", "runtime_irq.log", "irq_timing_trace.log"],
    }
    for source, candidates in sorted(file_fallbacks.items()):
        if _as_dict(payloads.get(source)):
            continue
        payloads[source] = _find_payload(output_dir, candidates)

    # Deterministic offline fallback sources from already generated artifacts.
    if not _as_dict(payloads.get("ftrace")):
        pcm = _read_json(output_dir / "pcm_lifecycle_trace.json")
        lines = []
        for row in _as_list(pcm.get("transitions")):
            item = _as_dict(row)
            ts = float(item.get("timestamp_ms", 0.0) or 0.0) / 1000.0
            lines.append(f"{ts:.3f}: pcm {item.get('stage', 'STATE')}")
        if lines:
            payloads["ftrace"] = {"lines": lines}

    if not _as_dict(payloads.get("trace_cmd")):
        dapm = _read_json(output_dir / "dapm_transition_trace.json")
        events = []
        for row in _as_list(dapm.get("transitions")):
            item = _as_dict(row)
            events.append(
                {
                    "timestamp_ms": float(item.get("timestamp_ms", 0.0) or 0.0),
                    "event_type": "dapm_trace",
                    "detail": str(item.get("transition", "STATE")),
                }
            )
        if events:
            payloads["trace_cmd"] = {"events": events}

    if not _as_dict(payloads.get("dmesg")):
        drift = _read_json(output_dir / "runtime_drift_report.json")
        lines = [
            str(_as_dict(row).get("details", ""))
            for row in _as_list(drift.get("drifts"))
            if str(_as_dict(row).get("details", "")).strip()
        ]
        if lines:
            payloads["dmesg"] = {"lines": lines}

    if not _as_dict(payloads.get("perf")):
        drift = _read_json(output_dir / "runtime_drift_report.json")
        lines = [
            f"perf:{idx}:{str(_as_dict(row).get('type', 'drift'))}"
            for idx, row in enumerate(_as_list(drift.get("drifts")), start=1)
        ]
        if lines:
            payloads["perf"] = {"lines": lines}

    if not _as_dict(payloads.get("tinymix_state")):
        correlation = _read_json(output_dir / "runtime_patch_correlation.json")
        lines = [
            f"{str(_as_dict(row).get('runtime_command', 'mixer_cmd'))}:{str(_as_dict(row).get('correlation_confidence', 0.0))}"
            for row in _as_list(correlation.get("command_patch_mappings"))
        ]
        if lines:
            payloads["tinymix_state"] = {"lines": lines}

    if not _as_dict(payloads.get("procfs_runtime")):
        topology = _read_json(output_dir / "topology_runtime_graph.json")
        routes = _as_list(_as_dict(topology.get("normalized_portable_audio_graph")).get("fe_be_routes"))
        lines = [f"procfs route {item}" for item in routes if str(item).strip()]
        if lines:
            payloads["procfs_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("debugfs_runtime")):
        topology = _read_json(output_dir / "topology_runtime_graph.json")
        lines = [
            str(_as_dict(edge).get("from", "")) + "->" + str(_as_dict(edge).get("to", ""))
            for edge in _as_list(topology.get("edges"))
        ]
        lines = [line for line in lines if line.strip() and line != "->"]
        if lines:
            payloads["debugfs_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("soundwire_runtime")):
        swr = _read_json(output_dir / "soundwire_runtime_graph.json")
        lines = [
            str(_as_dict(node).get("id", ""))
            for node in _as_list(swr.get("nodes"))
            if "swr" in str(_as_dict(node).get("id", "")).lower()
            or "soundwire" in str(_as_dict(node).get("id", "")).lower()
        ]
        if lines:
            payloads["soundwire_runtime"] = {"lines": lines}

    if not _as_dict(payloads.get("dsp_mailbox")):
        dsp = _read_json(output_dir / "dsp_sync_report.json")
        lines = [
            f"dsp latency {value}"
            for value in _as_list(dsp.get("pair_latencies_ms"))
        ]
        if lines:
            payloads["dsp_mailbox"] = {"lines": lines}

    if not _as_dict(payloads.get("irq_runtime")):
        irq = _read_json(output_dir / "irq_timing_report.json")
        lines = [
            f"irq {str(_as_dict(row).get('event_id', 'irq'))}"
            for row in _as_list(irq.get("ordered_irq_events"))
        ]
        if lines:
            payloads["irq_runtime"] = {"lines": lines}

    return payloads


def _load_domain_artifacts(output_dir: Path) -> dict[str, Any]:
    return {
        "runtime_truth_graph": _read_json(output_dir / "runtime_truth_graph.json"),
        "topology_cognition": _read_json(output_dir / "topology_runtime_graph.json"),
        "migration_lineage": _read_json(output_dir / "migration_lineage.json"),
        "patch_lineage": _read_json(output_dir / "patch_runtime_lineage.json"),
        "structural_cognition": _read_json(output_dir / "structural_graph.json"),
        "semantic_ontology": _read_json(output_dir / "semantic_ontology.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate runtime evidence ingestion artifacts")
    parser.add_argument("--output-dir", default=_default_output_dir())
    parser.add_argument(
        "--registry-path",
        default=_default_registry_path(),
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="runtime_session_v1")
    parser.add_argument("--lineage-id", default="runtime_evidence_ingestion_v1")
    parser.add_argument("--plugin-registry", default="")
    parser.add_argument("--capture-root", default="/")
    parser.add_argument("--bridge-root", default=_default_bridge_root())
    parser.add_argument("--disable-live-discovery", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    capture_root = Path(args.capture_root)
    bridge_root = Path(args.bridge_root)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    replay_det = _read_json(output_dir / "aura_replay_determinism_report.json")
    replay_traces = {
        "deterministic_event_ordering": bool(
            _as_dict(replay_det).get("event_ordering_stable", True)
        ),
        "deterministic_replay_fingerprint": str(
            _as_dict(replay_det).get("deterministic_fingerprint", "")
        ),
    }

    governance_state = _as_dict(registry_payload.get("governance_state"))
    if not governance_state:
        governance_state = {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        }

    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    plugin_capability_state = {
        "supported": bool(target_knowledge),
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
    }

    previous_session_history = [
        row
        for row in _as_list(registry_payload.get("runtime_session_lineage"))
        if isinstance(row, dict)
    ]

    runtime_discovery_state = {}
    toolchain_discovery_state = {}
    live_payloads = {}
    if not args.disable_live_discovery:
        runtime_discovery_state = _discover_runtime_environment(capture_root, output_dir, bridge_root)
        toolchain_discovery_state = _discover_toolchain(capture_root, bridge_root, output_dir)
        live_payloads = _build_live_source_payloads(runtime_discovery_state, toolchain_discovery_state, capture_root)

    source_payloads = _load_source_payloads(output_dir, live_payloads=live_payloads)
    domain_artifacts = _load_domain_artifacts(output_dir)

    loader = (
        TargetPluginLoader(registry_path=args.plugin_registry)
        if str(args.plugin_registry).strip()
        else TargetPluginLoader()
    )
    ingestor = RuntimeEvidenceIngestor(plugin_loader=loader)

    result = ingestor.analyze(
        target_id=str(args.target_id),
        lineage_id=str(args.lineage_id),
        session_id=str(args.session_id),
        source_payloads=source_payloads,
        domain_artifacts=domain_artifacts,
        replay_traces=replay_traces,
        governance_state=governance_state,
        plugin_capability_state=plugin_capability_state,
        evidence_references=[
            "registry://governance_state",
            "registry://runtime_truth_cognition",
            "registry://migration_lineage",
            "registry://patch_cognition",
            "artifact://runtime_truth_graph",
            "artifact://topology_runtime_graph",
            "artifact://migration_lineage",
            "artifact://patch_runtime_lineage",
            "artifact://structural_graph",
            "artifact://semantic_ontology",
            "runtime://hardware_self_discovery",
            "runtime://toolchain_discovery",
        ],
        previous_session_history=previous_session_history,
        runtime_discovery_state=runtime_discovery_state,
        toolchain_discovery_state=toolchain_discovery_state,
    )

    store = RuntimeSessionRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.runtime_evidence_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "REAL_RUNTIME_EVIDENCE_INGESTION_LAYER",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "runtime_evidence_ingestion_fingerprint": result.runtime_evidence_bundle.get(
            "runtime_evidence_ingestion_fingerprint", ""
        ),
        "classification": result.runtime_evidence_bundle.get("classification", "UNKNOWN"),
        "artifact_files": {
            "normalized_runtime_evidence": str((output_dir / "normalized_runtime_evidence.json").resolve()),
            "runtime_session_graph": str((output_dir / "runtime_session_graph.json").resolve()),
            "evidence_capture_lineage": str((output_dir / "evidence_capture_lineage.json").resolve()),
            "subsystem_runtime_state": str((output_dir / "subsystem_runtime_state.json").resolve()),
            "dsp_runtime_trace": str((output_dir / "dsp_runtime_trace.json").resolve()),
            "soundwire_runtime_trace": str((output_dir / "soundwire_runtime_trace.json").resolve()),
            "pcm_runtime_state": str((output_dir / "pcm_runtime_state.json").resolve()),
            "runtime_discovery_report": str((output_dir / "runtime_discovery_report.json").resolve()),
            "runtime_toolchain_discovery": str((output_dir / "runtime_toolchain_discovery.json").resolve()),
            "hardware_topology_graph": str((output_dir / "hardware_topology_graph.json").resolve()),
            "audio_component_lineage_map": str((output_dir / "audio_component_lineage_map.json").resolve()),
            "runtime_evidence_snapshots": str((output_dir / "runtime_evidence_snapshots.json").resolve()),
            "inferred_playback_route_graph": str((output_dir / "inferred_playback_route_graph.json").resolve()),
            "inferred_capture_route_graph": str((output_dir / "inferred_capture_route_graph.json").resolve()),
            "mixer_dependency_report": str((output_dir / "mixer_dependency_report.json").resolve()),
            "real_playback_observability_timeline": str(
                (output_dir / "real_playback_observability_timeline.json").resolve()
            ),
            "offline_runtime_replay_foundation": str((output_dir / "offline_runtime_replay_foundation.json").resolve()),
            "runtime_capture_fingerprint": str((output_dir / "runtime_capture_fingerprint.json").resolve()),
            "deterministic_runtime_session_replay": str(
                (output_dir / "deterministic_runtime_session_replay.json").resolve()
            ),
        },
        "runtime_discovery_summary": _as_dict(
            _as_dict(result.runtime_evidence_bundle.get("artifacts")).get("runtime_discovery_report")
        ).get("summary", {}),
        "toolchain_summary": _as_dict(
            _as_dict(result.runtime_evidence_bundle.get("artifacts")).get("runtime_toolchain_discovery")
        ).get("summary", {}),
        "persisted": persisted,
        "replay": replay,
        "generated_at_epoch": time.time(),
    }

    (output_dir / "runtime_evidence_ingestion_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
