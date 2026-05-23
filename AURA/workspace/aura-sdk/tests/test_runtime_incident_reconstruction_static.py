from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.runtime_incident_reconstructor import (  # noqa: E402
    RuntimeIncidentReconstructionRegistry,
    RuntimeIncidentReconstructor,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime_sources() -> dict:
    return {
        "dmesg": {"lines": ["1.100: deferred probe resolved", "1.130: asoc route active"]},
        "ftrace": {"lines": ["1.200: pcm prepare", "1.210: pcm start", "1.420: pcm close"]},
        "trace_cmd": {
            "events": [
                {"timestamp_ms": 1210.0, "category": "dapm", "detail": "POWER_UP"},
                {"timestamp_ms": 1420.0, "category": "dapm", "detail": "POWER_DOWN"},
            ]
        },
        "mailbox_trace": {"lines": ["1.250: mailbox tx", "1.265: mailbox rx ack"]},
        "dsp_response_log": {"lines": ["1.280: dsp tx", "1.300: dsp ack"]},
    }


def _runtime_artifacts() -> dict:
    return {
        "runtime_truth_graph": {
            "edges": [
                {"from": "runtime_event_ingestion", "to": "trace_correlation"},
                {"from": "trace_correlation", "to": "runtime_drift_report"},
            ],
            "deterministic_fingerprint": "runtime-truth-fp-static",
        },
        "pcm_lifecycle_trace": {
            "summary": {"observed_stages": ["PREPARE", "START", "CLOSE"]},
            "transitions": [
                {"event_id": "pcm:1", "timestamp_ms": 1200.0, "stage": "PREPARE"},
                {"event_id": "pcm:2", "timestamp_ms": 1210.0, "stage": "START"},
                {"event_id": "pcm:3", "timestamp_ms": 1420.0, "stage": "CLOSE"},
            ],
        },
        "dapm_transition_trace": {
            "transitions": [
                {"event_id": "dapm:1", "timestamp_ms": 1215.0, "transition": "POWER_UP"},
                {"event_id": "dapm:2", "timestamp_ms": 1410.0, "transition": "POWER_DOWN"},
            ]
        },
        "soundwire_runtime_graph": {
            "summary": {"runtime_soundwire_events": 3},
            "nodes": [{"id": "swr:0"}],
            "edges": [{"from": "swr:0", "to": "swr:1"}],
        },
        "irq_timing_report": {
            "ordered_irq_events": [
                {"event_id": "irq:1", "timestamp_ms": 1218.0},
                {"event_id": "irq:2", "timestamp_ms": 1232.0},
            ]
        },
        "dsp_sync_report": {
            "pair_latencies_ms": [1.8, 2.1],
            "summary": {"sync_failure_count": 0},
        },
        "runtime_drift_report": {
            "drifts": [{"severity": "MEDIUM", "type": "ordering_warning", "details": "minor jitter"}],
        },
        "fusion_rootcause_report": {
            "root_causes": [
                {
                    "cause": "runtime_drift",
                    "severity": "MEDIUM",
                    "details": "sequence drift observed",
                    "confidence": 0.65,
                }
            ]
        },
    }


def _topology_artifacts() -> dict:
    return {
        "topology_runtime_graph": {
            "edges": [
                {"from": "fe:0", "to": "be:0"},
                {"from": "be:0", "to": "codec:0"},
            ],
            "normalized_portable_audio_graph": {
                "fe_be_routes": ["fe0->be0", "fe1->be1"],
            },
        }
    }


def _patch_artifacts() -> dict:
    return {
        "patch_series_plan": {
            "series": [
                {"patch_group_id": "patch_a", "risk": "LOW"},
                {"patch_group_id": "patch_b", "risk": "MEDIUM"},
            ]
        },
        "runtime_patch_correlation": {
            "command_patch_mappings": [
                {
                    "runtime_command": "AURA_AMIXER_NAME_SET alpha 1",
                    "correlation_confidence": 0.9,
                    "impacted_patch_nodes": ["patch_a"],
                },
                {
                    "runtime_command": "AURA_APLAY /tmp/test.wav",
                    "correlation_confidence": 0.8,
                    "impacted_patch_nodes": ["patch_b"],
                },
            ]
        },
        "vendor_contamination_report": {
            "contamination_score": 0.28,
        },
    }


def _migration_artifacts() -> dict:
    return {
        "migration_runtime_alignment": {
            "classification": "ADVISORY_ONLY",
        },
        "portability_blockers": {
            "summary": {"blocked_unsafe_count": 0},
        },
        "upstream_equivalence_map": {
            "entries": [
                {
                    "downstream_construct": "vendor_api_x",
                    "equivalence_status": "UNRESOLVED",
                },
                {
                    "downstream_construct": "snd_soc_dai_link",
                    "equivalence_status": "EXACT",
                },
            ]
        },
    }


def _semantic_artifacts() -> dict:
    return {
        "semantic_confidence_report": {
            "classification": {"primary_classification": "partially_portable"},
            "semantic_fingerprint": "semantic-fp-static",
        },
        "dts_topology_graph": {
            "backend_frontend_mappings": ["fe0->be0"],
        },
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "incident-replay-fp-static",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_runtime_incident_artifacts_and_determinism(tmp_path: Path) -> None:
    engine = RuntimeIncidentReconstructor(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "runtime-incident-v1",
        "runtime_sources": _runtime_sources(),
        "runtime_artifacts": _runtime_artifacts(),
        "topology_artifacts": _topology_artifacts(),
        "patch_artifacts": _patch_artifacts(),
        "migration_artifacts": _migration_artifacts(),
        "semantic_artifacts": _semantic_artifacts(),
        "replay_traces": _replay(),
        "governance_state": _governance(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "evidence_references": ["test://runtime_incident/determinism"],
        "previous_incident_lineage": [],
    }

    first = engine.analyze(**args).incident_bundle
    second = engine.analyze(**args).incident_bundle

    assert first["runtime_incident_reconstruction_fingerprint"] == second["runtime_incident_reconstruction_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "runtime_incident_graph",
        "root_cause_candidates",
        "lifecycle_violation_report",
        "runtime_sequence_drift",
        "topology_runtime_causality",
        "regression_causality_report",
        "deterministic_incident_replay",
        "engineering_confidence_report",
    }
    assert required.issubset(set(artifacts.keys()))


def test_runtime_incident_registry_replay(tmp_path: Path) -> None:
    engine = RuntimeIncidentReconstructor(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-incident-replay-v1",
        runtime_sources=_runtime_sources(),
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        patch_artifacts=_patch_artifacts(),
        migration_artifacts=_migration_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_incident/replay"],
        previous_incident_lineage=[],
    ).incident_bundle

    registry = RuntimeIncidentReconstructionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="runtime-incident-replay-v1")
    replay_two = registry.replay(lineage_id="runtime-incident-replay-v1")

    assert persisted["lineage_id"] == "runtime-incident-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "runtime_incident_graph.json").exists()
    assert (tmp_path / "ops" / "root_cause_candidates.json").exists()
    assert (tmp_path / "ops" / "lifecycle_violation_report.json").exists()
    assert (tmp_path / "ops" / "runtime_sequence_drift.json").exists()
    assert (tmp_path / "ops" / "topology_runtime_causality.json").exists()
    assert (tmp_path / "ops" / "regression_causality_report.json").exists()
    assert (tmp_path / "ops" / "deterministic_incident_replay.json").exists()
    assert (tmp_path / "ops" / "engineering_confidence_report.json").exists()


def test_runtime_incident_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = RuntimeIncidentReconstructor(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_runtime_mutation_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-incident-governance-v1",
        runtime_sources=_runtime_sources(),
        runtime_artifacts=_runtime_artifacts(),
        topology_artifacts=_topology_artifacts(),
        patch_artifacts=_patch_artifacts(),
        migration_artifacts=_migration_artifacts(),
        semantic_artifacts=_semantic_artifacts(),
        replay_traces=_replay(),
        governance_state=governance,
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_incident/governance"],
        previous_incident_lineage=[],
    ).incident_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert bundle["artifacts"]["engineering_confidence_report"]["classification"] == "FAIL_CLOSED"


def test_runtime_incident_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/runtime_incident_reconstructor.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_evidence_adapter(" in src
    assert ".topology_evidence_adapter(" in src
    assert ".semantic_evidence_adapter(" in src
