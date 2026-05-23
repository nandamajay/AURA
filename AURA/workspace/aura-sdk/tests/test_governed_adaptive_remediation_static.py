from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.governed_adaptive_remediation import (  # noqa: E402
    GovernedAdaptiveRemediationEngine,
    GovernedAdaptiveRemediationRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _translation_artifacts() -> dict:
    return {
        "api_replacement_map": {
            "replacements": [
                {
                    "downstream_construct": "vendor_callback_x",
                    "upstream_replacement": "snd_soc_component_open",
                    "candidate_confidence": 0.74,
                    "runtime_safe": True,
                    "transformation_class": "callback_replacement",
                    "evidence_sources": ["test://mapping/callback"],
                },
                {
                    "downstream_construct": "vendor_macro_a",
                    "upstream_replacement": "snd_soc_component_macro_a",
                    "candidate_confidence": 0.81,
                    "runtime_safe": True,
                    "transformation_class": "vendor_macro_elimination",
                    "evidence_sources": ["test://mapping/macro"],
                },
            ]
        },
        "unsupported_vendor_constructs": {
            "summary": {"unsupported_count": 1},
            "unsupported": [
                {"construct": "vendor_unsupported_a", "reason": "no_upstream_equivalent"},
            ],
        },
        "runtime_equivalence_validation": {
            "candidate_validations": [
                {
                    "downstream_construct": "vendor_callback_x",
                    "runtime_equivalent": True,
                    "validation_confidence": 0.88,
                    "blocking_runtime_reasons": [],
                },
                {
                    "downstream_construct": "vendor_macro_a",
                    "runtime_equivalent": False,
                    "validation_confidence": 0.41,
                    "blocking_runtime_reasons": ["macro_behavior_mismatch"],
                },
            ]
        },
    }


def _execution_artifacts(*, with_runtime_segment: bool = True) -> dict:
    segments = []
    if with_runtime_segment:
        segments = [
            {
                "segment_id": "segment:1",
                "file": "sound/soc/vendor/test.c",
                "stage_id": "phase_vendor_callback_abstraction",
                "category": "callback_replacement",
                "downstream_construct": "vendor_callback_x",
                "upstream_replacement": "snd_soc_component_open",
                "replacement_count": 2,
            }
        ]
    return {
        "runtime_validated_patch_segments": {
            "classification": "PASS" if with_runtime_segment else "FAIL_CLOSED",
            "segments": segments,
        },
        "translation_execution_report": {
            "classification": "PASS" if with_runtime_segment else "FAIL_CLOSED",
            "fail_closed_justification": "" if with_runtime_segment else "no_runtime_validated_transformations",
        },
        "unsafe_transformation_blocks": {
            "blocks": [
                {"construct": "vendor_macro_a", "reason": "runtime_equivalence_false", "category": "vendor_macro_elimination"},
                {"construct": "vendor_macro_b", "reason": "runtime_equivalence_false", "category": "vendor_macro_elimination"},
            ]
        },
        "transformation_lineage": {
            "migration_staging_boundaries": {
                "stage_order": {
                    "phase_pcm_lifecycle_translation": 1,
                    "phase_dapm_route_equivalence": 2,
                    "phase_soundwire_mapping": 3,
                    "phase_vendor_callback_abstraction": 4,
                }
            }
        },
    }


def _runtime_artifacts() -> dict:
    return {"runtime_truth_graph": {"classification": "PASS", "deterministic_fingerprint": "runtime-truth-fp"}}


def _replay_traces() -> dict:
    return {"deterministic_event_ordering": True, "deterministic_replay_fingerprint": "adaptive-replay-fp"}


def _manual_outcomes() -> dict:
    return {
        "entries": [
            {
                "downstream_construct": "vendor_macro_a",
                "upstream_replacement": "snd_soc_component_macro_a",
                "resolution_status": "resolved",
                "runtime_validated": True,
                "outcome": "success",
                "subsystem": "asoc",
                "evidence_references": ["test://manual/macro_a"],
            }
        ]
    }


def test_adaptive_learning_deterministic_replay(tmp_path: Path) -> None:
    engine = GovernedAdaptiveRemediationEngine(_loader(tmp_path))

    bundle_one = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-a",
        lineage_id="adaptive-lineage-a",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=True),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes=_manual_outcomes(),
        previous_learning_history=[],
        evidence_references=["test://adaptive/deterministic"],
    ).learning_bundle

    bundle_two = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-a",
        lineage_id="adaptive-lineage-a",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=True),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes=_manual_outcomes(),
        previous_learning_history=[],
        evidence_references=["test://adaptive/deterministic"],
    ).learning_bundle

    assert bundle_one["classification"] == "PASS"
    assert bundle_two["classification"] == "PASS"
    assert (
        bundle_one["artifacts"]["learned_translation_patterns"]["deterministic_fingerprint"]
        == bundle_two["artifacts"]["learned_translation_patterns"]["deterministic_fingerprint"]
    )
    assert (
        bundle_one["artifacts"]["adaptive_remediation_trace"]["deterministic_fingerprint"]
        == bundle_two["artifacts"]["adaptive_remediation_trace"]["deterministic_fingerprint"]
    )

    registry = GovernedAdaptiveRemediationRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(bundle_one)
    replay_one = registry.replay(lineage_id="adaptive-lineage-a")
    replay_two = registry.replay(lineage_id="adaptive-lineage-a")
    assert persisted["lineage_id"] == "adaptive-lineage-a"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_governance_consistency_fail_closed(tmp_path: Path) -> None:
    engine = GovernedAdaptiveRemediationEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-b",
        lineage_id="adaptive-lineage-b",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=True),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=governance,
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes=_manual_outcomes(),
        previous_learning_history=[],
        evidence_references=["test://adaptive/governance"],
    ).learning_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "governance_violation:autonomous_patching_allowed" in bundle["fail_closed_justification"]
    patterns = bundle["artifacts"]["learned_translation_patterns"]["patterns"]
    assert all(not p["governance_gate"]["eligible_for_reuse"] for p in patterns)


