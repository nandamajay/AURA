from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.runtime_evidence_ingestor import RuntimeEvidenceIngestor  # noqa: E402
from aura_sdk.transport.runtime_session_registry import RuntimeSessionRegistry  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _source_payloads() -> dict:
    return {
        "dmesg": {"lines": ["1.100: ALSA card registered", "1.110: route enabled"]},
        "ftrace": {"lines": ["1.200: pcm open", "1.220: pcm start", "1.420: pcm close"]},
        "trace_cmd": {
            "events": [
                {"timestamp_ms": 1215.0, "event_type": "dapm_trace", "detail": "power_up FE0->BE0"},
                {"timestamp_ms": 1405.0, "event_type": "dapm_trace", "detail": "power_down FE0->BE0"},
            ]
        },
        "perf": {
            "events": [
                {"timestamp_ms": 1220.0, "event_type": "perf_trace", "detail": "irq runtime sample"}
            ]
        },
        "tinymix_state": {"lines": ["WSA RX0 MUX:AIF1_PB", "SpkrLeft DAC Switch:on"]},
        "procfs_runtime": {"lines": ["00-00: MultiMedia1 Playback", "00-01: MultiMedia2 Capture"]},
        "debugfs_runtime": {"lines": ["asoc dapm widget active", "asoc route FE0 -> BE0"]},
        "soundwire_runtime": {"lines": ["swrm_master_0 active", "soundwire_slave_1 connected"]},
        "dsp_mailbox": {"lines": ["mailbox tx cmd", "dsp ack"]},
        "irq_runtime": {"lines": ["1.240 irq 21 handled", "1.300 interrupt latency 0.2ms"]},
    }


def _domain_artifacts() -> dict:
    return {
        "runtime_truth_graph": {
            "deterministic_fingerprint": "runtime-truth-fp-static",
            "edges": [{"from": "runtime_event_ingestion", "to": "trace_correlation"}],
        },
        "topology_cognition": {
            "deterministic_fingerprint": "topology-fp-static",
            "normalized_portable_audio_graph": {"fe_be_routes": ["FE0->BE0"]},
            "edges": [{"from": "FE0", "to": "BE0"}],
        },
        "migration_lineage": {
            "deterministic_fingerprint": "migration-fp-static",
            "phases": [{"phase": "fe_be_split", "status": "in_progress"}],
        },
        "patch_lineage": {
            "deterministic_fingerprint": "patch-fp-static",
            "series": [{"patch_group_id": "audio_route_a"}],
        },
        "structural_cognition": {
            "deterministic_fingerprint": "structural-fp-static",
            "nodes": [{"id": "snd_soc_component"}],
        },
        "semantic_ontology": {
            "deterministic_fingerprint": "semantic-fp-static",
            "concepts": [{"id": "dpcm_lifecycle"}],
        },
    }


def _replay() -> dict:
    return {
        "deterministic_event_ordering": True,
        "deterministic_replay_fingerprint": "runtime-evidence-replay-fp-static",
    }


def _governance() -> dict:
    return {
        "fail_closed_posture": True,
        "autonomous_patching_allowed": False,
        "autonomous_topology_rewrite_allowed": False,
        "autonomous_runtime_mutation_allowed": False,
        "autonomous_upstream_generation_allowed": False,
    }


def test_runtime_evidence_ingestion_deterministic(tmp_path: Path) -> None:
    engine = RuntimeEvidenceIngestor(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "runtime-evidence-v1",
        "session_id": "session-alpha",
        "source_payloads": _source_payloads(),
        "domain_artifacts": _domain_artifacts(),
        "replay_traces": _replay(),
        "governance_state": _governance(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "evidence_references": ["test://runtime_evidence/determinism"],
        "previous_session_history": [],
    }

    first = engine.analyze(**args).runtime_evidence_bundle
    second = engine.analyze(**args).runtime_evidence_bundle

    assert first["runtime_evidence_ingestion_fingerprint"] == second["runtime_evidence_ingestion_fingerprint"]
    assert first["artifacts"]["runtime_capture_fingerprint"]["deterministic_fingerprint"] == second["artifacts"]["runtime_capture_fingerprint"]["deterministic_fingerprint"]

    normalized = first["artifacts"]["normalized_runtime_evidence"]
    events = normalized["normalized_events"]
    timestamps = [float(row["timestamp_ms"]) for row in events]
    assert timestamps == sorted(timestamps)

    correlation_summary = normalized["domain_correlation"]["summary"]
    assert int(correlation_summary["domain_count"]) >= 1
    assert int(correlation_summary["linked_event_count"]) >= 1


def test_runtime_evidence_registry_replay_stable(tmp_path: Path) -> None:
    engine = RuntimeEvidenceIngestor(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-evidence-replay-v1",
        session_id="session-replay",
        source_payloads=_source_payloads(),
        domain_artifacts=_domain_artifacts(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_evidence/replay"],
        previous_session_history=[],
    ).runtime_evidence_bundle

    registry = RuntimeSessionRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="runtime-evidence-replay-v1")
    replay_two = registry.replay(lineage_id="runtime-evidence-replay-v1")

    assert persisted["lineage_id"] == "runtime-evidence-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "normalized_runtime_evidence.json").exists()
    assert (tmp_path / "ops" / "runtime_session_graph.json").exists()
    assert (tmp_path / "ops" / "evidence_capture_lineage.json").exists()
    assert (tmp_path / "ops" / "subsystem_runtime_state.json").exists()
    assert (tmp_path / "ops" / "dsp_runtime_trace.json").exists()
    assert (tmp_path / "ops" / "soundwire_runtime_trace.json").exists()
    assert (tmp_path / "ops" / "pcm_runtime_state.json").exists()
    assert (tmp_path / "ops" / "runtime_capture_fingerprint.json").exists()
    assert (tmp_path / "ops" / "deterministic_runtime_session_replay.json").exists()


def test_runtime_evidence_fail_closed_on_missing_evidence(tmp_path: Path) -> None:
    engine = RuntimeEvidenceIngestor(_loader(tmp_path))
    sources = _source_payloads()
    sources["perf"] = {}

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-evidence-missing-v1",
        session_id="session-missing",
        source_payloads=sources,
        domain_artifacts=_domain_artifacts(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_evidence/missing"],
        previous_session_history=[],
    ).runtime_evidence_bundle

    assert bundle["classification"] == "FAIL_CLOSED"
    assert "perf" in bundle["artifacts"]["normalized_runtime_evidence"]["summary"]["missing_required_sources"]


def test_runtime_evidence_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = RuntimeEvidenceIngestor(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_runtime_mutation_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-evidence-governance-v1",
        session_id="session-governance",
        source_payloads=_source_payloads(),
        domain_artifacts=_domain_artifacts(),
        replay_traces=_replay(),
        governance_state=governance,
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        evidence_references=["test://runtime_evidence/governance"],
        previous_session_history=[],
    ).runtime_evidence_bundle

    assert bundle["classification"] == "FAIL_CLOSED"


def test_runtime_evidence_core_plugin_isolation() -> None:
    src = (
        SRC_DIR / "aura_sdk/transport/runtime_evidence_ingestor.py"
    ).read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_evidence_adapter(" in src
    assert ".topology_evidence_adapter(" in src
    assert ".semantic_evidence_adapter(" in src
