from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.downstream_driver_ingestion import ingest_downstream_driver_tree  # noqa: E402
from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.real_downstream_conversion_planner import (  # noqa: E402
    RealDownstreamConversionPlanner,
    RealDownstreamConversionRegistry,
)
from aura_sdk.transport.topology_reconstruction_cognition import (  # noqa: E402
    reconstruct_topology_runtime_graph,
)
from aura_sdk.transport.upstream_semantic_matcher import match_upstream_semantics  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _real_downstream_root() -> Path:
    return REPO_ROOT.parents[2] / "evidence/wcd937x_real_study_20260519_062557/repos/downstream-audio-kernel-ar"


def _real_upstream_root() -> Path:
    return REPO_ROOT.parents[2] / "evidence/wcd937x_real_study_20260519_062557/repos/linux-upstream-v6.18"


def _fixture_downstream(tmp_path: Path) -> Path:
    root = tmp_path / "downstream"
    (root / "asoc").mkdir(parents=True, exist_ok=True)
    (root / "asoc" / "audio_machine.c").write_text(
        """
        #include <sound/soc.h>
        #include <linux/clk.h>
        static struct snd_soc_ops msm_common_be_ops = { 0 };
        static struct snd_soc_dai_link msm_test_fe_dai_links[] = { 0 };
        static struct snd_soc_dai_link msm_test_be_dai_links[] = { 0 };
        static const struct snd_soc_dapm_route msm_audio_routes[] = { 0 };
        static const char *name = "MultiMedia1 Playback";
        static int qcom_audio_route_enable(void) { return 0; }
        static int vendor_hook_audio_boost(void) { msleep(10); return 0; }
        """,
        encoding="utf-8",
    )
    return root


def _fixture_upstream(tmp_path: Path) -> Path:
    root = tmp_path / "upstream"
    (root / "sound/soc").mkdir(parents=True, exist_ok=True)
    (root / "include/sound").mkdir(parents=True, exist_ok=True)
    (root / "drivers/soundwire").mkdir(parents=True, exist_ok=True)
    (root / "sound/soc/soc-core.c").write_text(
        """
        struct snd_soc_component { int dummy; };
        struct snd_soc_dai_link { int dummy; };
        struct snd_soc_ops { int dummy; };
        int snd_soc_dpcm_runtime(void) { return 0; }
        """,
        encoding="utf-8",
    )
    (root / "include/sound/soc-dapm.h").write_text("struct snd_soc_dapm_widget { int x; };\n", encoding="utf-8")
    (root / "drivers/soundwire/bus.c").write_text("int soundwire_bus_init(void) { return 0; }\n", encoding="utf-8")
    return root


def test_downstream_parser_validation_with_real_samples_or_fixture(tmp_path: Path) -> None:
    real_root = _real_downstream_root()
    source = real_root if real_root.exists() else _fixture_downstream(tmp_path)

    result = ingest_downstream_driver_tree(
        target_id="RB3Gen2",
        downstream_root=source,
        adapter_payload={},
        evidence_references=["test://downstream/source"],
        max_files=2000,
    )

    graph = result.downstream_driver_graph
    assert graph["graph_name"] == "downstream_driver_graph"
    assert graph["scanned_files"]["total"] > 0
    assert 0.0 <= result.ingestion_confidence <= 1.0

    extracted = graph["extracted"]
    assert extracted["dai_links"]["all"] or extracted["ops_structures"]


def test_topology_reconstruction_validation(tmp_path: Path) -> None:
    down_root = _fixture_downstream(tmp_path)
    ingestion = ingest_downstream_driver_tree(
        target_id="RB3Gen2",
        downstream_root=down_root,
        adapter_payload={},
        evidence_references=[],
    )

    topology = reconstruct_topology_runtime_graph(
        target_id="RB3Gen2",
        downstream_driver_graph=ingestion.downstream_driver_graph,
        runtime_evidence={
            "process_success": True,
            "playback_completion": True,
            "playback_runtime_seconds": 25.0,
            "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
        },
        adapter_payload={},
    )

    payload = topology.topology_runtime_graph
    assert payload["graph_name"] == "topology_runtime_graph"
    assert payload["normalized_portable_audio_graph"]["frontend_dai"]
    assert payload["normalized_portable_audio_graph"]["backend_dai"]
    assert 0.0 <= topology.topology_reconstruction_confidence <= 1.0


