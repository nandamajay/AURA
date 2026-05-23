from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.semantic_confidence_engine import build_semantic_confidence_report  # noqa: E402
from aura_sdk.transport.semantic_entity_extractor import extract_semantic_entities  # noqa: E402
from aura_sdk.transport.semantic_equivalence_mapper import build_semantic_equivalence_map  # noqa: E402
from aura_sdk.transport.semantic_governance_boundary import evaluate_semantic_governance_boundary  # noqa: E402
from aura_sdk.transport.semantic_html_parser import parse_semantic_html  # noqa: E402
from aura_sdk.transport.semantic_ontology_builder import build_semantic_ontology  # noqa: E402
from aura_sdk.transport.semantic_portability_reasoning import build_semantic_portability_rules  # noqa: E402
from aura_sdk.transport.semantic_relationship_graph import build_semantic_relationship_map  # noqa: E402
from aura_sdk.transport.semantic_replay_compatibility import build_semantic_replay_compatibility  # noqa: E402
from aura_sdk.transport.semantic_runtime_advisory import SemanticRuntimeAdvisoryEngine  # noqa: E402
from aura_sdk.transport.semantic_traceability_engine import (  # noqa: E402
    KernelSemanticKnowledgeRegistry,
    build_semantic_traceability_graph,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "sim_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _fixture_html(tmp_path: Path) -> Path:
    path = tmp_path / "hub.html"
    path.write_text(
        """
        <html>
          <head><title>Qualcomm Audio Kernel Knowledge Hub</title></head>
          <body>
            <h1>ALSA ASoC Topology</h1>
            <p>ALSA snd_pcm lifecycle open hw_params prepare trigger close and DAPM route widget semantics.</p>
            <h2>FE BE DPCM</h2>
            <p>Frontend FE links map to Backend BE links via snd_soc_dpcm and snd_soc_dai_link.</p>
            <h2>SoundWire and Qualcomm</h2>
            <p>SoundWire swr sdw qcom msm_ lpass wcd apr_ gpr_ with downstream only vendor hook workaround mapping upstream snd_soc_component.</p>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    return path


def _build_bundle(tmp_path: Path) -> dict:
    html_path = _fixture_html(tmp_path)
    source_id = "qcom_audio_knowledge_hub"
    source_version = "v16-test"

    parsed = parse_semantic_html(source_path=html_path, source_id=source_id, source_version=source_version)
    extracted = extract_semantic_entities(
        source_id=source_id,
        source_version=source_version,
        parsed_document=parsed.parsed_document,
        adapter_payload={},
    )
    relationships = build_semantic_relationship_map(
        source_id=source_id,
        source_version=source_version,
        semantic_entity_graph=extracted.semantic_entity_graph,
        parsed_document=parsed.parsed_document,
    )
    ontology = build_semantic_ontology(
        source_id=source_id,
        source_version=source_version,
        semantic_entity_graph=extracted.semantic_entity_graph,
        semantic_relationship_map=relationships.semantic_relationship_map,
    )
    governance = evaluate_semantic_governance_boundary(
        governance_state={
            "fail_closed_posture": True,
            "autonomous_patching_allowed": False,
            "autonomous_topology_rewrite_allowed": False,
            "autonomous_upstream_generation_allowed": False,
            "autonomous_runtime_mutation_allowed": False,
        },
        requested_actions=["analyze", "lookup", "recommend", "replay", "trace"],
    )
    equivalence = build_semantic_equivalence_map(
        source_id=source_id,
        source_version=source_version,
        semantic_entity_graph=extracted.semantic_entity_graph,
        adapter_payload={},
    )
    portability = build_semantic_portability_rules(
        source_id=source_id,
        source_version=source_version,
        semantic_entity_graph=extracted.semantic_entity_graph,
        semantic_equivalence_map=equivalence.semantic_equivalence_map,
        semantic_relationship_map=relationships.semantic_relationship_map,
        adapter_payload={},
    )
    replay = build_semantic_replay_compatibility(
        source_id=source_id,
        source_version=source_version,
        artifacts={
            "semantic_entity_graph": extracted.semantic_entity_graph,
            "semantic_relationship_map": relationships.semantic_relationship_map,
            "semantic_ontology": ontology.semantic_ontology,
            "semantic_portability_rules": portability.semantic_portability_rules,
            "semantic_equivalence_map": equivalence.semantic_equivalence_map,
        },
        governance_boundary=governance.governance_boundary,
    )
    confidence = build_semantic_confidence_report(
        source_id=source_id,
        source_version=source_version,
        semantic_entity_graph=extracted.semantic_entity_graph,
        semantic_relationship_map=relationships.semantic_relationship_map,
        semantic_portability_rules=portability.semantic_portability_rules,
        semantic_equivalence_map=equivalence.semantic_equivalence_map,
        semantic_replay_compatibility=replay.semantic_replay_compatibility,
        semantic_governance_boundary=governance.governance_boundary,
    )
    traceability = build_semantic_traceability_graph(
        source_id=source_id,
        source_version=source_version,
        source_path=str(html_path.resolve()),
        source_sha256=str(parsed.parsed_document.get("source_sha256", "")),
        lineage_id="lineage-semantic-v1",
        artifacts={
            "semantic_entity_graph": extracted.semantic_entity_graph,
            "semantic_relationship_map": relationships.semantic_relationship_map,
            "semantic_ontology": ontology.semantic_ontology,
            "semantic_portability_rules": portability.semantic_portability_rules,
            "semantic_equivalence_map": equivalence.semantic_equivalence_map,
            "semantic_confidence_report": confidence.semantic_confidence_report,
            "semantic_replay_compatibility": replay.semantic_replay_compatibility,
            "semantic_governance_boundary": governance.governance_boundary,
        },
    )

    return {
        "source_id": source_id,
        "source_version": source_version,
        "source_sha256": str(parsed.parsed_document.get("source_sha256", "")),
        "lineage_id": "lineage-semantic-v1",
        "artifacts": {
            "semantic_entity_graph": extracted.semantic_entity_graph,
            "semantic_relationship_map": relationships.semantic_relationship_map,
            "semantic_ontology": ontology.semantic_ontology,
            "semantic_portability_rules": portability.semantic_portability_rules,
            "semantic_equivalence_map": equivalence.semantic_equivalence_map,
            "semantic_runtime_advisories": {
                "schema_version": "1.0",
                "report_name": "semantic_runtime_advisories",
                "classification": "PASS",
                "advisory_only": True,
                "runtime_state_mutation_allowed": False,
                "deterministic_fingerprint": stable_fingerprint({"x": 1}),
            },
            "semantic_traceability_graph": traceability.semantic_traceability_graph,
            "semantic_confidence_report": confidence.semantic_confidence_report,
        },
        "semantic_knowledge_fingerprint": stable_fingerprint({"bundle": "semantic"}),
        "evidence_references": ["source://hub", "artifact://semantic_entity_graph"],
    }


def test_semantic_html_parser_deterministic(tmp_path: Path) -> None:
    html_path = _fixture_html(tmp_path)
    one = parse_semantic_html(source_path=html_path, source_id="hub", source_version="v16")
    two = parse_semantic_html(source_path=html_path, source_id="hub", source_version="v16")

    assert one.deterministic_fingerprint == two.deterministic_fingerprint
    assert one.parsed_document["section_count"] >= 1


def test_entity_extraction_required_categories(tmp_path: Path) -> None:
    html_path = _fixture_html(tmp_path)
    parsed = parse_semantic_html(source_path=html_path, source_id="hub", source_version="v16")
    result = extract_semantic_entities(
        source_id="hub",
        source_version="v16",
        parsed_document=parsed.parsed_document,
        adapter_payload={},
    )

    categories = set(result.semantic_entity_graph["entity_categories"].keys())
    required = {
        "alsa_entities",
        "asoc_entities",
        "fe_be_topology_concepts",
        "dpcm_concepts",
        "dapm_graph_semantics",
        "pcm_lifecycle_semantics",
        "soundwire_concepts",
        "qcom_downstream_abstractions",
        "upstream_equivalence_mappings",
        "runtime_lifecycle_relationships",
        "known_portability_blockers",
        "migration_equivalence_rules",
        "vendor_workaround_patterns",
        "kernel_subsystem_vocabulary_graph",
    }
    assert required.issubset(categories)


def test_relationship_ontology_and_confidence_generation(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)

    assert bundle["artifacts"]["semantic_relationship_map"]["graph_name"] == "semantic_relationship_map"
    assert bundle["artifacts"]["semantic_ontology"]["ontology_name"] == "kernel_semantic_ontology"
    assert bundle["artifacts"]["semantic_confidence_report"]["report_name"] == "semantic_confidence_report"


def test_governance_boundary_fail_closed_enforced() -> None:
    report = evaluate_semantic_governance_boundary(
        governance_state={
            "fail_closed_posture": True,
            "autonomous_patching_allowed": True,
        },
        requested_actions=["analyze", "autonomous_runtime_mutation"],
    )

    payload = report.governance_boundary
    assert payload["classification"] == "FAIL_CLOSED"
    assert payload["runtime_mutation_permitted"] is False


def test_runtime_advisory_is_advisory_only_and_plugin_safe(tmp_path: Path) -> None:
    loader = _loader(tmp_path)
    engine = SemanticRuntimeAdvisoryEngine(plugin_loader=loader)

    result = engine.analyze(
        target_id="fake_target_alpha",
        source_id="hub",
        source_version="v16",
        runtime_evidence={
            "run_id": "run-1",
            "process_success": True,
            "playback_completion": True,
            "classification": "PASS",
        },
        semantic_entity_graph={
            "entity_categories": {
                "runtime_lifecycle_relationships": ["start", "stop"],
            }
        },
        semantic_portability_rules={
            "classification": "PASS",
            "rules": {
                "blocked_unsafe": [],
            },
        },
        semantic_governance_boundary={
            "classification": "PASS",
        },
    )

    payload = result.semantic_runtime_advisories
    assert payload["advisory_only"] is True
    assert payload["runtime_state_mutation_allowed"] is False
    assert payload["runtime_execution_permitted_from_semantics"] is False
    assert result.adapter_payload.get("provider", "").endswith("semantic_knowledge_adapter")


def test_traceability_registry_replay_deterministic(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    registry = KernelSemanticKnowledgeRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="lineage-semantic-v1")
    replay_two = registry.replay(lineage_id="lineage-semantic-v1")

    assert persisted["lineage_id"] == "lineage-semantic-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "semantic_traceability_graph.json").exists()


def test_semantic_runtime_advisory_core_is_target_agnostic() -> None:
    src = (SRC_DIR / "aura_sdk/transport/semantic_runtime_advisory.py").read_text(encoding="utf-8").lower()
    assert "if target ==" not in src
    assert ".semantic_knowledge_adapter(" in src
