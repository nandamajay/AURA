from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus  # noqa: E402
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine  # noqa: E402


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cognition_bus_fail_closed_and_quarantine(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    bus = AURACognitionBus(output_dir=out)

    try:
        bus.emit_event(
            category="unsupported",
            event_name="bad_event",
            originating_agent="runtime_agent",
            payload={},
            governance_classification="GOVERNED_APPROVED",
        )
        assert False, "expected PermissionError"
    except PermissionError:
        pass

    lineage = _read(out / "aura_event_lineage.json")
    assert lineage["ordering_validation"]["quarantine_count"] >= 1
    assert lineage["events"] == []


def test_cognition_bus_lifecycle_replay_and_sync(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    bus = AURACognitionBus(output_dir=out)

    event = bus.process_event(
        category="runtime",
        event_name="runtime_validation_state",
        originating_agent="runtime_agent",
        target_agent="topology_agent",
        payload={"ok": True},
        confidence=1.0,
        evidence_references=["/tmp/trace.json"],
        cognition_lineage_id="lineage-1",
        replay_correlation_id="replay-1",
        governance_classification="GOVERNED_APPROVED",
    )
    assert event["lifecycle"]["state"] == "persisted"

    replayed = bus.replay_persisted_events()
    assert event["event_id"] in replayed

    ordering = bus.validate_ordering()
    assert ordering["valid"]

    replay_engine = AURAEventReplayEngine(
        lineage_path=out / "aura_event_lineage.json",
        sync_state_path=out / "aura_agent_sync_state.json",
    )
    replay_state = replay_engine.reconstruct()
    assert replay_state["reconstructed_from_stream_only"]
    assert replay_state["replay_event_count"] == 1
    assert "runtime_agent" in replay_state["agent_sync_state"]


def test_cognition_bus_confidence_propagation_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "ops"
    bus = AURACognitionBus(output_dir=out)

    bus.process_event(
        category="governance",
        event_name="policy_verdict",
        originating_agent="governance_agent",
        target_agent="runtime_agent",
        payload={"allowed": True},
        confidence=1.0,
        governance_classification="FAIL_CLOSED",
    )

    model = bus.get_confidence_propagation_model()
    score = model["agent_confidence"]["governance_agent"]["score"]
    assert round(score, 3) == 0.625

    # Tamper ordering to ensure validation detects sequence regression.
    bus._events.append(dict(bus._events[0]))  # noqa: SLF001
    report = bus.validate_ordering()
    assert not report["valid"]
