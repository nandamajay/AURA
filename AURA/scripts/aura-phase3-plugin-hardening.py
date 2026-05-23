#!/usr/bin/env python3
"""Generate Phase-3 plugin hardening artifacts for portable target runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.portable_runtime_layer import PortableRuntimeLayer


def _save_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True), encoding="utf-8")


def _save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(dict(payload), sort_keys=True).encode("utf-8")).hexdigest()


def _sample_fingerprint() -> dict[str, Any]:
    return {
        "target_id": "phase3-sample",
        "capabilities": {
            "supports_amixer": "SUPPORTED",
            "supports_tinymix": "SUPPORTED",
            "supports_procfs": "SUPPORTED",
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
            "amixer_controls": [{"name": "WSA RX0 MUX", "index": 0}],
            "tinymix_controls": [{"control_id": 1, "name": "SpkrLeft PA", "value": "17"}],
        },
        "environment": {
            "primary_environment": "Qualcomm Linux",
            "detected_environments": ["Embedded Linux", "Qualcomm Linux"],
            "confidence": "HIGH",
        },
    }


def _contract_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "contract_name": "aura_target_plugin_contract",
        "required_fields": [
            "target_id",
            "topology_provider",
            "mixer_provider",
            "pcm_provider",
            "route_provider",
            "evidence_provider",
            "capability_provider",
            "validation_provider",
        ],
        "core_runtime_restrictions": [
            "no_target_specific_branching",
            "no_autonomous_mutation",
            "fail_closed_default",
            "deterministic_replay_required",
        ],
        "generated_at_epoch": time.time(),
    }


def _portable_runtime_layer_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "layer_name": "portable_runtime_layer",
        "core_runtime_scope": [
            "cognition_lifecycle",
            "governance",
            "replay",
            "persistence",
            "event_bus",
            "evidence_contracts",
            "orchestration",
        ],
        "plugin_runtime_scope": [
            "target_topology_reasoning",
            "mixer_assumptions",
            "pcm_mapping",
            "route_fingerprints",
            "evidence_interpretation",
            "target_routing_rules",
        ],
        "invariants": {
            "fail_closed": True,
            "no_autonomous_patching": True,
            "no_autonomous_topology_rewriting": True,
            "no_autonomous_runtime_mutation": True,
        },
        "generated_at_epoch": time.time(),
    }


def _negotiation_graph(negotiation: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [{"id": "runtime", "kind": "runtime_layer"}]
    edges: list[dict[str, Any]] = []
    for candidate in negotiation.get("candidate_scores", []):
        target_id = str(candidate.get("target_id", "unknown"))
        node_id = f"plugin:{target_id}"
        nodes.append(
            {
                "id": node_id,
                "kind": "target_plugin",
                "score": candidate.get("score", 0.0),
                "supported": candidate.get("plugin_supported", False),
            }
        )
        edges.append(
            {
                "from": "runtime",
                "to": node_id,
                "relation": "candidate",
                "confidence": candidate.get("score", 0.0),
            }
        )

    selected = str(negotiation.get("selected_target_id", "")).strip()
    if selected:
        edges.append(
            {
                "from": "runtime",
                "to": f"plugin:{selected}",
                "relation": "selected",
                "classification": negotiation.get("classification", "UNKNOWN"),
            }
        )

    return {
        "schema_version": "1.0",
        "graph_name": "target_negotiation_graph",
        "nodes": nodes,
        "edges": edges,
        "generated_at_epoch": time.time(),
    }


def _migration_notes() -> str:
    return """# Phase-3 Plugin Migration Notes

## Objective
Move target-specific cognition from generic runtime into explicit target plugins without destabilizing validated runtime evidence/replay/governance flows.

## What Changed
- Added explicit target plugin contract with required providers.
- Added registry-driven plugin loader and deterministic negotiation.
- Added first formal plugin (`RB3Gen2`).
- Added portable runtime orchestration layer that stays target-agnostic.

## What Did Not Change
- Existing RB3 runtime execution paths remain available.
- Existing governance enforcement logic remains unchanged.
- Existing event lineage, persistence, and replay artifacts remain unchanged.

