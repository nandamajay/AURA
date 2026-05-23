#!/usr/bin/env python3
"""RB3Gen2 deep playback cognition validation (planning + static correlation only)."""

from __future__ import annotations

import argparse
import json
import sys
import uuid
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


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="RB3 speaker playback cognition validation")
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
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_payload = _load_json(Path(args.runtime_report))
    fingerprint = runtime_payload.get("fingerprint", {})

    workflow_result = build_rb3_speaker_workflow(
        fingerprint,
        entry_dts=args.entry_dts,
        memory_path=args.memory_path,
        bridge_root=args.bridge_root,
        intent="validate speaker playback",
        target_path="/data/local/tmp/aura/audio/speaker_validation.wav",
        overwrite_policy="no_overwrite",
    )

    workflow = workflow_result.workflow

    # Static correlation template only; no new live command execution performed.
    evidence_template = {
        "pcm_before": "",
        "pcm_after": "",
        "dmesg_before": "",
        "dmesg_after": "",
        "dapm_before": "",
        "dapm_after": "",
        "mixer_before": "",
        "mixer_after": "",
        "playback_exit_code": -1,
        "playback_stderr": "not_executed_static_validation",
    }
    correlation = correlate_runtime_evidence(evidence_template)
    state_machine = build_playback_state_machine(workflow, correlation=correlation)
    failure_reasoning = explain_playback_failure(
        workflow,
        correlation,
        static_context=workflow_result.static_context,
    )

    memory = RB3ProceduralMemory(args.memory_path)
    memory_snapshot = memory.load()
    memory_snapshot = memory.record_result(
        run_id=str(uuid.uuid4()),
        success=False,
        asset_id=str(
            (
                workflow.get("asset_deployment", {})
                .get("selected_asset", {})
                .get("asset_id", "UNRESOLVED")
            )
        ),
        overlay=str(workflow.get("overlay", {}).get("overlay", "UNRESOLVED")),
        mixer_sequence=[
            str(step.get("step", ""))
            for step in workflow.get("mixer_dependency", {}).get("mixer_sequence", [])
            if isinstance(step, dict)
        ],
        quirks=["static_validation_without_live_playback"],
        unsupported_format=None,
        route_constraints=["speaker_validation_requires_overlay_resolution"],
        recovery_patterns=["re-run with live telemetry and operator-approved playback"],
    )

    output = {
        "board": "RB3Gen2",
        "workflow": workflow,
        "state_machine": state_machine,
        "runtime_correlation": correlation,
        "failure_reasoning": failure_reasoning,
        "memory_snapshot": memory_snapshot,
        "governance_posture": "ADVISORY_ONLY",
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }

    plan_json = output_dir / "rb3_speaker_playback_plan.json"
    state_json = output_dir / "rb3_playback_state_machine_trace.json"
    corr_json = output_dir / "rb3_runtime_validation_correlation.json"
    memory_json = output_dir / "rb3_procedural_memory_snapshot.json"
    fail_md = output_dir / "rb3_failure_reasoning_report.md"

    plan_json.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    state_json.write_text(json.dumps(state_machine, indent=2, sort_keys=True), encoding="utf-8")
    corr_json.write_text(json.dumps(correlation, indent=2, sort_keys=True), encoding="utf-8")
    memory_json.write_text(json.dumps(memory_snapshot, indent=2, sort_keys=True), encoding="utf-8")

    fail_md.write_text(
        "# RB3 Failure Reasoning (Static Validation)\n\n"
        f"- classification: `{failure_reasoning.get('classification', 'ADVISORY_ONLY')}`\n"
        f"- current_state: `{state_machine.get('current_state', 'UNKNOWN')}`\n"
        "\n## Reasons\n"
        + "\n".join(
            f"- `{item.get('code', 'unknown')}`: {item.get('why', '')}"
            for item in failure_reasoning.get("failure_reasons", [])
            if isinstance(item, dict)
        )
        + "\n\n## Notes\n"
        "- Report generated from static evidence and prior runtime snapshots only.\n"
        "- No live playback command executed in this validation run.\n"
        "- Advisory-only posture preserved.\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "plan": str(plan_json),
                "state_machine": str(state_json),
                "correlation": str(corr_json),
                "memory": str(memory_json),
                "failure_report": str(fail_md),
                "current_state": state_machine.get("current_state"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
