#!/usr/bin/env python3
"""AURA confidence integrity validation."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_SRC = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus  # noqa: E402


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


def _event_confidence_integrity_checks(events: list[dict[str, Any]]) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []

    runtime_truth_categories = {"runtime", "topology", "regression", "transport"}
    for event in events:
        metadata = event.get("metadata", {}) if isinstance(event, dict) else {}
        confidence = float(metadata.get("confidence", 0.0) or 0.0)
        category = str(event.get("category", ""))
        source = str(metadata.get("originating_agent", ""))
        target = str(metadata.get("target_agent", ""))
        evidence = metadata.get("evidence_references", [])
        has_evidence = isinstance(evidence, list) and bool([item for item in evidence if str(item).strip()])

        if category in runtime_truth_categories and confidence > 0.0 and not has_evidence:
            violations.append(
                {
                    "code": "runtime_confidence_without_evidence",
                    "event_id": str(event.get("event_id", "")),
                    "category": category,
                }
            )

        if source and target and source == target and confidence > 0.0:
            violations.append(
                {
                    "code": "agent_self_reinforcement_detected",
                    "event_id": str(event.get("event_id", "")),
                    "agent": source,
                }
            )

    return {
        "violations": violations,
        "violations_count": len(violations),
    }


def _simulate_confidence_dynamics() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="aura_confidence_integrity_") as tmp:
        root = Path(tmp)
        base_bus = AURACognitionBus(output_dir=root / "base")
        base_bus.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"process_success": True},
            confidence=1.0,
            evidence_references=["/tmp/runtime_trace.json"],
            governance_classification="GOVERNED_APPROVED",
        )
        base_bus.replay_persisted_events()
        score_base = float(
            base_bus.get_confidence_propagation_model().get("agent_confidence", {}).get("runtime_agent", {}).get("score", 0.0)
        )

        missing_bus = AURACognitionBus(output_dir=root / "missing")
        missing_bus.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"process_success": True},
            confidence=1.0,
            evidence_references=[],
            governance_classification="GOVERNED_APPROVED",
        )
        missing_bus.replay_persisted_events()
        score_missing = float(
            missing_bus.get_confidence_propagation_model().get("agent_confidence", {}).get("runtime_agent", {}).get("score", 0.0)
        )

        unsupported_bus = AURACognitionBus(output_dir=root / "unsupported")
        unsupported_bus.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"process_success": True},
            confidence=1.0,
            evidence_references=["unsupported://evidence"],
            governance_classification="QUARANTINED",
        )
        unsupported_bus.replay_persisted_events()
        score_unsupported = float(
            unsupported_bus.get_confidence_propagation_model().get("agent_confidence", {}).get("runtime_agent", {}).get("score", 0.0)
        )

        reinforcement_bus = AURACognitionBus(output_dir=root / "reinforcement")
        reinforcement_bus.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"process_success": True},
            confidence=1.0,
            evidence_references=["/tmp/runtime_trace.json"],
            governance_classification="GOVERNED_APPROVED",
        )
        reinforcement_bus.process_event(
            category="runtime",
            event_name="runtime_validation_state",
            originating_agent="runtime_agent",
            target_agent="topology_agent",
            payload={"process_success": True},
            confidence=1.0,
            evidence_references=["/tmp/runtime_trace.json"],
            governance_classification="GOVERNED_APPROVED",
        )
        reinforcement_bus.replay_persisted_events()
        score_reinforced = float(
            reinforcement_bus.get_confidence_propagation_model().get("agent_confidence", {}).get("runtime_agent", {}).get("score", 0.0)
        )

    checks = {
        "missing_evidence_never_increases_confidence": score_missing <= score_base,
        "unsupported_evidence_lowers_confidence": score_unsupported < score_base,
        "no_confidence_amplification_loops": score_reinforced <= score_base,
        "scores": {
            "base": score_base,
            "missing": score_missing,
            "unsupported": score_unsupported,
            "reinforced": score_reinforced,
        },
    }
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA confidence integrity validation")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    parser.add_argument(
        "--report-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_confidence_integrity_report.json",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    lineage = _load_json_if_exists(output_dir / "aura_event_lineage.json")
    events = lineage.get("events", []) if isinstance(lineage.get("events"), list) else []

    observed_checks = _event_confidence_integrity_checks([item for item in events if isinstance(item, dict)])
    simulated_checks = _simulate_confidence_dynamics()

    boolean_checks = {
        "runtime_evidence_truth_preserved": observed_checks["violations_count"] == 0,
        "missing_evidence_never_increases_confidence": bool(
            simulated_checks["missing_evidence_never_increases_confidence"]
        ),
        "unsupported_evidence_lowers_confidence": bool(simulated_checks["unsupported_evidence_lowers_confidence"]),
        "no_confidence_amplification_loops": bool(simulated_checks["no_confidence_amplification_loops"]),
    }
    passed = sum(1 for v in boolean_checks.values() if v)
    total = len(boolean_checks)
    confidence_integrity_score = round(passed / total, 6) if total else 0.0

    report = {
        "schema_version": "1.0",
        "validator": "aura_confidence_integrity",
        "observed_checks": observed_checks,
        "simulated_checks": simulated_checks,
        "boolean_checks": boolean_checks,
        "confidence_integrity_score": confidence_integrity_score,
        "generated_at_epoch": time.time(),
    }

    report_path = Path(args.report_path)
    _save_json(report_path, report)
    print(
        json.dumps(
            {
                "report": str(report_path.resolve()),
                "confidence_integrity_score": confidence_integrity_score,
                "violations": observed_checks["violations_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
