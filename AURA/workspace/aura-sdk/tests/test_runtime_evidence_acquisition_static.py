from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.runtime_evidence_acquisition import (  # noqa: E402
    RuntimeEvidenceAcquisitionEngine,
    RuntimeEvidenceAcquisitionRegistry,
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


def _source_payloads(*, out_of_order_ftrace: bool = False) -> dict:
    ftrace_events = [
        {"timestamp_ms": 1200.0, "event_type": "pcm_trace", "detail": "pcm open FE0"},
        {"timestamp_ms": 1220.0, "event_type": "pcm_trace", "detail": "pcm start BE0"},
    ]
    if out_of_order_ftrace:
        ftrace_events = [
            {"timestamp_ms": 1220.0, "event_type": "pcm_trace", "detail": "pcm start BE0"},
            {"timestamp_ms": 1100.0, "event_type": "pcm_trace", "detail": "pcm open FE0"},
        ]

    return {
        "dmesg": {"lines": ["1.000: ALSA init", "1.100: route FE0->BE0 enabled"]},
        "ftrace": {"events": ftrace_events},
        "trace_cmd": {"lines": ["dapm widget power_up", "dapm route enable"]},
        "tinymix_state": {"lines": ["WSA RX0 MUX:AIF1_PB", "SpkrLeft DAC Switch:on"]},
        "procfs_runtime": {"lines": ["00-00: MultiMedia1 Playback", "00-01: MultiMedia2 Capture"]},
        "debugfs_runtime": {"lines": ["asoc route FE0 -> BE0", "asoc widget active"]},
        "soundwire_runtime": {"lines": ["soundwire_slave_1 active", "swrm_master_0 running"]},
        "dsp_mailbox": {"lines": ["mailbox tx cmd", "dsp ack complete"]},
        "irq_runtime": {"lines": ["1.500 irq 21 handled", "1.520 interrupt done"]},
        "clocks": {"lines": ["clock audio_core enabled", "clock mi2s active"]},
        "regulators": {"lines": ["regulator vdd_audio enabled", "regulator vdd_codec enabled"]},
        "ipc_path": {"lines": ["ipc glink channel ready", "ipc apr routing active"]},
    }


def _translation_artifacts(*, strong_validation: bool = True) -> dict:
    conf = 0.91 if strong_validation else 0.40
    runtime_equivalent = bool(strong_validation)
    return {
        "upstream_translation_plan": {
            "ast_aware_conversion_plan": {
                "stages": [
                    {"stage_id": "phase_pcm_lifecycle_translation"},
                    {"stage_id": "phase_dapm_route_equivalence"},
                    {"stage_id": "phase_soundwire_mapping"},
                ]
            }
        },
        "api_replacement_map": {
            "replacements": [
                {
                    "downstream_construct": "pcm_open",
                    "upstream_replacement": "snd_pcm_open_substream",
                    "candidate_confidence": 0.87,
                    "runtime_safe": True,
                },
                {
                    "downstream_construct": "dapm_route_enable",
                    "upstream_replacement": "snd_soc_dapm_add_routes",
                    "candidate_confidence": 0.85,
                    "runtime_safe": True,
                },
            ]
        },
        "runtime_equivalence_validation": {
            "candidate_validations": [
                {
                    "downstream_construct": "pcm_open",
                    "runtime_equivalent": runtime_equivalent,
                    "validation_confidence": conf,
                    "blocking_runtime_reasons": [] if runtime_equivalent else ["pcm_state_mismatch"],
                },
                {
                    "downstream_construct": "dapm_route_enable",
                    "runtime_equivalent": runtime_equivalent,
                    "validation_confidence": conf,
                    "blocking_runtime_reasons": [] if runtime_equivalent else ["dapm_sequence_mismatch"],
                },
            ]
        },
    }


def _runtime_artifacts() -> dict:
    return {
        "runtime_truth_graph": {
            "classification": "PASS",
            "edges": [{"from": "runtime_event_ingestion", "to": "trace_correlation"}],
        },
        "topology_runtime_graph": {
            "normalized_portable_audio_graph": {"fe_be_routes": ["FE0->BE0"]},
            "edges": [{"from": "FE0", "to": "BE0"}],
        },
        "dts_topology_graph": {
            "backend_frontend_mappings": ["FE0->BE0"],
            "soundwire_topology_markers": ["soundwire_slave_1"],
        },
    }


def _ipcat() -> dict:
    return {
        "platform": "fake_target_alpha",
        "soc": "qcom-sim",
        "board": "sim-board",
        "audio_subsystem": "qcom_audio",
        "ipc_nodes": ["apr", "rpmsg", "glink"],
        "ip_blocks": ["asoc", "soundwire", "dsp", "irq", "clock", "regulator"],
    }


def _replay_traces() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "runtime-evidence-acquisition-replay-fp",
    }


