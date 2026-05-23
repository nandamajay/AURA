#!/usr/bin/env python3
"""Boot and reconstruct AURA cognitive persistence state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.cognitive_persistence import (  # noqa: E402
    AURAArtifactIndexEngine,
    AURACognitionBootLoader,
    AURACognitionReplayEngine,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA cognition boot and state reconstruction")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--runtime-report",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/runtime_capability_report.json",
    )
    parser.add_argument(
        "--baseline-registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_audible_baseline_registry.json",
    )
    parser.add_argument(
        "--procedural-memory-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/rb3gen2_procedural_memory.json",
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
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    boot = AURACognitionBootLoader(
        registry_path=args.cognition_registry_path,
        phase_state_path=args.cognition_phase_state_path,
        governance_state_path=args.cognition_governance_state_path,
        output_dir=out,
        runtime_report_path=args.runtime_report,
        baseline_registry_path=args.baseline_registry_path,
        procedural_memory_path=args.procedural_memory_path,
        procedural_lock_path=args.procedural_lock_path,
        procedural_route_memory_path=args.procedural_route_memory_path,
    ).boot()

    artifact_index = AURAArtifactIndexEngine(
        index_path=args.cognition_artifact_index_path,
        artifact_root=out,
    ).refresh()

    replay_ready = False
    replay_reason = ""
    try:
        replay = AURACognitionReplayEngine(
            baseline_registry_path=args.baseline_registry_path,
            procedural_lock_path=args.procedural_lock_path,
            procedural_route_memory_path=args.procedural_route_memory_path,
            phase_state_path=args.cognition_phase_state_path,
            governance_state_path=args.cognition_governance_state_path,
        ).build_known_good_replay()
        replay_ready = bool(replay.get("replay_ready", False))
    except Exception as exc:
        replay_reason = str(exc)

    print(
        json.dumps(
            {
                "boot_summary": boot.boot_summary,
                "registry_path": str(Path(args.cognition_registry_path).resolve()),
                "phase_state_path": str(Path(args.cognition_phase_state_path).resolve()),
                "governance_state_path": str(Path(args.cognition_governance_state_path).resolve()),
                "artifact_index_path": str(Path(args.cognition_artifact_index_path).resolve()),
                "artifact_count": len(artifact_index.get("artifacts", [])),
                "replay_ready": replay_ready,
                "replay_reason": replay_reason,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
