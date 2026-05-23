from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.semantic_cognition import SemanticCognitionEngine  # noqa: E402
from aura_sdk.transport.semantic_fingerprint import build_vendor_dependency_fingerprint  # noqa: E402
from aura_sdk.transport.semantic_registry import SemanticCognitionRegistry  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def test_plugin_semantic_isolation_no_target_specific_core_branching() -> None:
    core = (SRC_DIR / "aura_sdk/transport/semantic_cognition.py").read_text(encoding="utf-8").lower()
    assert "if target ==" not in core
    assert "rb3" not in core
    assert ".dts_adapter(" in core
    assert ".vendor_api_adapter(" in core


def test_dts_cognition_via_plugin_adapter(tmp_path: Path) -> None:
    engine = SemanticCognitionEngine(_loader(tmp_path))
    result = engine.analyze(
        target_id="fake_target_alpha",
        entry_dts=None,
        driver_context="",
        static_context={},
        replay_compatibility="FULL",
        evidence_references=["sim://alpha/dts"],
        governance_state={"fail_closed_posture": True},
        lineage_id="semantic-alpha",
    ).semantic_bundle

    dts_semantic = result["adapters"]["dts"]["semantic_dts"]
    assert dts_semantic["overlay_hierarchy"]
    assert dts_semantic["fe_be_route_topology"]
    assert "dts_topology_graph" in result["artifacts"]


def test_vendor_dependency_fingerprint_and_classification(tmp_path: Path) -> None:
    engine = SemanticCognitionEngine(_loader(tmp_path))
    result = engine.analyze(
        target_id="degraded_target_gamma",
        entry_dts=None,
        driver_context="vendor_hook gamma_vendor_api shim codec",
        static_context={},
        replay_compatibility="INCOMPATIBLE",
        evidence_references=["sim://gamma/driver"],
        governance_state={"fail_closed_posture": True},
        lineage_id="semantic-gamma",
    ).semantic_bundle

    fp = build_vendor_dependency_fingerprint(
        target_id="degraded_target_gamma",
        dts_semantics=result["adapters"]["dts"]["semantic_dts"],
        driver_semantics=result["adapters"]["vendor_api"]["semantic_driver"],
    )
    assert fp.fingerprint
    assert result["classification"]["primary_classification"] in {
        "vendor_coupled",
        "governance_risky",
        "replay_sensitive",
        "topology_sensitive",
        "partially_portable",
        "upstream_friendly",
    }


def test_semantic_persistence_and_replay_determinism(tmp_path: Path) -> None:
    engine = SemanticCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_beta",
        entry_dts=None,
        driver_context="vendor_hook_beta beta_shim",
        static_context={},
        replay_compatibility="PARTIAL",
        evidence_references=["sim://beta/semantic"],
        governance_state={"fail_closed_posture": True},
        lineage_id="semantic-beta",
    ).semantic_bundle

    registry_path = tmp_path / "aura_registry.json"
    output_dir = tmp_path / "ops"
    store = SemanticCognitionRegistry(cognition_registry_path=registry_path, output_dir=output_dir)

    persisted = store.persist(bundle)
    replay_one = store.replay(lineage_id="semantic-beta")
    replay_two = store.replay(lineage_id="semantic-beta")

    assert persisted["lineage_id"] == "semantic-beta"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (output_dir / "downstream_semantic_graph.json").exists()
    assert (output_dir / "semantic_confidence_report.json").exists()


def test_semantic_registry_lineage_and_evidence_refs(tmp_path: Path) -> None:
    engine = SemanticCognitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        entry_dts=None,
        driver_context="",
        static_context={},
        replay_compatibility="FULL",
        evidence_references=["sim://alpha/evidence", "sim://alpha/dts"],
        governance_state={"fail_closed_posture": True},
        lineage_id="semantic-lineage-1",
    ).semantic_bundle

    registry_path = tmp_path / "registry.json"
    store = SemanticCognitionRegistry(cognition_registry_path=registry_path, output_dir=tmp_path / "ops")
    _ = store.persist(bundle)

    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    semantic_state = payload.get("semantic_cognition", {})
    history = semantic_state.get("history", [])
    assert history
    assert history[-1]["lineage_id"] == "semantic-lineage-1"
    assert "sim://alpha/evidence" in history[-1]["evidence_references"]
