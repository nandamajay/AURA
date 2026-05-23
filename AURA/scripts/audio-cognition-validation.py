#!/usr/bin/env python3
"""Subsystem-aware audio cognition validation (governance-side reasoning only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.command_planner import build_procedural_audio_plan


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_summary(cognition: dict[str, Any]) -> dict[str, Any]:
    questions = cognition.get("targeted_questions", [])
    return {
        "cognition_mode": cognition.get("cognition_mode", "Discovery Mode"),
        "runtime_confidence": cognition.get("runtime_confidence", "LOW"),
        "unsupported_commands": cognition.get("unsupported_commands", []),
        "supported_playback_targets": cognition.get("supported_playback_targets", []),
        "selected_playback_target": cognition.get("selected_playback_target", "UNRESOLVED"),
        "overlay_selection": cognition.get("overlay_selection", "UNRESOLVED"),
        "alsa_playback_device": cognition.get("playback_workflow", {}).get(
            "alsa_playback_device", {}
        ),
        "question_count": len(questions),
        "questions": questions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Subsystem-aware audio cognition validation")
    parser.add_argument(
        "--runtime-report",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/runtime_capability_report.json",
        help="Path to runtime capability report JSON",
    )
    parser.add_argument(
        "--entry-dts",
        default="/local/mnt/workspace/AURA_V1/evidence/wcd937x_patchgen_20260519_194926/repos/linux-upstream-v6.18-patch-proposals/arch/arm64/boot/dts/qcom/qcs6490-rb3gen2.dts",
        help="Entry DTS file for static audio cognition",
    )
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
        help="Output directory",
    )
    parser.add_argument(
        "--overlay",
        default=None,
        help="Optional selected overlay name",
    )
    parser.add_argument(
        "--playback-target",
        default=None,
        help="Optional selected playback target",
    )
    parser.add_argument(
        "--wav-asset",
        default=None,
        help="Optional WAV asset path",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    runtime_payload = _load_json(Path(args.runtime_report))
    fingerprint = runtime_payload.get("fingerprint", {})

    procedural = build_procedural_audio_plan(
        fingerprint,
        entry_dts=args.entry_dts,
        selected_overlay=args.overlay,
        selected_playback_target=args.playback_target,
        wav_asset_path=args.wav_asset,
    )

    cognition = procedural.cognition
    summary = _build_summary(cognition)

    unsupported_getprop = any(
        str(item.get("normalized_command", "")) == "getprop ro.build.fingerprint"
        for item in cognition.get("unsupported_commands", [])
        if isinstance(item, dict)
    )

    report_payload = {
        "validation_target": "RB3Gen2",
        "execution_mode": "COGNITION_ONLY",
        "summary": summary,
        "static_audio_context": procedural.static_context,
        "cognition": cognition,
        "demonstration": {
            "identified_unsupported_commands": unsupported_getprop,
            "inferred_alsa_playback_path": cognition.get("playback_workflow", {}).get(
                "alsa_playback_device", {}
            ),
            "overlay_clarification_requested": any(
                q.get("id") == "overlay_selection"
                for q in cognition.get("targeted_questions", [])
                if isinstance(q, dict)
            ),
            "generated_validated_playback_workflow": bool(cognition.get("playback_workflow")),
        },
        "governance_posture": "ADVISORY_ONLY",
        "claims": {
            "runtime_parity": "NOT_CLAIMED",
            "behavioral_equivalence": "NOT_CLAIMED",
            "merge_readiness": "NOT_CLAIMED",
        },
    }

    report_json = output_dir / "rb3gen2_audio_cognition_report.json"
    graph_json = output_dir / "rb3gen2_audio_knowledge_graph.json"
    md_report = output_dir / "rb3gen2_adaptive_playback_validation.md"

    report_json.write_text(json.dumps(report_payload, indent=2, sort_keys=True), encoding="utf-8")
    graph_json.write_text(
        json.dumps(
            cognition.get("runtime_audio_knowledge_graph", {}),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    playback_device = cognition.get("playback_workflow", {}).get("alsa_playback_device", {})
    md_report.write_text(
        "# RB3Gen2 Adaptive Playback Cognition Validation\n\n"
        "- execution_mode: `COGNITION_ONLY`\n"
        f"- cognition_mode: `{summary['cognition_mode']}`\n"
        f"- runtime_confidence: `{summary['runtime_confidence']}`\n"
        f"- unsupported_getprop_detected: `{unsupported_getprop}`\n"
        f"- inferred_alsa_device: `{playback_device.get('alsa_device', 'UNKNOWN')}`\n"
        f"- playback_device_confidence: `{playback_device.get('confidence', 'LOW')}`\n"
        f"- selected_playback_target: `{summary['selected_playback_target']}`\n"
        f"- overlay_selection: `{summary['overlay_selection']}`\n"
        "\n## Adaptive Workflow Outcome\n"
        "- Linux side performed governance/cognition only.\n"
        "- Windows execute-only worker boundary remains unchanged.\n"
        "- Unsupported commands remain explicit in lineage evidence.\n"
        "- Mixer mutation commands are blocked by design in generated workflow templates.\n"
        "\n## Targeted Questions\n"
        + "\n".join(
            f"- `{q.get('id', 'unknown')}`: {q.get('question', '')}"
            for q in summary["questions"]
            if isinstance(q, dict)
        )
        + "\n\n## Governance Posture\n"
        "- advisory-only\n"
        "- no runtime parity claims\n"
        "- no behavioral equivalence claims\n"
        "- no merge-readiness claims\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "report_json": str(report_json),
                "graph_json": str(graph_json),
                "report_md": str(md_report),
                "cognition_mode": summary["cognition_mode"],
                "unsupported_getprop_detected": unsupported_getprop,
                "inferred_alsa_device": playback_device.get("alsa_device", "UNKNOWN"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
