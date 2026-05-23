from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.controlled_pilot_conversion import (  # noqa: E402
    ControlledPilotConversionEngine,
    ControlledPilotConversionRegistry,
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


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "pilot-replay-fp",
    }


def _source_snapshots() -> dict[str, str]:
    return {
        "sound/soc/qcom/pilot_test.c": "\n".join(
            [
                "int pilot_entry(void)",
                "{",
                "    int x = VENDOR_AUDIO_MACRO;",
                "    x += vendor_log_wrap(x);",
                "    return vendor_helper_wrap(x);",
                "}",
                "",
            ]
        )
    }


def _translation_artifacts(*, unsupported_count: int = 0) -> dict:
    return {
        "api_replacement_map": {
            "replacements": [
                {
                    "downstream_construct": "VENDOR_AUDIO_MACRO",
                    "upstream_replacement": "SND_SOC_AUDIO_FLAG",
                    "candidate_confidence": 0.93,
                    "runtime_safe": True,
                    "transformation_class": "vendor_macro_elimination",
                    "evidence_sources": ["test://pilot/macro"],
                },
                {
                    "downstream_construct": "vendor_log_wrap",
                    "upstream_replacement": "dev_dbg",
                    "candidate_confidence": 0.9,
                    "runtime_safe": True,
                    "transformation_class": "callback_replacement",
                    "evidence_sources": ["test://pilot/logging"],
                },
                {
                    "downstream_construct": "vendor_helper_wrap",
                    "upstream_replacement": "snd_soc_component_enable",
                    "candidate_confidence": 0.88,
                    "runtime_safe": True,
                    "transformation_class": "runtime_safe_api_substitution",
                    "evidence_sources": ["test://pilot/helper"],
                },
            ]
        },
        "unsupported_vendor_constructs": {
            "classification": "PASS" if unsupported_count == 0 else "FAIL_CLOSED",
            "summary": {"unsupported_count": int(unsupported_count)},
            "unsupported": (
                []
                if unsupported_count <= 0
                else [{"construct": "vendor_unsupported_k", "reason": "no_upstream_equivalent"}]
            ),
        },
        "runtime_equivalence_validation": {
            "classification": "PASS",
            "candidate_validations": [
                {
                    "downstream_construct": "VENDOR_AUDIO_MACRO",
                    "runtime_equivalent": True,
                    "validation_confidence": 0.9,
                },
                {
                    "downstream_construct": "vendor_log_wrap",
                    "runtime_equivalent": True,
                    "validation_confidence": 0.86,
                },
                {
                    "downstream_construct": "vendor_helper_wrap",
                    "runtime_equivalent": True,
                    "validation_confidence": 0.87,
                },
            ],
        },
    }


def _execution_artifacts(*, split_subsystems: bool = False) -> dict:
    file_a = "sound/soc/qcom/pilot_test.c"
    file_b = "drivers/soundwire/pilot_test.c"
    return {
        "runtime_validated_patch_segments": {
            "segments": [
                {
                    "file": file_a,
                    "downstream_construct": "VENDOR_AUDIO_MACRO",
                    "upstream_replacement": "SND_SOC_AUDIO_FLAG",
                },
                {
                    "file": file_b if split_subsystems else file_a,
                    "downstream_construct": "vendor_log_wrap",
                    "upstream_replacement": "dev_dbg",
                },
                {
                    "file": file_a,
                    "downstream_construct": "vendor_helper_wrap",
                    "upstream_replacement": "snd_soc_component_enable",
                },
            ]
        },
        "translation_execution_report": {"classification": "PASS"},
    }


def _acceptance_artifacts(*, acceptance_pass: bool = True) -> dict:
    return {
        "upstream_acceptance_report": {"classification": "PASS" if acceptance_pass else "FAIL_CLOSED"},
        "acceptance_confidence_score": {
            "classification": "PASS" if acceptance_pass else "FAIL_CLOSED",
            "acceptance_confidence": 0.9 if acceptance_pass else 0.6,
        },
        "regression_risk_assessment": {
            "classification": "PASS",
            "regression_containment_confidence": 0.88,
        },
    }


def _runtime_artifacts() -> dict:
    return {
        "runtime_equivalence_fingerprint": {
            "classification": "PASS",
            "summary": {"mean_runtime_backed_confidence": 0.92},
        },
        "topology_runtime_graph": {
            "classification": "PASS",
        },
    }


