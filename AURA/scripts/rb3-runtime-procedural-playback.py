#!/usr/bin/env python3
"""Controlled runtime procedural validation for RB3Gen2 speaker playback."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.command_planner import build_rb3_speaker_workflow
from aura_sdk.transport.rb3_playback_cognition import (
    RB3ProceduralMemory,
    build_playback_state_machine,
    correlate_runtime_evidence,
    explain_playback_failure,
)
from aura_sdk.transport.rb3_baseline_profiles import (
    RB3BaselineProfileRegistry,
    RB3ProceduralMemoryLock,
    build_runtime_regression_comparison,
)
from aura_sdk.transport.rb3_topology_cognition import (
    RB3ProceduralRouteMemory,
    build_rb3_topology_cognition,
)
from aura_sdk.transport.cognitive_persistence import (
    AURAArtifactIndexEngine,
    AURACognitionBootLoader,
    AURACognitionPortability,
    AURACognitionRegistry,
    AURAGovernanceEngine,
    AURAPhaseEngine,
)
from aura_sdk.transport.agentization import AURAInternalAgentizationCoordinator


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    payload: dict[str, Any]
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            payload = {
                "classification": "INVALID",
                "reason": "submit_non_json_stdout",
                "raw_stdout": stdout,
                "raw_stderr": stderr,
            }
    else:
        payload = {
            "classification": "INVALID",
            "reason": "submit_empty_stdout",
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }

    response_payload = None
    response_path = payload.get("response")
    if isinstance(response_path, str) and response_path:
        path = Path(response_path)
        if path.exists():
            response_payload = _load_json(path)

    return {
        "return_code": proc.returncode,
        "summary": payload,
        "response": response_payload,
        "stdout": stdout,
        "stderr": stderr,
        "commands": commands,
        "execution_mode": execution_mode,
        "allow_write_ops": allow_write_ops,
    }


def _trace_to_command_output(response: dict[str, Any] | None, command: str) -> str:
    if not isinstance(response, dict):
        return ""
    trace = response.get("executor_command_trace", [])
    if not isinstance(trace, list):
        return ""
    for item in trace:
        if isinstance(item, dict) and str(item.get("normalized_command", "")) == command:
            return str(item.get("stdout", ""))
    return ""


def _trace_to_command_stderr(response: dict[str, Any] | None, command: str) -> str:
    if not isinstance(response, dict):
        return ""
    trace = response.get("executor_command_trace", [])
    if not isinstance(trace, list):
        return ""
    for item in trace:
        if isinstance(item, dict) and str(item.get("normalized_command", "")) == command:
            return str(item.get("stderr", ""))
    return ""


def _trace_to_command_exit_code(response: dict[str, Any] | None, command: str, default: int = -1) -> int:
    if not isinstance(response, dict):
        return default
    trace = response.get("executor_command_trace", [])
    if not isinstance(trace, list):
        return default
    for item in trace:
        if isinstance(item, dict) and str(item.get("normalized_command", "")) == command:
            try:
                return int(item.get("exit_code", default))
            except Exception:
                return default
    return default


def _extract_soundwire_view(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("soundwire", "swr", "wsa")):
            lines.append(line)
    return "\n".join(lines)


def _capability_state(fingerprint: dict[str, Any], key: str) -> str:
    capabilities = fingerprint.get("capabilities", {})
    if not isinstance(capabilities, dict):
        return "UNKNOWN"
    return str(capabilities.get(key, "UNKNOWN")).upper()


def _snapshot_timeout(default_timeout: int, upper_bound: int) -> int:
    return max(5, min(default_timeout, upper_bound))


def _build_snapshot_plan(
    fingerprint: dict[str, Any],
    *,
    default_timeout: int,
    execution_profile: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if execution_profile == "fast_locked_replay":
        return (
            [
                {
                    "command": "cat /proc/asound/cards",
                    "timeout_seconds": _snapshot_timeout(default_timeout, 20),
                    "optional": False,
                },
                {
                    "command": "cat /proc/asound/pcm",
                    "timeout_seconds": _snapshot_timeout(default_timeout, 20),
                    "optional": False,
                },
            ],
            [
                {"command": "cat /sys/kernel/debug/asoc/*/dapm", "reason": "fast_locked_replay_skip"},
                {"command": "dmesg | tail -200", "reason": "fast_locked_replay_skip"},
                {"command": "tinymix", "reason": "fast_locked_replay_skip"},
                {"command": "amixer", "reason": "fast_locked_replay_skip"},
            ],
        )

    commands: list[dict[str, Any]] = [
        {
            "command": "cat /proc/asound/cards",
            "timeout_seconds": _snapshot_timeout(default_timeout, 30),
            "optional": False,
        },
        {
            "command": "cat /proc/asound/pcm",
            "timeout_seconds": _snapshot_timeout(default_timeout, 30),
            "optional": False,
        },
        {
            "command": "cat /sys/kernel/debug/asoc/*/dapm",
            "timeout_seconds": _snapshot_timeout(default_timeout, 45),
            "optional": True,
        },
        {
            "command": "dmesg | tail -200",
            "timeout_seconds": _snapshot_timeout(default_timeout, 45),
            "optional": False,
        },
    ]
    skipped: list[dict[str, str]] = []

    tinymix_state = _capability_state(fingerprint, "supports_tinymix")
    if tinymix_state == "SUPPORTED":
        commands.append(
            {
                "command": "tinymix",
                "timeout_seconds": _snapshot_timeout(default_timeout, 20),
                "optional": True,
            }
        )
    else:
        skipped.append(
            {
                "command": "tinymix",
                "reason": f"capability_supports_tinymix:{tinymix_state.lower()}",
            }
        )

    amixer_state = _capability_state(fingerprint, "supports_amixer")
    if amixer_state == "SUPPORTED":
        commands.append(
            {
                "command": "amixer",
                "timeout_seconds": _snapshot_timeout(default_timeout, 20),
                "optional": True,
            }
        )
    else:
        skipped.append(
            {
                "command": "amixer",
                "reason": f"capability_supports_amixer:{amixer_state.lower()}",
            }
        )

    return commands, skipped


def _parse_iso8601(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, tail = text.split(".", 1)
        frac = []
        rest_index = None
        for idx, ch in enumerate(tail):
            if ch.isdigit():
                frac.append(ch)
                continue
            rest_index = idx
            break
        if frac:
            trimmed = "".join(frac[:6])
            rest = tail[rest_index:] if rest_index is not None else ""
            text = f"{head}.{trimmed}{rest}"
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _seconds_between(start: str, finish: str) -> float:
    s = _parse_iso8601(start)
    f = _parse_iso8601(finish)
    if s is None or f is None:
        return 0.0
    return max(0.0, (f - s).total_seconds())


def _extract_wav_metadata(workflow: dict[str, Any]) -> dict[str, Any]:
    selected_asset = workflow.get("asset_deployment", {}).get("selected_asset", {})
    wav_path = Path(str(selected_asset.get("repository_path_abs", "")))
    if not wav_path.exists():
        return {
            "repository_path_abs": str(wav_path),
            "duration_seconds": 0.0,
            "channels": 0,
            "sample_rate_hz": 0,
            "sample_width_bytes": 0,
            "sha256": str(selected_asset.get("sha256", "")),
            "asset_id": str(selected_asset.get("asset_id", "UNRESOLVED")),
        }
    with wave.open(str(wav_path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
        duration = (frames / rate) if rate > 0 else 0.0
        return {
            "repository_path_abs": str(wav_path),
            "duration_seconds": round(duration, 6),
            "channels": wav.getnchannels(),
            "sample_rate_hz": rate,
            "sample_width_bytes": wav.getsampwidth(),
            "sha256": str(selected_asset.get("sha256", "")),
            "asset_id": str(selected_asset.get("asset_id", "UNRESOLVED")),
        }


def _extract_request_ids(phase_trace: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        summary = phase.get("summary", {})
        if not isinstance(summary, dict):
            continue
        request_id = str(summary.get("request_id", "")).strip()
        if request_id and request_id not in ids:
            ids.append(request_id)
    return ids


def _collect_transport_metrics(phase_trace: list[dict[str, Any]]) -> dict[str, Any]:
    timeout_count = 0
    unknown_count = 0
    disconnected_count = 0
    invalid_count = 0
    capture_ready_count = 0
    command_runtime = "UNKNOWN"

    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        summary = phase.get("summary", {})
        if isinstance(summary, dict):
            classification = str(summary.get("classification", ""))
            if classification == "UNKNOWN":
                unknown_count += 1
            elif classification == "INVALID":
                invalid_count += 1
            elif classification == "CAPTURE_READY":
                capture_ready_count += 1
        response = phase.get("response")
        if isinstance(response, dict):
            execution_status = str(response.get("execution_status", ""))
            if execution_status == "timeout":
                timeout_count += 1
            if execution_status == "transport_disconnected":
                disconnected_count += 1
            transport_meta = response.get("transport_metadata", {})
            if isinstance(transport_meta, dict):
                runtime = str(transport_meta.get("command_runtime", "")).strip()
                if runtime:
                    command_runtime = runtime

    return {
        "transport_mode": command_runtime,
        "timeout_count": timeout_count,
        "unknown_count": unknown_count,
        "invalid_count": invalid_count,
        "disconnected_count": disconnected_count,
        "capture_ready_count": capture_ready_count,
    }


def _collect_timing_metrics(
    phase_trace: list[dict[str, Any]],
    *,
    playback_command: str,
) -> dict[str, Any]:
    phase_durations: dict[str, float] = {}
    total_runtime = 0.0
    first_start = None
    last_finish = None
    playback_runtime = 0.0
    cleanup_runtime = 0.0
    evidence_runtime = 0.0

    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        phase_name = str(phase.get("phase", "unknown"))
        started = float(phase.get("started_at", 0.0))
        completed = float(phase.get("completed_at", 0.0))
        duration = max(0.0, completed - started)
        phase_key = phase_name
        if phase.get("snapshot_command"):
            phase_key = f"{phase_name}:{phase.get('snapshot_command')}"
        phase_durations[phase_key] = round(duration, 6)

        if first_start is None or started < first_start:
            first_start = started
        if last_finish is None or completed > last_finish:
            last_finish = completed

        if phase_name in {"pre_runtime_snapshot", "post_runtime_snapshot"}:
            evidence_runtime += duration
        if phase_name == "cleanup":
            cleanup_runtime += duration

        response = phase.get("response")
        if isinstance(response, dict):
            for item in response.get("executor_command_trace", []):
                if not isinstance(item, dict):
                    continue
                cmd = str(item.get("normalized_command", ""))
                cmd_duration = _seconds_between(str(item.get("started_at", "")), str(item.get("finished_at", "")))
                if cmd == playback_command or (
                    cmd.startswith("AURA_PLAYBACK_APLAY ") and playback_command.startswith("AURA_PLAYBACK_APLAY ")
                ):
                    playback_runtime = round(cmd_duration, 6)

    if first_start is not None and last_finish is not None:
        total_runtime = round(max(0.0, last_finish - first_start), 6)

    return {
        "total_runtime_seconds": total_runtime,
        "playback_runtime_seconds": playback_runtime,
        "cleanup_runtime_seconds": round(cleanup_runtime, 6),
        "evidence_collection_runtime_seconds": round(evidence_runtime, 6),
        "phase_durations_seconds": phase_durations,
    }


def _extract_sequences_for_lock(phase_trace: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str], list[str]]:
    successful_sequence: list[str] = []
    command_ordering: list[str] = []
    cleanup_ordering: list[str] = []
    evidence_sequence: list[str] = []

    for phase in phase_trace:
        if not isinstance(phase, dict):
            continue
        phase_name = str(phase.get("phase", ""))
        snapshot_command = str(phase.get("snapshot_command", "")).strip()
        if snapshot_command and not phase.get("skipped", False):
            evidence_sequence.append(snapshot_command)

        response = phase.get("response")
        if not isinstance(response, dict):
            continue
        for item in response.get("executor_command_trace", []):
            if not isinstance(item, dict):
                continue
            cmd = str(item.get("normalized_command", "")).strip()
            if not cmd:
                continue
            command_ordering.append(cmd)
            if str(item.get("execution_status", "")) == "executed":
                successful_sequence.append(cmd)
            if phase_name == "cleanup":
                cleanup_ordering.append(cmd)

    return successful_sequence, command_ordering, cleanup_ordering, evidence_sequence


def main() -> int:
    parser = argparse.ArgumentParser(description="RB3 controlled runtime procedural validation")
    parser.add_argument(
        "--runtime-report",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/runtime_capability_report.json",
    )
    parser.add_argument(
        "--entry-dts",
        default="/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926/repos/linux-upstream-v6.18-patch-proposals/arch/arm64/boot/dts/qcom/qcs6490-rb3gen2.dts",
    )
    parser.add_argument(
        "--bridge-root",
        default="/local/mnt/workspace/AURA_V1/bridge",
    )
    parser.add_argument(
        "--memory-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_procedural_memory.json",
    )
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
    )
    parser.add_argument(
        "--overwrite-policy",
        choices=("no_overwrite", "allow_overwrite"),
        default="allow_overwrite",
    )
    parser.add_argument(
        "--live-run",
        action="store_true",
        help="Execute runtime bridge commands. Without this flag, run is dry-run planning only.",
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
    )
    parser.add_argument(
        "--baseline-registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_audible_baseline_registry.json",
    )
    parser.add_argument(
        "--procedural-lock-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_procedural_memory_lock.json",
    )
    parser.add_argument(
        "--procedural-route-memory-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_procedural_route_memory.json",
    )
    parser.add_argument(
        "--cognition-registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument(
        "--cognition-phase-state-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_phase_state.json",
    )
    parser.add_argument(
        "--cognition-governance-state-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_governance_state.json",
    )
    parser.add_argument(
        "--cognition-artifact-index-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_artifact_index.json",
    )
    parser.add_argument(
        "--cognition-portable-export-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_portable_snapshot.json",
    )
    parser.add_argument(
        "--baseline-profile-id",
        default="audible_25s_speaker_v1",
    )
    parser.add_argument(
        "--baseline-profile-version",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--human-audible-validation",
        choices=("confirmed", "rejected", "unknown"),
        default="unknown",
    )
    parser.add_argument(
        "--evidence-mode",
        default="governed_runtime",
    )
    parser.add_argument(
        "--execution-profile",
        choices=("full_governed", "fast_locked_replay"),
        default="full_governed",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    boot_result = AURACognitionBootLoader(
        registry_path=args.cognition_registry_path,
        phase_state_path=args.cognition_phase_state_path,
        governance_state_path=args.cognition_governance_state_path,
        output_dir=output_dir,
        runtime_report_path=args.runtime_report,
        baseline_registry_path=args.baseline_registry_path,
        procedural_memory_path=args.memory_path,
        procedural_lock_path=args.procedural_lock_path,
        procedural_route_memory_path=args.procedural_route_memory_path,
    ).boot()
    phase_engine = AURAPhaseEngine(boot_result.phase_state)
    governance_engine = AURAGovernanceEngine(boot_result.governance_state)

    try:
        phase_engine.assert_execution_scope("board:RB3Gen2")
        phase_engine.assert_execution_scope("workflow:playback")
        phase_engine.assert_execution_scope("transport:adb_shell")
        phase_engine.assert_capability("rb3_playback_execution" if args.live_run else "rb3_playback_planning")
        governance_engine.assert_action(
            action="rb3_controlled_playback",
            execution_mode="governed_write_approved" if args.live_run else "governed_read_only",
            allow_write_ops=args.live_run,
            transport_mode="adb_shell",
        )
    except PermissionError as exc:
        print(
            json.dumps(
                {
                    "classification": "INVALID",
                    "reason": "cognition_policy_blocked",
                    "error": str(exc),
                    "phase_state_path": str(Path(args.cognition_phase_state_path).resolve()),
                    "governance_state_path": str(Path(args.cognition_governance_state_path).resolve()),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 6

    runtime_payload = _load_json(Path(args.runtime_report))
    fingerprint = runtime_payload.get("fingerprint", {})

    workflow_result = build_rb3_speaker_workflow(
        fingerprint,
        entry_dts=args.entry_dts,
        memory_path=args.memory_path,
        bridge_root=args.bridge_root,
        intent="validate speaker playback",
        target_path="/data/local/tmp/aura/audio/speaker_validation.wav",
        overwrite_policy=args.overwrite_policy,
    )

    workflow = workflow_result.workflow

    submit_script = REPO_ROOT / "scripts" / "linux-bridge-submit.sh"
    bridge_root = Path(args.bridge_root)

    snapshot_commands, snapshot_skipped = _build_snapshot_plan(
        fingerprint,
        default_timeout=args.timeout_seconds,
        execution_profile=args.execution_profile,
    )

    deployment_cmd = workflow.get("asset_deployment", {}).get("push_command")
    mixer_cmds = [
        str(cmd)
        for cmd in workflow.get("playback_workflow", {}).get("mixer_apply_commands", [])
        if str(cmd).strip()
    ]
    playback_cmd = str(workflow.get("playback_workflow", {}).get("playback_command", "")).strip()
    cleanup_cmd = str(workflow.get("playback_workflow", {}).get("cleanup_command", "")).strip()

    phase_trace: list[dict[str, Any]] = []

    def execute_phase(
        phase_name: str,
        commands: list[str],
        *,
        execution_mode: str,
        allow_write_ops: bool,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        if not commands:
            return {
                "phase": phase_name,
                "skipped": True,
                "reason": "no_commands",
                "started_at": started,
                "completed_at": time.time(),
            }
        if not args.live_run:
            return {
                "phase": phase_name,
                "skipped": True,
                "reason": "dry_run",
                "commands": commands,
                "execution_mode": execution_mode,
                "allow_write_ops": allow_write_ops,
                "started_at": started,
                "completed_at": time.time(),
            }

        try:
            governance_engine.assert_action(
                action=f"phase:{phase_name}",
                execution_mode=execution_mode,
                allow_write_ops=allow_write_ops,
                transport_mode="adb_shell",
            )
        except PermissionError as exc:
            return {
                "phase": phase_name,
                "skipped": True,
                "reason": "governance_blocked",
                "error": str(exc),
                "commands": commands,
                "execution_mode": execution_mode,
                "allow_write_ops": allow_write_ops,
                "started_at": started,
                "completed_at": time.time(),
                "summary": {"classification": "INVALID", "reason": "governance_blocked"},
                "response": {"execution_status": "invalid"},
            }

        result = _run_bridge_submit(
            submit_script,
            bridge_root,
            commands,
            timeout_seconds=timeout_seconds if isinstance(timeout_seconds, int) else args.timeout_seconds,
            execution_mode=execution_mode,
            allow_write_ops=allow_write_ops,
        )
        result["phase"] = phase_name
        result["started_at"] = started
        result["completed_at"] = time.time()
        return result

    for item in snapshot_skipped:
        phase_trace.append(
            {
                "phase": "pre_runtime_snapshot",
                "snapshot_command": str(item.get("command", "")),
                "skipped": True,
                "reason": str(item.get("reason", "unsupported_or_unknown")),
                "started_at": time.time(),
                "completed_at": time.time(),
            }
        )

    pre_outputs: dict[str, str] = {}
    pre_stderr: dict[str, str] = {}
    pre_exit_codes: dict[str, int] = {}
    for spec in snapshot_commands:
        command = str(spec.get("command", "")).strip()
        if not command:
            continue
        pre_phase = execute_phase(
            "pre_runtime_snapshot",
            [command],
            execution_mode="governed_read_only",
            allow_write_ops=False,
            timeout_seconds=int(spec.get("timeout_seconds", args.timeout_seconds)),
        )
        pre_phase["snapshot_command"] = command
        pre_phase["snapshot_optional"] = bool(spec.get("optional", False))
        phase_trace.append(pre_phase)
        pre_resp = pre_phase.get("response") if isinstance(pre_phase, dict) else None
        pre_outputs[command] = _trace_to_command_output(pre_resp, command)
        pre_stderr[command] = _trace_to_command_stderr(pre_resp, command)
        pre_exit_codes[command] = _trace_to_command_exit_code(pre_resp, command, default=-1)

    deploy_phase = execute_phase(
        "asset_deploy",
        [deployment_cmd] if isinstance(deployment_cmd, str) and deployment_cmd else [],
        execution_mode="governed_write_approved",
        allow_write_ops=True,
    )
    phase_trace.append(deploy_phase)

    mixer_phase = execute_phase(
        "mixer_apply",
        mixer_cmds,
        execution_mode="governed_write_approved",
        allow_write_ops=True,
    )
    phase_trace.append(mixer_phase)

    playback_phase = execute_phase(
        "pcm_playback",
        [playback_cmd] if playback_cmd else [],
        execution_mode="governed_write_approved",
        allow_write_ops=True,
    )
    phase_trace.append(playback_phase)

    for item in snapshot_skipped:
        phase_trace.append(
            {
                "phase": "post_runtime_snapshot",
                "snapshot_command": str(item.get("command", "")),
                "skipped": True,
                "reason": str(item.get("reason", "unsupported_or_unknown")),
                "started_at": time.time(),
                "completed_at": time.time(),
            }
        )

    post_outputs: dict[str, str] = {}
    post_stderr: dict[str, str] = {}
    post_exit_codes: dict[str, int] = {}
    for spec in snapshot_commands:
        command = str(spec.get("command", "")).strip()
        if not command:
            continue
        post_phase = execute_phase(
            "post_runtime_snapshot",
            [command],
            execution_mode="governed_read_only",
            allow_write_ops=False,
            timeout_seconds=int(spec.get("timeout_seconds", args.timeout_seconds)),
        )
        post_phase["snapshot_command"] = command
        post_phase["snapshot_optional"] = bool(spec.get("optional", False))
        phase_trace.append(post_phase)
        post_resp = post_phase.get("response") if isinstance(post_phase, dict) else None
        post_outputs[command] = _trace_to_command_output(post_resp, command)
        post_stderr[command] = _trace_to_command_stderr(post_resp, command)
        post_exit_codes[command] = _trace_to_command_exit_code(post_resp, command, default=-1)

    cleanup_phase = execute_phase(
        "cleanup",
        [] if args.skip_cleanup else ([cleanup_cmd] if cleanup_cmd else []),
        execution_mode="governed_write_approved",
        allow_write_ops=True,
    )
    phase_trace.append(cleanup_phase)

    playback_resp = playback_phase.get("response") if isinstance(playback_phase, dict) else None
    cleanup_resp = cleanup_phase.get("response") if isinstance(cleanup_phase, dict) else None

    pcm_before = pre_outputs.get("cat /proc/asound/pcm", "")
    pcm_after = post_outputs.get("cat /proc/asound/pcm", "")
    dmesg_before = pre_outputs.get("dmesg | tail -200", "")
    dmesg_after = post_outputs.get("dmesg | tail -200", "")
    dapm_before = pre_outputs.get("cat /sys/kernel/debug/asoc/*/dapm", "")
    dapm_after = post_outputs.get("cat /sys/kernel/debug/asoc/*/dapm", "")
    mixer_before = "\n".join([
        pre_outputs.get("tinymix", ""),
        pre_outputs.get("amixer", ""),
    ]).strip()
    mixer_after = "\n".join([
        post_outputs.get("tinymix", ""),
        post_outputs.get("amixer", ""),
    ]).strip()

    playback_exit_code = _trace_to_command_exit_code(playback_resp, playback_cmd, default=-1)
    playback_stderr = _trace_to_command_stderr(playback_resp, playback_cmd)
    cleanup_exit_code = _trace_to_command_exit_code(cleanup_resp, cleanup_cmd, default=-1)

    evidence_payload = {
        "pcm_before": pcm_before,
        "pcm_after": pcm_after,
        "dmesg_before": dmesg_before,
        "dmesg_after": dmesg_after,
        "dapm_before": dapm_before,
        "dapm_after": dapm_after,
        "mixer_before": mixer_before,
        "mixer_after": mixer_after,
        "soundwire_before": _extract_soundwire_view(dmesg_before),
        "soundwire_after": _extract_soundwire_view(dmesg_after),
        "pcm_runtime_state_before": pcm_before,
        "pcm_runtime_state_after": pcm_after,
        "playback_exit_code": playback_exit_code,
        "playback_stderr": playback_stderr,
        "cleanup_exit_code": cleanup_exit_code,
        "snapshot_skipped_commands": snapshot_skipped,
        "snapshot_pre_stderr": pre_stderr,
        "snapshot_post_stderr": post_stderr,
        "snapshot_pre_exit_codes": pre_exit_codes,
        "snapshot_post_exit_codes": post_exit_codes,
    }

    correlation = correlate_runtime_evidence(evidence_payload)
    state_machine = build_playback_state_machine(workflow, correlation=correlation)
    failure_reasoning = explain_playback_failure(
        workflow,
        correlation,
        static_context=workflow_result.static_context,
    )

    success = bool(
        correlation.get("playback_completion")
        and correlation.get("route_activation_confidence") == "HIGH"
    )
    run_id = str(uuid.uuid4())

    memory_store = RB3ProceduralMemory(args.memory_path)
    memory_snapshot = memory_store.record_result(
        run_id=run_id,
        success=success,
        asset_id=str(
            workflow.get("asset_deployment", {}).get("selected_asset", {}).get("asset_id", "UNRESOLVED")
        ),
        overlay=str(workflow.get("overlay", {}).get("overlay", "UNRESOLVED")),
        mixer_sequence=[str(cmd) for cmd in mixer_cmds],
        quirks=["live_runtime_validation" if args.live_run else "dry_run_planning_only"],
        unsupported_format=None,
        route_constraints=[
            "route_activation_requires_backend_and_dapm"
        ],
        recovery_patterns=[
            "retry_with_verified_mixer_sequence",
            "re-capture_dmesg_and_dapm_after_mixer_apply",
        ],
        runtime_signature={
            "route_activation_confidence": correlation.get("route_activation_confidence"),
            "pcm_activation": correlation.get("pcm_activation"),
            "backend_activity": correlation.get("backend_activity"),
            "soundwire_activity": correlation.get("soundwire_activity"),
            "playback_completion": correlation.get("playback_completion"),
        },
        failure_signature=",".join(
            str(item.get("code", ""))
            for item in failure_reasoning.get("failure_reasons", [])
            if isinstance(item, dict)
        ),
    )

    route_graph = workflow.get("audio_route_knowledge_graph", {})
    timing_metrics = _collect_timing_metrics(phase_trace, playback_command=playback_cmd)
    transport_metrics = _collect_transport_metrics(phase_trace)
    wav_metadata = _extract_wav_metadata(workflow)

    if args.execution_profile == "fast_locked_replay":
        required_evidence = [
            "cat /proc/asound/cards",
            "cat /proc/asound/pcm",
        ]
    else:
        required_evidence = [
            "cat /proc/asound/cards",
            "cat /proc/asound/pcm",
            "cat /sys/kernel/debug/asoc/*/dapm",
            "dmesg | tail -200",
        ]
    missing_evidence = [
        cmd
        for cmd in required_evidence
        if not str(pre_outputs.get(cmd, "")).strip() or not str(post_outputs.get(cmd, "")).strip()
    ]

    critical_phase_ok: dict[str, bool] = {}
    for phase_name in ("asset_deploy", "mixer_apply", "pcm_playback", "cleanup"):
        matching = [
            phase
            for phase in phase_trace
            if isinstance(phase, dict) and str(phase.get("phase", "")) == phase_name
        ]
        phase_ok = False
        for phase in matching:
            summary = phase.get("summary", {})
            response = phase.get("response", {})
            if (
                isinstance(summary, dict)
                and isinstance(response, dict)
                and str(summary.get("classification", "")) == "CAPTURE_READY"
                and str(response.get("execution_status", "")) == "executed"
            ):
                phase_ok = True
                break
        critical_phase_ok[phase_name] = phase_ok

    process_success = (
        bool(correlation.get("playback_completion"))
        and playback_exit_code == 0
        and cleanup_exit_code == 0
        and all(critical_phase_ok.values())
    )
    evidence_success = (len(missing_evidence) == 0) and (
        str(correlation.get("evidence_quality", "LOW")) in {"HIGH", "MEDIUM"}
    )
    human_confirmed = args.human_audible_validation == "confirmed"
    human_validation = {
        "audible_status": args.human_audible_validation,
        "audible_confirmation": human_confirmed,
        "process_success": process_success,
        "evidence_success": evidence_success,
    }

    wav_duration_seconds = float(wav_metadata.get("duration_seconds", 0.0))
    playback_runtime_seconds = float(timing_metrics.get("playback_runtime_seconds", 0.0))
    playback_duration_match = (
        playback_runtime_seconds >= (wav_duration_seconds * 0.80)
        if wav_duration_seconds > 0
        else False
    )

    profile_payload = {
        "run_id": run_id,
        "board": "RB3Gen2",
        "overlay": str(workflow.get("overlay", {}).get("overlay", "UNRESOLVED")),
        "pcm": {
            "alsa_device": str(workflow.get("pcm_inference", {}).get("alsa_device", "UNKNOWN")),
            "pcm_id": str(workflow.get("pcm_inference", {}).get("pcm_id", "UNKNOWN")),
            "signature_sha256": hashlib.sha256(
                (str(pcm_before) + "\n---\n" + str(pcm_after)).encode("utf-8")
            ).hexdigest(),
        },
        "route": {
            "route_dependencies": list(workflow.get("mixer_dependency", {}).get("route_dependencies", [])),
            "route_fingerprint": hashlib.sha256(
                json.dumps(route_graph, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "route_activation_confidence": str(correlation.get("route_activation_confidence", "LOW")),
        },
        "wav_asset": {
            "asset_id": str(wav_metadata.get("asset_id", "UNRESOLVED")),
            "repository_path_abs": str(wav_metadata.get("repository_path_abs", "")),
            "sha256": str(wav_metadata.get("sha256", "")),
            "duration_seconds": wav_duration_seconds,
            "channels": int(wav_metadata.get("channels", 0)),
            "sample_rate_hz": int(wav_metadata.get("sample_rate_hz", 0)),
            "format": "S16_LE",
        },
        "evidence_mode": args.evidence_mode,
        "mixer_capability_state": {
            "supports_tinymix": _capability_state(fingerprint, "supports_tinymix"),
            "supports_amixer": _capability_state(fingerprint, "supports_amixer"),
        },
        "runtime_timing": {
            **timing_metrics,
            "wav_duration_seconds": wav_duration_seconds,
            "playback_duration_match": playback_duration_match,
            "duration_drift_seconds": round(abs(playback_runtime_seconds - wav_duration_seconds), 6),
        },
        "transport": transport_metrics,
        "execution_profile": args.execution_profile,
        "human_validation": human_validation,
        "final_classification": state_machine.get("final_classification", "ADVISORY_ONLY"),
        "evidence": {
            "missing_evidence": missing_evidence,
            "evidence_quality": str(correlation.get("evidence_quality", "LOW")),
        },
    }

    baseline_registry = RB3BaselineProfileRegistry(args.baseline_registry_path)
    existing_registry = baseline_registry.load()
    existing_profile = (
        existing_registry.get("profiles", {})
        .get(args.baseline_profile_id, {})
        if isinstance(existing_registry, dict)
        else {}
    )
    existing_baseline = (
        existing_profile.get("baseline_profile")
        if isinstance(existing_profile, dict)
        else None
    )
    regression = build_runtime_regression_comparison(profile_payload, existing_baseline)

    request_ids = _extract_request_ids(phase_trace)
    evidence_lineage = {
        "board": "RB3Gen2",
        "profile_id": args.baseline_profile_id,
        "request_ids": request_ids,
        "trace_path": str((output_dir / "rb3_runtime_procedural_execution_trace.json").resolve()),
        "correlation_path": str((output_dir / "rb3_runtime_validation_correlation_live.json").resolve()),
        "state_machine_path": str((output_dir / "rb3_runtime_playback_state_machine_live.json").resolve()),
        "memory_snapshot_path": str((output_dir / "rb3_runtime_procedural_memory_live.json").resolve()),
        "regression_fingerprint": str(regression.get("regression_fingerprint", "")),
    }

    baseline_record = baseline_registry.record_run(
        profile_id=args.baseline_profile_id,
        profile_version=args.baseline_profile_version,
        run_id=run_id,
        runtime_profile=profile_payload,
        regression=regression,
        evidence_lineage=evidence_lineage,
        process_success=process_success,
        evidence_success=evidence_success,
        audible_status=args.human_audible_validation,
    )

    successful_sequence, command_ordering, cleanup_ordering, evidence_sequence = _extract_sequences_for_lock(
        phase_trace
    )
    degradation_decisions = [
        f"snapshot_skipped:{item.get('command')}:{item.get('reason')}"
        for item in snapshot_skipped
        if isinstance(item, dict)
    ]
    if transport_metrics.get("timeout_count", 0) > 0:
        degradation_decisions.append("transport_timeout_detected")
    if missing_evidence:
        degradation_decisions.append("missing_evidence_detected")

    lock_store = RB3ProceduralMemoryLock(args.procedural_lock_path)
    lock_snapshot = lock_store.record_run(
        run_id=run_id,
        profile_id=args.baseline_profile_id,
        successful_sequence=successful_sequence,
        command_ordering=command_ordering,
        cleanup_ordering=cleanup_ordering,
        evidence_sequence=evidence_sequence,
        timing_windows={
            "total_runtime_seconds": float(timing_metrics.get("total_runtime_seconds", 0.0)),
            "playback_runtime_seconds": playback_runtime_seconds,
            "cleanup_runtime_seconds": float(timing_metrics.get("cleanup_runtime_seconds", 0.0)),
            "evidence_collection_runtime_seconds": float(
                timing_metrics.get("evidence_collection_runtime_seconds", 0.0)
            ),
        },
        degradation_decisions=degradation_decisions,
        process_success=process_success,
        evidence_success=evidence_success,
        audible_status=args.human_audible_validation,
    )

    effective_baseline_profile = baseline_record.profile.get("baseline_profile")
    if not isinstance(effective_baseline_profile, dict):
        effective_baseline_profile = (
            dict(existing_baseline)
            if isinstance(existing_baseline, dict)
            else {}
        )

    topology_result = build_rb3_topology_cognition(
        run_id=run_id,
        entry_dts=args.entry_dts,
        static_context=workflow_result.static_context,
        workflow=workflow,
        runtime_evidence=evidence_payload,
        runtime_correlation=correlation,
        phase_trace=phase_trace,
        profile_payload=profile_payload,
        baseline_profile=effective_baseline_profile if effective_baseline_profile else None,
        procedural_lock=lock_snapshot,
    )

    route_memory_store = RB3ProceduralRouteMemory(args.procedural_route_memory_path)
    route_memory_snapshot = route_memory_store.record_run(
        run_id=run_id,
        profile_id=args.baseline_profile_id,
        overlay=str(profile_payload.get("overlay", "UNRESOLVED")),
        process_success=process_success,
        evidence_success=evidence_success,
        topology_state=str(topology_result.topology_confidence_report.get("topology_state", "LOW_CONFIDENCE")),
        topology_confidence=float(topology_result.topology_confidence_report.get("topology_confidence", 0.0)),
        pcm_signature=str(profile_payload.get("pcm", {}).get("signature_sha256", "")),
        route_fingerprint=str(profile_payload.get("route", {}).get("route_fingerprint", "")),
        successful_playback_route=list(profile_payload.get("route", {}).get("route_dependencies", [])),
        backend_activation_ordering=list(topology_result.playback_route_trace.get("backend_activation_ordering", [])),
        mixer_dependency_chains=list(topology_result.playback_route_trace.get("mixer_dependency_chains", [])),
        runtime_evidence_pattern=dict(topology_result.runtime_route_graph.get("runtime_activation", {})),
        overlay_mutation_delta=dict(topology_result.overlay_mutation_graph.get("overlay_mutation_delta", {})),
        deterministic_alignment=dict(topology_result.playback_route_trace.get("deterministic_alignment", {})),
    )

    final_payload = {
        "run_id": run_id,
        "board": "RB3Gen2",
        "execution_mode": "live_controlled" if args.live_run else "dry_run",
        "execution_profile": args.execution_profile,
        "phase_trace": phase_trace,
        "workflow": workflow,
        "runtime_evidence": evidence_payload,
        "runtime_correlation": correlation,
        "state_machine": state_machine,
        "failure_reasoning": failure_reasoning,
        "audio_route_knowledge_graph": route_graph,
        "topology_graph": topology_result.topology_graph,
        "runtime_route_graph": topology_result.runtime_route_graph,
        "overlay_mutation_graph": topology_result.overlay_mutation_graph,
        "pcm_backend_correlation": topology_result.pcm_backend_correlation,
        "playback_route_trace": topology_result.playback_route_trace,
        "topology_confidence_report": topology_result.topology_confidence_report,
        "targeted_interrogation": {
            "enabled": bool(topology_result.topology_confidence_report.get("targeted_interrogation_mode", False)),
            "questions": list(topology_result.topology_confidence_report.get("targeted_questions", [])),
        },
        "procedural_memory": memory_snapshot,
        "procedural_memory_lock": lock_snapshot,
        "procedural_route_memory": route_memory_snapshot,
        "baseline_profile": profile_payload,
        "baseline_regression": regression,
        "baseline_registry_path": str(Path(args.baseline_registry_path).resolve()),
        "procedural_lock_path": str(Path(args.procedural_lock_path).resolve()),
        "procedural_route_memory_path": str(Path(args.procedural_route_memory_path).resolve()),
        "human_validation": human_validation,
        "playback_timing_verification": {
            "wav_duration_seconds": wav_duration_seconds,
            "playback_runtime_seconds": playback_runtime_seconds,
            "playback_duration_match": playback_duration_match,
            "duration_drift_seconds": round(abs(playback_runtime_seconds - wav_duration_seconds), 6),
        },
        "process_success": process_success,
        "critical_phase_success": critical_phase_ok,
        "evidence_success": evidence_success,
        "classification": state_machine.get("final_classification", "ADVISORY_ONLY"),
        "governance_posture": "ADVISORY_ONLY",
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }

    trace_json = output_dir / "rb3_runtime_procedural_execution_trace.json"
    corr_json = output_dir / "rb3_runtime_validation_correlation_live.json"
    state_json = output_dir / "rb3_runtime_playback_state_machine_live.json"
    graph_json = output_dir / "rb3_runtime_route_knowledge_graph.json"
    mem_json = output_dir / "rb3_runtime_procedural_memory_live.json"
    baseline_json = output_dir / f"rb3gen2_baseline_profile_{run_id}.json"
    lineage_json = output_dir / "rb3gen2_baseline_evidence_lineage.json"
    regression_json = output_dir / "rb3gen2_regression_fingerprint.json"
    lock_export_json = output_dir / "rb3gen2_procedural_memory_lock_snapshot.json"
    topology_graph_json = output_dir / "topology_graph.json"
    runtime_route_graph_json = output_dir / "runtime_route_graph.json"
    overlay_mutation_graph_json = output_dir / "overlay_mutation_graph.json"
    pcm_backend_correlation_json = output_dir / "pcm_backend_correlation.json"
    playback_route_trace_json = output_dir / "playback_route_trace.json"
    topology_confidence_report_json = output_dir / "topology_confidence_report.json"
    procedural_route_memory_json = output_dir / "procedural_route_memory.json"
    aura_agent_architecture_json = output_dir / "aura_agent_architecture.json"
    aura_agent_capability_graph_json = output_dir / "aura_agent_capability_graph.json"
    aura_agent_state_machine_json = output_dir / "aura_agent_state_machine.json"
    aura_inter_agent_protocol_json = output_dir / "aura_inter_agent_protocol.json"
    aura_cognition_versioning_json = output_dir / "aura_cognition_versioning.json"
    aura_event_schema_json = output_dir / "aura_event_schema.json"
    aura_event_lineage_json = output_dir / "aura_event_lineage.json"
    aura_agent_sync_state_json = output_dir / "aura_agent_sync_state.json"
    aura_cognition_bus_architecture_json = output_dir / "aura_cognition_bus_architecture.json"
    aura_event_flow_graph_json = output_dir / "aura_event_flow_graph.json"
    aura_replay_lifecycle_graph_json = output_dir / "aura_replay_lifecycle_graph.json"
    aura_event_persistence_schema_json = output_dir / "aura_event_persistence_schema.json"
    aura_confidence_propagation_model_json = output_dir / "aura_confidence_propagation_model.json"
    report_md = output_dir / "rb3_runtime_procedural_validation_report.md"

    baseline_export_payload = {
        "run_id": run_id,
        "profile_id": args.baseline_profile_id,
        "profile_version": args.baseline_profile_version,
        "state": baseline_record.profile.get("state", "CANDIDATE"),
        "baseline_locked": baseline_record.baseline_locked,
        "confidence": baseline_record.profile.get("confidence", {}),
        "runtime_profile": profile_payload,
        "regression": regression,
    }
    lineage_export_payload = {
        "run_id": run_id,
        "profile_id": args.baseline_profile_id,
        "evidence_lineage": evidence_lineage,
        "trace_path": str(trace_json.resolve()),
        "memory_snapshot_path": str(mem_json.resolve()),
        "procedural_lock_path": str(Path(args.procedural_lock_path).resolve()),
    }
    regression_export_payload = {
        "run_id": run_id,
        "profile_id": args.baseline_profile_id,
        "regression_fingerprint": regression.get("regression_fingerprint", ""),
        "regression_detected": regression.get("regression_detected", False),
        "severity": regression.get("severity", "NONE"),
        "deviations": regression.get("deviations", []),
    }

    final_payload["baseline_exports"] = {
        "registry": str(Path(args.baseline_registry_path).resolve()),
        "baseline_json": str(baseline_json.resolve()),
        "evidence_lineage_json": str(lineage_json.resolve()),
        "regression_json": str(regression_json.resolve()),
        "procedural_lock_snapshot_json": str(lock_export_json.resolve()),
        "topology_graph_json": str(topology_graph_json.resolve()),
        "runtime_route_graph_json": str(runtime_route_graph_json.resolve()),
        "overlay_mutation_graph_json": str(overlay_mutation_graph_json.resolve()),
        "pcm_backend_correlation_json": str(pcm_backend_correlation_json.resolve()),
        "playback_route_trace_json": str(playback_route_trace_json.resolve()),
        "topology_confidence_report_json": str(topology_confidence_report_json.resolve()),
        "procedural_route_memory_json": str(procedural_route_memory_json.resolve()),
        "cognition_registry_json": str(Path(args.cognition_registry_path).resolve()),
        "cognition_phase_state_json": str(Path(args.cognition_phase_state_path).resolve()),
        "cognition_governance_state_json": str(Path(args.cognition_governance_state_path).resolve()),
        "cognition_artifact_index_json": str(Path(args.cognition_artifact_index_path).resolve()),
        "cognition_portable_snapshot_json": str(Path(args.cognition_portable_export_path).resolve()),
        "aura_agent_architecture_json": str(aura_agent_architecture_json.resolve()),
        "aura_agent_capability_graph_json": str(aura_agent_capability_graph_json.resolve()),
        "aura_agent_state_machine_json": str(aura_agent_state_machine_json.resolve()),
        "aura_inter_agent_protocol_json": str(aura_inter_agent_protocol_json.resolve()),
        "aura_cognition_versioning_json": str(aura_cognition_versioning_json.resolve()),
        "aura_event_schema_json": str(aura_event_schema_json.resolve()),
        "aura_event_lineage_json": str(aura_event_lineage_json.resolve()),
        "aura_agent_sync_state_json": str(aura_agent_sync_state_json.resolve()),
        "aura_cognition_bus_architecture_json": str(aura_cognition_bus_architecture_json.resolve()),
        "aura_event_flow_graph_json": str(aura_event_flow_graph_json.resolve()),
        "aura_replay_lifecycle_graph_json": str(aura_replay_lifecycle_graph_json.resolve()),
        "aura_event_persistence_schema_json": str(aura_event_persistence_schema_json.resolve()),
        "aura_confidence_propagation_model_json": str(aura_confidence_propagation_model_json.resolve()),
    }

    trace_json.write_text(json.dumps(final_payload, indent=2, sort_keys=True), encoding="utf-8")
    corr_json.write_text(json.dumps(correlation, indent=2, sort_keys=True), encoding="utf-8")
    state_json.write_text(json.dumps(state_machine, indent=2, sort_keys=True), encoding="utf-8")
    graph_json.write_text(json.dumps(route_graph, indent=2, sort_keys=True), encoding="utf-8")
    mem_json.write_text(json.dumps(memory_snapshot, indent=2, sort_keys=True), encoding="utf-8")
    baseline_json.write_text(json.dumps(baseline_export_payload, indent=2, sort_keys=True), encoding="utf-8")
    lineage_json.write_text(json.dumps(lineage_export_payload, indent=2, sort_keys=True), encoding="utf-8")
    regression_json.write_text(json.dumps(regression_export_payload, indent=2, sort_keys=True), encoding="utf-8")
    lock_export_json.write_text(json.dumps(lock_snapshot, indent=2, sort_keys=True), encoding="utf-8")
    topology_graph_json.write_text(
        json.dumps(topology_result.topology_graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    runtime_route_graph_json.write_text(
        json.dumps(topology_result.runtime_route_graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    overlay_mutation_graph_json.write_text(
        json.dumps(topology_result.overlay_mutation_graph, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    pcm_backend_correlation_json.write_text(
        json.dumps(topology_result.pcm_backend_correlation, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    playback_route_trace_json.write_text(
        json.dumps(topology_result.playback_route_trace, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    topology_confidence_report_json.write_text(
        json.dumps(topology_result.topology_confidence_report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    procedural_route_memory_json.write_text(
        json.dumps(route_memory_snapshot, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    transport_confidence = (
        1.0
        if (
            int(transport_metrics.get("timeout_count", 0)) == 0
            and int(transport_metrics.get("invalid_count", 0)) == 0
            and int(transport_metrics.get("disconnected_count", 0)) == 0
        )
        else 0.0
    )
    playback_confidence = 1.0 if (process_success and playback_duration_match) else 0.0
    evidence_confidence = 1.0 if evidence_success else 0.0
    runtime_confidence = round(
        (0.40 * transport_confidence)
        + (0.40 * playback_confidence)
        + (0.20 * evidence_confidence),
        3,
    )

    runtime_cognition_snapshot = {
        "run_id": run_id,
        "state_machine_state": str(state_machine.get("current_state", "")),
        "classification": str(final_payload.get("classification", "ADVISORY_ONLY")),
        "process_success": process_success,
        "evidence_success": evidence_success,
        "confidence": {
            "transport_confidence": transport_confidence,
            "playback_confidence": playback_confidence,
            "evidence_confidence": evidence_confidence,
            "runtime_confidence": runtime_confidence,
        },
        "timing": dict(final_payload.get("playback_timing_verification", {})),
        "runtime_signatures": {
            "pcm_signature": str(profile_payload.get("pcm", {}).get("signature_sha256", "")),
            "route_fingerprint": str(profile_payload.get("route", {}).get("route_fingerprint", "")),
            "execution_profile": args.execution_profile,
        },
        "evidence_paths": {
            "trace": str(trace_json.resolve()),
            "correlation": str(corr_json.resolve()),
            "state_machine": str(state_json.resolve()),
        },
    }
    topology_cognition_snapshot = {
        "run_id": run_id,
        "topology_state": str(topology_result.topology_confidence_report.get("topology_state", "LOW_CONFIDENCE")),
        "topology_confidence": float(topology_result.topology_confidence_report.get("topology_confidence", 0.0)),
        "targeted_interrogation_mode": bool(
            topology_result.topology_confidence_report.get("targeted_interrogation_mode", False)
        ),
        "targeted_questions": list(topology_result.topology_confidence_report.get("targeted_questions", [])),
        "deterministic_alignment": dict(topology_result.playback_route_trace.get("deterministic_alignment", {})),
        "artifact_paths": {
            "topology_graph": str(topology_graph_json.resolve()),
            "runtime_route_graph": str(runtime_route_graph_json.resolve()),
            "overlay_mutation_graph": str(overlay_mutation_graph_json.resolve()),
            "pcm_backend_correlation": str(pcm_backend_correlation_json.resolve()),
            "playback_route_trace": str(playback_route_trace_json.resolve()),
            "topology_confidence_report": str(topology_confidence_report_json.resolve()),
        },
    }
    target_knowledge_snapshot = {
        "board": "RB3Gen2",
        "environment": dict(fingerprint.get("environment", {})) if isinstance(fingerprint, dict) else {},
        "capabilities": dict(fingerprint.get("capabilities", {})) if isinstance(fingerprint, dict) else {},
        "audio_discovery": dict(fingerprint.get("audio_discovery", {})) if isinstance(fingerprint, dict) else {},
    }
    overlay_knowledge_snapshot = {
        "count": 1,
        "active_overlay": str(profile_payload.get("overlay", "UNRESOLVED")),
        "overlay_mutation_delta": dict(topology_result.overlay_mutation_graph.get("overlay_mutation_delta", {})),
        "overlay_conflicts": bool(
            topology_result.overlay_mutation_graph.get("merged_runtime_topology_reasoning", {}).get(
                "conflicting_overlays",
                False,
            )
        ),
    }

    cognition_registry_store = AURACognitionRegistry(args.cognition_registry_path)
    baseline_registry_snapshot = baseline_registry.load()
    cognition_registry_snapshot = cognition_registry_store.record_runtime_update(
        run_id=run_id,
        phase_state=phase_engine.state,
        governance_state=governance_engine.state,
        runtime_cognition=runtime_cognition_snapshot,
        topology_cognition=topology_cognition_snapshot,
        procedural_memory={
            "procedural_memory_path": str(Path(args.memory_path).resolve()),
            "procedural_memory_lock_path": str(Path(args.procedural_lock_path).resolve()),
            "procedural_route_memory_path": str(Path(args.procedural_route_memory_path).resolve()),
            "snapshot": route_memory_snapshot,
        },
        baseline_registry=baseline_registry_snapshot,
        regression=regression_export_payload,
        target_knowledge=target_knowledge_snapshot,
        overlay_knowledge=overlay_knowledge_snapshot,
        lineage_entry={
            "decision": "rb3_runtime_cognition_persistence_update",
            "why": "Persist runtime/topology/governance cognition as machine-readable state for restart-safe replay.",
            "supporting_evidence": {
                "trace_path": str(trace_json.resolve()),
                "topology_confidence_report": str(topology_confidence_report_json.resolve()),
                "regression_report": str(regression_json.resolve()),
            },
            "confidence_evolution": {
                "runtime_confidence": runtime_confidence,
                "topology_confidence": float(
                    topology_result.topology_confidence_report.get("topology_confidence", 0.0)
                ),
            },
        },
    )

    artifact_index_engine = AURAArtifactIndexEngine(
        index_path=args.cognition_artifact_index_path,
        artifact_root=output_dir,
    )
    artifact_index_snapshot = artifact_index_engine.refresh()

    portability_export = AURACognitionPortability().export_snapshot(
        output_path=args.cognition_portable_export_path,
        registry=cognition_registry_snapshot,
        phase_state=phase_engine.state,
        governance_state=governance_engine.state,
        artifact_index=artifact_index_snapshot,
        artifact_root=output_dir,
    )

    agentization = AURAInternalAgentizationCoordinator(
        output_dir=output_dir,
        cognition_registry_path=args.cognition_registry_path,
        phase_state_path=args.cognition_phase_state_path,
        governance_state_path=args.cognition_governance_state_path,
        baseline_registry_path=args.baseline_registry_path,
        procedural_memory_path=args.memory_path,
        procedural_lock_path=args.procedural_lock_path,
        procedural_route_memory_path=args.procedural_route_memory_path,
        runtime_report_path=args.runtime_report,
        artifact_index_path=args.cognition_artifact_index_path,
        portable_snapshot_path=args.cognition_portable_export_path,
    )
    agentization_result = agentization.run_cycle()
    agentization_paths = agentization.export_architecture_artifacts(agentization_result)

    final_payload["cognitive_persistence"] = {
        "boot_summary": boot_result.boot_summary,
        "registry_path": str(Path(args.cognition_registry_path).resolve()),
        "phase_state_path": str(Path(args.cognition_phase_state_path).resolve()),
        "governance_state_path": str(Path(args.cognition_governance_state_path).resolve()),
        "artifact_index_path": str(Path(args.cognition_artifact_index_path).resolve()),
        "portable_export_path": str(Path(args.cognition_portable_export_path).resolve()),
        "registry_updated": True,
        "artifact_index_updated": True,
        "portable_snapshot_exported": bool(portability_export),
    }
    final_payload["internal_agentization"] = {
        "active_agents": list(agentization_result.agent_runtime.get("active_agents", [])),
        "agent_health": dict(agentization_result.agent_runtime.get("agent_health", {})),
        "state_machine_state": str(agentization_result.state_machine.get("current_state", "unknown")),
        "artifact_paths": agentization_paths,
    }

    report_md.write_text(
        "# RB3 Runtime Procedural Validation\n\n"
        f"- execution_mode: `{final_payload['execution_mode']}`\n"
        f"- current_state: `{state_machine.get('current_state', 'unknown')}`\n"
        f"- final_classification: `{final_payload['classification']}`\n"
        f"- process_success: `{process_success}`\n"
        f"- evidence_success: `{evidence_success}`\n"
        f"- audible_human_validation: `{args.human_audible_validation}`\n"
        f"- route_activation_confidence: `{correlation.get('route_activation_confidence', 'LOW')}`\n"
        f"- playback_completion: `{correlation.get('playback_completion', False)}`\n"
        f"- wav_duration_seconds: `{wav_duration_seconds}`\n"
        f"- playback_runtime_seconds: `{playback_runtime_seconds}`\n"
        f"- playback_duration_match: `{playback_duration_match}`\n"
        f"- soundwire_activity: `{correlation.get('soundwire_activity', False)}`\n"
        f"- regression_detected: `{regression.get('regression_detected', False)}`\n"
        f"- regression_severity: `{regression.get('severity', 'NONE')}`\n"
        f"- topology_state: `{topology_result.topology_confidence_report.get('topology_state', 'LOW_CONFIDENCE')}`\n"
        f"- topology_confidence: `{topology_result.topology_confidence_report.get('topology_confidence', 0.0)}`\n"
        f"- agentization_state: `{agentization_result.state_machine.get('current_state', 'unknown')}`\n"
        "\n## Failure Reasons\n"
        + "\n".join(
            f"- `{item.get('code', 'unknown')}`: {item.get('why', '')}"
            for item in failure_reasoning.get("failure_reasons", [])
            if isinstance(item, dict)
        )
        + "\n\n## Missing Evidence\n"
        + (
            "\n".join(f"- `{item}`" for item in missing_evidence)
            if missing_evidence
            else "- none"
        )
        + "\n\n## Governance\n"
        "- windows remains execute-only\n"
        "- linux remains cognition authority\n"
        "- write operations require governed_write_approved\n"
        "- fail-closed classification preserved\n",
        encoding="utf-8",
    )

    trace_json.write_text(json.dumps(final_payload, indent=2, sort_keys=True), encoding="utf-8")

    print(
        json.dumps(
            {
                "trace": str(trace_json),
                "correlation": str(corr_json),
                "state_machine": str(state_json),
                "route_graph": str(graph_json),
                "memory": str(mem_json),
                "baseline": str(baseline_json),
                "lineage": str(lineage_json),
                "regression": str(regression_json),
                "procedural_lock": str(lock_export_json),
                "topology_graph": str(topology_graph_json),
                "runtime_route_graph": str(runtime_route_graph_json),
                "overlay_mutation_graph": str(overlay_mutation_graph_json),
                "pcm_backend_correlation": str(pcm_backend_correlation_json),
                "playback_route_trace": str(playback_route_trace_json),
                "topology_confidence_report": str(topology_confidence_report_json),
                "procedural_route_memory": str(procedural_route_memory_json),
                "cognition_registry": str(Path(args.cognition_registry_path).resolve()),
                "cognition_phase_state": str(Path(args.cognition_phase_state_path).resolve()),
                "cognition_governance_state": str(Path(args.cognition_governance_state_path).resolve()),
                "cognition_artifact_index": str(Path(args.cognition_artifact_index_path).resolve()),
                "cognition_portable_snapshot": str(Path(args.cognition_portable_export_path).resolve()),
                "aura_agent_architecture": str(Path(agentization_paths["aura_agent_architecture"]).resolve()),
                "aura_agent_capability_graph": str(Path(agentization_paths["aura_agent_capability_graph"]).resolve()),
                "aura_agent_state_machine": str(Path(agentization_paths["aura_agent_state_machine"]).resolve()),
                "aura_inter_agent_protocol": str(Path(agentization_paths["aura_inter_agent_protocol"]).resolve()),
                "aura_cognition_versioning": str(Path(agentization_paths["aura_cognition_versioning"]).resolve()),
                "aura_event_schema": str(Path(agentization_paths["aura_event_schema"]).resolve()),
                "aura_event_lineage": str(Path(agentization_paths["aura_event_lineage"]).resolve()),
                "aura_agent_sync_state": str(Path(agentization_paths["aura_agent_sync_state"]).resolve()),
                "aura_cognition_bus_architecture": str(
                    Path(agentization_paths["aura_cognition_bus_architecture"]).resolve()
                ),
                "aura_event_flow_graph": str(Path(agentization_paths["aura_event_flow_graph"]).resolve()),
                "aura_replay_lifecycle_graph": str(
                    Path(agentization_paths["aura_replay_lifecycle_graph"]).resolve()
                ),
                "aura_event_persistence_schema": str(
                    Path(agentization_paths["aura_event_persistence_schema"]).resolve()
                ),
                "aura_confidence_propagation_model": str(
                    Path(agentization_paths["aura_confidence_propagation_model"]).resolve()
                ),
                "baseline_registry": str(Path(args.baseline_registry_path).resolve()),
                "report": str(report_md),
                "current_state": state_machine.get("current_state"),
                "classification": final_payload["classification"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
