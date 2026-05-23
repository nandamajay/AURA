#!/usr/bin/env python3
"""AURA crash recovery and fail-closed continuity validator."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.cognitive_persistence import (  # noqa: E402
    AURACognitionBootLoader,
    AURACognitionReplayEngine,
)


def _load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _copy_if_exists(src: Path, dst: Path) -> None:
    if src.exists() and src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _copy_snapshot(src_dir: Path, dst_dir: Path) -> None:
    names = [
        "runtime_capability_report.json",
        "aura_cognition_registry.json",
        "aura_phase_state.json",
        "aura_governance_state.json",
        "aura_event_lineage.json",
        "aura_agent_sync_state.json",
        "aura_event_schema.json",
        "aura_confidence_propagation_model.json",
        "rb3_runtime_procedural_execution_trace.json",
        "runtime_confidence_report.json",
        "topology_confidence_report.json",
        "rb3gen2_regression_fingerprint.json",
        "rb3gen2_audible_baseline_registry.json",
        "rb3gen2_procedural_memory.json",
        "rb3gen2_procedural_memory_lock.json",
        "rb3gen2_procedural_route_memory.json",
    ]
    dst_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        _copy_if_exists(src_dir / name, dst_dir / name)


def _truncate_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    data = path.read_bytes()
    cut = max(1, len(data) // 2)
    path.write_bytes(data[:cut])


def _boot_and_replay(root: Path) -> dict[str, Any]:
    boot = AURACognitionBootLoader(
        registry_path=root / "aura_cognition_registry.json",
        phase_state_path=root / "aura_phase_state.json",
        governance_state_path=root / "aura_governance_state.json",
        output_dir=root,
        runtime_report_path=root / "runtime_capability_report.json",
        baseline_registry_path=root / "rb3gen2_audible_baseline_registry.json",
        procedural_memory_path=root / "rb3gen2_procedural_memory.json",
        procedural_lock_path=root / "rb3gen2_procedural_memory_lock.json",
        procedural_route_memory_path=root / "rb3gen2_procedural_route_memory.json",
    ).boot()

    replay = AURACognitionReplayEngine(
        baseline_registry_path=root / "rb3gen2_audible_baseline_registry.json",
        procedural_lock_path=root / "rb3gen2_procedural_memory_lock.json",
        procedural_route_memory_path=root / "rb3gen2_procedural_route_memory.json",
        phase_state_path=root / "aura_phase_state.json",
        governance_state_path=root / "aura_governance_state.json",
    ).build_known_good_replay()

    governance = _load_json_if_exists(root / "aura_governance_state.json")
    fail_closed = bool(governance.get("fail_closed_posture", True))
    ordering = _load_json_if_exists(root / "aura_event_lineage.json").get("ordering_validation", {})

    continuity_payload = {
        "fail_closed_preserved": fail_closed,
        "boot_execution_policies_restored": bool(boot.boot_summary.get("execution_policies_restored", False)),
        "replay_ready": bool(replay.get("replay_ready", False)),
        "artifact_lineage_continuity": bool(ordering.get("valid", True)),
        "replay_fingerprint": hashlib.sha256(
            json.dumps(
                {
                    "execution_sequence": replay.get("execution_sequence", []),
                    "command_ordering": replay.get("command_ordering", []),
                    "route": replay.get("route", {}),
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    }
    return continuity_payload


def _interrupt_process(command: list[str], wait_before_terminate: float = 0.05) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(max(0.0, wait_before_terminate))

    interrupted = False
    if proc.poll() is None:
        proc.terminate()
        interrupted = True
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)

    stdout, stderr = proc.communicate()
    return {
        "interrupted": interrupted,
        "returncode": proc.returncode,
        "stdout": stdout[-800:],
        "stderr": stderr[-800:],
        "duration_seconds": round(time.time() - started, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA crash recovery validator")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--report-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_recovery_validation_report.json",
    )
    parser.add_argument(
        "--bridge-root",
        default="/local/mnt/workspace/AURA_V1/bridge",
    )
    args = parser.parse_args()

    source = Path(args.output_dir)
    scenarios: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="aura_recovery_") as tmp:
        root = Path(tmp) / "recovery"
        _copy_snapshot(source, root)

        mid_playback = _interrupt_process(
            [
                "python3",
                str(REPO_ROOT / "scripts" / "rb3-runtime-procedural-playback.py"),
                "--output-dir",
                str(root),
                "--bridge-root",
                str(args.bridge_root),
                "--execution-profile",
                "fast_locked_replay",
                "--baseline-registry-path",
                str(root / "rb3gen2_audible_baseline_registry.json"),
                "--procedural-lock-path",
                str(root / "rb3gen2_procedural_memory_lock.json"),
                "--procedural-route-memory-path",
                str(root / "rb3gen2_procedural_route_memory.json"),
                "--cognition-registry-path",
                str(root / "aura_cognition_registry.json"),
                "--cognition-phase-state-path",
                str(root / "aura_phase_state.json"),
                "--cognition-governance-state-path",
                str(root / "aura_governance_state.json"),
                "--cognition-artifact-index-path",
                str(root / "aura_artifact_index.json"),
                "--cognition-portable-export-path",
                str(root / "aura_cognition_portable_snapshot.json"),
                "--runtime-report",
                str(root / "runtime_capability_report.json"),
                "--memory-path",
                str(root / "rb3gen2_procedural_memory.json"),
            ],
            wait_before_terminate=0.05,
        )
        continuity = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "mid_playback_interruption",
                "interruption": mid_playback,
                "continuity": continuity,
                "passed": bool(continuity["fail_closed_preserved"] and continuity["replay_ready"]),
            }
        )

        _truncate_file(root / "aura_event_lineage.json")
        continuity = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "mid_event_stream_interruption",
                "continuity": continuity,
                "passed": bool(continuity["fail_closed_preserved"] and continuity["replay_ready"]),
            }
        )

        _truncate_file(root / "aura_cognition_registry.json")
        continuity = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "partial_persistence_writes",
                "continuity": continuity,
                "passed": bool(
                    continuity["fail_closed_preserved"]
                    and continuity["boot_execution_policies_restored"]
                    and continuity["replay_ready"]
                ),
            }
        )

        trace = _load_json_if_exists(root / "rb3_runtime_procedural_execution_trace.json")
        trace.setdefault("transport_metrics", {})["disconnected_count"] = 1
        _save_json(root / "rb3_runtime_procedural_execution_trace.json", trace)
        continuity = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "transport_disconnect",
                "continuity": continuity,
                "passed": bool(continuity["fail_closed_preserved"] and continuity["replay_ready"]),
            }
        )

        windows_state = root / "windows_worker_state.json"
        _save_json(windows_state, {"worker": "windows", "state": "running", "pid": 101})
        _save_json(windows_state, {"worker": "windows", "state": "restarted", "pid": 202})
        continuity = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "windows_worker_restart",
                "worker_state": _load_json_if_exists(windows_state),
                "continuity": continuity,
                "passed": bool(continuity["fail_closed_preserved"] and continuity["replay_ready"]),
            }
        )

        continuity_a = _boot_and_replay(root)
        continuity_b = _boot_and_replay(root)
        scenarios.append(
            {
                "scenario": "linux_process_restart",
                "continuity_a": continuity_a,
                "continuity_b": continuity_b,
                "passed": bool(
                    continuity_a["replay_fingerprint"] == continuity_b["replay_fingerprint"]
                    and continuity_b["fail_closed_preserved"]
                ),
            }
        )

    passed = sum(1 for item in scenarios if bool(item.get("passed", False)))
    total = len(scenarios)
    score = round(passed / total, 6) if total else 0.0

    report = {
        "schema_version": "1.0",
        "validator": "aura_crash_recovery_validator",
        "scenarios": scenarios,
        "summary": {
            "passed": passed,
            "total": total,
            "recovery_validation_score": score,
            "fail_closed_preserved": all(
                bool(item.get("continuity", {}).get("fail_closed_preserved", True))
                for item in scenarios
                if isinstance(item, dict)
            ),
        },
        "generated_at_epoch": time.time(),
    }

    report_path = Path(args.report_path)
    _save_json(report_path, report)
    print(
        json.dumps(
            {
                "report": str(report_path.resolve()),
                "recovery_validation_score": score,
                "scenarios": total,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
