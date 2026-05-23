#!/usr/bin/env python3
"""Generate AURA internal agentization architecture artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.agentization import AURAInternalAgentizationCoordinator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA internal agentization architecture")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
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
        "--runtime-report",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/runtime_capability_report.json",
    )
    parser.add_argument(
        "--artifact-index-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_artifact_index.json",
    )
    parser.add_argument(
        "--portable-snapshot-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_portable_snapshot.json",
    )
    args = parser.parse_args()

    coordinator = AURAInternalAgentizationCoordinator(
        output_dir=args.output_dir,
        cognition_registry_path=args.cognition_registry_path,
        phase_state_path=args.cognition_phase_state_path,
        governance_state_path=args.cognition_governance_state_path,
        baseline_registry_path=args.baseline_registry_path,
        procedural_memory_path=args.procedural_memory_path,
        procedural_lock_path=args.procedural_lock_path,
        procedural_route_memory_path=args.procedural_route_memory_path,
        runtime_report_path=args.runtime_report,
        artifact_index_path=args.artifact_index_path,
        portable_snapshot_path=args.portable_snapshot_path,
    )
    result = coordinator.run_cycle()
    paths = coordinator.export_architecture_artifacts(result)

    print(
        json.dumps(
            {
                "artifacts": paths,
                "agent_health": result.agent_runtime.get("agent_health", {}),
                "state_machine_state": result.state_machine.get("current_state", "unknown"),
                "active_agents": result.agent_runtime.get("active_agents", []),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
