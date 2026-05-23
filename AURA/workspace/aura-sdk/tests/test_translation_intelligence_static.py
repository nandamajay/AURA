from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.upstream_conversion_planner import (  # noqa: E402
    TranslationIntelligenceRegistry,
    UpstreamConversionPlanner,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _payload() -> dict:
    return {
        "runtime_evidence": {
            "run_id": "run-translation-1",
            "process_success": True,
            "playback_completion": True,
            "playback_runtime_seconds": 25.0,
            "route_fingerprint": "route-fp-1",
            "capabilities": {
                "supports_amixer": "SUPPORTED",
                "supports_tinymix": "SUPPORTED",
            },
            "command_sequence": [
                "resolve_pcm",
                "resolve_backend",
                "validate_route",
            ],
        },
        "topology_cognition": {
            "confidence": {"topology_confidence": 0.8},
            "runtime_route_graph": {
                "runtime_paths": [
                    "fake_target_alpha:fe0->be0",
                ]
            },
            "procedural_route_memory": {
                "stable_pcm_fingerprints": ["pcm-fp-1"],
            },
        },
        "dts_cognition": {
            "backend_frontend_mappings": ["fake_target_alpha:fe0->be0"],
            "qcom_audio_routing": ["fake_target_alpha:pcm0->spkr"],
        },
        "semantic_cognition": {
            "classification": {
                "primary_classification": "partially_portable",
                "scores": {
                    "upstream_friendly": 0.7,
                    "vendor_coupled": 0.2,
                    "governance_risky": 0.1,
                },
            },
            "adapters": {
                "vendor_api": {
                    "semantic_driver": {
                        "downstream_only_apis": ["vendor_alpha_wrap"],
                        "vendor_hooks": ["vendor_hook_alpha"],
                        "wrapper_layers": ["alpha_shim"],
                    }
                },
                "dts": {
                    "semantic_dts": {
                        "vendor_only_nodes": ["fake_target_alpha:vendor_node"],
                    }
                },
            },
        },
        "replay_traces": {
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "replay-fp-translation-1",
        },
        "regression_history": [
            {
                "run_id": "run-translation-1",
                "regression_detected": False,
                "deviations": [],
                "severity": "LOW",
            }
        ],
        "plugin_capability_state": {
            "supported": True,
            "capabilities": {
                "supports_amixer": "SUPPORTED",
                "supports_tinymix": "SUPPORTED",
            },
        },
        "governance_state": {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
    }


def test_semantic_equivalence_validation(tmp_path: Path) -> None:
    planner = UpstreamConversionPlanner(_loader(tmp_path))
    payload = _payload()

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        lineage_id="translation-semantic-v1",
        evidence_references=["test://translation/semantic"],
        previous_migration_lineage=[],
        **payload,
    ).conversion_bundle

    mapping_graph = bundle["artifacts"]["downstream_upstream_mapping_graph"]
    assert mapping_graph["entries"]
    assert 0.0 <= mapping_graph["semantic_equivalence_confidence"] <= 1.0


def test_replay_compatibility_validation(tmp_path: Path) -> None:
    planner = UpstreamConversionPlanner(_loader(tmp_path))
    payload = _payload()
    bundle = planner.analyze(
        target_id="fake_target_alpha",
        lineage_id="translation-replay-v1",
        evidence_references=["test://translation/replay"],
        previous_migration_lineage=[],
        **payload,
    ).conversion_bundle

    registry = TranslationIntelligenceRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    _ = registry.persist(bundle)
    one = registry.replay(lineage_id="translation-replay-v1")
    two = registry.replay(lineage_id="translation-replay-v1")

    assert one["deterministic_replay_fingerprint"] == two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "deterministic_translation_replay.json").exists()


def test_governance_boundary_validation(tmp_path: Path) -> None:
    planner = UpstreamConversionPlanner(_loader(tmp_path))
    payload = _payload()
    payload["governance_state"]["autonomous_patching_allowed"] = True

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        lineage_id="translation-governance-v1",
        evidence_references=["test://translation/governance"],
        previous_migration_lineage=[],
        **payload,
    ).conversion_bundle

    confidence = bundle["artifacts"]["upstream_conversion_confidence"]
    runtime_report = bundle["artifacts"]["runtime_portability_analysis"]

    assert confidence["classification"] == "FAIL_CLOSED"
    assert runtime_report["governance_classification"] == "FAIL_CLOSED"
    assert "autonomous_code_rewrite" in runtime_report["transformation_classes"]["forbidden_autonomous_transformations"]


def test_topology_translation_validation(tmp_path: Path) -> None:
    planner = UpstreamConversionPlanner(_loader(tmp_path))
    payload = _payload()

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        lineage_id="translation-topology-v1",
        evidence_references=["test://translation/topology"],
        previous_migration_lineage=[],
        **payload,
    ).conversion_bundle

    report = bundle["artifacts"]["topology_translation_report"]
    assert report["fe_be_route_equivalence"]
    assert report["pcm_dpcm_graph_normalization"]["normalized"] is True
    assert report["portable_runtime_topology_model"]["normalized_routes"]


def test_regression_drift_detection_validation(tmp_path: Path) -> None:
    planner = UpstreamConversionPlanner(_loader(tmp_path))
    payload = _payload()
    payload["runtime_evidence"]["playback_runtime_seconds"] = 40.0
    payload["runtime_evidence"]["route_fingerprint"] = "runtime-route-a"
    payload["runtime_evidence"]["command_sequence"] = ["resolve_pcm", "unexpected_step_only"]
    payload["regression_history"] = [
        {
            "run_id": "run-translation-drift",
            "regression_detected": True,
            "severity": "MEDIUM",
            "deviations": [
                {
                    "code": "runtime_latency_drift",
                    "severity": "MEDIUM",
                    "details": "runtime drift observed",
                }
            ],
        }
    ]

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        lineage_id="translation-drift-v1",
        evidence_references=["test://translation/drift"],
        previous_migration_lineage=[],
        **payload,
    ).conversion_bundle

    lineage = bundle["artifacts"]["migration_lineage"]
    drift_types = {row["type"] for row in lineage["drifts"]}

    assert "timing_drift" in drift_types
    assert "sequencing_drift" in drift_types
    assert "runtime_latency_drift" in drift_types


def test_translation_core_plugin_isolation() -> None:
    planner_src = (SRC_DIR / "aura_sdk/transport/upstream_conversion_planner.py").read_text(encoding="utf-8").lower()
    assert "if target ==" not in planner_src
    assert "rb3" not in planner_src
    assert ".downstream_upstream_adapter(" in planner_src
    assert ".topology_translation_adapter(" in planner_src
    assert ".runtime_conversion_adapter(" in planner_src
