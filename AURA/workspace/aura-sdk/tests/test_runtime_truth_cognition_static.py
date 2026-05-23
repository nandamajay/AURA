from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader, build_simulation_registry_payload  # noqa: E402
from aura_sdk.transport.runtime_truth_engine import RuntimeTruthEngine, RuntimeTruthRegistry  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _loader(tmp_path: Path) -> TargetPluginLoader:
    path = tmp_path / "simulation_registry.json"
    _write_json(path, build_simulation_registry_payload())
    return TargetPluginLoader(registry_path=path)


def _runtime() -> dict:
    return {
        "run_id": "runtime-truth-run-1",
        "process_success": True,
        "playback_completion": True,
        "classification": "PASS",
        "playback_runtime_seconds": 25.0,
        "expected_runtime_seconds": 25.0,
        "route_fingerprint": "route-fp-runtime-1",
        "command_sequence": ["resolve_pcm", "resolve_backend", "validate_route"],
        "pcm_activity": {
            "pcm_entries": [{"pcm_id": "00-00", "name": "MultiMedia1", "direction": "playback"}],
        },
        "mixer_state": {
            "controls": ["WSA RX0 MUX", "SpkrLeft DAC"],
        },
    }


def _sources() -> dict:
    return {
        "dmesg": {"lines": ["1.100: deferred probe resolved", "1.150: ALSA card registered"]},
        "ftrace": {"lines": ["1.200: pcm open", "1.220: pcm prepare", "1.240: pcm start", "1.500: pcm close"]},
        "trace_cmd": {"lines": ["1.210: dapm power_up", "1.230: route enable", "1.490: dapm power_down"]},
        "tinyalsa_dump": {"lines": ["1.250: tinymix snapshot captured"]},
        "procfs_sysfs": {"lines": ["1.260: /proc/asound/pcm", "1.270: /sys/kernel/debug/asoc"]},
        "soundwire_debugfs": {"lines": ["1.280: soundwire port active", "1.290: soundwire lane stable"]},
        "alsa_topology_runtime": {"lines": ["1.300: FE->BE active", "1.320: DPCM stable"]},
        "mailbox_trace": {"lines": ["1.330: mailbox tx cmd", "1.360: mailbox rx ack"]},
        "dsp_response_log": {"lines": ["1.370: dsp tx", "1.390: dsp ack"]},
    }


def _structural() -> dict:
    return {
        "topology_runtime_graph": {
            "nodes": [
                {"id": "fe:alpha_fe0", "kind": "frontend_dai"},
                {"id": "be:alpha_be0", "kind": "backend_dai"},
            ],
            "edges": [
                {
                    "from": "fe:alpha_fe0",
                    "to": "be:alpha_be0",
                    "relation": "dpcm_route",
                    "confidence": 0.8,
                }
            ],
            "normalized_portable_audio_graph": {
                "backend_dai": ["alpha_be0"],
            },
        },
        "runtime_source_correlation": {
            "command_source_correlations": [
                {
                    "runtime_command": "AURA_AMIXER_NAME_SET alpha 1",
                    "correlation_confidence": 0.9,
                    "matched_source_files": ["sound/soc/qcom/alpha.c"],
                }
            ]
        },
    }


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
        "deterministic_replay_fingerprint": "runtime-replay-fp-1",
    }