## Migration Guidance
1. Keep existing RB3 scripts operational while incrementally adopting plugin workflow entrypoints.
2. Register each new target plugin only through registry metadata and contract validation.
3. Enforce fail-closed negotiation for low-confidence target selection.
4. Validate deterministic replay compatibility before execution authorization.
"""


def _plugin_lifecycle_notes() -> str:
    return """# Plugin Lifecycle Documentation

## Lifecycle
1. **Register**: Add plugin metadata to registry with detection + governance constraints.
2. **Load**: Runtime loader resolves module entrypoint and validates contract.
3. **Negotiate**: Evidence-based scoring selects plugin with fail-closed thresholds.
4. **Execute Providers**: Topology/mixer/PCM/route/evidence providers run through plugin API.
5. **Validate**: Replay compatibility + governance boundary checks execute deterministically.
6. **Persist**: Negotiation, workflow metadata, and evidence lineage are persisted.
7. **Replay**: Replay compatibility is re-evaluated before deterministic reconstruction.

## Safety Rules
- No target-specific branching in generic runtime layer.
- No autonomous mutation, patching, or topology rewrite.
- Missing/ambiguous evidence lowers confidence deterministically.
- Unsupported/unknown target selection fails closed.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Phase-3 plugin hardening artifacts")
    parser.add_argument(
        "--output-dir",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport",
    )
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    loader = TargetPluginLoader()
    runtime = PortableRuntimeLayer(loader)

    fingerprint = _sample_fingerprint()
    target_profile = {"target_id": "RB3Gen2", "overlay_id": "qcs6490-audioreach.dtsi"}
    governance_state = {"fail_closed_posture": True}

    negotiation = runtime.negotiate_target(
        fingerprint=fingerprint,
        target_profile=target_profile,
        capability_registry={},
        governance_state=governance_state,
    )

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
    replay_validation = loader.validate_replay_compatibility(
        target_id=str(negotiation.get("selected_target_id", "RB3Gen2")),
        replay_contract=replay_contract,
    )

    rb3_plugin = loader.load_plugin("RB3Gen2")
    rb3_cap = rb3_plugin.capability_provider({"fingerprint": fingerprint})

    artifacts: dict[str, dict[str, Any]] = {
        "aura_plugin_contract.json": _contract_payload(),
        "aura_target_plugin_registry.json": loader.registry,
        "rb3_plugin_capabilities.json": {
            "schema_version": "1.0",
            "target_id": "RB3Gen2",
            "capability_provider_output": rb3_cap,
            "generated_at_epoch": time.time(),
        },
        "portable_runtime_layer.json": _portable_runtime_layer_payload(),
        "plugin_replay_compatibility.json": {
            "schema_version": "1.0",
            "validation": replay_validation,
            "contract": replay_contract,
            "generated_at_epoch": time.time(),
        },
        "target_negotiation_graph.json": _negotiation_graph(negotiation),
    }

    written: dict[str, str] = {}
    fingerprints: dict[str, str] = {}
    for name, payload in artifacts.items():
        path = out / name
        _save_json(path, payload)
        written[name] = str(path.resolve())
        fingerprints[name] = _hash(payload)

    migration_path = out / "phase3_plugin_migration_notes.md"
    lifecycle_path = out / "plugin_lifecycle.md"
    _save_text(migration_path, _migration_notes())
    _save_text(lifecycle_path, _plugin_lifecycle_notes())

    summary = {
        "schema_version": "1.0",
        "phase": "PHASE3_PLUGIN_HARDENING",
        "artifacts": written,
        "fingerprints": fingerprints,
        "docs": {
            "migration_notes": str(migration_path.resolve()),
            "plugin_lifecycle": str(lifecycle_path.resolve()),
        },
        "constraints": {
            "deterministic_replay": True,
            "fail_closed": True,
            "no_autonomous_behavior": True,
            "runtime_core_target_agnostic": True,
        },
        "generated_at_epoch": time.time(),
    }
    summary_path = out / "phase3_plugin_hardening_summary.json"
    _save_json(summary_path, summary)

    print(
        json.dumps(
            {
                "artifacts": written,
                "docs": {
                    "migration_notes": str(migration_path.resolve()),
                    "plugin_lifecycle": str(lifecycle_path.resolve()),
                },
                "summary": str(summary_path.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
