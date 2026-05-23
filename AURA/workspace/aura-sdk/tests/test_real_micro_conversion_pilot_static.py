from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.real_micro_conversion_pilot import (  # noqa: E402
    RealMicroConversionPilotEngine,
    RealMicroConversionPilotRegistry,
    build_real_micro_source_input_model,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _governance(*, violate: bool = False) -> dict:
    state = {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }
    if violate:
        state["autonomous_patching_allowed"] = True
    return state


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "real-micro-pilot-replay-fp",
    }


def test_real_micro_source_input_model_contains_real_qcom_constructs() -> None:
    model = build_real_micro_source_input_model()
    source_snapshots = model["source_snapshots"]
    assert "sound/soc/qcom/q6apm-compat-micro-pilot.c" in source_snapshots
    source = source_snapshots["sound/soc/qcom/q6apm-compat-micro-pilot.c"]
    assert "qcom_dbg_log" in source
    assert "qcom_cap_bool" in source
    assert "dev_dbg" in source
    assert "device_is_registered" in source


def test_real_micro_conversion_pilot_runs_end_to_end(tmp_path: Path) -> None:
    engine = RealMicroConversionPilotEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="real-micro-session-a",
        lineage_id="real-micro-lineage-a",
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        evidence_references=["test://real_micro/end_to_end"],
    ).pilot_bundle

    artifacts = bundle["artifacts"]
    required = {
        "real_micro_conversion_patch",
        "transformation_explainability_report",
        "runtime_equivalence_validation",
        "governance_decision_report",
        "conversion_confidence_report",
        "rollback_lineage",
        "deterministic_conversion_replay",
        "upstream_acceptance_prediction",
    }
    assert required.issubset(set(artifacts.keys()))
    assert artifacts["runtime_equivalence_validation"]["summary"]["candidate_count"] >= 1
    assert "compile_validation" in artifacts["governance_decision_report"]


def test_governance_fail_closed_cannot_be_bypassed(tmp_path: Path) -> None:
    engine = RealMicroConversionPilotEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="real-micro-session-b",
        lineage_id="real-micro-lineage-b",
        governance_state=_governance(violate=True),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        evidence_references=["test://real_micro/governance"],
    ).pilot_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_decision_report"]["decision"]["escalation_reasons"]
    assert any(str(reason).startswith("governance_violation") for reason in reasons)


def test_unsupported_construct_rejection_fail_closed(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import real_micro_conversion_pilot as module  # noqa: E402

    base_model = build_real_micro_source_input_model()

    def _patched_model() -> dict:
        model = copy.deepcopy(base_model)
        model["downstream_upstream_mapping_graph"]["entries"].append(
            {
                "downstream_construct": "qcom_unsupported_private",
                "upstream_equivalent": "UNRESOLVED",
                "equivalence_confidence": 0.1,
            }
        )
        model["upstream_equivalence_map"]["entries"].append(
            {
                "downstream_construct": "qcom_unsupported_private",
                "upstream_equivalent": "UNRESOLVED",
                "equivalence_confidence": 0.1,
            }
        )
        model["semantic_entity_graph"]["nodes"].append({"id": "n5", "label": "qcom_unsupported_private"})
        model["structural_artifacts"]["downstream_driver_graph"]["extracted"]["vendor_extensions"].append(
            "qcom_unsupported_private"
        )
        return model

    monkeypatch.setattr(module, "build_real_micro_source_input_model", _patched_model)
    engine = RealMicroConversionPilotEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="real-micro-session-c",
        lineage_id="real-micro-lineage-c",
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        evidence_references=["test://real_micro/unsupported"],
    ).pilot_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["governance_decision_report"]["decision"]["escalation_reasons"]
    assert "unsupported_vendor_abstractions_unresolved" in reasons


def test_deterministic_replay_registry_persistence(tmp_path: Path) -> None:
    engine = RealMicroConversionPilotEngine(_loader(tmp_path))
    kwargs = {
        "target_id": "fake_target_alpha",
        "session_id": "real-micro-session-d",
        "lineage_id": "real-micro-lineage-d",
        "governance_state": _governance(),
        "replay_traces": _replay(),
        "plugin_capability_state": {"supported": True},
        "previous_history": [],
        "evidence_references": ["test://real_micro/replay"],
    }
    first = engine.analyze(**kwargs).pilot_bundle
    second = engine.analyze(**kwargs).pilot_bundle
    assert first["real_micro_conversion_fingerprint"] == second["real_micro_conversion_fingerprint"]
    assert (
        first["artifacts"]["deterministic_conversion_replay"]["deterministic_fingerprint"]
        == second["artifacts"]["deterministic_conversion_replay"]["deterministic_fingerprint"]
    )

    registry = RealMicroConversionPilotRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="real-micro-lineage-d")
    replay_two = registry.replay(lineage_id="real-micro-lineage-d")
    assert persisted["lineage_id"] == "real-micro-lineage-d"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
