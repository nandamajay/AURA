from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_ingestion_contracts import (  # noqa: E402
    RuntimeEvidenceSchema,
    RuntimeGraphSchema,
    RuntimeReplaySchema,
    build_lineage,
    replay_fingerprint_from_inputs,
)


def test_build_lineage_deterministic_for_same_inputs() -> None:
    first = build_lineage(target_id="RB3Gen2", session_id="session-a", parent_lineage_id="root")
    second = build_lineage(target_id="RB3Gen2", session_id="session-a", parent_lineage_id="root")
    assert first.lineage_id == second.lineage_id


def test_contract_models_parse_with_minimal_payload() -> None:
    lineage = build_lineage(target_id="RB3Gen2", session_id="session-b")
    graph = RuntimeGraphSchema(
        graph_name="runtime_path_graph",
        lineage=lineage,
        nodes=[],
        edges=[],
        classification="PASS",
    )
    evidence = RuntimeEvidenceSchema(
        lineage=lineage,
        evidence=[],
    )
    replay = RuntimeReplaySchema(
        lineage=lineage,
        replay_fingerprint=replay_fingerprint_from_inputs({"a": "1"}),
        replay_inputs={"a": "1"},
        deterministic_ready=True,
        classification="PASS",
    )
    assert graph.classification == "PASS"
    assert evidence.classification == "PASS"
    assert replay.classification == "PASS"
