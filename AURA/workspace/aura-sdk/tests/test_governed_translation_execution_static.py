from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.governed_translation_execution import (  # noqa: E402
    GovernedTranslationExecutionEngine,
    GovernedTranslationExecutionRegistry,
    _replace_identifier_tokens,
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
        }
    }


def _replay_traces() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "governed-execution-replay-fp",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def _source_snapshots() -> dict[str, str]:
    return {
        "sound/soc/vendor/test.c": "\n".join(
            [
                "static int vendor_callback_x(void)",
                "{",
                "    int a = vendor_macro;",
                "    // vendor_callback_x should stay in comment",
                "    const char *s = \"vendor_macro in string\";",
                "    return a;",
                "}",
                "",
            ]
        )
    }


def _translation_artifacts(*, runtime_equivalent: bool = True, unsupported_count: int = 0) -> dict:
    return {
        "upstream_translation_plan": {
            "classification": "PASS",
            "ast_aware_conversion_plan": {
                "stages": [
                    {"stage_id": "phase_pcm_lifecycle_translation"},
                    {"stage_id": "phase_dapm_route_equivalence"},
                    {"stage_id": "phase_soundwire_mapping"},
                    {"stage_id": "phase_vendor_callback_abstraction"},
                ]
            },
        },
        "api_replacement_map": {
            "replacements": [
                {
                    "downstream_construct": "vendor_callback_x",
                    "upstream_replacement": "snd_soc_component_open",
                    "candidate_confidence": 0.92,
                    "runtime_safe": True,
                    "evidence_sources": ["test://mapping/callback"],
                },
                {
                    "downstream_construct": "vendor_macro",
                    "upstream_replacement": "snd_soc_component_macro",
                    "candidate_confidence": 0.89,
                    "runtime_safe": True,
                    "evidence_sources": ["test://mapping/macro"],
                },
            ]
        },
        "unsupported_vendor_constructs": {
            "classification": "PASS" if unsupported_count == 0 else "FAIL_CLOSED",
            "summary": {"unsupported_count": int(unsupported_count)},
        },
        "runtime_equivalence_validation": {
            "classification": "PASS",
            "candidate_validations": [
                {
                    "downstream_construct": "vendor_callback_x",
                    "runtime_equivalent": bool(runtime_equivalent),
                    "validation_confidence": 0.85,
                    "blocking_runtime_reasons": ["callback_unstable"] if not runtime_equivalent else [],
                },
                {
                    "downstream_construct": "vendor_macro",
                    "runtime_equivalent": bool(runtime_equivalent),
                    "validation_confidence": 0.82,
                    "blocking_runtime_reasons": ["macro_unstable"] if not runtime_equivalent else [],
                },
            ],
        },
        "translation_confidence_report": {
            "classification": "PASS",
            "translation_confidence": 0.93,
            "fail_closed_justification": "",
        },
    }


def test_ast_identifier_replacement_comment_and_string_safe() -> None:
    code = "\n".join(
        [
            "int vendor_macro = 0;",
            "// vendor_macro in comment",
            "const char *s = \"vendor_macro in string\";",
            "char c = 'x';",
            "",
        ]
    )
    replaced, count = _replace_identifier_tokens(code, "vendor_macro", "snd_soc_component_macro")

    assert count == 1
    assert "int snd_soc_component_macro = 0;" in replaced
    assert "// vendor_macro in comment" in replaced
    assert "\"vendor_macro in string\"" in replaced


def test_governed_translation_execution_applies_runtime_validated_changes(tmp_path: Path) -> None:
    engine = GovernedTranslationExecutionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="execution-session-a",
        lineage_id="execution-lineage-a",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dry_run=False,
        evidence_references=["test://governed_execution/static"],
        previous_patch_history=[],
    ).execution_bundle

    assert bundle["classification"] == "PASS"
    artifacts = bundle["artifacts"]
    assert artifacts["translation_execution_report"]["classification"] == "PASS"
    assert artifacts["translation_execution_report"]["patch_emitted"] is True
    assert artifacts["runtime_validated_patch_segments"]["summary"]["segment_count"] >= 2
    assert artifacts["generated_upstream_patch"]["changed_files"] == ["sound/soc/vendor/test.c"]
    patch = artifacts["generated_upstream_patch"]["patch_text"]
    assert "snd_soc_component_open" in patch
    assert "snd_soc_component_macro" in patch


def test_governance_fail_closed_blocks_transformation(tmp_path: Path) -> None:
    engine = GovernedTranslationExecutionEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_patching_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="execution-session-b",
        lineage_id="execution-lineage-b",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=governance,
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dry_run=False,
        evidence_references=["test://governed_execution/governance"],
        previous_patch_history=[],
    ).execution_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["runtime_validated_patch_segments"]["summary"]["segment_count"] == 0
    assert "# mode=blocked" in bundle["artifacts"]["generated_upstream_patch"]["patch_text"]


def test_runtime_equivalence_verification_blocks_unvalidated_transformation(tmp_path: Path) -> None:
    engine = GovernedTranslationExecutionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="execution-session-c",
        lineage_id="execution-lineage-c",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(runtime_equivalent=False),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dry_run=True,
        evidence_references=["test://governed_execution/runtime_validation"],
        previous_patch_history=[],
    ).execution_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["runtime_validated_patch_segments"]["summary"]["segment_count"] == 0
    reasons = {item["reason"] for item in bundle["artifacts"]["unsafe_transformation_blocks"]["blocks"]}
    assert "runtime_equivalence_false" in reasons


def test_unresolved_blockers_fail_closed_no_transformations(tmp_path: Path) -> None:
    engine = GovernedTranslationExecutionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="execution-session-d",
        lineage_id="execution-lineage-d",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(unsupported_count=3),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dry_run=False,
        evidence_references=["test://governed_execution/unsupported_blockers"],
        previous_patch_history=[],
    ).execution_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["translation_execution_report"]["fail_closed_justification"] == (
        "unsupported_vendor_constructs_present"
    )
    assert bundle["artifacts"]["runtime_validated_patch_segments"]["summary"]["segment_count"] == 0


def test_replay_consistency_and_artifact_persistence(tmp_path: Path) -> None:
    engine = GovernedTranslationExecutionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="execution-session-e",
        lineage_id="execution-lineage-e",
        source_snapshots=_source_snapshots(),
        translation_artifacts=_translation_artifacts(),
        runtime_artifacts=_runtime_artifacts(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dry_run=True,
        evidence_references=["test://governed_execution/replay"],
        previous_patch_history=[],
    ).execution_bundle

    registry = GovernedTranslationExecutionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="execution-lineage-e")
    replay_two = registry.replay(lineage_id="execution-lineage-e")

    assert persisted["lineage_id"] == "execution-lineage-e"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]
    assert (tmp_path / "ops" / "generated_upstream_patch.diff").exists()
    assert (tmp_path / "ops" / "transformation_lineage.json").exists()
    assert (tmp_path / "ops" / "unsafe_transformation_blocks.json").exists()
    assert (tmp_path / "ops" / "runtime_validated_patch_segments.json").exists()
    assert (tmp_path / "ops" / "deterministic_patch_generation_replay.json").exists()
    assert (tmp_path / "ops" / "translation_execution_report.json").exists()


def test_governed_translation_execution_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/governed_translation_execution.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_conversion_adapter(" in src