def test_runtime_evidence_acquisition_deterministic_replay(tmp_path: Path) -> None:
    engine = RuntimeEvidenceAcquisitionEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "session_id": "runtime-acq-session-a",
        "lineage_id": "runtime-acq-lineage-a",
        "source_payloads": _source_payloads(),
        "translation_artifacts": _translation_artifacts(strong_validation=True),
        "runtime_artifacts": _runtime_artifacts(),
        "ipcat_hardware_metadata": _ipcat(),
        "governance_state": _governance(),
        "replay_traces": _replay_traces(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "previous_session_history": [],
        "evidence_references": ["test://runtime_evidence_acquisition/deterministic"],
    }

    first = engine.analyze(**args).acquisition_bundle
    second = engine.analyze(**args).acquisition_bundle

    assert first["runtime_evidence_acquisition_fingerprint"] == second["runtime_evidence_acquisition_fingerprint"]
    assert (
        first["artifacts"]["runtime_equivalence_fingerprint"]["deterministic_fingerprint"]
        == second["artifacts"]["runtime_equivalence_fingerprint"]["deterministic_fingerprint"]
    )

    registry = RuntimeEvidenceAcquisitionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )
    persisted = registry.persist(first)
    replay_one = registry.replay(lineage_id="runtime-acq-lineage-a")
    replay_two = registry.replay(lineage_id="runtime-acq-lineage-a")
    assert persisted["lineage_id"] == "runtime-acq-lineage-a"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]


def test_runtime_ordering_validation_detects_disorder(tmp_path: Path) -> None:
    engine = RuntimeEvidenceAcquisitionEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="runtime-acq-session-b",
        lineage_id="runtime-acq-lineage-b",
        source_payloads=_source_payloads(out_of_order_ftrace=True),
        translation_artifacts=_translation_artifacts(strong_validation=True),
        runtime_artifacts=_runtime_artifacts(),
        ipcat_hardware_metadata=_ipcat(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_session_history=[],
        evidence_references=["test://runtime_evidence_acquisition/ordering"],
    ).acquisition_bundle

    quality = bundle["artifacts"]["evidence_quality_report"]
    assert quality["ordering_validation"]["raw_ordering_violations"] > 0
    assert quality["classification"] == "FAIL_CLOSED"


def test_hardware_topology_consistency_with_ipcat(tmp_path: Path) -> None:
    engine = RuntimeEvidenceAcquisitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="runtime-acq-session-c",
        lineage_id="runtime-acq-lineage-c",
        source_payloads=_source_payloads(),
        translation_artifacts=_translation_artifacts(strong_validation=True),
        runtime_artifacts=_runtime_artifacts(),
        ipcat_hardware_metadata=_ipcat(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_session_history=[],
        evidence_references=["test://runtime_evidence_acquisition/topology"],
    ).acquisition_bundle

    ipc_map = bundle["artifacts"]["ipc_topology_map"]
    truth = bundle["artifacts"]["hardware_truth_graph"]
    assert ipc_map["ipcat_hardware_descriptor"]["platform"] == "fake_target_alpha"
    assert ipc_map["summary"]["ipc_node_count"] >= 1
    assert truth["summary"]["fe_count"] >= 1
    assert truth["summary"]["be_count"] >= 1


def test_evidence_integrity_and_coverage_reporting(tmp_path: Path) -> None:
    engine = RuntimeEvidenceAcquisitionEngine(_loader(tmp_path))
    src = _source_payloads()
    src["irq_runtime"] = {}
    src["ipc_path"] = {}

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="runtime-acq-session-d",
        lineage_id="runtime-acq-lineage-d",
        source_payloads=src,
        translation_artifacts=_translation_artifacts(strong_validation=True),
        runtime_artifacts=_runtime_artifacts(),
        ipcat_hardware_metadata=_ipcat(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_session_history=[],
        evidence_references=["test://runtime_evidence_acquisition/integrity"],
    ).acquisition_bundle

    quality = bundle["artifacts"]["evidence_quality_report"]
    missing = quality["coverage"]["missing_required_sources"]
    assert "irq_runtime" in missing
    assert "ipc_path" in missing


def test_governance_enforces_runtime_backed_equivalence_threshold(tmp_path: Path) -> None:
    engine = RuntimeEvidenceAcquisitionEngine(_loader(tmp_path))
    bundle = engine.analyze(
        target_id="fake_target_alpha",
        session_id="runtime-acq-session-e",
        lineage_id="runtime-acq-lineage-e",
        source_payloads=_source_payloads(),
        translation_artifacts=_translation_artifacts(strong_validation=False),
        runtime_artifacts=_runtime_artifacts(),
        ipcat_hardware_metadata=_ipcat(),
        governance_state=_governance(),
        replay_traces=_replay_traces(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        previous_session_history=[],
        evidence_references=["test://runtime_evidence_acquisition/governance_threshold"],
    ).acquisition_bundle

    eq = bundle["artifacts"]["runtime_equivalence_fingerprint"]
    assert eq["classification"] == "FAIL_CLOSED"
    assert eq["governance_gate"]["transformations_allowed"] is False
    assert bundle["classification"] == "FAIL_CLOSED"


def test_runtime_evidence_acquisition_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/runtime_evidence_acquisition.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".topology_evidence_adapter(" in src
    assert ".subsystem_descriptor_provider(" in src
