#!/usr/bin/env python3
"""Live SAFE_READ validation for target fingerprint + adaptive command planning."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure local aura-sdk sources are importable without venv activation.
REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.command_planner import build_adaptive_plan
from aura_sdk.transport.target_fingerprint_engine import TargetFingerprintEngine


def _run_bridge_submit(
    submit_script: Path,
    bridge_root: Path,
    commands: list[str],
    timeout_seconds: int,
) -> tuple[int, dict[str, Any], str, str]:
    cmd = [
        "bash",
        str(submit_script),
        "--bridge-root",
        str(bridge_root),
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    for command in commands:
        cmd.extend(["--command", command])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    payload: dict[str, Any] = {}
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            # Keep raw output visible for fail-closed analysis.
            payload = {
                "classification": "INVALID",
                "reason": "non_json_submit_output",
                "raw_stdout": stdout,
                "raw_stderr": stderr,
            }
    else:
        payload = {
            "classification": "INVALID",
            "reason": "empty_submit_output",
            "raw_stdout": stdout,
            "raw_stderr": stderr,
        }

    return proc.returncode, payload, stdout, stderr


def _load_json_if_exists(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime cognition live validation")
    parser.add_argument(
        "--bridge-root",
        default="/local/mnt/workspace/AURA_V1/bridge",
        help="Shared bridge root path",
    )
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
        help="Output directory",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=45,
        help="Per-command timeout for bridge submit",
    )
    args = parser.parse_args()

    submit_script = REPO_ROOT / "scripts" / "linux-bridge-submit.sh"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Required live validation probes.
    probe_commands = [
        "getprop ro.build.fingerprint",
        "cat /proc/version",
        "cat /proc/asound/cards",
    ]

    probe_rc, probe_summary, probe_stdout, probe_stderr = _run_bridge_submit(
        submit_script,
        Path(args.bridge_root),
        probe_commands,
        args.timeout_seconds,
    )

    probe_response = _load_json_if_exists(probe_summary.get("response"))

    fingerprint_engine = TargetFingerprintEngine()
    fingerprint_result = (
        fingerprint_engine.build_fingerprint(probe_response).fingerprint
        if probe_response is not None
        else {
            "target_id": probe_summary.get("request_id", "unknown"),
            "environment": {
                "primary_environment": "Unknown",
                "detected_environments": ["Unknown"],
                "confidence": "LOW",
                "evidence": {},
            },
            "capabilities": {},
            "probe_outputs": {},
            "unsupported_command_evidence": [],
            "audio_discovery": {},
            "runtime_capability_graph": {"nodes": [], "edges": []},
            "governance_posture": "ADVISORY_ONLY",
            "claims": {
                "runtime_parity": "NOT_CLAIMED",
                "behavioral_equivalence": "NOT_CLAIMED",
                "merge_readiness": "NOT_CLAIMED",
            },
        }
    )

    plan = build_adaptive_plan(fingerprint_result)

    adaptive_rc = 0
    adaptive_summary: dict[str, Any] = {
        "classification": "ADVISORY_ONLY",
        "reason": "no_adaptive_commands_selected",
    }
    adaptive_response: dict[str, Any] | None = None
    if plan.selected_commands:
        adaptive_rc, adaptive_summary, _, _ = _run_bridge_submit(
            submit_script,
            Path(args.bridge_root),
            plan.selected_commands,
            args.timeout_seconds,
        )
        adaptive_response = _load_json_if_exists(adaptive_summary.get("response"))

    capabilities = fingerprint_result.get("capabilities", {})
    supports_getprop = str(capabilities.get("supports_getprop", "UNKNOWN"))
    planner_avoided_getprop = "getprop ro.build.fingerprint" not in plan.selected_commands
    avoidance_proof = {
        "supports_getprop": supports_getprop,
        "selected_commands": plan.selected_commands,
        "planner_avoided_getprop": planner_avoided_getprop,
        "proof": (
            supports_getprop != "SUPPORTED" and planner_avoided_getprop
        ),
    }

    capability_report = {
        "probe": {
            "commands": probe_commands,
            "return_code": probe_rc,
            "summary": probe_summary,
            "response": probe_response,
        },
        "fingerprint": fingerprint_result,
        "adaptive_plan": {
            "planning_mode": plan.planning_mode,
            "selected_commands": plan.selected_commands,
            "skipped_commands": plan.skipped_commands,
            "proof_getprop_avoidance": avoidance_proof,
        },
        "adaptive_execution": {
            "return_code": adaptive_rc,
            "summary": adaptive_summary,
            "response": adaptive_response,
        },
        "governance_posture": "ADVISORY_ONLY",
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }

    report_json = output_dir / "runtime_capability_report.json"
    plan_json = output_dir / "runtime_adaptive_plan.json"
    graph_json = output_dir / "runtime_capability_graph_live.json"
    report_md = output_dir / "runtime_cognition_live_validation.md"

    report_json.write_text(json.dumps(capability_report, indent=2, sort_keys=True), encoding="utf-8")
    plan_json.write_text(
        json.dumps(capability_report["adaptive_plan"], indent=2, sort_keys=True),
        encoding="utf-8",
    )
    graph_json.write_text(
        json.dumps(fingerprint_result.get("runtime_capability_graph", {}), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    report_md.write_text(
        "# Runtime Cognition Live Validation\n\n"
        f"- probe_request_id: `{probe_summary.get('request_id', 'unknown')}`\n"
        f"- probe_classification: `{probe_summary.get('classification', 'unknown')}`\n"
        f"- target_primary_environment: `{fingerprint_result.get('environment', {}).get('primary_environment', 'Unknown')}`\n"
        f"- supports_getprop: `{supports_getprop}`\n"
        f"- adaptive_planning_mode: `{plan.planning_mode}`\n"
        f"- adaptive_selected_commands: `{', '.join(plan.selected_commands) if plan.selected_commands else 'none'}`\n"
        f"- adaptive_classification: `{adaptive_summary.get('classification', 'ADVISORY_ONLY')}`\n"
        f"- proof_planner_avoids_getprop_when_unsupported: `{avoidance_proof['proof']}`\n"
        "\n## Notes\n"
        "- Unsupported commands are preserved as raw evidence and classified advisory/unknown fail-closed.\n"
        "- No runtime parity, behavioral equivalence, or merge-readiness claims are made.\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "probe_request_id": probe_summary.get("request_id", "unknown"),
                "probe_classification": probe_summary.get("classification", "unknown"),
                "adaptive_classification": adaptive_summary.get("classification", "unknown"),
                "supports_getprop": supports_getprop,
                "planner_avoided_getprop": planner_avoided_getprop,
                "avoidance_proof": avoidance_proof["proof"],
                "report_json": str(report_json),
                "report_md": str(report_md),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
