#!/usr/bin/env python3
"""Run runtime governance + replay consistency gating."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.runtime_execution_contract import enforce_runtime_contract
from aura_sdk.transport.runtime_governance_engine import RuntimeGovernanceEngine, RuntimeGovernanceRegistry
from aura_sdk.transport.runtime_replay_engine import RuntimeReplayEngine, RuntimeReplayRegistry
from aura_sdk.transport.deterministic_serialization import dump_canonical_json


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    dump_canonical_json(path, payload)


def _stamp_runtime_execution_fingerprint(output_dir: Path) -> None:
    script = REPO_ROOT / "scripts" / "runtime_execution_fingerprint.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-dir",
            str(output_dir),
            "--repo-root",
            str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _runtime_sensitive_impact_count(
    equivalence_report: dict[str, Any],
    divergence_report: dict[str, Any],
) -> int:
    dimensions = _as_list(_as_dict(equivalence_report).get("dimensions"))
    for row in dimensions:
        item = _as_dict(row)
        if str(item.get("dimension", "")) == "runtime_sensitive_region_instability":
            try:
                return int(item.get("difference_count", 0))
            except (TypeError, ValueError):
                return 0
    diverged = _as_list(_as_dict(divergence_report).get("diverged_dimensions"))
    return 1 if "runtime_sensitive_region_instability" in diverged else 0


def main() -> int:
    enforce_runtime_contract("aura-runtime-governance")
    parser = argparse.ArgumentParser(description="Run runtime governance cognition")
    parser.add_argument(
        "--output-dir",
        default=str((REPO_ROOT.parent / "docs" / "operations" / "transport").resolve()),
    )
    parser.add_argument(
        "--registry-path",
        default=str((REPO_ROOT.parent / "docs" / "operations" / "transport" / "aura_cognition_registry.json").resolve()),
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--session-id", default="runtime_governance_session_v1")
    parser.add_argument("--lineage-id", default="runtime_governance_v1")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    registry = AURACognitionRegistry(args.registry_path)
    registry_payload = registry.load()
    governance_state = _as_dict(registry_payload.get("governance_state"))
    if not governance_state:
        governance_state = {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        }

    equivalence_report = _read_json(output_dir / "runtime_equivalence_report.json")
    divergence_report = _read_json(output_dir / "runtime_divergence_report.json")
    confidence_report = _read_json(output_dir / "runtime_confidence_report.json")
    deterministic_runtime_replay = _read_json(output_dir / "deterministic_runtime_replay.json")
    runtime_equivalence_fingerprint = _read_json(output_dir / "runtime_equivalence_fingerprint.json")

    runtime_sensitive_impact_count = _runtime_sensitive_impact_count(equivalence_report, divergence_report)

    governance_store = RuntimeGovernanceRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    confidence_history = governance_store.load_confidence_history()

    governance_engine = RuntimeGovernanceEngine()
    governance = governance_engine.evaluate(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        governance_state=governance_state,
        runtime_equivalence_report=equivalence_report,
        runtime_divergence_report=divergence_report,
        runtime_confidence_report=confidence_report,
        deterministic_runtime_replay=deterministic_runtime_replay,
        runtime_sensitive_impact_count=runtime_sensitive_impact_count,
        previous_confidence_history=confidence_history,
        evidence_references=[
            "artifact://runtime_equivalence_report",
            "artifact://runtime_divergence_report",
            "artifact://runtime_confidence_report",
            "artifact://deterministic_runtime_replay",
            "registry://governance_state",
        ],
    )

    persisted_governance = governance_store.persist(
        runtime_governance_decision=governance.runtime_governance_decision,
        runtime_escalation_report=governance.runtime_escalation_report,
        runtime_risk_report=governance.runtime_risk_report,
    )

    replay_store = RuntimeReplayRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    previous_history = replay_store.load_history()

    replay_engine = RuntimeReplayEngine()
    replay = replay_engine.evaluate(
        target_id=str(args.target_id),
        session_id=str(args.session_id),
        lineage_id=str(args.lineage_id),
        deterministic_runtime_replay=deterministic_runtime_replay,
        runtime_equivalence_fingerprint=runtime_equivalence_fingerprint,
        runtime_governance_decision=governance.runtime_governance_decision,
        previous_registry_history=previous_history,
        evidence_references=[
            "artifact://deterministic_runtime_replay",
            "artifact://runtime_equivalence_fingerprint",
            "artifact://runtime_governance_decision",
        ],
    )
    persisted_replay = replay_store.persist(
        runtime_replay_registry=replay.runtime_replay_registry,
        replay_consistency_report=replay.replay_consistency_report,
    )
    replay_summary = replay_store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "RUNTIME_GOVERNANCE",
        "target_id": str(args.target_id),
        "session_id": str(args.session_id),
        "lineage_id": str(args.lineage_id),
        "classification": str(_as_dict(governance.runtime_governance_decision).get("classification", "UNKNOWN")),
        "promotion_eligible": bool(_as_dict(governance.runtime_governance_decision).get("promotion_eligible", False)),
        "runtime_sensitive_impact_count": int(runtime_sensitive_impact_count),
        "fail_closed_reasons": _as_list(_as_dict(governance.runtime_governance_decision).get("fail_closed_reasons")),
        "artifact_files": {
            "runtime_governance_decision": str((output_dir / "runtime_governance_decision.json").resolve()),
            "runtime_escalation_report": str((output_dir / "runtime_escalation_report.json").resolve()),
            "runtime_risk_report": str((output_dir / "runtime_risk_report.json").resolve()),
            "runtime_replay_registry": str((output_dir / "runtime_replay_registry.json").resolve()),
            "replay_consistency_report": str((output_dir / "replay_consistency_report.json").resolve()),
        },
        "persisted": {
            "runtime_governance": persisted_governance,
            "runtime_replay": persisted_replay,
            "runtime_replay_summary": replay_summary,
        },
        "generated_at_epoch": time.time(),
    }
    _write_json(output_dir / "runtime_governance_runner_summary.json", summary)
    _stamp_runtime_execution_fingerprint(output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
