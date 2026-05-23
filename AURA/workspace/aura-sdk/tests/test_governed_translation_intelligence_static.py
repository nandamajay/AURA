from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.governed_translation_intelligence import (  # noqa: E402
    GovernedTranslationIntelligenceEngine,
    GovernedTranslationIntelligenceRegistry,
)
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
        "runtime_truth_graph": {
            "classification": "PASS",
            "deterministic_fingerprint": "runtime-truth-fp",
        },
        "pcm_lifecycle_trace": {
            "transitions": [
                {"stage": "OPEN", "timestamp_ms": 1000.0},
                {"stage": "PREPARE", "timestamp_ms": 1010.0},
                {"stage": "START", "timestamp_ms": 1020.0},
                {"stage": "STOP", "timestamp_ms": 1200.0},
                {"stage": "CLOSE", "timestamp_ms": 1210.0},
            ]
        },
    }


def _topology_artifacts() -> dict:
    return {
        "topology_runtime_graph": {
            "nodes": [{"id": "FE0"}, {"id": "BE0"}],
            "edges": [{"from": "FE0", "to": "BE0"}],
        },
        "dts_topology_graph": {
            "backend_frontend_mappings": ["FE0->BE0"],
        },
    }


def _semantic_artifacts() -> dict:
    return {
        "semantic_entity_graph": {
            "nodes": [
                {"id": "n1", "label": "pcm_open"},
                {"id": "n2", "label": "dapm_route_enable"},
                {"id": "n3", "label": "swr_port_activate"},
                {"id": "n4", "label": "vendor_callback_x"},
            ]
        },
        "semantic_confidence_report": {
            "classification": {
                "scores": {
                    "upstream_friendly": 0.78,
                }
            }
        },
        "semantic_cognition": {
            "classification": {
                "scores": {
                    "upstream_friendly": 0.78,
                }
            }
        },
    }


def _structural_artifacts() -> dict:
    return {
        "downstream_driver_graph": {
            "downstream_root": "/kernel/downstream",
            "extracted": {
                "ops_structures": ["pcm_open", "pcm_prepare", "pcm_start", "pcm_stop", "pcm_close"],
                "vendor_extensions": ["vendor_callback_x"],
                "proprietary_runtime_hooks": ["vendor_callback_x"],
                "routing_structures": ["dapm_route_enable"],
                "pcm_dpcm_paths": ["FE0->BE0"],
                "dependencies": {
                    "soundwire": ["swr_port_activate"],
                },
                "dai_links": {
                    "all": ["fe0_be0_dai_link"],
                },
            },
        },
        "structural_graph": {
            "nodes": [{"id": "snd_soc_ops"}],
            "edges": [{"from": "snd_soc_ops", "to": "snd_soc_component"}],
        },
    }


def _translation_artifacts() -> dict:
    return {
        "downstream_upstream_mapping_graph": {
            "entries": [
                {
                    "downstream_construct": "pcm_open",
                    "upstream_equivalent": "snd_pcm_open_substream",
                    "equivalence_confidence": 0.88,
                },
                {
                    "downstream_construct": "dapm_route_enable",
                    "upstream_equivalent": "snd_soc_dapm_add_routes",
                    "equivalence_confidence": 0.86,
                },
                {
                    "downstream_construct": "swr_port_activate",
                    "upstream_equivalent": "sdw_stream_add_master",
                    "equivalence_confidence": 0.84,
                },
                {
                    "downstream_construct": "vendor_callback_x",
                    "upstream_equivalent": "snd_soc_component_driver.ops",
                    "equivalence_confidence": 0.82,
                },
                {
                    "downstream_construct": "pcm_prepare",
                    "upstream_equivalent": "snd_pcm_prepare",
                    "equivalence_confidence": 0.86,
                },
                {
                    "downstream_construct": "pcm_start",
                    "upstream_equivalent": "snd_pcm_start",
                    "equivalence_confidence": 0.86,
                },
                {
                    "downstream_construct": "pcm_stop",
                    "upstream_equivalent": "snd_pcm_stop",
                    "equivalence_confidence": 0.84,
                },
                {
                    "downstream_construct": "pcm_close",
                    "upstream_equivalent": "snd_pcm_release_substream",
                    "equivalence_confidence": 0.83,
                },
            ]
        },
        "upstream_equivalence_map": {
            "entries": [
                {
                    "downstream_construct": "pcm_open",
                    "upstream_equivalent": "snd_pcm_open_substream",
                    "equivalence_confidence": 0.88,
                },
                {
                    "downstream_construct": "dapm_route_enable",
                    "upstream_equivalent": "snd_soc_dapm_add_routes",
                    "equivalence_confidence": 0.86,
                },
                {
                    "downstream_construct": "swr_port_activate",
                    "upstream_equivalent": "sdw_stream_add_master",
                    "equivalence_confidence": 0.84,
                },
                {
                    "downstream_construct": "vendor_callback_x",
                    "upstream_equivalent": "snd_soc_component_driver.ops",
                    "equivalence_confidence": 0.82,
                },
            ]
        },
        "topology_translation_report": {
            "translation_confidence": 0.85,
            "fe_be_route_equivalence": [
                {
                    "downstream_route": "FE0->BE0",
                    "normalized_route": "FE0_BE0",
                    "equivalence": "MATCH",
                }
            ],
        },
        "runtime_portability_analysis": {
            "runtime_portability_score": 0.88,
            "runtime_portability_blockers": [],
            "unsupported_runtime_dependencies": [],
        },
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
        "deterministic_replay_fingerprint": "translation-replay-fp",
    }


