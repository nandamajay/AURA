from __future__ import annotations

import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.governed_patchset_orchestration import (  # noqa: E402
    GovernedPatchsetOrchestrationEngine,
    GovernedPatchsetOrchestrationRegistry,
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
        "deterministic_replay_fingerprint": "governed-patchset-replay-fp",
    }


def _compile_ok(_: dict[str, str]) -> dict:
    return {
        "compile_validation_executed": True,
        "compile_validation_passed": True,
        "compiler": "cc",
        "command": "cc -x c -std=gnu11 -fsyntax-only <source>",
        "stderr": "",
        "stdout": "",
        "files_checked": 3,
        "failed_files": [],
    }


def _run_engine(
    tmp_path: Path,
    *,
    session_id: str,
    lineage_id: str,
) -> dict:
    engine = GovernedPatchsetOrchestrationEngine(_loader(tmp_path))
    return engine.analyze(
        target_id="fake_target_alpha",
        session_id=session_id,
        lineage_id=lineage_id,
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True},
        previous_history=[],
        evidence_references=["test://patchset/static"],
    ).patchset_bundle


def test_patchset_orchestration_generates_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    monkeypatch.setattr(module, "_compile_sources", _compile_ok)
    bundle = _run_engine(
        tmp_path,
        session_id="patchset-session-a",
        lineage_id="patchset-lineage-a",
    )

    assert bundle["classification"] in {"PASS", "FAIL_CLOSED"}
    artifacts = bundle["artifacts"]
    required = {
        "governed_patchset_plan",
        "patch_dependency_graph",
        "runtime_patchset_equivalence",
        "patch_ordering_rationale",
        "bisectability_report",
        "patchset_review_risk_report",
        "rollback_checkpoint_registry",
        "deterministic_patchset_replay",
        "cumulative_runtime_validation",
        "upstream_patchset_prediction",
        "governed_patchset_summary",
        "tiny_multi_patchset",
        "tiny_patchset_model",
    }
    assert required.issubset(set(artifacts.keys()))
    patch_text = artifacts["tiny_multi_patchset"]["patch_text"]
    assert "qcom_dbg_log" in patch_text
    assert "dev_dbg" in patch_text
    assert "device_is_registered" in patch_text
    assert artifacts["tiny_multi_patchset"]["real_multi_patchset_generated"] is True


def test_ordering_consistency_and_bisectability(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    monkeypatch.setattr(module, "_compile_sources", _compile_ok)
    bundle = _run_engine(
        tmp_path,
        session_id="patchset-session-b",
        lineage_id="patchset-lineage-b",
    )

    order = bundle["artifacts"]["patch_dependency_graph"]["ordered_patch_ids"]
    assert order == [
        "asoc_patch_01_logging_wrapper_conversion",
        "runtime_patch_02_capability_wrapper_normalization",
        "asoc_patch_03_helper_alias_cleanup",
    ]
    bisect = bundle["artifacts"]["bisectability_report"]
    assert bisect["classification"] == "PASS"
    assert bisect["unsafe_ordering_detected"] is False
    assert bisect["intermediate_states_logically_safe"] is True


def test_deterministic_replay_and_registry_persistence(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    monkeypatch.setattr(module, "_compile_sources", _compile_ok)
    first = _run_engine(
        tmp_path,
        session_id="patchset-session-c",
        lineage_id="patchset-lineage-c",
    )
    second = _run_engine(
        tmp_path,
        session_id="patchset-session-c",
        lineage_id="patchset-lineage-c",
    )

    assert first["governed_patchset_orchestration_fingerprint"] == second["governed_patchset_orchestration_fingerprint"]
    assert (
        first["artifacts"]["deterministic_patchset_replay"]["deterministic_fingerprint"]
        == second["artifacts"]["deterministic_patchset_replay"]["deterministic_fingerprint"]
    )

    registry = GovernedPatchsetOrchestrationRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="patchset-lineage-c")
    replay_two = registry.replay(lineage_id="patchset-lineage-c")
    assert persisted["lineage_id"] == "patchset-lineage-c"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_fail_closed_on_unsafe_ordering_cycle(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    base_model = module._tiny_patchset_model()

    def _cycle_model() -> dict:
        model = copy.deepcopy(base_model)
        units = model["patch_units"]
        units[0]["depends_on"] = ["asoc_patch_03_helper_alias_cleanup"]
        return model

    monkeypatch.setattr(module, "_tiny_patchset_model", _cycle_model)
    monkeypatch.setattr(module, "_compile_sources", _compile_ok)
    bundle = _run_engine(
        tmp_path,
        session_id="patchset-session-d",
        lineage_id="patchset-lineage-d",
    )

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "unsafe_ordering_detected" in bundle["fail_closed_reasons"]
    assert bundle["artifacts"]["patch_dependency_graph"]["dependency_cycles_detected"] is True


def test_fail_closed_on_compile_failure(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    def _compile_fail(_: dict[str, str]) -> dict:
        return {
            "compile_validation_executed": True,
            "compile_validation_passed": False,
            "compiler": "cc",
            "command": "cc -x c -std=gnu11 -fsyntax-only <source>",
            "stderr": "error: expected ';' before '}' token",
            "stdout": "",
            "files_checked": 3,
            "failed_files": [{"source_path": "sound/soc/qcom/q6apm-log-wrapper.c"}],
        }

    monkeypatch.setattr(module, "_compile_sources", _compile_fail)
    bundle = _run_engine(
        tmp_path,
        session_id="patchset-session-e",
        lineage_id="patchset-lineage-e",
    )

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "intermediate_compile_failure" in bundle["fail_closed_reasons"]
    assert bundle["artifacts"]["bisectability_report"]["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["bisectability_report"]["intermediate_states_logically_safe"] is False


def test_fail_closed_on_runtime_equivalence_conflict(tmp_path: Path, monkeypatch) -> None:
    from aura_sdk.transport import governed_patchset_orchestration as module  # noqa: E402

    class _LowConfidenceTranslation:
        def __init__(self, plugin_loader: TargetPluginLoader | None = None):
            self._plugin_loader = plugin_loader

        def analyze(self, **_: object):
            return type(
                "TranslationResult",
                (),
                {
                    "translation_bundle": {
                        "classification": "FAIL_CLOSED",
                        "artifacts": {
                            "runtime_equivalence_validation": {
                                "candidate_validations": [
                                    {
                                        "downstream_construct": "qcom_dbg_log",
                                        "runtime_equivalent": False,
                                        "validation_confidence": 0.2,
                                    },
                                    {
                                        "downstream_construct": "qcom_cap_bool",
                                        "runtime_equivalent": True,
                                        "validation_confidence": 0.9,
                                    },
                                    {
                                        "downstream_construct": "qcom_helper_alias",
                                        "runtime_equivalent": True,
                                        "validation_confidence": 0.9,
                                    },
                                ]
                            },
                            "downstream_upstream_mapping_graph": {"entries": []},
                            "upstream_equivalence_map": {"entries": []},
                        },
                    }
                },
            )()

    monkeypatch.setattr(module, "GovernedTranslationIntelligenceEngine", _LowConfidenceTranslation)
    monkeypatch.setattr(module, "_compile_sources", _compile_ok)
    bundle = _run_engine(
        tmp_path,
        session_id="patchset-session-f",
        lineage_id="patchset-lineage-f",
    )

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "cumulative_runtime_confidence_drop_or_conflict" in bundle["fail_closed_reasons"]
    cumulative = bundle["artifacts"]["cumulative_runtime_validation"]
    assert cumulative["classification"] == "FAIL_CLOSED"
    assert cumulative["summary"]["conflict_count"] >= 1
