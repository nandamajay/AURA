from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.plugins import TargetPluginLoader  # noqa: E402
from aura_sdk.transport.portable_runtime_layer import PortableRuntimeLayer  # noqa: E402


def _rb3_fingerprint() -> dict:
    return {
        "target_id": "test-target",
        "capabilities": {
            "supports_amixer": "SUPPORTED",
            "supports_tinymix": "SUPPORTED",
        },
        "audio_discovery": {
            "rb3gen2_detected": True,
            "alsa_topology_cards": [
                {
                    "card_index": 0,
                    "card_id": "QCS6490RB3Gen2",
                    "descriptor": "qcs6490 - QCS6490-RB3Gen2",
                }
            ],
            "pcm_entries": [
                {
                    "pcm_id": "00-00",
                    "name": "MultiMedia1",
                    "interface": "Primary MI2S",
                    "direction": "playback",
                    "streams": 1,
                }
            ],
        },
    }


def test_plugin_isolation_contract_and_core_genericity() -> None:
    loader = TargetPluginLoader()
    plugin = loader.load_plugin("RB3Gen2")

    assert plugin.target_id == "RB3Gen2"
    for field in (
        "topology_provider",
        "mixer_provider",
        "pcm_provider",
        "route_provider",
        "evidence_provider",
        "capability_provider",
        "validation_provider",
        "dts_adapter",
        "topology_adapter",
        "vendor_api_adapter",
        "subsystem_descriptor_provider",
        "runtime_evidence_adapter",
        "topology_evidence_adapter",
        "semantic_evidence_adapter",
    ):
        assert callable(getattr(plugin, field))

    runtime_src = (SRC_DIR / "aura_sdk/transport/portable_runtime_layer.py").read_text(encoding="utf-8").lower()
    loader_src = (SRC_DIR / "aura_sdk/transport/plugins/loader.py").read_text(encoding="utf-8").lower()

    assert "if target == rb3" not in runtime_src
    assert "if target == rb3" not in loader_src
    assert "rb3" not in runtime_src


def test_deterministic_plugin_replay_compatibility() -> None:
    loader = TargetPluginLoader()
    replay_contract = {
        "sequence_contract": [
            "execution_ordering",
            "timing_windows",
            "route_fingerprint",
            "pcm_signature",
            "evidence_sequence",
            "cleanup_sequence",
        ]
    }

    first = loader.validate_replay_compatibility(target_id="RB3Gen2", replay_contract=replay_contract)
    second = loader.validate_replay_compatibility(target_id="RB3Gen2", replay_contract=replay_contract)

    assert first == second
    assert first["compatibility_level"] == "FULL"
    assert first["deterministic"] is True


def test_governance_boundary_fail_closed_behavior() -> None:
    loader = TargetPluginLoader()
    plugin = loader.load_plugin("RB3Gen2")

    boundary = plugin.validation_provider(
        {
            "mode": "governance_boundary",
            "governance_state": {
                "autonomous_patching_allowed": False,
                "autonomous_topology_rewrite_allowed": False,
                "autonomous_mixer_mutation_allowed": False,
                "autonomous_upstream_generation_allowed": False,
            },
        }
    )
    assert boundary["governance_boundary_ok"] is True
    assert boundary["classification"] == "PASS"

    boundary_fail = plugin.validation_provider(
        {
            "mode": "governance_boundary",
            "governance_state": {
                "autonomous_patching_allowed": True,
            },
        }
    )
    assert boundary_fail["governance_boundary_ok"] is False
    assert boundary_fail["classification"] == "FAIL_CLOSED"


def test_cross_target_abstraction_via_registry_negotiation() -> None:
    runtime = PortableRuntimeLayer()

    incompatible = runtime.negotiate_target(
        fingerprint={
            "target_id": "unknown",
            "capabilities": {"supports_amixer": "UNSUPPORTED"},
            "audio_discovery": {"rb3gen2_detected": False},
        },
        target_profile={"target_id": "UNKNOWN"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert incompatible["classification"].startswith("FAIL_CLOSED")

    compatible = runtime.negotiate_target(
        fingerprint=_rb3_fingerprint(),
        target_profile={"target_id": "RB3Gen2"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert compatible["classification"] == "COMPATIBLE"
    assert compatible["selected_target_id"] == "RB3Gen2"
