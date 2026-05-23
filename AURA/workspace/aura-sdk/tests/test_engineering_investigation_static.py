from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.engineering_query_engine import EngineeringQueryEngine  # noqa: E402
from aura_sdk.transport.investigation_session_registry import InvestigationSessionRegistry  # noqa: E402
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime_artifacts() -> dict:
    return {
        "runtime_truth_graph": {"deterministic_fingerprint": "rt-fp", "edges": [{"from": "a", "to": "b"}]},
        "pcm_lifecycle_trace": {"transitions": [{"stage": "START", "timestamp_ms": 1200.0}]},
        "dsp_sync_report": {"summary": {"sync_failure_count": 1}, "events": [{"message": "dsp sync failed"}]},
    }


def _topology_artifacts() -> dict:
    return {
        "topology_runtime_graph": {
            "normalized_portable_audio_graph": {"fe_be_routes": ["FE0->BE0"]},
            "edges": [{"from": "FE0", "to": "BE0"}],
            "deterministic_fingerprint": "topo-fp",
        },
        "runtime_topology_correlation": {
            "route_mismatches": [{"expected": "FE0->BE0", "observed": "FE0->BE1"}],
            "deterministic_fingerprint": "topo-corr-fp",
        },
        "dts_topology_graph": {"backend_frontend_mappings": ["FE0->BE0"]},
    }


def _migration_artifacts() -> dict:
    return {
        "portability_blockers": {"summary": {"blocked_unsafe_count": 1, "advisory_only_count": 2}},
        "migration_runtime_alignment": {"classification": "FAIL_CLOSED"},
        "migration_phase_plan": {"phases": [{"phase": "p1"}, {"phase": "p2"}]},
        "upstream_equivalence_map": {
            "entries": [
                {"downstream_construct": "vendor_api", "equivalence_status": "UNRESOLVED"},
                {"downstream_construct": "snd_soc", "equivalence_status": "EXACT"},
            ]
        },
    }


def _patch_artifacts() -> dict:
    return {
        "runtime_patch_correlation": {
            "command_patch_mappings": [
                {
                    "runtime_command": "AURA_APLAY /tmp/test.wav",
                    "correlation_confidence": 0.88,
                    "impacted_patch_nodes": ["patch_audio_regression"],
                }
            ]
        },
        "patch_series_plan": {"series": [{"patch_group_id": "patch_audio_regression"}]},
        "upstream_readiness_report": {"classification": "ADVISORY_ONLY"},
        "regression_causality_report": {
            "causes": [
                {
                    "cause": "patch_audio_regression",
                    "severity": "HIGH",
                    "confidence": 0.86,
                }
            ]
        },
    }


def _semantic_artifacts() -> dict:
    return {
        "semantic_confidence_report": {
            "classification": {"primary_classification": "partially_portable"},
            "deterministic_fingerprint": "semantic-fp",
        },
        "dts_topology_graph": {"backend_frontend_mappings": ["FE0->BE0"]},
    }


def _structural_artifacts() -> dict:
    return {"structural_graph": {"nodes": [{"id": "snd_soc_component"}], "deterministic_fingerprint": "struct-fp"}}


def _incident_artifacts() -> dict:
    return {
        "runtime_incident_graph": {"deterministic_fingerprint": "incident-fp"},
        "root_cause_candidates": {
            "candidates": [
                {
                    "candidate": "runtime_sequence_drift",
                    "origin": "runtime_sequence_drift_engine",
                    "confidence": 0.82,
                }
            ]
        },
        "runtime_sequence_drift": {"drifts": [{"severity": "HIGH", "details": "start/stop reordering"}]},
        "lifecycle_violation_report": {"violations": [{"severity": "HIGH", "code": "LIFE_001"}]},
        "topology_runtime_causality": {"inconsistencies": [{"severity": "HIGH"}]},
        "regression_causality_report": {"causes": [{"cause": "patch_audio_regression", "confidence": 0.86}]},
        "engineering_confidence_report": {"engineering_confidence": 0.71},
    }


def _fusion_artifacts() -> dict:
    return {"engineering_confidence_score": {"engineering_confidence": 0.72}}


def _replay_artifacts() -> dict:
    return {
        "deterministic_runtime_session_replay": {
            "replay_score": 0.84,
            "replay_signal": {
                "deterministic_event_ordering": True,
                "deterministic_replay_fingerprint": "replay-runtime-fp",
            },
        },
        "deterministic_fusion_replay": {
            "replay_score": 0.81,
            "replay_signal": {
                "deterministic_event_ordering": True,
                "deterministic_replay_fingerprint": "replay-fusion-fp",
            },
        },
        "deterministic_incident_replay": {
            "replay_score": 0.79,
            "replay_signal": {
                "deterministic_event_ordering": True,
                "deterministic_replay_fingerprint": "replay-incident-fp",
            },
        },
    }


