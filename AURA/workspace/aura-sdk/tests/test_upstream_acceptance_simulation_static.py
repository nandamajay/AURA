from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.upstream_acceptance_simulation import (  # noqa: E402
    UpstreamAcceptanceSimulationEngine,
    UpstreamAcceptanceSimulationRegistry,
)


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


def _translation_artifacts(*, unsupported_count: int = 0) -> dict:
    return {
        "unsupported_vendor_constructs": {
            "summary": {"unsupported_count": int(unsupported_count)},
            "unsupported": (
                []
                if unsupported_count <= 0
                else [{"construct": "vendor_unsupported_a", "reason": "no_upstream_equivalent"}]
            ),
        }
    }


def _execution_artifacts() -> dict:
    return {
        "generated_upstream_patch": {
            "patch_text": "\n".join(
                [
                    "# Governed Translation Execution Patch",
                    "# mode=emit",
                    "",
                    "--- a/sound/soc/qcom/test.c",
                    "+++ b/sound/soc/qcom/test.c",
                    "@@ -1,3 +1,3 @@",
                    "-old_symbol();",
                    "+snd_soc_prepare_enable();",
                    "",
                ]
            )
        }
    }


def _patch_artifacts(*, high_risk_crossings: int = 0, blast_radius: str = "LOW") -> dict:
    return {
        "patch_dependency_graph": {
            "nodes": [
                {"patch_id": "asoc_pcm_prepare", "depends_on": []},
                {"patch_id": "asoc_route_enable", "depends_on": ["asoc_pcm_prepare"]},
            ]
        },
        "subsystem_boundary_map": {
            "classification": "PASS" if high_risk_crossings == 0 else "ADVISORY_ONLY",
            "summary": {"high_risk_crossings": int(high_risk_crossings)},
            "subsystems": [{"subsystem": "asoc_core"}],
        },
        "bisectability_report": {
            "classification": "PASS",
            "bisectability_score": 0.94,
            "summary": {"blocked_units": 0},
        },
        "patch_series_plan": {
            "series": [
                {
                    "sequence": 1,
                    "patch_group_id": "asoc_pcm_prepare",
                    "scope": ["asoc_core"],
                    "maintainer_review_groups": ["soc-audio-maintainers"],
                    "subsystem_owners": ["asoc_core"],
                },
                {
                    "sequence": 2,
                    "patch_group_id": "asoc_route_enable",
                    "scope": ["asoc_topology"],
                    "maintainer_review_groups": ["soc-audio-maintainers"],
                    "subsystem_owners": ["asoc_topology"],
                },
            ]
        },
        "api_evolution_trace": {
            "summary": {"unresolved_count": 0},
        },
        "runtime_patch_correlation": {
            "regression_blast_radius": str(blast_radius),
        },
    }


def _runtime_acquisition_artifacts(*, runtime_conf: float = 0.92, quality: float = 0.9, missing_domains: int = 0, non_equivalent: int = 0) -> dict:
    return {
        "runtime_equivalence_fingerprint": {
            "classification": "PASS" if runtime_conf >= 0.72 else "FAIL_CLOSED",
            "summary": {
                "mean_runtime_backed_confidence": float(runtime_conf),
                "governed_reusable_count": 2 if runtime_conf >= 0.72 else 0,
            },
            "entries": [
                {
                    "downstream_construct": "pcm_open",
                    "upstream_replacement": "snd_pcm_open_substream",
                    "runtime_backed_confidence": float(runtime_conf),
                    "equivalence_fingerprint": "eq-fp-pcm-open",
                }
            ],
        },
        "runtime_divergence_report": {
            "classification": "PASS" if non_equivalent == 0 and missing_domains == 0 else "FAIL_CLOSED",
            "divergence_signals": {
                "missing_domain_count": int(missing_domains),
                "non_equivalent_count": int(non_equivalent),
                "governed_reusable_count": 2 if runtime_conf >= 0.72 else 0,
                "evidence_quality_score": float(quality),
            },
        },
        "downstream_upstream_runtime_diff": {
            "classification": "PASS" if non_equivalent == 0 and missing_domains == 0 else "FAIL_CLOSED",
            "summary": {
                "missing_domain_count": int(missing_domains),
                "non_equivalent_count": int(non_equivalent),
            },
        },
        "evidence_quality_report": {
            "classification": "PASS" if quality >= 0.68 else "FAIL_CLOSED",
            "quality_score": float(quality),
        },
        "target_runtime_capture": {
            "normalized_events": [
                {"event_id": "evt1", "timestamp_ms": 1000.0, "message": "pcm_open FE0", "domain": "PCM"},
                {"event_id": "evt2", "timestamp_ms": 1020.0, "message": "dapm route enable", "domain": "DAPM"},
            ]
        },
        "ipc_topology_map": {"classification": "PASS"},
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "upstream-acceptance-replay-fp",
    }