def test_translation_cognition_static_outputs(tmp_path: Path) -> None:
    engine = GovernedTranslationIntelligenceEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="translation-session-a",
        lineage_id="translation-lineage-a",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        structural_artifacts=_structural_artifacts(),
        translation_artifacts=_translation_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://governed_translation/static"],
        previous_translation_history=[],
    ).translation_bundle

    artifacts = bundle["artifacts"]
    required = {
        "upstream_translation_plan",
        "api_replacement_map",
        "unsupported_vendor_constructs",
        "lifecycle_translation_graph",
        "runtime_equivalence_validation",
        "translation_confidence_report",
        "deterministic_translation_replay",
    }
    assert required.issubset(set(artifacts.keys()))
    assert artifacts["upstream_translation_plan"]["ast_aware_conversion_plan"]["ast_entity_counts"]["ops_structures"] > 0
    assert artifacts["unsupported_vendor_constructs"]["summary"]["unsupported_count"] == 0


def test_runtime_equivalence_validation_fail_closed(tmp_path: Path) -> None:
    engine = GovernedTranslationIntelligenceEngine(_loader(tmp_path))

    runtime = _runtime_artifacts()
    runtime["runtime_truth_graph"]["classification"] = "FAIL_CLOSED"

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="translation-session-b",
        lineage_id="translation-lineage-b",
        runtime_artifacts=runtime,
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        structural_artifacts=_structural_artifacts(),
        translation_artifacts=_translation_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://governed_translation/runtime_equivalence"],
        previous_translation_history=[],
    ).translation_bundle

    runtime_validation = bundle["artifacts"]["runtime_equivalence_validation"]
    assert runtime_validation["classification"] == "FAIL_CLOSED"
    assert runtime_validation["fail_closed_justification"] == "runtime_truth_fail_closed"


def test_governance_fail_closed_translation(tmp_path: Path) -> None:
    engine = GovernedTranslationIntelligenceEngine(_loader(tmp_path))

    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="translation-session-c",
        lineage_id="translation-lineage-c",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        structural_artifacts=_structural_artifacts(),
        translation_artifacts=_translation_artifacts(),
        governance_state=governance,
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://governed_translation/governance"],
        previous_translation_history=[],
    ).translation_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["translation_confidence_report"]["classification"] == "FAIL_CLOSED"


def test_translation_replay_lineage_persistence(tmp_path: Path) -> None:
    engine = GovernedTranslationIntelligenceEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="translation-session-d",
        lineage_id="translation-lineage-d",
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        structural_artifacts=_structural_artifacts(),
        translation_artifacts=_translation_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://governed_translation/replay"],
        previous_translation_history=[],
    ).translation_bundle

    registry = GovernedTranslationIntelligenceRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="translation-lineage-d")
    replay_two = registry.replay(lineage_id="translation-lineage-d")

    assert persisted["lineage_id"] == "translation-lineage-d"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "upstream_translation_plan.json").exists()
    assert (tmp_path / "ops" / "api_replacement_map.json").exists()
    assert (tmp_path / "ops" / "unsupported_vendor_constructs.json").exists()
    assert (tmp_path / "ops" / "lifecycle_translation_graph.json").exists()
    assert (tmp_path / "ops" / "runtime_equivalence_validation.json").exists()
    assert (tmp_path / "ops" / "translation_confidence_report.json").exists()
    assert (tmp_path / "ops" / "deterministic_translation_replay.json").exists()


def test_governed_translation_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/governed_translation_intelligence.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_conversion_adapter(" in src
    assert ".topology_translation_adapter(" in src
    assert ".downstream_upstream_adapter(" in src