def test_runtime_truth_artifacts_and_determinism(tmp_path: Path) -> None:
    engine = RuntimeTruthEngine(_loader(tmp_path))

    args = {
        "target_id": "fake_target_alpha",
        "lineage_id": "runtime-truth-v1",
        "runtime_evidence": _runtime(),
        "source_payloads": _sources(),
        "structural_artifacts": _structural(),
        "replay_traces": _replay(),
        "governance_state": _governance(),
        "plugin_capability_state": {"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        "dts_cognition": {"backend_frontend_mappings": ["alpha_fe0->alpha_be0"]},
        "archived_runtime_lineage": [],
        "evidence_references": ["test://runtime_truth/determinism"],
    }

    first = engine.analyze(**args).runtime_truth_bundle
    second = engine.analyze(**args).runtime_truth_bundle

    assert first["runtime_truth_fingerprint"] == second["runtime_truth_fingerprint"]

    artifacts = first["artifacts"]
    required = {
        "runtime_truth_graph",
        "dapm_transition_trace",
        "pcm_lifecycle_trace",
        "soundwire_runtime_graph",
        "irq_timing_report",
        "dsp_sync_report",
        "runtime_drift_report",
        "deterministic_runtime_replay",
        "runtime_confidence_score",
    }
    assert required.issubset(set(artifacts.keys()))


def test_runtime_truth_registry_replay(tmp_path: Path) -> None:
    engine = RuntimeTruthEngine(_loader(tmp_path))

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-truth-replay-v1",
        runtime_evidence=_runtime(),
        source_payloads=_sources(),
        structural_artifacts=_structural(),
        replay_traces=_replay(),
        governance_state=_governance(),
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dts_cognition={"backend_frontend_mappings": ["alpha_fe0->alpha_be0"]},
        archived_runtime_lineage=[],
        evidence_references=["test://runtime_truth/replay"],
    ).runtime_truth_bundle

    registry = RuntimeTruthRegistry(
        cognition_registry_path=tmp_path / "registry.json",
        output_dir=tmp_path / "ops",
    )

    persisted = registry.persist(bundle)
    replay_one = registry.replay(lineage_id="runtime-truth-replay-v1")
    replay_two = registry.replay(lineage_id="runtime-truth-replay-v1")

    assert persisted["lineage_id"] == "runtime-truth-replay-v1"
    assert replay_one["deterministic_replay_fingerprint"] == replay_two["deterministic_replay_fingerprint"]

    assert (tmp_path / "ops" / "runtime_truth_graph.json").exists()
    assert (tmp_path / "ops" / "dapm_transition_trace.json").exists()
    assert (tmp_path / "ops" / "pcm_lifecycle_trace.json").exists()
    assert (tmp_path / "ops" / "soundwire_runtime_graph.json").exists()
    assert (tmp_path / "ops" / "irq_timing_report.json").exists()
    assert (tmp_path / "ops" / "dsp_sync_report.json").exists()
    assert (tmp_path / "ops" / "runtime_drift_report.json").exists()
    assert (tmp_path / "ops" / "deterministic_runtime_replay.json").exists()
    assert (tmp_path / "ops" / "runtime_confidence_score.json").exists()


def test_runtime_truth_fail_closed_on_governance_violation(tmp_path: Path) -> None:
    engine = RuntimeTruthEngine(_loader(tmp_path))
    governance = _governance()
    governance["autonomous_runtime_mutation_allowed"] = True

    bundle = engine.analyze(
        target_id="fake_target_alpha",
        lineage_id="runtime-truth-governance-v1",
        runtime_evidence=_runtime(),
        source_payloads=_sources(),
        structural_artifacts=_structural(),
        replay_traces=_replay(),
        governance_state=governance,
        plugin_capability_state={"supported": True, "capabilities": {"supports_amixer": "SUPPORTED"}},
        dts_cognition={"backend_frontend_mappings": ["alpha_fe0->alpha_be0"]},
        archived_runtime_lineage=[],
        evidence_references=["test://runtime_truth/governance"],
    ).runtime_truth_bundle

    assert bundle["classification"] == "FAIL_CLOSED"


def test_runtime_truth_core_plugin_isolation() -> None:
    src = (SRC_DIR / "aura_sdk/transport/runtime_truth_engine.py").read_text(encoding="utf-8").lower()

    assert "if target ==" not in src
    assert "rb3" not in src
    assert ".runtime_evidence_adapter(" in src
    assert ".topology_evidence_adapter(" in src
    assert ".runtime_conversion_adapter(" in src
