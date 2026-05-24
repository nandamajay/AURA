from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_replay_engine import RuntimeReplayEngine, RuntimeReplayRegistry  # noqa: E402


def _deterministic_replay() -> dict:
    return {
        "schema_version": "1.0",
        "report_name": "deterministic_runtime_replay",
        "deterministic_fingerprint": "replay-fingerprint-a",
        "replay_signal": {
            "deterministic_event_ordering": True,
            "event_count": 12,
            "fingerprint": "fp-a",
        },
    }


def _equivalence_fingerprint(fp: str) -> dict:
    return {
        "schema_version": "1.0",
        "report_name": "runtime_equivalence_fingerprint",
        "deterministic_fingerprint": fp,
    }


def _governance_decision() -> dict:
    return {
        "schema_version": "1.0",
        "report_name": "runtime_governance_decision",
        "deterministic_fingerprint": "gov-fingerprint-a",
        "classification": "PASS",
        "promotion_eligible": True,
    }


def test_runtime_replay_registry_persistence(tmp_path: Path) -> None:
    out_dir = tmp_path / "ops"
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps({"schema_version": "1.0"}, indent=2), encoding="utf-8")

    store = RuntimeReplayRegistry(cognition_registry_path=registry_path, output_dir=out_dir)

    engine = RuntimeReplayEngine()
    result = engine.evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-replay-session-a",
        lineage_id="runtime-replay-lineage-a",
        deterministic_runtime_replay=_deterministic_replay(),
        runtime_equivalence_fingerprint=_equivalence_fingerprint("eq-fp-a"),
        runtime_governance_decision=_governance_decision(),
        previous_registry_history=store.load_history(),
        evidence_references=["test://runtime_replay/persist"],
    )

    persisted = store.persist(
        runtime_replay_registry=result.runtime_replay_registry,
        replay_consistency_report=result.replay_consistency_report,
    )
    replay = store.replay(lineage_id="runtime-replay-lineage-a")

    assert persisted["lineage_id"] == "runtime-replay-lineage-a"
    assert replay["lineage_id"] == "runtime-replay-lineage-a"
    assert (out_dir / "runtime_replay_registry.json").exists()
    assert (out_dir / "replay_consistency_report.json").exists()


def test_runtime_replay_detects_cross_session_drift() -> None:
    engine = RuntimeReplayEngine()
    previous = [
        {
            "lineage_id": "prior-lineage",
            "session_id": "prior-session",
            "lineage_fingerprint": "different-lineage-fp",
        }
    ]

    result = engine.evaluate(
        target_id="fake_target_alpha",
        session_id="runtime-replay-session-b",
        lineage_id="runtime-replay-lineage-b",
        deterministic_runtime_replay=_deterministic_replay(),
        runtime_equivalence_fingerprint=_equivalence_fingerprint("eq-fp-b"),
        runtime_governance_decision=_governance_decision(),
        previous_registry_history=previous,
        evidence_references=["test://runtime_replay/drift"],
    )

    assert result.replay_consistency_report["classification"] == "FAIL_CLOSED"
    assert "cross_session_replay_drift_detected" in set(result.replay_consistency_report["reasons"])