def _confidence_artifacts() -> dict:
    return {
        "runtime_confidence_score": {"runtime_confidence": 0.74},
        "engineering_confidence_score": {"engineering_confidence": 0.71},
        "engineering_confidence_report": {"engineering_confidence": 0.69},
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _replay_traces() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "replay-master-fp",
    }


def test_engineering_investigation_deterministic_answers(tmp_path: Path) -> None:
    engine = EngineeringQueryEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "session_id": "investigation-session-a",
        "lineage_id": "investigation-v1",
        "question": "What caused this runtime failure?",
        "runtime_artifacts": _runtime_artifacts(),
        "topology_artifacts": _topology_artifacts(),
        "migration_artifacts": _migration_artifacts(),
        "patch_artifacts": _patch_artifacts(),
        "semantic_artifacts": _semantic_artifacts(),
        "structural_artifacts": _structural_artifacts(),
        "incident_artifacts": _incident_artifacts(),
        "fusion_artifacts": _fusion_artifacts(),
        "replay_artifacts": _replay_artifacts(),
        "confidence_artifacts": _confidence_artifacts(),
        "governance_state": _governance(),
        "replay_traces": _replay_traces(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "evidence_references": ["test://engineering_investigation/determinism"],
        "previous_query_history": [],
        "previous_reasoning_lineage": [],
    }

    first = engine.analyze(**args).investigation_bundle
    second = engine.analyze(**args).investigation_bundle

    assert first["engineering_investigation_fingerprint"] == second["engineering_investigation_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "investigation_reasoning_graph",
        "engineering_answer_trace",
        "causality_resolution_report",
        "migration_blocker_reasoning",
        "runtime_question_lineage",
        "deterministic_investigation_replay",
    }
    assert required.issubset(set(artifacts.keys()))

    answer = artifacts["engineering_answer_trace"]["answers"][0]
    assert isinstance(answer.get("evidence_sources"), list)
    assert isinstance(answer.get("causality_chain"), list)
    assert isinstance(answer.get("confidence_score"), float)
    assert isinstance(answer.get("replay_lineage"), dict)
    assert isinstance(answer.get("governance_state"), dict)
    assert "fail_closed_justification" in answer


def test_engineering_investigation_lineage_and_registry_replay(tmp_path: Path) -> None:
    engine = EngineeringQueryEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="investigation-session-b",
        lineage_id="investigation-replay-v1",
        question="Which lifecycle sequence drifted?",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        migration_artifacts=_migration_artifacts(),
        patch_artifacts=_patch_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        structural_artifacts=_structural_artifacts(),
        incident_artifacts=_incident_artifacts(),
        fusion_artifacts=_fusion_artifacts(),
        replay_artifacts=_replay_artifacts(),
        confidence_artifacts=_confidence_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://engineering_investigation/replay"],
        previous_query_history=[],
        previous_reasoning_lineage=[],
    ).investigation_bundle

    lineage = bundle["artifacts"]["runtime_question_lineage"]["lineage"]
    assert len(lineage) >= 1
    assert lineage[-1]["entry_hash"]

    registry = InvestigationSessionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="investigation-replay-v1")
    replay_two = registry.replay(lineage_id="investigation-replay-v1")

    assert persisted["lineage_id"] == "investigation-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "investigation_reasoning_graph.json").exists()
    assert (tmp_path / "ops" / "engineering_answer_trace.json").exists()
    assert (tmp_path / "ops" / "causality_resolution_report.json").exists()
    assert (tmp_path / "ops" / "migration_blocker_reasoning.json").exists()
    assert (tmp_path / "ops" / "runtime_question_lineage.json").exists()
    assert (tmp_path / "ops" / "deterministic_investigation_replay.json").exists()


def test_engineering_investigation_fail_closed_on_insufficient_evidence(tmp_path: Path) -> None:
    engine = EngineeringQueryEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="investigation-session-c",
        lineage_id="investigation-failclosed-v1",
        question="Which DSP synchronization failed?",
        runtime_artifacts={},
        topology_artifacts={},
        migration_artifacts={},
        patch_artifacts={},
        semantic_artifacts={},
        structural_artifacts={},
        incident_artifacts={},
        fusion_artifacts={},
        replay_artifacts={},
        confidence_artifacts={},
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://engineering_investigation/failclosed"],
        previous_query_history=[],
        previous_reasoning_lineage=[],
    ).investigation_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["engineering_answer_trace"]["classification"] == "FAIL_CLOSED"


def test_engineering_investigation_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/engineering_query_engine.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_evidence_adapter(" in src
    assert ".topology_evidence_adapter(" in src
    assert ".semantic_evidence_adapter(" in src