def test_semantic_mapping_validation(tmp_path: Path) -> None:
    down_root = _fixture_downstream(tmp_path)
    up_root = _real_upstream_root()
    if not up_root.exists():
        up_root = _fixture_upstream(tmp_path)

    ingestion = ingest_downstream_driver_tree(
        target_id="RB3Gen2",
        downstream_root=down_root,
        adapter_payload={},
        evidence_references=[],
    )

    mapping = match_upstream_semantics(
        target_id="RB3Gen2",
        upstream_root=up_root,
        downstream_driver_graph=ingestion.downstream_driver_graph,
        adapter_payload={
            "upstream_equivalent_hints": {
                "prefix": {
                    "msm_": "snd_soc_component",
                    "qcom_": "snd_soc_qcom",
                }
            }
        },
        evidence_references=["test://upstream/reference"],
    )

    payload = mapping.upstream_equivalence_map
    assert payload["graph_name"] == "upstream_equivalence_map"
    assert payload["entries"]
    assert 0.0 <= mapping.semantic_equivalence_confidence <= 1.0


def test_replay_compatibility_validation(tmp_path: Path) -> None:
    planner = RealDownstreamConversionPlanner(_loader(tmp_path))
    down_root = _fixture_downstream(tmp_path)
    up_root = _fixture_upstream(tmp_path)

    analyze_args = {
        "target_id": "fake_target_alpha",
        "downstream_root": down_root,
        "upstream_root": up_root,
        "runtime_evidence": {
            "run_id": "run-real-ingest-1",
            "process_success": True,
            "playback_completion": True,
            "playback_runtime_seconds": 25.0,
            "expected_runtime_seconds": 25.0,
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "fp-replay-1",
            "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
            "capabilities": {"supports_amixer": "SUPPORTED"},
            "route_fingerprint": "route-fp-1",
        },
        "governance_state": {
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
        "replay_contract": {
            "sequence_contract": [
                "execution_ordering",
                "timing_windows",
                "route_fingerprint",
                "pcm_signature",
                "evidence_sequence",
                "cleanup_sequence",
            ]
        },
        "lineage_id": "real-ingest-replay-v1",
        "evidence_references": ["test://real_ingest/replay"],
        "regression_history": [],
        "previous_migration_lineage": [],
    }

    one = planner.analyze(**analyze_args).conversion_bundle
    two = planner.analyze(**analyze_args).conversion_bundle

    assert one["conversion_fingerprint"] == two["conversion_fingerprint"]

    registry = RealDownstreamConversionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    _ = registry.persist(one)
    replay_one = registry.replay(lineage_id="real-ingest-replay-v1")
    replay_two = registry.replay(lineage_id="real-ingest-replay-v1")

    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_governance_boundary_validation(tmp_path: Path) -> None:
    planner = RealDownstreamConversionPlanner(_loader(tmp_path))
    down_root = _fixture_downstream(tmp_path)
    up_root = _fixture_upstream(tmp_path)

    bundle = planner.analyze(
        target_id="fake_target_alpha",
        downstream_root=down_root,
        upstream_root=up_root,
        runtime_evidence={
            "process_success": True,
            "playback_completion": True,
            "playback_runtime_seconds": 25.0,
            "expected_runtime_seconds": 25.0,
            "deterministic_event_ordering": True,
            "deterministic_replay_fingerprint": "fp-replay-1",
            "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
            "capabilities": {"supports_amixer": "SUPPORTED"},
            "route_fingerprint": "route-fp-1",
        },
        governance_state={
            "fail_closed_posture": True,
            "autonomous_patching_allowed": True,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
        },
        replay_contract={
            "sequence_contract": [
                "execution_ordering",
                "timing_windows",
                "route_fingerprint",
                "pcm_signature",
                "evidence_sequence",
                "cleanup_sequence",
            ]
        },
        lineage_id="real-ingest-governance-v1",
        evidence_references=["test://real_ingest/governance"],
        regression_history=[],
        previous_migration_lineage=[],
    ).conversion_bundle

    boundaries = bundle["artifacts"]["governance_conversion_boundaries"]
    plan = bundle["artifacts"]["deterministic_conversion_plan"]

    assert boundaries["classification"] == "FAIL_CLOSED"
    assert plan["classification"] == "FAIL_CLOSED"


def test_real_ingestion_core_plugin_isolation() -> None:
    core = (SRC_DIR / "aura_sdk/transport/real_downstream_conversion_planner.py").read_text(encoding="utf-8").lower()
    assert "if target ==" not in core
    assert "rb3" not in core
    assert ".downstream_ingestion_adapter(" in core
    assert ".upstream_match_adapter(" in core
    assert ".topology_reconstruction_adapter(" in core
