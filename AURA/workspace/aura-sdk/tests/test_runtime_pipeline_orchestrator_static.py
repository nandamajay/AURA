from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.runtime_pipeline_orchestrator import (  # noqa: E402
    RuntimePipelineOrchestrator,
    RuntimePipelineStage,
    build_default_runtime_orchestrator,
)


def test_default_runtime_orchestrator_dependency_order() -> None:
    orchestrator = build_default_runtime_orchestrator()
    report = orchestrator.resolve_order()
    assert report["classification"] == "PASS"
    order = report["ordered_stages"]
    assert order.index("runtime_trace_ingestion") < order.index("runtime_equivalence")
    assert order.index("runtime_equivalence") < order.index("runtime_governance")


def test_incremental_rebuild_triggers_dependents_and_replay_regeneration() -> None:
    orchestrator = build_default_runtime_orchestrator()
    plan = orchestrator.incremental_rebuild_plan(
        changed_artifacts=["runtime_trace_ingestion_baseline.json"],
        cached_state={"deterministic_fingerprint": "abc123"},
    )
    assert plan["classification"] == "PASS"
    assert "runtime_trace_ingestion" in set(plan["impacted_stages"])
    assert "runtime_equivalence" in set(plan["impacted_stages"])
    assert "runtime_governance" in set(plan["impacted_stages"])
    assert plan["replay_regeneration_required"] is True


def test_orchestrator_detects_dependency_cycle_fail_closed() -> None:
    orchestrator = RuntimePipelineOrchestrator(
        stages=[
            RuntimePipelineStage(
                name="a",
                dependencies=("b",),
                outputs=("a.json",),
            ),
            RuntimePipelineStage(
                name="b",
                dependencies=("a",),
                outputs=("b.json",),
            ),
        ]
    )
    report = orchestrator.resolve_order()
    assert report["classification"] == "FAIL_CLOSED"
    assert any(reason.startswith("dependency_cycle:") for reason in report["fail_closed_reasons"])