def test_confidence_drift_validation(tmp_path: Path) -> None:
    engine = GovernedAdaptiveRemediationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-c",
        lineage_id="adaptive-lineage-c",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=True),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes=_manual_outcomes(),
        previous_learning_history=[],
        evidence_references=["test://adaptive/confidence"],
    ).learning_bundle

    rows = bundle["artifacts"]["confidence_calibration_report"]["patterns"]
    assert rows
    by_construct = {row["downstream_construct"]: row for row in rows}
    assert by_construct["vendor_callback_x"]["confidence_drift"] > 0.0
    assert by_construct["vendor_macro_a"]["runtime_backed_evidence"] is True


def test_fail_closed_without_runtime_backed_evidence(tmp_path: Path) -> None:
    engine = GovernedAdaptiveRemediationEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-d",
        lineage_id="adaptive-lineage-d",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=False),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes={"entries": []},
        previous_learning_history=[],
        evidence_references=["test://adaptive/failclosed"],
    ).learning_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["fail_closed_justification"] == "translation_execution_fail_closed_without_runtime_backed_patterns"
    patterns = bundle["artifacts"]["learned_translation_patterns"]["patterns"]
    assert patterns
    for pattern in patterns:
        assert pattern["governance_gate"]["runtime_backed_evidence"] is False
        assert pattern["governance_gate"]["eligible_for_reuse"] is False


def test_required_artifacts_present(tmp_path: Path) -> None:
    engine = GovernedAdaptiveRemediationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="adaptive-session-e",
        lineage_id="adaptive-lineage-e",
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(with_runtime_segment=True),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        manual_remediation_outcomes=_manual_outcomes(),
        previous_learning_history=[],
        evidence_references=["test://adaptive/artifacts"],
    ).learning_bundle

    artifacts = bundle["artifacts"]
    required = {
        "learned_translation_patterns",
        "remediation_template_registry",
        "historical_blocker_similarity_map",
        "confidence_calibration_report",
        "reusable_equivalence_library",
        "subsystem_translation_memory",
        "adaptive_remediation_trace",
    }
    assert required.issubset(set(artifacts.keys()))


def test_governed_adaptive_remediation_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/governed_adaptive_remediation.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_conversion_adapter(" in src
