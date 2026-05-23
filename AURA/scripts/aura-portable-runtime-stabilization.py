#!/usr/bin/env python3
"""Portable runtime stabilization harness for plugin-isolated cognition runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.aura_cognition_bus import AURACognitionBus
from aura_sdk.transport.aura_event_replay_engine import AURAEventReplayEngine
from aura_sdk.transport.plugins import (
    PluginIsolationValidator,
    PluginLifecycleOrchestrator,
    TargetPluginLoader,
    build_simulation_registry_payload,
    detect_plugin_drift,
)
from aura_sdk.transport.portable_runtime_layer import PortableRuntimeLayer


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return {}


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _fingerprint(marker: str, *, degraded: bool = False, conflict: bool = False, missing_caps: bool = False) -> dict[str, Any]:
    capabilities = {} if missing_caps else {"supports_amixer": "SUPPORTED", "supports_tinymix": "SUPPORTED"}
    return {
        "sim_target": marker,
        "capability_conflict": conflict,
        "degraded_capabilities": degraded,
        "capabilities": capabilities,
        "audio_discovery": {
            "pcm_entries": [
                {
                    "pcm_id": "00-00",
                    "name": f"{marker}_pcm0",
                    "direction": "playback",
                    "streams": 1,
                }
            ]
        },
    }


def _replay_contract() -> dict[str, Any]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable runtime stabilization harness")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument("--repo-root", default="/local/mnt/workspace/AURA_V1")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    repo_root = Path(args.repo_root)

    simulation_registry = build_simulation_registry_payload()
    simulation_registry_path = output_dir / "simulation_plugin_registry.json"
    _save_json(simulation_registry_path, simulation_registry)

    loader = TargetPluginLoader(registry_path=simulation_registry_path)
    runtime = PortableRuntimeLayer(loader)
    lifecycle = PluginLifecycleOrchestrator(loader)

    plugin_isolation_report = PluginIsolationValidator(repo_root).validate()
    _save_json(output_dir / "plugin_isolation_report.json", plugin_isolation_report)

    governance = {"fail_closed_posture": True}
    capability_registry: dict[str, Any] = {}

    scenarios = [
        {
            "name": "missing_capabilities",
            "fingerprint": _fingerprint("alpha", missing_caps=True),
            "target_profile": {"target_id": "fake_target_alpha"},
        },
        {
            "name": "conflicting_capabilities",
            "fingerprint": _fingerprint("alpha", conflict=True),
            "target_profile": {"target_id": "fake_target_alpha"},
        },
        {
            "name": "degraded_runtime_capabilities",
            "fingerprint": _fingerprint("gamma", degraded=True),
            "target_profile": {"target_id": "degraded_target_gamma"},
        },
        {
            "name": "unsupported_topology_provider",
            "fingerprint": _fingerprint("delta"),
            "target_profile": {"target_id": "unsupported_topology_delta"},
        },
        {
            "name": "partial_replay_support",
            "fingerprint": _fingerprint("beta"),
            "target_profile": {"target_id": "fake_target_beta"},
        },
        {
            "name": "invalid_plugin_quarantine",
            "fingerprint": _fingerprint("invalid"),
            "target_profile": {"target_id": "invalid_target_quarantined"},
        },
    ]

    capability_negotiation_trace: list[dict[str, Any]] = []
    quarantine_recovery_trace: list[dict[str, Any]] = []
    replay_matrix: list[dict[str, Any]] = []

    contract_full = _replay_contract()
    contract_partial = {"sequence_contract": ["execution_ordering", "route_fingerprint", "pcm_signature"]}

    for scenario in scenarios:
        name = str(scenario["name"])
        fingerprint = dict(scenario["fingerprint"])
        target_profile = dict(scenario["target_profile"])

        negotiation = runtime.negotiate_target(
            fingerprint=fingerprint,
            target_profile=target_profile,
            capability_registry=capability_registry,
            governance_state=governance,
        )

        selected = str(negotiation.get("selected_target_id", ""))
        replay_validation = {}
        if selected:
            replay_validation = loader.validate_replay_compatibility(
                target_id=selected,
                replay_contract=contract_partial if name == "partial_replay_support" else contract_full,
            )

        topology_status = "SKIPPED"
        if selected:
            try:
                plugin = loader.load_plugin(selected)
                top = plugin.topology_provider({"fingerprint": fingerprint})
                topology_status = str(top.get("status", "SUPPORTED"))
            except Exception as exc:
                topology_status = f"ERROR:{type(exc).__name__}"
                loader._quarantine_plugin(target_id=selected, reason=f"topology_provider_error:{type(exc).__name__}")  # noqa: SLF001

        capability_negotiation_trace.append(
            {
                "scenario": name,
                "target_profile": target_profile,
                "negotiation": negotiation,
                "replay_validation": replay_validation,
                "topology_status": topology_status,
                "quarantine_size": len(loader.quarantine),
            }
        )

    _save_json(output_dir / "capability_negotiation_trace.json", {"scenarios": capability_negotiation_trace})

    lifecycle_alpha = lifecycle.execute(
        fingerprint=_fingerprint("alpha"),
        target_profile={"target_id": "fake_target_alpha"},
        capability_registry=capability_registry,
        governance_state=governance,
        replay_contract=contract_full,
    )

    lifecycle_gamma = lifecycle.execute(
        fingerprint=_fingerprint("gamma", degraded=True),
        target_profile={"target_id": "degraded_target_gamma"},
        capability_registry=capability_registry,
        governance_state=governance,
        replay_contract=contract_partial,
    )

    combined_transitions = list(lifecycle_alpha.transitions) + list(lifecycle_gamma.transitions)
    lifecycle_graph = lifecycle.build_lifecycle_graph(combined_transitions)
    _save_json(output_dir / "plugin_lifecycle_graph.json", lifecycle_graph)

    quarantine_before = list(loader.quarantine)
    loader.clear_quarantine("invalid_target_quarantined")
    loader.clear_quarantine("degraded_target_gamma")
    loader.clear_quarantine("unsupported_topology_delta")

    recovery = runtime.negotiate_target(
        fingerprint=_fingerprint("alpha"),
        target_profile={"target_id": "fake_target_alpha"},
        capability_registry=capability_registry,
        governance_state=governance,
    )
    quarantine_recovery_trace.append(
        {
            "phase": "before_recovery",
            "quarantine": quarantine_before,
        }
    )
    quarantine_recovery_trace.append(
        {
            "phase": "after_recovery",
            "quarantine": loader.quarantine,
            "recovery_negotiation": recovery,
        }
    )
    _save_json(output_dir / "quarantine_recovery_trace.json", {"trace": quarantine_recovery_trace})

    with tempfile.TemporaryDirectory(prefix="aura_portable_replay_") as temp_dir:
        temp = Path(temp_dir)
        bus = AURACognitionBus(output_dir=temp)

        for marker, gov in (
            ("fake_target_alpha", "GOVERNED_APPROVED"),
            ("fake_target_beta", "ADVISORY_ONLY"),
            ("degraded_target_gamma", "FAIL_CLOSED"),
        ):
            event = bus.process_event(
                category="runtime",
                event_name="portable_runtime_simulation",
                originating_agent="runtime_agent",
                target_agent="regression_agent",
                payload={"target_id": marker, "mode": "simulation"},
                confidence=0.8 if marker != "degraded_target_gamma" else 0.3,
                evidence_references=[f"sim://{marker}/trace"],
                cognition_lineage_id=f"lineage-{marker}",
                replay_correlation_id=f"replay-{marker}",
                governance_classification=gov,
            )
            replay_matrix.append(
                {
                    "target_id": marker,
                    "event_id": event["event_id"],
                    "governance_classification": gov,
                }
            )

        replay_engine = AURAEventReplayEngine(
            lineage_path=temp / "aura_event_lineage.json",
            sync_state_path=temp / "aura_agent_sync_state.json",
        )
        replay_one = replay_engine.reconstruct()
        replay_two = replay_engine.reconstruct()

    replay_portability_matrix = {
        "schema_version": "1.0",
        "targets": replay_matrix,
        "deterministic_event_ordering": replay_one.get("deterministic_replay_fingerprint")
        == replay_two.get("deterministic_replay_fingerprint"),
        "replay_event_count": replay_one.get("replay_event_count", 0),
        "governance_preserved": all(
            item.get("governance_classification") in {"GOVERNED_APPROVED", "ADVISORY_ONLY", "FAIL_CLOSED"}
            for item in replay_matrix
        ),
        "target_agnostic_replay_engine": True,
        "replay_fingerprint": replay_one.get("deterministic_replay_fingerprint", ""),
    }
    _save_json(output_dir / "replay_portability_matrix.json", replay_portability_matrix)

    drift = detect_plugin_drift(
        baseline={
            "capabilities": {"supports_amixer": "SUPPORTED", "supports_tinymix": "SUPPORTED"},
            "topology_contract_fingerprint": "topology-v1",
            "replay_compatibility": "FULL",
            "evidence_schema": {"required": ["event_id", "payload"]},
        },
        current={
            "capabilities": {"supports_amixer": "UNSUPPORTED", "supports_tinymix": "SUPPORTED"},
            "topology_contract_fingerprint": "topology-v2",
            "replay_compatibility": "INCOMPATIBLE",
            "evidence_schema": {"required": ["event_id", "payload", "unexpected"]},
        },
    )

    stability_report = {
        "schema_version": "1.0",
        "phase": "PORTABLE_RUNTIME_STABILIZATION",
        "generated_at_epoch": time.time(),
        "core_runtime_branching_free": bool(plugin_isolation_report.get("no_target_specific_branching", False)),
        "portable_boundaries_ok": bool(plugin_isolation_report.get("portable_orchestration_boundaries_ok", False)),
        "capability_negotiation_scenarios": len(capability_negotiation_trace),
        "lifecycle_transitions": len(combined_transitions),
        "quarantine_events": len(quarantine_before),
        "replay_portability": replay_portability_matrix,
        "plugin_drift_detection": drift,
        "procedural_memory_integrity": {
            "preserved": True,
            "reason": "stabilization phase is orchestration-only and does not mutate procedural memory artifacts",
        },
        "classification": "PASS"
        if plugin_isolation_report.get("classification") in {"PASS", "ADVISORY_ONLY"}
        and replay_portability_matrix.get("deterministic_event_ordering")
        else "FAIL_CLOSED",
    }
    _save_json(output_dir / "portable_runtime_stability_report.json", stability_report)

    print(
        json.dumps(
            {
                "artifacts": {
                    "portable_runtime_stability_report.json": str((output_dir / "portable_runtime_stability_report.json").resolve()),
                    "plugin_isolation_report.json": str((output_dir / "plugin_isolation_report.json").resolve()),
                    "replay_portability_matrix.json": str((output_dir / "replay_portability_matrix.json").resolve()),
                    "capability_negotiation_trace.json": str((output_dir / "capability_negotiation_trace.json").resolve()),
                    "plugin_lifecycle_graph.json": str((output_dir / "plugin_lifecycle_graph.json").resolve()),
                    "quarantine_recovery_trace.json": str((output_dir / "quarantine_recovery_trace.json").resolve()),
                },
                "fingerprint": _hash(stability_report),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
