from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.runtime_evidence_fusion_engine import (  # noqa: E402
    RuntimeEvidenceFusionEngine,
    RuntimeEvidenceFusionRegistry,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime_artifacts() -> dict:
    return {
        "runtime_truth_graph": {
            "nodes": [{"id": "target:alpha"}, {"id": "runtime"}],
            "edges": [{"from": "target:alpha", "to": "runtime"}],
            "deterministic_fingerprint": "runtime-truth-fp-1",
        },
        "dapm_transition_trace": {
            "transitions": [
                {"event_id": "dapm:1", "timestamp_ms": 1002.0, "transition": "POWER_UP"},
                {"event_id": "dapm:2", "timestamp_ms": 1040.0, "transition": "POWER_DOWN"},
            ]
        },
        "pcm_lifecycle_trace": {
            "transitions": [
                {"event_id": "pcm:1", "timestamp_ms": 1000.0, "stage": "OPEN"},
                {"event_id": "pcm:2", "timestamp_ms": 1010.0, "stage": "START"},
                {"event_id": "pcm:3", "timestamp_ms": 1030.0, "stage": "STOP"},
            ]
        },
        "soundwire_runtime_graph": {
            "summary": {"runtime_soundwire_events": 3},
            "soundwire_confidence": 0.8,
        },
        "irq_timing_report": {
            "ordered_irq_events": [
                {"event_id": "irq:1", "timestamp_ms": 1005.0},
                {"event_id": "irq:2", "timestamp_ms": 1014.0},
            ],
            "summary": {"latency_spike_count": 0},
            "irq_confidence": 0.9,
        },
        "dsp_sync_report": {
            "pair_latencies_ms": [2.0, 2.4],
            "summary": {"sync_failure_count": 0},
            "dsp_sync_confidence": 0.88,
        },
        "runtime_drift_report": {
            "drift_score": 0.08,
            "drifts": [],
            "classification": "PASS",
        },
        "runtime_confidence_score": {
            "runtime_confidence": 0.86,
            "classification": "PASS",
        },
    }


def _topology_artifacts() -> dict:
    return {
        "topology_runtime_graph": {
            "edges": [
                {"from": "fe:0", "to": "be:0"},
                {"from": "be:0", "to": "codec:0"},
            ],
            "normalized_portable_audio_graph": {
                "fe_be_routes": [
                    "fe0->be0",
                    "fe1->be1",
                    "fe2->be2",
                ]
            },
        }
    }


def _semantic_artifacts() -> dict:
    return {
        "semantic_entity_graph": {
            "entities": [{"id": "semantic:pcm"}],
            "deterministic_fingerprint": "semantic-fp-1",
        },
        "semantic_relationship_map": {
            "relationships": [{"from": "semantic:pcm", "to": "semantic:dapm"}],
        },
        "semantic_confidence_report": {
            "classification": {"primary_classification": "partially_portable"},
            "semantic_fingerprint": "semantic-confidence-fp",
        },
        "dts_topology_graph": {
            "backend_frontend_mappings": ["fe0->be0"],
        },
    }


def _migration_artifacts() -> dict:
    return {
        "migration_dependency_graph": {
            "nodes": [
                {"id": "phase_1", "risk": "LOW"},
                {"id": "phase_2", "risk": "MEDIUM"},
            ]
        },
        "portability_transition_state": {
            "transitions": [
                {"id": "t1", "state": "COMPLETED"},
                {"id": "t2", "state": "IN_PROGRESS"},
            ]
        },
        "migration_checkpoint_registry": {
            "checkpoint_integrity_score": 0.82,
        },
        "migration_lineage": {
            "deterministic_fingerprint": "migration-lineage-fp-1",
        },
    }


def _patch_artifacts() -> dict:
    return {
        "patch_series_plan": {
            "series": [
                {
                    "patch_group_id": "patch_01",
                    "sequence": 1,
                    "risk": "LOW",
                    "runtime_validation_gate": {"required": True},
                    "bisect_gate": {"current_score": 0.8},
                },
                {
                    "patch_group_id": "patch_02",
                    "sequence": 2,
                    "risk": "MEDIUM",
                    "runtime_validation_gate": {"required": True},
                    "bisect_gate": {"current_score": 0.7},
                },
            ],
            "deterministic_fingerprint": "patch-plan-fp-1",
        },
        "runtime_patch_correlation": {
            "command_patch_mappings": [
                {
                    "runtime_command": "AURA_AMIXER_NAME_SET xxx 1",
                    "impacted_patch_nodes": ["patch_01"],
                },
                {
                    "runtime_command": "AURA_APLAY /tmp/test.wav",
                    "impacted_patch_nodes": ["patch_01", "patch_02"],
                },
            ]
        },
        "upstream_readiness_report": {
            "readiness_score": 0.78,
        },
        "subsystem_boundary_map": {
            "deterministic_fingerprint": "subsystem-boundary-fp-1",
        },
        "api_evolution_trace": {
            "nodes": [{"id": "api:v1"}],
        },
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "fusion-replay-fp-1",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_runtime_evidence_fusion_artifacts_and_determinism(tmp_path: Path) -> None:
    engine = RuntimeEvidenceFusionEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "runtime-evidence-fusion-v1",
        "runtime_artifacts": _runtime_artifacts(),
        "topology_artifacts": _topology_artifacts(),
        "semantic_artifacts": _semantic_artifacts(),
        "migration_artifacts": _migration_artifacts(),
        "patch_artifacts": _patch_artifacts(),
        "replay_traces": _replay(),
        "governance_state": _governance(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "evidence_references": ["test://runtime_evidence_fusion/determinism"],
        "previous_fusion_lineage": [],
    }

    first = engine.analyze(**args).fusion_bundle
    second = engine.analyze(**args).fusion_bundle

    assert first["runtime_evidence_fusion_fingerprint"] == second["runtime_evidence_fusion_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "unified_engineering_truth_graph",
        "runtime_topology_correlation",
        "lifecycle_causality_map",
        "migration_runtime_alignment",
        "patch_runtime_lineage",
        "dsp_runtime_causality_report",
        "regression_rootcause_report",
        "deterministic_fusion_replay",
        "engineering_confidence_score",
    }
    assert required.issubset(set(artifacts.keys()))


def test_runtime_evidence_fusion_registry_replay(tmp_path: Path) -> None:
    engine = RuntimeEvidenceFusionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-evidence-fusion-replay-v1",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        migration_artifacts=_migration_artifacts(),
        patch_artifacts=_patch_artifacts(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_evidence_fusion/replay"],
        previous_fusion_lineage=[],
    ).fusion_bundle

    registry = RuntimeEvidenceFusionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="runtime-evidence-fusion-replay-v1")
    replay_two = registry.replay(lineage_id="runtime-evidence-fusion-replay-v1")

    assert persisted["lineage_id"] == "runtime-evidence-fusion-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "unified_engineering_truth_graph.json").exists()
    assert (tmp_path / "ops" / "runtime_topology_correlation.json").exists()
    assert (tmp_path / "ops" / "lifecycle_causality_map.json").exists()
    assert (tmp_path / "ops" / "migration_runtime_alignment.json").exists()
    assert (tmp_path / "ops" / "patch_runtime_lineage.json").exists()
    assert (tmp_path / "ops" / "dsp_runtime_causality_report.json").exists()
    assert (tmp_path / "ops" / "regression_rootcause_report.json").exists()
    assert (tmp_path / "ops" / "deterministic_fusion_replay.json").exists()
    assert (tmp_path / "ops" / "engineering_confidence_score.json").exists()


def test_runtime_evidence_fusion_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = RuntimeEvidenceFusionEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_runtime_mutation_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-evidence-fusion-governance-v1",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        migration_artifacts=_migration_artifacts(),
        patch_artifacts=_patch_artifacts(),
        replay_traces=_replay(),
        governance_state=governance,
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_evidence_fusion/governance"],
        previous_fusion_lineage=[],
    ).fusion_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["engineering_confidence_score"]["classification"] == "FAIL_CLOSED"


def test_runtime_evidence_fusion_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/runtime_evidence_fusion_engine.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_evidence_adapter(" in src
    assert ".topology_evidence_adapter(" in src
    assert ".semantic_evidence_adapter(" in src