def test_upstream_acceptance_simulation_deterministic_replay(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "session_id": "acceptance-session-a",
        "lineage_id": "acceptance-lineage-a",
        "translation_artifacts": _translation_artifacts(unsupported_count=0),
        "execution_artifacts": _execution_artifacts(),
        "patch_artifacts": _patch_artifacts(high_risk_crossings=0, blast_radius="LOW"),
        "runtime_acquisition_artifacts": _runtime_acquisition_artifacts(runtime_conf=0.92, quality=0.9),
        "governance_state": _governance(),
        "replay_traces": _replay(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "previous_submission_history": [],
        "evidence_references": ["test://upstream_acceptance/deterministic"],
    }

    first = engine.analyze(**args).acceptance_bundle
    second = engine.analyze(**args).acceptance_bundle

    assert first["classification"] == "PASS"
    assert second["classification"] == "PASS"
    assert first["upstream_acceptance_simulation_fingerprint"] == second["upstream_acceptance_simulation_fingerprint"]
    assert (
        first["artifacts"]["deterministic_submission_replay"]["deterministic_fingerprint"]
        == second["artifacts"]["deterministic_submission_replay"]["deterministic_fingerprint"]
    )

    registry = UpstreamAcceptanceSimulationRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="acceptance-lineage-a")
    replay_two = registry.replay(lineage_id="acceptance-lineage-a")
    assert persisted["lineage_id"] == "acceptance-lineage-a"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_fail_closed_on_low_runtime_equivalence_confidence(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="acceptance-session-b",
        lineage_id="acceptance-lineage-b",
        translation_artifacts=_translation_artifacts(unsupported_count=0),
        execution_artifacts=_execution_artifacts(),
        patch_artifacts=_patch_artifacts(high_risk_crossings=0, blast_radius="LOW"),
        runtime_acquisition_artifacts=_runtime_acquisition_artifacts(runtime_conf=0.41, quality=0.9),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_submission_history=[],
        evidence_references=["test://upstream_acceptance/runtime_conf"],
    ).acceptance_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["acceptance_confidence_score"]["fail_closed_reasons"]
    assert "runtime_backed_equivalence_confidence_below_threshold" in reasons


def test_fail_closed_on_subsystem_isolation_violation(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="acceptance-session-c",
        lineage_id="acceptance-lineage-c",
        translation_artifacts=_translation_artifacts(unsupported_count=0),
        execution_artifacts=_execution_artifacts(),
        patch_artifacts=_patch_artifacts(high_risk_crossings=2, blast_radius="LOW"),
        runtime_acquisition_artifacts=_runtime_acquisition_artifacts(runtime_conf=0.92, quality=0.9),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_submission_history=[],
        evidence_references=["test://upstream_acceptance/subsystem"],
    ).acceptance_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["acceptance_confidence_score"]["fail_closed_reasons"]
    assert "subsystem_isolation_violation" in reasons


def test_fail_closed_on_regression_containment_threshold(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="acceptance-session-d",
        lineage_id="acceptance-lineage-d",
        translation_artifacts=_translation_artifacts(unsupported_count=0),
        execution_artifacts=_execution_artifacts(),
        patch_artifacts=_patch_artifacts(high_risk_crossings=0, blast_radius="HIGH"),
        runtime_acquisition_artifacts=_runtime_acquisition_artifacts(runtime_conf=0.55, quality=0.6, missing_domains=2, non_equivalent=2),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_submission_history=[],
        evidence_references=["test://upstream_acceptance/regression"],
    ).acceptance_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["acceptance_confidence_score"]["fail_closed_reasons"]
    assert "regression_containment_confidence_below_threshold" in reasons


def test_fail_closed_on_unresolved_vendor_constructs(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="acceptance-session-e",
        lineage_id="acceptance-lineage-e",
        translation_artifacts=_translation_artifacts(unsupported_count=3),
        execution_artifacts=_execution_artifacts(),
        patch_artifacts=_patch_artifacts(high_risk_crossings=0, blast_radius="LOW"),
        runtime_acquisition_artifacts=_runtime_acquisition_artifacts(runtime_conf=0.92, quality=0.9),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_submission_history=[],
        evidence_references=["test://upstream_acceptance/unsupported"],
    ).acceptance_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    reasons = bundle["artifacts"]["acceptance_confidence_score"]["fail_closed_reasons"]
    assert "unsupported_vendor_abstractions_unresolved" in reasons


def test_required_artifacts_present(tmp_path: Path) -> None:
    engine = UpstreamAcceptanceSimulationEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="acceptance-session-f",
        lineage_id="acceptance-lineage-f",
        translation_artifacts=_translation_artifacts(unsupported_count=0),
        execution_artifacts=_execution_artifacts(),
        patch_artifacts=_patch_artifacts(high_risk_crossings=0, blast_radius="LOW"),
        runtime_acquisition_artifacts=_runtime_acquisition_artifacts(runtime_conf=0.92, quality=0.9),
        governance_state=_governance(),
        replay_traces=_replay(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_submission_history=[],
        evidence_references=["test://upstream_acceptance/artifacts"],
    ).acceptance_bundle

    artifacts = bundle["artifacts"]
    required = {
        "upstream_acceptance_report",
        "patch_series_validation",
        "maintainer_scope_map",
        "regression_risk_assessment",
        "bisectability_validation",
        "upstream_submission_plan",
        "patch_dependency_order",
        "acceptance_confidence_score",
        "deterministic_submission_replay",
    }
    assert required.issubset(set(artifacts.keys()))


def test_upstream_acceptance_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/upstream_acceptance_simulation.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_conversion_adapter(" in src
