#!/usr/bin/env python3
"""Multi-domain cognition correlation phase generator.

Unifies runtime/topology/semantic/replay/regression/governance into a single
replay-safe deterministic correlation model.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from aura_sdk.transport.cognition_correlation import (
    CognitionCorrelationRegistry,
    UnifiedCognitionCorrelationEngine,
)
from aura_sdk.transport.cognitive_persistence import AURACognitionRegistry
from aura_sdk.transport.plugins import TargetPluginLoader


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _derive_runtime_evidence(runtime_cognition: dict[str, Any]) -> dict[str, Any]:
    summary = _as_dict(runtime_cognition.get("last_trace_summary"))
    confidence = _as_dict(runtime_cognition.get("confidence"))
    return {
        "run_id": str(summary.get("run_id", "")),
        "process_success": bool(summary.get("process_success", False)),
        "evidence_success": bool(summary.get("evidence_success", False)),
        "playback_completion": bool(summary.get("process_success", False)),
        "classification": str(summary.get("classification", "UNKNOWN")),
        "confidence": confidence,
        "evidence_references": [
            "registry://runtime_cognition/last_trace_summary",
            "registry://runtime_cognition/confidence",
        ],
    }


def _derive_pcm_activity(target_knowledge: dict[str, Any]) -> dict[str, Any]:
    return {
        "pcm_entries": _as_list(target_knowledge.get("cards")),
        "known_pcm_signatures": _as_list(target_knowledge.get("known_pcm_signatures")),
        "active_paths": _as_list(_as_dict(target_knowledge.get("environment")).get("detected_environments")),
        "pcm_signature": "|".join(str(item) for item in _as_list(target_knowledge.get("known_pcm_signatures"))),
    }


def _derive_mixer_state(runtime_cognition: dict[str, Any], target_knowledge: dict[str, Any]) -> dict[str, Any]:
    lock = _as_dict(runtime_cognition.get("procedural_lock"))
    return {
        "controls": _as_list(lock.get("successful_execution_sequence")),
        "active_switches": _as_list(lock.get("degradation_decisions")),
        "mixer_capabilities": _as_dict(target_knowledge.get("capabilities")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate unified multi-domain cognition correlation artifacts")
    parser.add_argument("--output-dir", default="/local/mnt/workspace/AURA_V1/docs/operations/transport")
    parser.add_argument(
        "--registry-path",
        default="/local/mnt/workspace/AURA_V1/docs/operations/transport/aura_cognition_registry.json",
    )
    parser.add_argument("--target-id", default="RB3Gen2")
    parser.add_argument("--lineage-id", default="multi_domain_correlation_v1")
    parser.add_argument("--plugin-registry", default="")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cognition_registry = AURACognitionRegistry(args.registry_path)
    registry_payload = cognition_registry.load()

    runtime_cognition = _as_dict(registry_payload.get("runtime_cognition"))
    topology_cognition = _as_dict(registry_payload.get("topology_cognition"))
    semantic_cognition_state = _as_dict(registry_payload.get("semantic_cognition"))
    semantic_latest = _as_dict(semantic_cognition_state.get("latest"))
    dts_cognition = _as_dict(_as_dict(_as_dict(semantic_latest.get("adapters")).get("dts")).get("semantic_dts"))
    regression_history = [row for row in _as_list(registry_payload.get("regression_lineage")) if isinstance(row, dict)]
    target_knowledge = _as_dict(registry_payload.get("target_knowledge"))
    governance_state = _as_dict(registry_payload.get("governance_state"))

    replay_traces = {
        "semantic_replay": _read_json(output_dir / "semantic_replay_trace.json"),
        "event_replay": _read_json(output_dir / "aura_replay_determinism_report.json"),
        "deterministic_replay_fingerprint": str(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get(
                "deterministic_fingerprint",
                "",
            )
        ),
        "deterministic_event_ordering": bool(
            _as_dict(_read_json(output_dir / "aura_replay_determinism_report.json")).get(
                "event_ordering_stable",
                False,
            )
        ),
    }

    plugin_capability_state = {
        "supported": True,
        "capabilities": _as_dict(target_knowledge.get("capabilities")),
        "known_pcm_signatures": _as_list(target_knowledge.get("known_pcm_signatures")),
        "known_route_fingerprints": _as_list(target_knowledge.get("known_route_fingerprints")),
    }

    previous_confidence_state = {}
    correlation_state = _as_dict(registry_payload.get("cognition_correlation"))
    if correlation_state:
        history = _as_list(correlation_state.get("history"))
        if history:
            latest = _as_dict(history[-1])
            previous_confidence_state = {
                "overall_confidence": latest.get("overall_confidence", 0.0),
                "evidence_completeness": latest.get("evidence_completeness", 0.0),
            }

    runtime_evidence = _derive_runtime_evidence(runtime_cognition)
    pcm_activity = _derive_pcm_activity(target_knowledge)
    mixer_state = _derive_mixer_state(runtime_cognition, target_knowledge)

    loader = TargetPluginLoader(registry_path=args.plugin_registry) if str(args.plugin_registry).strip() else TargetPluginLoader()
    engine = UnifiedCognitionCorrelationEngine(plugin_loader=loader)

    result = engine.correlate(
        target_id=str(args.target_id),
        runtime_evidence=runtime_evidence,
        pcm_activity=pcm_activity,
        mixer_state=mixer_state,
        topology_cognition=topology_cognition,
        dts_cognition=dts_cognition,
        semantic_cognition=semantic_latest,
        replay_traces=replay_traces,
        regression_history=regression_history,
        plugin_capability_state=plugin_capability_state,
        governance_decisions=governance_state,
        lineage_id=str(args.lineage_id),
        evidence_references=[
            "registry://runtime_cognition",
            "registry://topology_cognition",
            "registry://semantic_cognition",
            "registry://regression_lineage",
            "registry://governance_state",
            "artifact://semantic_replay_trace",
            "artifact://aura_replay_determinism_report",
        ],
        previous_confidence_state=previous_confidence_state,
    )

    store = CognitionCorrelationRegistry(
        cognition_registry_path=Path(args.registry_path),
        output_dir=output_dir,
    )
    persisted = store.persist(result.correlation_bundle)
    replay = store.replay(lineage_id=str(args.lineage_id))

    summary = {
        "schema_version": "1.0",
        "phase": "MULTI_DOMAIN_COGNITION_CORRELATION",
        "target_id": str(args.target_id),
        "lineage_id": str(args.lineage_id),
        "correlation_fingerprint": result.correlation_bundle.get("correlation_fingerprint", ""),
        "artifact_files": {
            "unified_cognition_graph": str((output_dir / "unified_cognition_graph.json").resolve()),
            "causal_reasoning_graph": str((output_dir / "causal_reasoning_graph.json").resolve()),
            "evidence_lineage_graph": str((output_dir / "evidence_lineage_graph.json").resolve()),
            "confidence_evolution_report": str((output_dir / "confidence_evolution_report.json").resolve()),
            "anomaly_correlation_report": str((output_dir / "anomaly_correlation_report.json").resolve()),
            "cognition_fusion_trace": str((output_dir / "cognition_fusion_trace.json").resolve()),
        },
        "persisted": persisted,
        "replay": replay,
        "governance_restrictions": {
            "allowed_actions": ["correlate", "classify", "infer", "recommend", "replay", "quarantine"],
            "forbidden_actions": ["fabricate_evidence", "fabricate_causality", "auto_patch", "auto_modify_runtime", "override_governance"],
        },
        "generated_at_epoch": time.time(),
    }

    (output_dir / "multi_domain_cognition_correlation_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
