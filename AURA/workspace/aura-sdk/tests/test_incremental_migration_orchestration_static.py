from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.migration_orchestrator import (  # noqa: E402
    IncrementalMigrationOrchestrator,
    MigrationOrchestrationRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime_evidence() -> dict:
    return {
        "run_id": "incremental-run-1",
        "process_success": True,
        "playback_completion": True,
        "classification": "PASS",
        "playback_runtime_seconds": 25.0,
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": "route-fp-1",
        "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
    }


def _structural_artifacts() -> dict:
    return {
        "topology_structure_graph": {
            "classification": "ADVISORY_ONLY",
            "fe_be_topology": {
                "frontend_dais": ["alpha_fe0"],
                "backend_dais": ["alpha_be0"],
                "inferred_links": [
                    {"frontend": "alpha_fe0", "backend_candidates": ["alpha_be0"], "confidence": 0.8}
                ],
            },
        },
        "callback_chain_graph": {
            "nodes": [
                {"id": "cb:alpha_startup", "kind": "callback_function"},
                {"id": "cb:alpha_trigger", "kind": "callback_function"},
            ],
        },
        "upstream_equivalence_trace": {
            "summary": {
                "total": 2,
                "exact": 1,
                "partial": 0,
                "unresolved": 1,
            }
        },
    }


def _conversion_reasoning_artifacts() -> dict:
    return {
        "portability_blocker_report": {
            "classification": "ADVISORY_ONLY",
            "risk_classification": "MEDIUM",
            "summary": {
                "blocked_unsafe_count": 0,
            },
        },
        "lifecycle_incompatibility_report": {
            "lifecycle_incompatibilities": [
                {
                    "type": "component_lifecycle_mismatch",
                    "severity": "MEDIUM",
                }
            ]
        },
        "vendor_dependency_graph": {
            "unsupported_proprietary_hooks": ["vendor_hook_alpha"],
            "dsp_coupling": ["q6_audio_path"],
            "soundwire_portability_gaps": ["swr_private_bus"],
        },
        "runtime_portability_analysis": {
            "runtime_portability_blockers": [],
            "unsupported_runtime_dependencies": [],
        },
        "upstream_equivalence_confidence": {
            "scores": {
                "overall_confidence": 0.67,
                "topology_conversion_confidence": 0.64,
                "runtime_portability_confidence": 0.70,
            }
        },
    }


def _replay_traces() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "replay-fp-incremental-1",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_incremental_orchestration_artifacts_and_determinism(tmp_path: Path) -> None:
    orchestrator = IncrementalMigrationOrchestrator(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "incremental-orch-v1",
        "runtime_evidence": _runtime_evidence(),
        "structural_artifacts": _structural_artifacts(),
        "conversion_reasoning_artifacts": _conversion_reasoning_artifacts(),
        "replay_traces": _replay_traces(),
        "governance_state": _governance(),
        "previous_transition_state": {},
        "previous_checkpoint_history": [],
        "previous_trace_history": [],
        "evidence_references": ["test://incremental/orchestration"],
    }

    first = orchestrator.analyze(**args).orchestration_bundle
    second = orchestrator.analyze(**args).orchestration_bundle

    assert first["migration_orchestration_fingerprint"] == second["migration_orchestration_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "staged_migration_plan",
        "migration_dependency_graph",
        "rollback_boundary_report",
        "runtime_stability_gate_report",
        "portability_transition_state",
        "incremental_equivalence_report",
        "migration_checkpoint_registry",
        "deterministic_migration_orchestration_trace",
    }
    assert required.issubset(set(artifacts.keys()))


def test_incremental_orchestration_registry_replay(tmp_path: Path) -> None:
    orchestrator = IncrementalMigrationOrchestrator(_loader(tmp_path))
    bundle = orchestrator.analyze(
        target_id="fake_target_alpha",
        lineage_id="incremental-orch-replay-v1",
        runtime_evidence=_runtime_evidence(),
        structural_artifacts=_structural_artifacts(),
        conversion_reasoning_artifacts=_conversion_reasoning_artifacts(),
        replay_traces=_replay_traces(),
        governance_state=_governance(),
        previous_transition_state={},
        previous_checkpoint_history=[],
        previous_trace_history=[],
        evidence_references=["test://incremental/replay"],
    ).orchestration_bundle

    registry = MigrationOrchestrationRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="incremental-orch-replay-v1")
    replay_two = registry.replay(lineage_id="incremental-orch-replay-v1")

    assert persisted["lineage_id"] == "incremental-orch-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "staged_migration_plan.json").exists()
    assert (tmp_path / "ops" / "migration_dependency_graph.json").exists()
    assert (tmp_path / "ops" / "rollback_boundary_report.json").exists()
    assert (tmp_path / "ops" / "runtime_stability_gate_report.json").exists()
    assert (tmp_path / "ops" / "portability_transition_state.json").exists()
    assert (tmp_path / "ops" / "incremental_equivalence_report.json").exists()
    assert (tmp_path / "ops" / "migration_checkpoint_registry.json").exists()
    assert (tmp_path / "ops" / "deterministic_migration_orchestration_trace.json").exists()


def test_incremental_orchestration_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    orchestrator = IncrementalMigrationOrchestrator(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = orchestrator.analyze(
        target_id="fake_target_alpha",
        lineage_id="incremental-orch-governance-v1",
        runtime_evidence=_runtime_evidence(),
        structural_artifacts=_structural_artifacts(),
        conversion_reasoning_artifacts=_conversion_reasoning_artifacts(),
        replay_traces=_replay_traces(),
        governance_state=governance,
        previous_transition_state={},
        previous_checkpoint_history=[],
        previous_trace_history=[],
        evidence_references=["test://incremental/governance"],
    ).orchestration_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["runtime_stability_gate_report"]["classification"] == "FAIL_CLOSED"


def test_incremental_orchestration_core_plugin_isolation() -> None:
    src = (SRC_DIR / "aura_sdk/transport/migration_orchestrator.py").read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".topology_translation_adapter(" in src
    assert ".runtime_conversion_adapter(" in src
