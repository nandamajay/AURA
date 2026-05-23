from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.conversion_reasoning_engine import (  # noqa: E402
    GovernedConversionReasoningEngine,
    GovernedConversionReasoningRegistry,
)
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime() -> dict:
    return {
        "run_id": "governed-run-1",
        "process_success": True,
        "playback_completion": True,
        "classification": "PASS",
        "playback_runtime_seconds": 25.0,
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": "route-fp-1",
        "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "replay-fp-1",
    }


def _structural() -> dict:
    return {
        "downstream_hook_inventory": {
            "inventory": {
                "downstream_vendor_hooks": ["vendor_hook_alpha_path"],
                "downstream_only_apis": ["msm_alpha_api"],
                "vendor_tokens": ["q6_alpha_dep", "swr_alpha_path", "msm_alpha_api"],
                "proprietary_runtime_hooks": ["vendor_hook_alpha_path"],
            }
        },
        "callback_chain_graph": {
            "nodes": [
                {"id": "callback:msm_alpha_startup", "kind": "callback_function"},
                {"id": "callback:q6_alpha_trigger", "kind": "callback_function"},
            ],
            "edges": [],
        },
        "driver_registration_graph": {
            "component_lifecycle": [
                {
                    "component_driver": "alpha_component_driver",
                    "callbacks": [{"callback": "probe", "function": "alpha_probe"}],
                }
            ],
            "ops_lifecycle": [
                {
                    "ops_structure": "alpha_ops",
                    "callbacks": [
                        {"callback": "startup", "function": "msm_alpha_startup"},
                        {"callback": "trigger", "function": "q6_alpha_trigger"},
                    ],
                }
            ],
        },
        "topology_structure_graph": {
            "fe_be_topology": {
                "frontend_dais": ["alpha_fe0"],
                "backend_dais": ["alpha_be0", "alpha_be1"],
                "inferred_links": [
                    {"frontend": "alpha_fe0", "backend_candidates": ["alpha_be0"], "confidence": 0.7}
                ],
            },
            "dapm_graph": {
                "widgets": ["SPK"],
                "routes": [{"sink": "SPK", "source": "RX0"}],
            },
        },
        "upstream_equivalence_trace": {
            "entries": [
                {
                    "downstream_construct": "msm_alpha_api",
                    "upstream_equivalent": "UNRESOLVED",
                    "equivalence_status": "UNRESOLVED",
                    "equivalence_confidence": 0.2,
                },
                {
                    "downstream_construct": "snd_soc_dai_link",
                    "upstream_equivalent": "snd_soc_dai_link",
                    "equivalence_status": "EXACT",
                    "equivalence_confidence": 0.9,
                },
            ],
            "summary": {"total": 2, "exact": 1, "partial": 0, "unresolved": 1},
        },
        "runtime_source_correlation": {
            "correlation_confidence": 0.65,
            "runtime_snapshot": {"run_id": "governed-run-1"},
            "command_source_correlations": [
                {"runtime_command": "resolve_pcm", "matched_source_files": ["sound/soc/qcom/alpha.c"]}
            ],
        },
    }


def _semantic() -> dict:
    return {
        "classification": {
            "primary_classification": "vendor_coupled",
            "scores": {
                "vendor_coupled": 0.75,
                "upstream_friendly": 0.2,
            },
        },
        "adapters": {},
    }


def _topology() -> dict:
    return {
        "confidence": {"topology_confidence": 0.7},
        "runtime_route_graph": {"runtime_paths": ["alpha_fe0->alpha_be0"]},
    }


def _dts() -> dict:
    return {
        "backend_frontend_mappings": ["alpha_fe0->alpha_be0"],
        "qcom_audio_routing": ["RX0->SPK"],
        "soundwire_topology_markers": ["SWRM"],
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_governed_conversion_reasoning_artifacts_and_determinism(tmp_path: Path) -> None:
    engine = GovernedConversionReasoningEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "governed-conv-v1",
        "runtime_evidence": _runtime(),
        "structural_artifacts": _structural(),
        "semantic_cognition": _semantic(),
        "topology_cognition": _topology(),
        "dts_cognition": _dts(),
        "replay_traces": {
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "replay-fp-1",
        },
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "governance_state": _governance(),
        "evidence_references": ["test://governed/reasoning"],
        "regression_history": [],
        "previous_reasoning_lineage": [],
    }

    first = engine.analyze(**args).conversion_reasoning_bundle
    second = engine.analyze(**args).conversion_reasoning_bundle

    assert first["conversion_reasoning_fingerprint"] == second["conversion_reasoning_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "conversion_reasoning_graph",
        "portability_blocker_report",
        "migration_phase_plan",
        "abstraction_gap_report",
        "upstream_equivalence_confidence",
        "lifecycle_incompatibility_report",
        "vendor_dependency_graph",
        "runtime_portability_analysis",
        "deterministic_conversion_reasoning_trace",
    }
    assert required.issubset(set(artifacts.keys()))


def test_governed_conversion_reasoning_registry_replay(tmp_path: Path) -> None:
    engine = GovernedConversionReasoningEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="governed-conv-replay-v1",
        runtime_evidence=_runtime(),
        structural_artifacts=_structural(),
        semantic_cognition=_semantic(),
        topology_cognition=_topology(),
        dts_cognition=_dts(),
        replay_traces={
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "replay-fp-1",
        },
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        governance_state=_governance(),
        evidence_references=["test://governed/replay"],
        regression_history=[],
        previous_reasoning_lineage=[],
    ).conversion_reasoning_bundle

    registry = GovernedConversionReasoningRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="governed-conv-replay-v1")
    replay_two = registry.replay(lineage_id="governed-conv-replay-v1")

    assert persisted["lineage_id"] == "governed-conv-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "conversion_reasoning_graph.json").exists()
    assert (tmp_path / "ops" / "deterministic_conversion_reasoning_trace.json").exists()


def test_governed_conversion_reasoning_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = GovernedConversionReasoningEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="governed-conv-governance-v1",
        runtime_evidence=_runtime(),
        structural_artifacts=_structural(),
        semantic_cognition=_semantic(),
        topology_cognition=_topology(),
        dts_cognition=_dts(),
        replay_traces={
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "replay-fp-1",
        },
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        governance_state=governance,
        evidence_references=["test://governed/governance"],
        regression_history=[],
        previous_reasoning_lineage=[],
    ).conversion_reasoning_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["migration_phase_plan"]["classification"] == "FAIL_CLOSED"


def test_governed_conversion_reasoning_core_plugin_isolation() -> None:
    src = (SRC_DIR / "aura_sdk/transport/conversion_reasoning_engine.py").read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".downstream_upstream_adapter(" in src
    assert ".runtime_conversion_adapter(" in src
