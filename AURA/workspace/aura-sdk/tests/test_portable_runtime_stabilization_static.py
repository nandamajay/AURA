from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus  # noqa: E402
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine  # noqa: E402
from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry  # noqa: E402
from aura_sdk.transport.plugins import (  # noqa: E402
    PluginIsolationValidator,
    TargetPluginLoader,
    build_simulation_registry_payload,
)
from aura_sdk.transport.portable_runtime_layer import PortableRuntimeLayer  # noqa: E402


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_registry(tmp_path: Path) -> Path:
    registry = build_simulation_registry_payload()
    path = tmp_path / "sim_registry.json"
    _write_json(path, registry)
    return path


def _fingerprint(marker: str, *, missing: bool = False, conflict: bool = False, degraded: bool = False) -> dict:
    capabilities = {} if missing else {"supports_amixer": "SUPPORTED", "supports_tinymix": "SUPPORTED"}
    return {
        "sim_target": marker,
        "capabilities": capabilities,
        "capability_conflict": conflict,
        "degraded_capabilities": degraded,
        "audio_discovery": {"pcm_entries": [{"name": f"{marker}_pcm"}]},
    }


def _replay_contract() -> dict:
    return {
        "sequence_contract": [
            "execution_ordering",
            "timing_windows",
            "route_fingerprint",
            "pcm_signature",
            "evidence_sequence",
            "cleanup_sequence",
        ]
    }


def test_plugin_isolation_validator_reports_core_branching_free() -> None:
    repo_root = REPO_ROOT.parents[2]
    report = PluginIsolationValidator(repo_root).validate()
    assert report["no_target_specific_branching"] is True
    assert report["portable_orchestration_boundaries_ok"] is True


def test_replay_portability_determinism_and_governance_preservation(tmp_path: Path) -> None:
    bus = AURACognitionBus(output_dir=tmp_path)
    for marker, governance in (
        ("fake_target_alpha", "GOVERNED_APPROVED"),
        ("fake_target_beta", "ADVISORY_ONLY"),
        ("degraded_target_gamma", "FAIL_CLOSED"),
    ):
        bus.process_event(
            category="runtime",
            event_name="portable_runtime_simulation",
            originating_agent="runtime_agent",
            target_agent="regression_agent",
            payload={"target_id": marker},
            confidence=0.7,
            governance_classification=governance,
            replay_correlation_id=f"replay-{marker}",
            cognition_lineage_id=f"lineage-{marker}",
        )

    engine = AURAEventReplayEngine(
        lineage_path=tmp_path / "aura_event_lineage.json",
        sync_state_path=tmp_path / "sync.json",
    )
    one = engine.reconstruct()
    two = engine.reconstruct()

    assert one["deterministic_replay_fingerprint"] == two["deterministic_replay_fingerprint"]
    assert one["replay_event_count"] == 3


def test_degraded_capability_negotiation_and_partial_replay_support(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    loader = TargetPluginLoader(registry_path=registry)
    runtime = PortableRuntimeLayer(loader)

    missing = runtime.negotiate_target(
        fingerprint=_fingerprint("alpha", missing=True),
        target_profile={"target_id": "fake_target_alpha"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert missing["classification"].startswith("FAIL_CLOSED")

    conflict = runtime.negotiate_target(
        fingerprint=_fingerprint("alpha", conflict=True),
        target_profile={"target_id": "fake_target_alpha"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert conflict["classification"].startswith("FAIL_CLOSED")

    degraded = runtime.negotiate_target(
        fingerprint=_fingerprint("gamma", degraded=True),
        target_profile={"target_id": "degraded_target_gamma"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert degraded["classification"].startswith("FAIL_CLOSED")

    replay = loader.validate_replay_compatibility(
        target_id="fake_target_beta",
        replay_contract={"sequence_contract": ["execution_ordering", "route_fingerprint"]},
    )
    assert replay["compatibility_level"] in {"PARTIAL", "INCOMPATIBLE"}


def test_quarantine_recovery_preserves_runtime_stability(tmp_path: Path) -> None:
    registry = _make_registry(tmp_path)
    loader = TargetPluginLoader(registry_path=registry)
    runtime = PortableRuntimeLayer(loader)

    before_targets = loader.available_targets()

    invalid = runtime.negotiate_target(
        fingerprint=_fingerprint("invalid"),
        target_profile={"target_id": "invalid_target_quarantined"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert invalid["classification"].startswith("FAIL_CLOSED")
    assert any(item.get("target_id") == "invalid_target_quarantined" for item in loader.quarantine)

    loader.clear_quarantine("invalid_target_quarantined")
    loader.unload_plugin("invalid_target_quarantined")

    recovered = runtime.negotiate_target(
        fingerprint=_fingerprint("alpha"),
        target_profile={"target_id": "fake_target_alpha"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )
    assert recovered["classification"] == "COMPATIBLE"
    assert loader.available_targets() == before_targets


def test_cognition_persistence_integrity_unchanged_by_plugin_quarantine(tmp_path: Path) -> None:
    registry_path = tmp_path / "aura_cognition_registry.json"
    store = AURACognitionRegistry(registry_path)
    initial = store.load()
    store.save(initial)

    before_hash = _hash_file(registry_path)

    sim_registry = _make_registry(tmp_path)
    loader = TargetPluginLoader(registry_path=sim_registry)
    runtime = PortableRuntimeLayer(loader)
    _ = runtime.negotiate_target(
        fingerprint=_fingerprint("invalid"),
        target_profile={"target_id": "invalid_target_quarantined"},
        capability_registry={},
        governance_state={"fail_closed_posture": True},
    )

    after_hash = _hash_file(registry_path)
    assert before_hash == after_hash

    replay = loader.validate_replay_compatibility(
        target_id="fake_target_alpha",
        replay_contract=_replay_contract(),
    )
    assert replay["compatibility_level"] == "FULL"
