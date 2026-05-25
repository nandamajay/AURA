#!/usr/bin/env python3
"""Golden playback capture orchestrator for real ALSA runtime evidence.

This script captures the first authoritative real playback baseline as
GOLDEN_RUNTIME_SESSION_V1 using governed bridge commands only.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.target_fingerprint_engine import TargetFingerprintEngine

PARSER_VERSION = "golden-playback-capture-v1"
SESSION_ID = "GOLDEN_RUNTIME_SESSION_V1"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _trim_lines(text: str, limit: int = 4000) -> list[str]:
    return [line.rstrip("\n") for line in text.replace("\r", "").splitlines()[:limit] if line.strip()]


def _run_subprocess(cmd: list[str], timeout: int = 240) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _run_handshake(handshake_script: Path, bridge_root: Path, output_dir: Path) -> dict[str, Any]:
    cmd = [
        "bash",
        str(handshake_script),
        "--bridge-root",
        str(bridge_root),
        "--output-dir",
        str(output_dir),
    ]
    rc, stdout, stderr = _run_subprocess(cmd, timeout=120)
    payload: dict[str, Any]
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {
                "classification": "INVALID",
                "reason": "handshake_non_json_stdout",
                "raw_stdout": stdout,
                "raw_stderr": stderr,
            }
    else:
        payload = {
            "classification": "INVALID",
            "reason": "handshake_empty_stdout",
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }
    payload["return_code"] = rc
    return payload


def _run_bridge_submit(
    submit_script: Path,
    bridge_root: Path,
    commands: list[str],
    *,
    timeout_seconds: int,
    execution_mode: str,
    allow_write_ops: bool,
) -> dict[str, Any]:
    cmd = [
        "bash",
        str(submit_script),
        "--bridge-root",
        str(bridge_root),
        "--timeout-seconds",
        str(timeout_seconds),
        "--execution-mode",
        execution_mode,
    ]
    if allow_write_ops:
        cmd.append("--allow-write-ops")
    for command in commands:
        cmd.extend(["--command", command])

    rc, stdout, stderr = _run_subprocess(cmd, timeout=max(240, timeout_seconds + 120))

    summary: dict[str, Any]
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

    response_payload = _read_json(Path(str(summary.get("response", ""))))
    return {
        "return_code": rc,
        "summary": summary,
        "response": response_payload,
        "stdout": stdout,
        "stderr": stderr,
        "commands": list(commands),
        "execution_mode": execution_mode,
        "allow_write_ops": allow_write_ops,
        "started_at": _utc_now_iso(),
    }


def _trace_entry(response: Mapping[str, Any], command: str) -> dict[str, Any]:
    for item in _as_list(_as_dict(response).get("executor_command_trace")):
        row = _as_dict(item)
        if str(row.get("normalized_command", "")).strip() == command:
            return row
    return {}


def _trace_stdout(response: Mapping[str, Any], command: str) -> str:
    return str(_trace_entry(response, command).get("stdout", ""))


def _trace_stderr(response: Mapping[str, Any], command: str) -> str:
    return str(_trace_entry(response, command).get("stderr", ""))


def _trace_exit(response: Mapping[str, Any], command: str, default: int = -1) -> int:
    row = _trace_entry(response, command)
    try:
        return int(row.get("exit_code", default))
    except Exception:
        return default


def _extract_response_lines(response: Mapping[str, Any], command: str, limit: int = 6000) -> list[str]:
    stdout = _trace_stdout(response, command)
    stderr = _trace_stderr(response, command)
    return _trim_lines((stdout + "\n" + stderr), limit=limit)


def _sum_irq_counts(segment: str) -> tuple[int, str]:
    tokens = segment.split()
    counts: list[int] = []
    idx = 0
    while idx < len(tokens) and tokens[idx].isdigit():
        counts.append(int(tokens[idx]))
        idx += 1
    label = " ".join(tokens[idx:]).strip()
    return sum(counts), label


def _parse_interrupts(lines: list[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in lines:
        text = str(line).strip()
        if not text or text.startswith("CPU"):
            continue
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", text)
        if not match:
            continue
        irq_id = match.group(1)
        total, label = _sum_irq_counts(match.group(2))
        rows[irq_id] = {
            "irq_id": irq_id,
            "total": int(total),
            "label": label,
            "raw": text,
        }
    return rows


def _compute_irq_delta(before_lines: list[str], after_lines: list[str]) -> dict[str, Any]:
    before = _parse_interrupts(before_lines)
    after = _parse_interrupts(after_lines)
    delta_rows: list[dict[str, Any]] = []
    audio_tokens = ("snd", "audio", "wcd", "swr", "soundwire", "lpass", "q6", "adsp", "mi2s")

    for irq_id in sorted(set(before.keys()) | set(after.keys())):
        b = _as_dict(before.get(irq_id))
        a = _as_dict(after.get(irq_id))
        b_total = int(b.get("total", 0))
        a_total = int(a.get("total", 0))
        diff = a_total - b_total
        label = str(a.get("label", b.get("label", "")))
        if diff == 0:
            continue
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
        "delta_rows": delta_rows,
        "audio_delta_rows": audio_rows,
        "irq_active": bool(audio_rows),
        "total_delta_count": len(delta_rows),
        "audio_delta_count": len(audio_rows),
    }


def _ordered_diff(before_lines: list[str], after_lines: list[str]) -> list[str]:
    before_counter = Counter(before_lines)
    result: list[str] = []
    for line in after_lines:
        if before_counter[line] > 0:
            before_counter[line] -= 1
        else:
            result.append(line)
    return result


def _dapm_state(lines: list[str]) -> dict[str, str]:
    state: dict[str, str] = {}
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        lowered = text.lower()
        status = ""
        if "[on]" in lowered or re.search(r"\bon\b", lowered):
            status = "ON"
        elif "[off]" in lowered or re.search(r"\boff\b", lowered):
            status = "OFF"
        if not status:
            continue
        key = re.sub(r"\[(?:on|off)\]", "", text, flags=re.IGNORECASE)
        key = re.sub(r"\b(?:on|off)\b", "", key, flags=re.IGNORECASE).strip()
        if key:
            state[key] = status
    return state


def _dapm_delta(before_lines: list[str], after_lines: list[str]) -> dict[str, Any]:
    before = _dapm_state(before_lines)
    after = _dapm_state(after_lines)
    changes: list[dict[str, str]] = []
    oscillation = False
    for widget in sorted(set(before.keys()) | set(after.keys())):
        b = before.get(widget, "UNKNOWN")
        a = after.get(widget, "UNKNOWN")
        if b == a:
            continue
        changes.append({"widget": widget, "before": b, "after": a})
        if b == "ON" and a == "OFF":
            oscillation = True
    return {
        "changes": changes,
        "change_count": len(changes),
        "oscillation_detected": oscillation,
        "after_on_count": sum(1 for status in after.values() if status == "ON"),
        "before_on_count": sum(1 for status in before.values() if status == "ON"),
    }


def _extract_amixer_control_names(amixer_lines: list[str]) -> list[str]:
    names: list[str] = []
    for line in amixer_lines:
        match = re.search(r"Simple mixer control '([^']+)',\s*\d+", line)
        if match:
            names.append(match.group(1).strip())
    return sorted(set(name for name in names if name))


def _extract_tinymix_controls(tinymix_lines: list[str]) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for line in tinymix_lines:
        text = str(line).strip()
        match = re.match(r"^(\d+)\s+(.+?)\s+(-?\d+)\s*$", text)
        if not match:
            continue
        controls.append(
            {
                "control_id": int(match.group(1)),
                "name": match.group(2).strip(),
                "value": match.group(3).strip(),
            }
        )
    return controls


def _mixer_diff(before_lines: list[str], after_lines: list[str]) -> dict[str, Any]:
    diff_lines = _ordered_diff(before_lines, after_lines)
    return {
        "changed_line_count": len(diff_lines),
        "changed_lines_sample": diff_lines[:120],
    }


def _parse_pcm_device(pcm_id: str) -> str:
    parts = str(pcm_id).split("-", 1)
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"hw:{int(parts[0])},{int(parts[1])}"
    return ""


def _pick_pcm_routes(fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    pcm_entries = [
        _as_dict(item)
        for item in _as_list(_as_dict(fingerprint).get("audio_discovery", {}).get("pcm_entries"))
        if isinstance(item, dict)
    ]
    playback_entries = [
        entry
        for entry in pcm_entries
        if str(entry.get("direction", "")).lower() == "playback" and int(entry.get("streams", 0) or 0) > 0
    ]

    def score(entry: Mapping[str, Any], tokens: tuple[str, ...]) -> int:
        text = f"{entry.get('name', '')} {entry.get('interface', '')}".lower()
        return sum(1 for token in tokens if token in text)

    speaker_tokens = ("speaker", "spk", "primary", "multimedia", "mm")
    hp_tokens = ("headphone", "hph", "hp", "headset")

    speaker_sorted = sorted(
        playback_entries,
        key=lambda item: (score(item, speaker_tokens), int(item.get("streams", 0))),
        reverse=True,
    )
    hp_sorted = sorted(
        playback_entries,
        key=lambda item: (score(item, hp_tokens), int(item.get("streams", 0))),
        reverse=True,
    )

    speaker = _as_dict(speaker_sorted[0]) if speaker_sorted else {}
    headphone = _as_dict(hp_sorted[0]) if hp_sorted else {}
    candidate_devices: list[str] = []
    for entry in speaker_sorted:
        dev = _parse_pcm_device(str(_as_dict(entry).get("pcm_id", "")))
        if dev and dev not in candidate_devices:
            candidate_devices.append(dev)

    return {
        "playback_pcm_entries": playback_entries,
        "candidate_playback_devices": candidate_devices,
        "speaker_route": {
            "pcm_id": str(speaker.get("pcm_id", "")),
            "alsa_device": _parse_pcm_device(str(speaker.get("pcm_id", ""))),
            "name": str(speaker.get("name", "")),
            "interface": str(speaker.get("interface", "")),
            "streams": int(speaker.get("streams", 0) or 0),
        },
        "headphone_route": {
            "pcm_id": str(headphone.get("pcm_id", "")),
            "alsa_device": _parse_pcm_device(str(headphone.get("pcm_id", ""))),
            "name": str(headphone.get("name", "")),
            "interface": str(headphone.get("interface", "")),
            "streams": int(headphone.get("streams", 0) or 0),
        },
    }


def _infer_mixer_recipe(amixer_lines: list[str], tinymix_lines: list[str]) -> dict[str, Any]:
    amixer_controls = _extract_amixer_control_names(amixer_lines)
    tinymix_controls = _extract_tinymix_controls(tinymix_lines)

    speaker_tokens = ("speaker", "spkr", "wsa", "rx", "dac", "boost", "comp", "mux", "volume", "switch")
    hp_tokens = ("headphone", "hph", "hp", "rx", "dac", "mux", "volume", "switch")

    speaker_amixer = [
        name
        for name in amixer_controls
        if any(token in name.lower() for token in speaker_tokens)
    ]
    headphone_amixer = [
        name
        for name in amixer_controls
        if any(token in name.lower() for token in hp_tokens)
    ]

    speaker_tinymix = [
        row
        for row in tinymix_controls
        if any(token in str(row.get("name", "")).lower() for token in speaker_tokens)
    ]
    headphone_tinymix = [
        row
        for row in tinymix_controls
        if any(token in str(row.get("name", "")).lower() for token in hp_tokens)
    ]

    inferred_recipe: list[dict[str, Any]] = []
    for name in speaker_amixer[:80]:
        inferred_recipe.append({
            "source": "amixer",
            "control_name": name,
            "reason": "speaker_keyword_match",
        })
    for row in speaker_tinymix[:120]:
        inferred_recipe.append({
            "source": "tinymix",
            "control_id": int(row.get("control_id", 0) or 0),
            "control_name": str(row.get("name", "")),
            "current_value": str(row.get("value", "")),
            "reason": "speaker_keyword_match",
        })

    return {
        "speaker_amixer_controls": speaker_amixer,
        "headphone_amixer_controls": headphone_amixer,
        "speaker_tinymix_controls": speaker_tinymix,
        "headphone_tinymix_controls": headphone_tinymix,
        "inferred_activation_recipe": inferred_recipe,
    }


def _route_confidence(route_inference: Mapping[str, Any], fingerprint: Mapping[str, Any]) -> dict[str, Any]:
    speaker = _as_dict(route_inference.get("speaker_route"))
    mixer = _as_dict(route_inference.get("mixer_inference"))
    audio = _as_dict(fingerprint).get("audio_discovery", {})

    has_pcm = bool(str(speaker.get("alsa_device", "")))
    has_mixer = bool(_as_list(mixer.get("inferred_activation_recipe")))
    has_dapm = bool(_as_list(_as_dict(audio).get("dapm_widgets")))
    has_soundwire = bool(
        _as_list(_as_dict(audio).get("debugfs_asoc_nodes"))
        or _as_list(_as_dict(audio).get("debugfs_nodes"))
    )

    factors = {
        "speaker_pcm_discovered": has_pcm,
        "mixer_dependencies_discovered": has_mixer,
        "dapm_widgets_discovered": has_dapm,
        "soundwire_or_debugfs_present": has_soundwire,
    }
    score = round(sum(1.0 for value in factors.values() if value) / float(len(factors)), 3)

    confidence = "LOW"
    if score >= 0.85:
        confidence = "HIGH"
    elif score >= 0.6:
        confidence = "MEDIUM"

    return {
        "confidence_score": score,
        "confidence": confidence,
        "factors": factors,
    }


def _build_runtime_fingerprint(repo_root: Path) -> dict[str, Any]:
    try:
        rc, stdout, _ = _run_subprocess(["git", "-C", str(repo_root), "rev-parse", "HEAD"], timeout=30)
        git_sha = stdout.strip() if rc == 0 else "UNKNOWN"
    except Exception:
        git_sha = "UNKNOWN"

    deps: list[str] = []
    try:
        for dist in importlib.metadata.distributions():
            name = str(dist.metadata.get("Name", "")).strip() or str(dist.metadata.get("Summary", "")).strip()
            if not name:
                continue
            deps.append(f"{name}=={dist.version}")
    except Exception:
        deps = []

    deps_sorted = sorted(set(deps))
    dependency_hash = hashlib.sha256("\n".join(deps_sorted).encode("utf-8")).hexdigest()

    return {
        "python_version": sys.version.split()[0],
        "parser_version": PARSER_VERSION,
        "git_sha": git_sha,
        "execution_container_hash": str(os.getenv("AURA_EXECUTION_CONTAINER_HASH", "UNKNOWN")),
        "dependency_hash_sha256": dependency_hash,
        "dependency_count": len(deps_sorted),
        "generated_at": _utc_now_iso(),
    }


def _build_temporal_causality(
    *,
    pre_phase: Mapping[str, Any],
    playback_phase: Mapping[str, Any],
    post_phase: Mapping[str, Any],
    irq_delta: Mapping[str, Any],
    dmesg_delta: list[str],
    dapm_delta: Mapping[str, Any],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    pre_response = _as_dict(pre_phase.get("response"))
    playback_response = _as_dict(playback_phase.get("response"))
    post_response = _as_dict(post_phase.get("response"))

    def add_event(event_type: str, timestamp: str, details: Mapping[str, Any]) -> None:
        events.append(
            {
                "event_id": f"event:{len(events) + 1}",
                "event_type": event_type,
                "timestamp": timestamp,
                "details": dict(details),
            }
        )

    pre_finished = str(_as_dict(pre_response.get("timestamps")).get("finished_at", ""))
    if pre_finished:
        add_event(
            "pre_snapshot_completed",
            pre_finished,
            {
                "request_id": str(pre_response.get("request_id", "")),
                "command_count": len(_as_list(pre_response.get("executor_command_trace"))),
            },
        )

    playback_trace = _as_list(playback_response.get("executor_command_trace"))
    playback_entry = _as_dict(playback_trace[0]) if playback_trace else {}
    playback_started = str(playback_entry.get("started_at", ""))
    playback_finished = str(playback_entry.get("finished_at", ""))
    if playback_started:
        add_event(
            "playback_started",
            playback_started,
            {
                "request_id": str(playback_response.get("request_id", "")),
                "command": str(playback_entry.get("normalized_command", "")),
            },
        )
    if playback_finished:
        add_event(
            "playback_finished",
            playback_finished,
            {
                "exit_code": int(playback_entry.get("exit_code", -1) or -1),
                "execution_status": str(playback_entry.get("execution_status", "")),
            },
        )

    if int(_as_dict(irq_delta).get("audio_delta_count", 0) or 0) > 0:
        add_event(
            "irq_activity_observed",
            str(_as_dict(post_response.get("timestamps")).get("finished_at", "")) or _utc_now_iso(),
            {
                "audio_delta_count": int(_as_dict(irq_delta).get("audio_delta_count", 0) or 0),
                "sample": _as_list(_as_dict(irq_delta).get("audio_delta_rows"))[:20],
            },
        )

    if dmesg_delta:
        add_event(
            "dmesg_runtime_delta_observed",
            str(_as_dict(post_response.get("timestamps")).get("finished_at", "")) or _utc_now_iso(),
            {
                "line_count": len(dmesg_delta),
                "sample": dmesg_delta[:80],
            },
        )

    if int(_as_dict(dapm_delta).get("change_count", 0) or 0) > 0:
        add_event(
            "dapm_transition_observed",
            str(_as_dict(post_response.get("timestamps")).get("finished_at", "")) or _utc_now_iso(),
            {
                "change_count": int(_as_dict(dapm_delta).get("change_count", 0) or 0),
                "sample": _as_list(_as_dict(dapm_delta).get("changes"))[:60],
            },
        )

    post_finished = str(_as_dict(post_response.get("timestamps")).get("finished_at", ""))
    if post_finished:
        add_event(
            "post_snapshot_completed",
            post_finished,
            {
                "request_id": str(post_response.get("request_id", "")),
                "command_count": len(_as_list(post_response.get("executor_command_trace"))),
            },
        )

    edges: list[dict[str, Any]] = []

    def add_edge(from_type: str, to_type: str, relation: str, evidence: str) -> None:
        from_event = next((e for e in events if str(e.get("event_type", "")) == from_type), None)
        to_event = next((e for e in events if str(e.get("event_type", "")) == to_type), None)
        if not from_event or not to_event:
            return
        edges.append(
            {
                "from": str(from_event.get("event_id", "")),
                "to": str(to_event.get("event_id", "")),
                "relation": relation,
                "evidence": evidence,
            }
        )

    add_edge("playback_started", "playback_finished", "lifecycle", "aplay_trace")
    add_edge("playback_started", "irq_activity_observed", "causes", "irq_delta")
    add_edge("playback_started", "dmesg_runtime_delta_observed", "causes", "dmesg_delta")
    add_edge("playback_started", "dapm_transition_observed", "causes", "dapm_delta")
    add_edge("playback_finished", "post_snapshot_completed", "precedes", "post_capture")

    payload = {
        "session_id": SESSION_ID,
        "report_name": "golden_runtime_temporal_causality_graph",
        "events": events,
        "edges": edges,
        "generated_at": _utc_now_iso(),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _phase_transport_ok(phase: Mapping[str, Any]) -> bool:
    summary = _as_dict(phase.get("summary"))
    response = _as_dict(phase.get("response"))
    classification = str(summary.get("classification", ""))
    status = str(response.get("execution_status", ""))
    if classification in {"INVALID", "UNKNOWN"}:
        return False
    return status in {"executed", "failed"}


def _classify_governance(
    *,
    route_confidence: Mapping[str, Any],
    irq_delta: Mapping[str, Any],
    dapm_delta: Mapping[str, Any],
    playback_phase: Mapping[str, Any],
    push_phase: Mapping[str, Any],
    pre_phase: Mapping[str, Any],
    post_phase: Mapping[str, Any],
    route_inference: Mapping[str, Any],
    mixer_inference: Mapping[str, Any],
) -> dict[str, Any]:
    playback_response = _as_dict(playback_phase.get("response"))
    playback_trace = _as_list(playback_response.get("executor_command_trace"))
    playback_entry = _as_dict(playback_trace[0]) if playback_trace else {}

    playback_lifecycle_complete = (
        str(playback_entry.get("execution_status", "")) == "executed"
        and int(playback_entry.get("exit_code", -1) or -1) == 0
        and bool(str(playback_entry.get("started_at", "")))
        and bool(str(playback_entry.get("finished_at", "")))
    )

    route_stability_score = float(_as_dict(route_confidence).get("confidence_score", 0.0) or 0.0)
    route_stable = route_stability_score >= 0.6 and playback_lifecycle_complete

    irq_active = bool(_as_dict(irq_delta).get("irq_active", False))
    dapm_converged = (
        bool(_as_dict(dapm_delta).get("after_on_count", 0))
        and not bool(_as_dict(dapm_delta).get("oscillation_detected", False))
    )

    speaker_route = _as_dict(route_inference.get("speaker_route"))
    unresolved_dependency_collapse = not bool(str(speaker_route.get("alsa_device", ""))) or not bool(
        _as_list(_as_dict(mixer_inference).get("inferred_activation_recipe"))
    )
    invalid_route_oscillation = bool(_as_dict(dapm_delta).get("oscillation_detected", False))

    transport_ok = _phase_transport_ok(pre_phase) and _phase_transport_ok(post_phase)
    write_ok = _phase_transport_ok(push_phase) and playback_lifecycle_complete

    fail_reasons: list[str] = []
    if not route_stable:
        fail_reasons.append("route_not_stable")
    if not irq_active:
        fail_reasons.append("irq_not_active")
    if not dapm_converged:
        fail_reasons.append("dapm_not_converged")
    if not playback_lifecycle_complete:
        fail_reasons.append("playback_lifecycle_incomplete")
    if unresolved_dependency_collapse:
        fail_reasons.append("unresolved_dependency_collapse")
    if invalid_route_oscillation:
        fail_reasons.append("invalid_route_oscillation")
    if not transport_ok:
        fail_reasons.append("snapshot_transport_failure")
    if not write_ok:
        fail_reasons.append("playback_write_phase_failure")

    classification = "PASS" if not fail_reasons else "FAIL_CLOSED"

    payload = {
        "session_id": SESSION_ID,
        "classification": classification,
        "fail_closed_posture": True,
        "criteria": {
            "route_stable": route_stable,
            "irq_active": irq_active,
            "dapm_converged": dapm_converged,
            "playback_lifecycle_complete": playback_lifecycle_complete,
            "unresolved_dependency_collapse": unresolved_dependency_collapse,
            "invalid_route_oscillation": invalid_route_oscillation,
            "transport_ok": transport_ok,
            "write_ok": write_ok,
        },
        "route_stability_score": round(route_stability_score, 3),
        "fail_reasons": fail_reasons,
        "generated_at": _utc_now_iso(),
    }
    payload["deterministic_fingerprint"] = stable_fingerprint(payload)
    return payload


def _render_report_md(
    *,
    session_payload: Mapping[str, Any],
    governance_payload: Mapping[str, Any],
    output_paths: Mapping[str, Any],
) -> str:
    discovery = _as_dict(session_payload.get("hardware_discovery"))
    route = _as_dict(session_payload.get("playback_route_inference"))
    telemetry = _as_dict(session_payload.get("live_playback_observability"))
    replay = _as_dict(session_payload.get("replay_artifact"))
    blockers = [str(item) for item in _as_list(session_payload.get("blockers"))]

    lines = [
        "# GOLDEN_RUNTIME_SESSION_V1",
        "",
        "## Classification",
        f"- classification: `{governance_payload.get('classification', 'UNKNOWN')}`",
        f"- fail_reasons: `{', '.join(_as_list(governance_payload.get('fail_reasons'))) or 'none'}`",
        f"- blockers: `{'; '.join(blockers) or 'none'}`",
        "",
        "## Hardware Discovery",
        f"- kernel: `{_as_dict(discovery.get('kernel')).get('release', '')}`",
        f"- sound_cards: `{len(_as_list(_as_dict(discovery.get('fingerprint')).get('audio_discovery', {}).get('alsa_topology_cards')))}`",
        f"- pcm_entries: `{len(_as_list(_as_dict(discovery.get('fingerprint')).get('audio_discovery', {}).get('pcm_entries')))}`",
        f"- dapm_widgets: `{len(_as_list(_as_dict(discovery.get('fingerprint')).get('audio_discovery', {}).get('dapm_widgets')))}`",
        "",
        "## Route Inference",
        f"- speaker_alsa_device: `{_as_dict(route.get('speaker_route')).get('alsa_device', '')}`",
        f"- headphone_alsa_device: `{_as_dict(route.get('headphone_route')).get('alsa_device', '')}`",
        f"- confidence: `{_as_dict(route.get('route_confidence')).get('confidence', 'LOW')}`",
        f"- inferred_mixer_controls: `{len(_as_list(_as_dict(route.get('mixer_inference')).get('inferred_activation_recipe')))}`",
        "",
        "## Playback Observability",
        f"- playback_exit_code: `{_as_dict(telemetry.get('playback_execution')).get('exit_code', -1)}`",
        f"- irq_audio_deltas: `{_as_dict(_as_dict(telemetry.get('irq_delta')).get('summary')).get('audio_delta_count', 0)}`",
        f"- dmesg_delta_lines: `{_as_dict(_as_dict(telemetry.get('dmesg_delta')).get('summary')).get('line_count', 0)}`",
        f"- dapm_changes: `{_as_dict(_as_dict(telemetry.get('dapm_delta')).get('summary')).get('change_count', 0)}`",
        "",
        "## Replay",
        f"- runtime_sequence_fingerprint: `{replay.get('runtime_sequence_fingerprint', '')}`",
        f"- deterministic_replay_fingerprint: `{replay.get('deterministic_replay_fingerprint', '')}`",
        "",
        "## Artifacts",
    ]

    for key, value in sorted(dict(output_paths).items()):
        lines.append(f"- {key}: `{value}`")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture GOLDEN_RUNTIME_SESSION_V1 playback baseline")
    parser.add_argument("--bridge-root", default="/local/mnt/workspace/AURA_V1/bridge")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument(
        "--asset-source-rel",
        default="assets/rb3gen2/speaker_validation_48k_stereo.wav",
        help="Path relative to bridge root used for governed adb push",
    )
    parser.add_argument(
        "--target-playback-path",
        default="/data/local/tmp/aura/audio/golden_runtime_session_v1.wav",
    )
    parser.add_argument(
        "--playback-device-prefix",
        choices=("hw", "plughw"),
        default="plughw",
        help="ALSA device prefix for AURA_PLAYBACK_APLAY command",
    )
    parser.add_argument("--skip-push", action="store_true")
    parser.add_argument("--skip-cleanup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bridge_root = Path(args.bridge_root)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    submit_script = REPO_ROOT / "scripts" / "linux-bridge-submit.sh"
    handshake_script = REPO_ROOT / "scripts" / "linux-bridge-handshake.sh"

    runtime_fp = _build_runtime_fingerprint(REPO_ROOT.parent)

    handshake = _run_handshake(handshake_script, bridge_root, output_dir)

    discovery_commands = [
        "uname -a",
        "cat /proc/version",
        "cat /proc/asound/cards",
        "cat /proc/asound/pcm",
        "head -n 200 /proc/interrupts",
        "dmesg | tail -200",
        "ls /sys/kernel/debug",
        "ls /sys/kernel/debug/asoc",
        "cat /sys/kernel/debug/asoc/*/dapm",
        "amixer",
        "tinymix",
        "lsmod",
    ]

    discovery_phase = _run_bridge_submit(
        submit_script,
        bridge_root,
        discovery_commands,
        timeout_seconds=args.timeout_seconds,
        execution_mode="governed_read_only",
        allow_write_ops=False,
    )
    discovery_response = _as_dict(discovery_phase.get("response"))

    fingerprint = TargetFingerprintEngine().build_fingerprint(discovery_response).fingerprint

    kernel_release = ""
    uname_lines = _extract_response_lines(discovery_response, "uname -a", limit=10)
    if uname_lines:
        kernel_release = uname_lines[0]

    amixer_lines_discovery = _extract_response_lines(discovery_response, "amixer", limit=12000)
    tinymix_lines_discovery = _extract_response_lines(discovery_response, "tinymix", limit=12000)

    pcm_routes = _pick_pcm_routes(fingerprint)
    mixer_inference = _infer_mixer_recipe(amixer_lines_discovery, tinymix_lines_discovery)
    route_inference = {
        **pcm_routes,
        "mixer_inference": mixer_inference,
    }
    route_inference["route_confidence"] = _route_confidence(route_inference, fingerprint)

    speaker_device = str(_as_dict(route_inference.get("speaker_route")).get("alsa_device", ""))
    candidate_playback_devices: list[str] = []
    for base_dev in _as_list(route_inference.get("candidate_playback_devices")):
        value = str(base_dev).strip()
        if not value or ":" not in value:
            continue
        _, suffix = value.split(":", 1)
        for prefix in (
            args.playback_device_prefix,
            "hw" if args.playback_device_prefix == "plughw" else "plughw",
        ):
            candidate = f"{prefix}:{suffix}"
            if candidate not in candidate_playback_devices:
                candidate_playback_devices.append(candidate)
    if not candidate_playback_devices and speaker_device:
        candidate_playback_devices.append(speaker_device)
    for fallback_dev in ("default", "sysdefault"):
        if fallback_dev not in candidate_playback_devices:
            candidate_playback_devices.append(fallback_dev)
    asset_abs = bridge_root / str(args.asset_source_rel)
    asset_sha = ""
    if asset_abs.exists() and asset_abs.is_file():
        asset_sha = hashlib.sha256(asset_abs.read_bytes()).hexdigest()

    push_command = ""
    if not args.skip_push and asset_sha:
        push_command = (
            f"AURA_ADB_PUSH {args.asset_source_rel} {args.target_playback_path} "
            f"{asset_sha} allow_overwrite"
        )

    playback_command = (
        f"AURA_PLAYBACK_APLAY {candidate_playback_devices[0]} {args.target_playback_path}"
        if candidate_playback_devices
        else ""
    )
    cleanup_command = f"AURA_ADB_RM {args.target_playback_path}"

    pre_snapshot_commands = [
        "cat /proc/asound/cards",
        "cat /proc/asound/pcm",
        "head -n 200 /proc/interrupts",
        "dmesg | tail -200",
        "cat /sys/kernel/debug/asoc/*/dapm",
        "amixer",
        "tinymix",
    ]

    pre_phase = _run_bridge_submit(
        submit_script,
        bridge_root,
        pre_snapshot_commands,
        timeout_seconds=args.timeout_seconds,
        execution_mode="governed_read_only",
        allow_write_ops=False,
    )

    playback_attempts: list[dict[str, Any]] = []
    if args.dry_run:
        push_phase = {
            "summary": {"classification": "INVALID", "reason": "dry_run"},
            "response": {},
            "commands": [push_command] if push_command else [],
        }
        playback_phase = {
            "summary": {"classification": "INVALID", "reason": "dry_run"},
            "response": {},
            "commands": [playback_command] if playback_command else [],
        }
        if playback_command:
            playback_attempts.append(
                {
                    "playback_device": candidate_playback_devices[0],
                    "playback_command": playback_command,
                    "phase": playback_phase,
                }
            )
        cleanup_phase = {
            "summary": {"classification": "INVALID", "reason": "dry_run"},
            "response": {},
            "commands": [cleanup_command],
        }
    else:
        push_phase = _run_bridge_submit(
            submit_script,
            bridge_root,
            [push_command] if push_command else [],
            timeout_seconds=args.timeout_seconds,
            execution_mode="governed_write_approved",
            allow_write_ops=True,
        )
        playback_phase = {
            "summary": {"classification": "INVALID", "reason": "no_playback_device_candidates"},
            "response": {},
            "commands": [],
        }
        best_playback_phase: dict[str, Any] | None = None
        for dev in candidate_playback_devices:
            attempt_command = f"AURA_PLAYBACK_APLAY {dev} {args.target_playback_path}"
            attempt_phase = _run_bridge_submit(
                submit_script,
                bridge_root,
                [attempt_command],
                timeout_seconds=args.timeout_seconds,
                execution_mode="governed_write_approved",
                allow_write_ops=True,
            )
            playback_attempts.append(
                {
                    "playback_device": dev,
                    "playback_command": attempt_command,
                    "phase": attempt_phase,
                }
            )
            playback_phase = attempt_phase
            attempt_response = _as_dict(attempt_phase.get("response"))
            if str(attempt_response.get("execution_status", "")) in {"executed", "failed"}:
                best_playback_phase = attempt_phase
            attempt_trace = _as_list(attempt_response.get("executor_command_trace"))
            attempt_entry = _as_dict(attempt_trace[0]) if attempt_trace else {}
            if (
                str(attempt_entry.get("execution_status", "")) == "executed"
                and int(attempt_entry.get("exit_code", -1) or -1) == 0
            ):
                break
        if best_playback_phase is not None:
            playback_phase = best_playback_phase
        cleanup_phase = _run_bridge_submit(
            submit_script,
            bridge_root,
            [] if args.skip_cleanup else [cleanup_command],
            timeout_seconds=args.timeout_seconds,
            execution_mode="governed_write_approved",
            allow_write_ops=True,
        )

    post_phase = _run_bridge_submit(
        submit_script,
        bridge_root,
        pre_snapshot_commands,
        timeout_seconds=args.timeout_seconds,
        execution_mode="governed_read_only",
        allow_write_ops=False,
    )

    pre_response = _as_dict(pre_phase.get("response"))
    post_response = _as_dict(post_phase.get("response"))

    pre_interrupts = _extract_response_lines(pre_response, "head -n 200 /proc/interrupts", limit=3000)
    post_interrupts = _extract_response_lines(post_response, "head -n 200 /proc/interrupts", limit=3000)
    irq_delta = _compute_irq_delta(pre_interrupts, post_interrupts)

    pre_dmesg = _extract_response_lines(pre_response, "dmesg | tail -200", limit=3000)
    post_dmesg = _extract_response_lines(post_response, "dmesg | tail -200", limit=3000)
    dmesg_delta_lines = _ordered_diff(pre_dmesg, post_dmesg)
    dmesg_delta = {
        "lines": dmesg_delta_lines,
        "summary": {
            "line_count": len(dmesg_delta_lines),
            "soundwire_mentions": sum(1 for line in dmesg_delta_lines if "soundwire" in line.lower() or "swr" in line.lower()),
            "pcm_mentions": sum(1 for line in dmesg_delta_lines if "pcm" in line.lower()),
            "trigger_mentions": sum(1 for line in dmesg_delta_lines if "trigger" in line.lower()),
            "hw_params_mentions": sum(1 for line in dmesg_delta_lines if "hw_params" in line.lower()),
            "prepare_mentions": sum(1 for line in dmesg_delta_lines if "prepare" in line.lower()),
        },
    }

    pre_dapm = _extract_response_lines(pre_response, "cat /sys/kernel/debug/asoc/*/dapm", limit=12000)
    post_dapm = _extract_response_lines(post_response, "cat /sys/kernel/debug/asoc/*/dapm", limit=12000)
    dapm_delta = _dapm_delta(pre_dapm, post_dapm)
    dapm_delta_payload = {
        "changes": _as_list(dapm_delta.get("changes")),
        "summary": {
            "change_count": int(_as_dict(dapm_delta).get("change_count", 0) or 0),
            "oscillation_detected": bool(_as_dict(dapm_delta).get("oscillation_detected", False)),
            "before_on_count": int(_as_dict(dapm_delta).get("before_on_count", 0) or 0),
            "after_on_count": int(_as_dict(dapm_delta).get("after_on_count", 0) or 0),
        },
    }

    pre_amixer = _extract_response_lines(pre_response, "amixer", limit=12000)
    post_amixer = _extract_response_lines(post_response, "amixer", limit=12000)
    pre_tinymix = _extract_response_lines(pre_response, "tinymix", limit=12000)
    post_tinymix = _extract_response_lines(post_response, "tinymix", limit=12000)

    mixer_mutation = {
        "amixer": _mixer_diff(pre_amixer, post_amixer),
        "tinymix": _mixer_diff(pre_tinymix, post_tinymix),
    }

    irq_summary = {
        "total_delta_count": int(_as_dict(irq_delta).get("total_delta_count", 0) or 0),
        "audio_delta_count": int(_as_dict(irq_delta).get("audio_delta_count", 0) or 0),
        "irq_active": bool(_as_dict(irq_delta).get("irq_active", False)),
    }
    irq_delta_payload = {
        "rows": _as_list(_as_dict(irq_delta).get("delta_rows")),
        "audio_rows": _as_list(_as_dict(irq_delta).get("audio_delta_rows")),
        "summary": irq_summary,
    }

    temporal_causality = _build_temporal_causality(
        pre_phase=pre_phase,
        playback_phase=playback_phase,
        post_phase=post_phase,
        irq_delta=irq_delta,
        dmesg_delta=dmesg_delta_lines,
        dapm_delta=dapm_delta,
    )

    governance = _classify_governance(
        route_confidence=_as_dict(route_inference.get("route_confidence")),
        irq_delta=irq_delta,
        dapm_delta=dapm_delta,
        playback_phase=playback_phase,
        push_phase=push_phase,
        pre_phase=pre_phase,
        post_phase=post_phase,
        route_inference=route_inference,
        mixer_inference=mixer_inference,
    )

    blockers: list[str] = []
    if str(governance.get("classification", "")) != "PASS":
        for item in _as_list(governance.get("fail_reasons")):
            blockers.append(f"governance:{str(item)}")
    if playback_attempts:
        failed_attempts: list[str] = []
        for attempt in playback_attempts:
            phase = _as_dict(_as_dict(attempt).get("phase"))
            response = _as_dict(phase.get("response"))
            trace = _as_list(response.get("executor_command_trace"))
            entry = _as_dict(trace[0]) if trace else {}
            if int(entry.get("exit_code", -1) or -1) != 0:
                stdout_line = _trim_lines(str(entry.get("stdout", "")), limit=1)
                reason = stdout_line[0] if stdout_line else str(_as_dict(phase.get("summary")).get("reason", "playback_failed"))
                failed_attempts.append(f"{_as_dict(attempt).get('playback_device', 'unknown')}:{reason}")
        if failed_attempts and len(failed_attempts) == len(playback_attempts):
            blockers.append("playback_attempts_exhausted:" + " | ".join(failed_attempts[:8]))
    if not _as_list(_as_dict(fingerprint).get("audio_discovery", {}).get("dapm_widgets")):
        blockers.append("dapm_widget_states_not_extracted_from_runtime")
    blockers.append("during_window_metrics_derived_from_playback_trace_not_concurrent_sampling")
    blockers.append("dts_lineage_partial_due_bridge_allowlist_proc_device_tree_unavailable")

    playback_response = _as_dict(playback_phase.get("response"))
    playback_entry = _as_dict(_as_list(playback_response.get("executor_command_trace"))[0]) if _as_list(playback_response.get("executor_command_trace")) else {}

    replay_artifact = {
        "session_id": SESSION_ID,
        "replay_type": "real_alsa_playback",
        "ordered_events": _as_list(_as_dict(temporal_causality).get("events")),
        "causal_edges": _as_list(_as_dict(temporal_causality).get("edges")),
        "request_lineage": {
            "discovery_request_id": str(_as_dict(discovery_response).get("request_id", "")),
            "pre_snapshot_request_id": str(_as_dict(pre_response).get("request_id", "")),
            "playback_request_id": str(_as_dict(playback_response).get("request_id", "")),
            "post_snapshot_request_id": str(_as_dict(post_response).get("request_id", "")),
            "cleanup_request_id": str(_as_dict(_as_dict(cleanup_phase).get("response")).get("request_id", "")),
        },
        "runtime_sequence_fingerprint": stable_fingerprint(
            {
                "events": _as_list(_as_dict(temporal_causality).get("events")),
                "edges": _as_list(_as_dict(temporal_causality).get("edges")),
            }
        ),
        "deterministic_replay_fingerprint": stable_fingerprint(
            {
                "session_id": SESSION_ID,
                "playback_command": str(playback_command),
                "playback_exit_code": int(playback_entry.get("exit_code", -1) or -1),
                "route_confidence": _as_dict(route_inference.get("route_confidence")),
                "irq_summary": irq_summary,
                "governance": governance,
            }
        ),
        "generated_at": _utc_now_iso(),
    }

    hardware_discovery = {
        "session_id": SESSION_ID,
        "target_id": args.target_id,
        "kernel": {
            "release": kernel_release,
            "uname": uname_lines,
            "proc_version": _extract_response_lines(discovery_response, "cat /proc/version", limit=40),
        },
        "fingerprint": fingerprint,
        "dts_lineage": {
            "status": "PARTIAL",
            "reason": "runtime_bridge_has_no_direct_proc_device_tree_probe",
            "evidence": {
                "cards": _as_list(_as_dict(fingerprint).get("audio_discovery", {}).get("alsa_topology_cards")),
                "pcm_entries": _as_list(_as_dict(fingerprint).get("audio_discovery", {}).get("pcm_entries")),
            },
        },
        "discovery_request": {
            "summary": _as_dict(discovery_phase.get("summary")),
            "response_request_id": str(_as_dict(discovery_response).get("request_id", "")),
        },
        "runtime_fingerprint": runtime_fp,
    }
    hardware_discovery["deterministic_fingerprint"] = stable_fingerprint(hardware_discovery)

    route_payload = {
        "session_id": SESSION_ID,
        "speaker_route": _as_dict(route_inference.get("speaker_route")),
        "headphone_route": _as_dict(route_inference.get("headphone_route")),
        "mixer_inference": mixer_inference,
        "route_confidence": _as_dict(route_inference.get("route_confidence")),
        "dependency_graph": {
            "nodes": [
                {"id": "pcm:speaker", "kind": "pcm", "label": str(_as_dict(route_inference.get("speaker_route")).get("alsa_device", ""))},
                {"id": "mixer:inferred", "kind": "mixer", "label": "inferred_controls"},
                {"id": "dapm:widgets", "kind": "dapm", "label": "runtime_widgets"},
                {"id": "soundwire:runtime", "kind": "runtime", "label": "soundwire_or_swr"},
            ],
            "edges": [
                {"from": "pcm:speaker", "to": "mixer:inferred", "relation": "requires"},
                {"from": "mixer:inferred", "to": "dapm:widgets", "relation": "activates"},
                {"from": "dapm:widgets", "to": "soundwire:runtime", "relation": "propagates_to"},
            ],
        },
        "deterministic_fingerprint": "",
    }
    route_payload["deterministic_fingerprint"] = stable_fingerprint(route_payload)

    playback_execution = {
        "push_command": push_command,
        "playback_command": str(playback_entry.get("normalized_command", playback_command)),
        "playback_attempt_count": len(playback_attempts),
        "playback_attempts": [
            {
                "playback_device": str(_as_dict(item).get("playback_device", "")),
                "playback_command": str(_as_dict(item).get("playback_command", "")),
                "summary": _as_dict(_as_dict(item).get("phase", {}).get("summary")),
                "exit_code": int(
                    _trace_exit(
                        _as_dict(_as_dict(item).get("phase", {}).get("response")),
                        str(_as_dict(item).get("playback_command", "")),
                        default=-1,
                    )
                ),
            }
            for item in playback_attempts
        ],
        "cleanup_command": cleanup_command,
        "push_request": _as_dict(push_phase.get("summary")),
        "playback_request": _as_dict(playback_phase.get("summary")),
        "cleanup_request": _as_dict(cleanup_phase.get("summary")),
        "exit_code": int(playback_entry.get("exit_code", -1) or -1),
        "execution_status": str(playback_entry.get("execution_status", "")),
        "started_at": str(playback_entry.get("started_at", "")),
        "finished_at": str(playback_entry.get("finished_at", "")),
        "stderr": str(playback_entry.get("stderr", "")),
        "stdout_sample": _trim_lines(str(playback_entry.get("stdout", "")), limit=120),
    }

    live_playback_observability = {
        "session_id": SESSION_ID,
        "before_snapshot": {
            "request_id": str(_as_dict(pre_response).get("request_id", "")),
            "commands": pre_snapshot_commands,
        },
        "during_window": {
            "playback_trace": playback_execution,
            "note": "during metrics are derived from governed playback command trace window",
        },
        "after_snapshot": {
            "request_id": str(_as_dict(post_response).get("request_id", "")),
            "commands": pre_snapshot_commands,
        },
        "playback_execution": playback_execution,
        "irq_delta": irq_delta_payload,
        "dmesg_delta": dmesg_delta,
        "dapm_delta": dapm_delta_payload,
        "mixer_mutation": mixer_mutation,
    }
    live_playback_observability["deterministic_fingerprint"] = stable_fingerprint(live_playback_observability)

    golden_session = {
        "session_id": SESSION_ID,
        "schema_version": "1.0",
        "generated_at": _utc_now_iso(),
        "runtime_fingerprint": runtime_fp,
        "handshake": handshake,
        "hardware_discovery": hardware_discovery,
        "playback_route_inference": route_payload,
        "live_playback_observability": live_playback_observability,
        "temporal_causal_graph": temporal_causality,
        "replay_artifact": replay_artifact,
        "governance": governance,
        "blockers": blockers,
        "fail_closed_posture": True,
        "evidence_lineage": {
            "bridge_requests": {
                "discovery": str(_as_dict(discovery_response).get("request_id", "")),
                "pre_snapshot": str(_as_dict(pre_response).get("request_id", "")),
                "playback": str(_as_dict(playback_response).get("request_id", "")),
                "post_snapshot": str(_as_dict(post_response).get("request_id", "")),
                "cleanup": str(_as_dict(_as_dict(cleanup_phase).get("response")).get("request_id", "")),
            },
            "bridge_response_paths": {
                "discovery": str(_as_dict(discovery_phase.get("summary")).get("response", "")),
                "pre_snapshot": str(_as_dict(pre_phase.get("summary")).get("response", "")),
                "playback": str(_as_dict(playback_phase.get("summary")).get("response", "")),
                "post_snapshot": str(_as_dict(post_phase.get("summary")).get("response", "")),
                "cleanup": str(_as_dict(cleanup_phase.get("summary")).get("response", "")),
            },
        },
    }
    golden_session["deterministic_fingerprint"] = stable_fingerprint(golden_session)

    base = output_dir / "golden_runtime_session_v1"
    golden_json = base.with_suffix(".json")
    hardware_json = output_dir / "golden_runtime_session_v1_hardware_discovery.json"
    route_json = output_dir / "golden_runtime_session_v1_route_inference.json"
    observability_json = output_dir / "golden_runtime_session_v1_live_playback_observability.json"
    causality_json = output_dir / "golden_runtime_session_v1_temporal_causal_graph.json"
    replay_json = output_dir / "golden_runtime_session_v1_replay.json"
    governance_json = output_dir / "golden_runtime_session_v1_governance.json"
    report_md = output_dir / "golden_runtime_session_v1_report.md"

    _write_json(golden_json, golden_session)
    _write_json(hardware_json, hardware_discovery)
    _write_json(route_json, route_payload)
    _write_json(observability_json, live_playback_observability)
    _write_json(causality_json, temporal_causality)
    _write_json(replay_json, replay_artifact)
    _write_json(governance_json, governance)

    output_paths = {
        "golden_session": str(golden_json.resolve()),
        "hardware_discovery": str(hardware_json.resolve()),
        "route_inference": str(route_json.resolve()),
        "live_playback_observability": str(observability_json.resolve()),
        "temporal_causal_graph": str(causality_json.resolve()),
        "replay_artifact": str(replay_json.resolve()),
        "governance": str(governance_json.resolve()),
        "report": str(report_md.resolve()),
    }

    report_text = _render_report_md(
        session_payload=golden_session,
        governance_payload=governance,
        output_paths=output_paths,
    )
    report_md.write_text(report_text, encoding="utf-8")

    print(
        json.dumps(
            {
                "session_id": SESSION_ID,
                "classification": str(governance.get("classification", "UNKNOWN")),
                "fail_reasons": _as_list(governance.get("fail_reasons")),
                "route_confidence": _as_dict(_as_dict(route_payload).get("route_confidence")).get("confidence", "LOW"),
                "irq_audio_delta_count": int(_as_dict(_as_dict(irq_delta_payload).get("summary")).get("audio_delta_count", 0) or 0),
                "output_paths": output_paths,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
