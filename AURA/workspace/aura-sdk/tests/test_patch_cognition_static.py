from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.patch_cognition_engine import (  # noqa: E402
    PatchCognitionEngine,
    PatchCognitionRegistry,
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
        "run_id": "patch-run-1",
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
        "downstream_driver_graph": {
            "extracted": {
                "vendor_extensions": ["vendor_alpha_ext"],
                "proprietary_hooks": ["vendor_hook_alpha"],
            }
        },
        "downstream_hook_inventory": {
            "inventory": {
                "vendor_tokens": ["qcom_alpha", "msm_alpha"],
                "proprietary_runtime_hooks": ["vendor_hook_alpha"],
                "downstream_only_apis": ["msm_alpha_api"],
            }
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
        "callback_chain_graph": {
            "nodes": [
                {"id": "callback:msm_alpha_startup", "kind": "callback_function"},
                {"id": "callback:q6_alpha_trigger", "kind": "callback_function"},
            ],
            "edges": [],
        },
        "topology_runtime_graph": {
            "nodes": [
                {"id": "fe:alpha_fe0", "kind": "frontend_dai"},
                {"id": "be:alpha_be0", "kind": "backend_dai"},
            ],
            "edges": [
                {
                    "from": "fe:alpha_fe0",
                    "to": "be:alpha_be0",
                    "relation": "dpcm_route",
                    "confidence": 0.8,
                }
            ],
            "normalized_portable_audio_graph": {
                "backend_dai": ["alpha_be0"],
            },
        },
        "runtime_source_correlation": {
            "command_source_correlations": [
                {
                    "runtime_command": "AURA_AMIXER_NAME_SET alpha 1",
                    "correlation_confidence": 0.9,
                    "matched_source_files": ["sound/soc/qcom/alpha.c"],
                },
                {
                    "runtime_command": "AURA_ADB_PUSH /tmp/test.wav /tmp/test.wav",
                    "correlation_confidence": 1.0,
                    "matched_source_files": ["sound/core/pcm_lib.c"],
                },
            ]
        },
        "upstream_equivalence_map": {
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
        "portability_blockers": {
            "summary": {"blocked_unsafe_count": 0, "advisory_count": 1},
        },
    }


def _conversion_artifacts() -> dict:
    return {
        "runtime_portability_analysis": {
            "unsupported_runtime_dependencies": [],
        }
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "replay-fp-patch-1",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _semantic() -> dict:
    return {
        "classification": {
            "primary_classification": "vendor_coupled",
            "scores": {
                "vendor_coupled": 0.7,
                "upstream_friendly": 0.2,
            },
        },
    }


def test_patch_cognition_artifacts_and_determinism(tmp_path: Path) -> None:
    engine = PatchCognitionEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "patch-cognition-v1",
        "runtime_evidence": _runtime_evidence(),
        "structural_artifacts": _structural_artifacts(),
        "conversion_artifacts": _conversion_artifacts(),
        "replay_traces": _replay(),
        "governance_state": _governance(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "semantic_cognition": _semantic(),
        "evidence_references": ["test://patch/cognition"],
        "previous_patch_lineage": [],
    }

    first = engine.analyze(**args).patch_cognition_bundle
    second = engine.analyze(**args).patch_cognition_bundle

    assert first["patch_cognition_fingerprint"] == second["patch_cognition_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "upstream_readiness_report",
        "patch_dependency_graph",
        "subsystem_boundary_map",
        "vendor_contamination_report",
        "runtime_patch_correlation",
        "bisectability_report",
        "api_evolution_trace",
        "patch_series_plan",
    }
    assert required.issubset(set(artifacts.keys()))


def test_patch_cognition_registry_replay(tmp_path: Path) -> None:
    engine = PatchCognitionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="patch-cognition-replay-v1",
        runtime_evidence=_runtime_evidence(),
        structural_artifacts=_structural_artifacts(),
        conversion_artifacts=_conversion_artifacts(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        semantic_cognition=_semantic(),
        evidence_references=["test://patch/replay"],
        previous_patch_lineage=[],
    ).patch_cognition_bundle

    registry = PatchCognitionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="patch-cognition-replay-v1")
    replay_two = registry.replay(lineage_id="patch-cognition-replay-v1")

    assert persisted["lineage_id"] == "patch-cognition-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "upstream_readiness_report.json").exists()
    assert (tmp_path / "ops" / "patch_dependency_graph.json").exists()
    assert (tmp_path / "ops" / "subsystem_boundary_map.json").exists()
    assert (tmp_path / "ops" / "vendor_contamination_report.json").exists()
    assert (tmp_path / "ops" / "runtime_patch_correlation.json").exists()
    assert (tmp_path / "ops" / "bisectability_report.json").exists()
    assert (tmp_path / "ops" / "api_evolution_trace.json").exists()
    assert (tmp_path / "ops" / "patch_series_plan.json").exists()
    assert (tmp_path / "ops" / "deterministic_patch_replay.json").exists()


def test_patch_cognition_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = PatchCognitionEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="patch-cognition-governance-v1",
        runtime_evidence=_runtime_evidence(),
        structural_artifacts=_structural_artifacts(),
        conversion_artifacts=_conversion_artifacts(),
        replay_traces=_replay(),
        governance_state=governance,
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        semantic_cognition=_semantic(),
        evidence_references=["test://patch/governance"],
        previous_patch_lineage=[],
    ).patch_cognition_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["upstream_governance_gate"]["classification"] == "FAIL_CLOSED"


def test_patch_cognition_core_plugin_isolation() -> None:
    src = (SRC_DIR / "aura_sdk/transport/patch_cognition_engine.py").read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".subsystem_descriptor_provider(" in src
    assert ".runtime_conversion_adapter(" in src
    assert ".vendor_api_adapter(" in src