def test_controlled_pilot_conversion_generates_required_artifacts(tmp_path: Path) -> None:
    engine = ControlledPilotConversionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="pilot-session-a",
        lineage_id="pilot-lineage-a",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(),
        acceptance_artifacts=_acceptance_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        dry_run=False,
        evidence_references=["test://pilot/artifacts"],
        previous_pilot_history=[],
    ).pilot_bundle

    assert bundle["classification"] == "PASS"
    artifacts = bundle["artifacts"]
    required = {
        "pilot_conversion_patch",
        "transformation_explainability_report",
        "runtime_equivalence_validation",
        "upstream_review_package",
        "pilot_risk_assessment",
        "transformation_lineage",
        "rollback_validation_report",
        "deterministic_pilot_replay",
        "governance_decision_report",
    }
    assert required.issubset(set(artifacts.keys()))
    patch_text = artifacts["pilot_conversion_patch"]["patch_text"]
    assert "dev_dbg" in patch_text
    assert "snd_soc_component_enable" in patch_text
    assert artifacts["governance_decision_report"]["classification"] == "PASS"


def test_fail_closed_when_unsupported_vendor_constructs_present(tmp_path: Path) -> None:
    engine = ControlledPilotConversionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="pilot-session-b",
        lineage_id="pilot-lineage-b",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(unsupported_count=2),
        execution_artifacts=_execution_artifacts(),
        acceptance_artifacts=_acceptance_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        dry_run=False,
        evidence_references=["test://pilot/unsupported"],
        previous_pilot_history=[],
    ).pilot_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_decision_report"]["decision"]["escalation_reasons"]
    assert "unsupported_vendor_abstractions_unresolved" in reasons


def test_fail_closed_when_cross_subsystem_scope_detected(tmp_path: Path) -> None:
    engine = ControlledPilotConversionEngine(_loader(tmp_path))
    source_snapshots = dict(_source_snapshots())
    source_snapshots["drivers/soundwire/pilot_test.c"] = "int y = vendor_log_wrap(1);\n"
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="pilot-session-c",
        lineage_id="pilot-lineage-c",
        source_snapshots=source_snapshots,
        translation_artifacts=_translation_artifacts(),
        execution_artifacts=_execution_artifacts(split_subsystems=True),
        acceptance_artifacts=_acceptance_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        dry_run=True,
        evidence_references=["test://pilot/subsystem"],
        previous_pilot_history=[],
    ).pilot_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_decision_report"]["decision"]["escalation_reasons"]
    assert "cross_subsystem_transformations_prohibited" in reasons


def test_deterministic_replay_and_registry_persistence(tmp_path: Path) -> None:
    engine = ControlledPilotConversionEngine(_loader(tmp_path))
    kwargs = {
        "target_id": "fake_target_alpha",
        "session_id": "pilot-session-d",
        "lineage_id": "pilot-lineage-d",
        "source_snapshots": _source_snapshots(),
        "translation_artifacts": _translation_artifacts(),
        "execution_artifacts": _execution_artifacts(),
        "acceptance_artifacts": _acceptance_artifacts(),
        "runtime_artifacts": _runtime_artifacts(),
        "governance_state": _governance(),
        "replay_traces": _replay(),
        "plugin_capability_state": {"supported": True},
        "dry_run": False,
        "evidence_references": ["test://pilot/replay"],
        "previous_pilot_history": [],
    }
    first = engine.analyze(**kwargs).pilot_bundle
    second = engine.analyze(**kwargs).pilot_bundle
    assert first["controlled_pilot_conversion_fingerprint"] == second["controlled_pilot_conversion_fingerprint"]
    assert (
        first["artifacts"]["deterministic_pilot_replay"]["deterministic_fingerprint"]
        == second["artifacts"]["deterministic_pilot_replay"]["deterministic_fingerprint"]
    )

    registry = ControlledPilotConversionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="pilot-lineage-d")
    replay_two = registry.replay(lineage_id="pilot-lineage-d")
    assert persisted["lineage_id"] == "pilot-lineage-d"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_controlled_pilot_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/controlled_pilot_conversion.py"
    ).read_text(encoding="utf-8").lower()
    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_conversion_adapter(" in src
