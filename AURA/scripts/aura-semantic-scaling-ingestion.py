#!/usr/bin/env python3
"""Large-scale semantic ingestion runner for Linux audio source trees."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "workspace" / "aura-sdk" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from aura_sdk.transport.deterministic_serialization import dump_canonical_json, stable_sha256
from aura_sdk.transport.runtime_execution_contract import enforce_runtime_contract
from aura_sdk.transport.semantic_scaling_ingestion_engine import SemanticScalingIngestionEngine


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _write_alias_artifacts(output_dir: Path, result: Any) -> dict[str, str]:
    discovery = _as_dict(result.discovery_registry)
    registry = _as_dict(discovery.get("registry"))
    lineage_id = str(discovery.get("lineage_id", "semantic_scaling_unknown"))
    topology = _as_dict(result.topology_model)
    stream_paths = _as_dict(result.stream_path_relationships)
    behavioral_timeline = _as_dict(result.behavioral_replay_timeline)
    behavioral_state = _as_dict(result.behavioral_state_graph)
    power_sequence = _as_dict(result.power_sequence_graph)
    stream_intelligence = _as_dict(result.stream_intelligence_report)
    governance_confidence = _as_dict(result.governance_confidence_report)

    codec_graph = {
        "schema_version": "1.0",
        "graph_name": "codec_graph",
        "lineage_id": lineage_id,
        "codecs": sorted(str(item) for item in _as_list(registry.get("codecs")) if str(item).strip()),
        "machine_drivers": sorted(
            str(item) for item in _as_list(registry.get("machine_drivers")) if str(item).strip()
        ),
        "classification": "PASS" if _as_list(registry.get("codecs")) else "FAIL_CLOSED",
    }
    if codec_graph["classification"] != "PASS":
        codec_graph["fail_closed_reasons"] = ["no_codec_candidates_discovered"]
    codec_graph["deterministic_fingerprint"] = stable_sha256(codec_graph)

    dapm_topology_graph = {
        "schema_version": "1.0",
        "graph_name": "dapm_topology_graph",
        "lineage_id": lineage_id,
        "widgets": _as_list(topology.get("widgets")),
        "routes": _as_list(topology.get("routes")),
        "playback_paths": _as_list(stream_paths.get("playback_paths")),
        "capture_paths": _as_list(stream_paths.get("capture_paths")),
        "classification": str(topology.get("classification", "FAIL_CLOSED")),
        "fail_closed_reasons": _as_list(topology.get("fail_closed_reasons")),
    }
    dapm_topology_graph["deterministic_fingerprint"] = stable_sha256(dapm_topology_graph)

    control_relationships = {
        "schema_version": "1.0",
        "graph_name": "control_relationships",
        "lineage_id": lineage_id,
        "controls": sorted(str(item) for item in _as_list(registry.get("controls")) if str(item).strip()),
        "edges": _as_list(_as_dict(result.control_propagation_graph).get("edges")),
        "classification": "PASS",
    }
    control_relationships["deterministic_fingerprint"] = stable_sha256(control_relationships)

    macro_dependencies = {
        "schema_version": "1.0",
        "graph_name": "macro_dependencies",
        "lineage_id": lineage_id,
        "edges": _as_list(_as_dict(result.macro_lineage_graph).get("edges")),
        "classification": "PASS",
    }
    macro_dependencies["deterministic_fingerprint"] = stable_sha256(macro_dependencies)

    call_graph = {
        "schema_version": "1.0",
        "graph_name": "call_graph",
        "lineage_id": lineage_id,
        "edges": _as_list(_as_dict(result.function_call_graph).get("edges")),
        "classification": "PASS",
    }
    call_graph["deterministic_fingerprint"] = stable_sha256(call_graph)

    stream_routing = {
        "schema_version": "1.0",
        "graph_name": "stream_routing",
        "lineage_id": lineage_id,
        "stream_paths": sorted(
            str(item) for item in _as_list(registry.get("stream_paths")) if str(item).strip()
        ),
        "playback_paths": _as_list(stream_paths.get("playback_paths")),
        "capture_paths": _as_list(stream_paths.get("capture_paths")),
        "classification": "PASS"
        if _as_list(stream_paths.get("playback_paths")) or _as_list(stream_paths.get("capture_paths"))
        else "FAIL_CLOSED",
    }
    if stream_routing["classification"] != "PASS":
        stream_routing["fail_closed_reasons"] = ["no_stream_paths_reconstructed"]
    stream_routing["deterministic_fingerprint"] = stable_sha256(stream_routing)

    subsystem_lineage = {
        "schema_version": "1.0",
        "report_name": "subsystem_lineage",
        "lineage_id": lineage_id,
        "entries": [
            {"subsystem": key, "files": value}
            for key, value in sorted(_as_dict(discovery.get("subsystem_groups")).items())
        ],
        "classification": "PASS"
        if _as_dict(discovery.get("subsystem_groups"))
        else "FAIL_CLOSED",
    }
    if subsystem_lineage["classification"] != "PASS":
        subsystem_lineage["fail_closed_reasons"] = ["no_subsystem_groups_discovered"]
    subsystem_lineage["deterministic_fingerprint"] = stable_sha256(subsystem_lineage)

    activation_timelines = {
        "schema_version": "1.0",
        "report_name": "activation_timelines",
        "lineage_id": lineage_id,
        "events": _as_list(behavioral_timeline.get("route_transition_events"))
        + _as_list(behavioral_timeline.get("lifecycle_transition_events")),
        "classification": str(behavioral_timeline.get("classification", "FAIL_CLOSED")),
    }
    activation_timelines["deterministic_fingerprint"] = stable_sha256(activation_timelines)

    state_transition_graph = {
        "schema_version": "1.0",
        "graph_name": "state_transition_graph",
        "lineage_id": lineage_id,
        "edges": _as_list(behavioral_state.get("edges")),
        "classification": "PASS" if _as_list(behavioral_state.get("edges")) else "FAIL_CLOSED",
    }
    if state_transition_graph["classification"] != "PASS":
        state_transition_graph["fail_closed_reasons"] = ["no_state_transition_edges"]
    state_transition_graph["deterministic_fingerprint"] = stable_sha256(state_transition_graph)

    power_propagation_graph = {
        "schema_version": "1.0",
        "graph_name": "power_propagation_graph",
        "lineage_id": lineage_id,
        "edges": _as_list(power_sequence.get("edges")),
        "classification": "PASS" if _as_list(power_sequence.get("edges")) else "FAIL_CLOSED",
    }
    if power_propagation_graph["classification"] != "PASS":
        power_propagation_graph["fail_closed_reasons"] = ["no_power_sequence_edges"]
    power_propagation_graph["deterministic_fingerprint"] = stable_sha256(power_propagation_graph)

    mappings = {
        "codec_graph.json": codec_graph,
        "dapm_topology_graph.json": dapm_topology_graph,
        "control_relationships.json": control_relationships,
        "macro_dependencies.json": macro_dependencies,
        "call_graph.json": call_graph,
        "stream_routing.json": stream_routing,
        "subsystem_lineage.json": subsystem_lineage,
        "activation_timelines.json": activation_timelines,
        "state_transition_graph.json": state_transition_graph,
        "power_propagation_graph.json": power_propagation_graph,
        "stream_intelligence_report.json": stream_intelligence,
        "governance_confidence_report.json": governance_confidence,
    }
    written: dict[str, str] = {}
    for name, payload in mappings.items():
        path = output_dir / name
        dump_canonical_json(path, payload)
        written[name] = str(path.resolve())
    return written


def main() -> int:
    enforce_runtime_contract("aura-semantic-scaling-ingestion")
    parser = argparse.ArgumentParser(description="Run deterministic large-scale semantic ingestion")
    parser.add_argument(
        "--source-root",
        default=str(
            (
                REPO_ROOT.parent
                / "evidence"
                / "wcd937x_real_study_20260519_062557"
                / "repos"
                / "linux-upstream-v6.18"
            ).resolve()
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=str((REPO_ROOT.parent / "docs" / "operations" / "transport").resolve()),
    )
    parser.add_argument(
        "--cache-file",
        default=str(
            (
                REPO_ROOT.parent
                / "docs"
                / "operations"
                / "transport"
                / "semantic_cache_state.json"
            ).resolve()
        ),
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-paths", type=int, default=200000)
    parser.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Repeatable evidence reference",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = asyncio.run(
        SemanticScalingIngestionEngine().run(
            source_root=Path(args.source_root).resolve(),
            output_dir=output_dir,
            cache_file=Path(args.cache_file).resolve(),
            max_paths=max(1, int(args.max_paths)),
            workers=max(1, int(args.workers)),
            evidence_references=list(args.evidence_ref),
        )
    )

    alias_paths = _write_alias_artifacts(output_dir, result)
    summary = {
        "schema_version": "1.0",
        "phase": "LARGE_SCALE_SEMANTIC_INGESTION_EXPANSION",
        "classification": str(_as_dict(result.summary).get("classification", "FAIL_CLOSED")),
        "lineage_id": str(_as_dict(result.summary).get("lineage_id", "")),
        "source_root": str(Path(args.source_root).resolve()),
        "file_count": int(_as_dict(result.summary).get("file_count", 0)),
        "changed_file_count": int(_as_dict(result.summary).get("changed_file_count", 0)),
        "reparsed_file_count": int(_as_dict(result.summary).get("reparsed_file_count", 0)),
        "cache_reuse_ratio": float(_as_dict(result.summary).get("cache_reuse_ratio", 0.0)),
        "topology_classification": str(
            _as_dict(result.summary).get("topology_classification", "UNKNOWN")
        ),
        "simulation_classification": str(
            _as_dict(result.summary).get("simulation_classification", "UNKNOWN")
        ),
        "fail_closed_reasons": sorted(
            set(
                [str(item) for item in _as_list(_as_dict(result.summary).get("fail_closed_reasons"))]
                + [
                    str(item)
                    for item in _as_list(_as_dict(result.failure_diagnostics).get("replay_mismatches"))
                ]
            )
        ),
        "artifacts": {
            "semantic_driver_discovery_registry": str(
                (output_dir / "semantic_driver_discovery_registry.json").resolve()
            ),
            "semantic_incremental_ingestion_report": str(
                (output_dir / "semantic_incremental_ingestion_report.json").resolve()
            ),
            "semantic_include_dependency_graph": str(
                (output_dir / "semantic_include_dependency_graph.json").resolve()
            ),
            "semantic_function_call_graph": str(
                (output_dir / "semantic_function_call_graph.json").resolve()
            ),
            "semantic_macro_lineage_graph": str(
                (output_dir / "semantic_macro_lineage_graph.json").resolve()
            ),
            "semantic_dapm_route_graph": str((output_dir / "semantic_dapm_route_graph.json").resolve()),
            "semantic_clock_dependency_graph": str(
                (output_dir / "semantic_clock_dependency_graph.json").resolve()
            ),
            "semantic_control_propagation_graph": str(
                (output_dir / "semantic_control_propagation_graph.json").resolve()
            ),
            "semantic_subsystem_ownership_graph": str(
                (output_dir / "semantic_subsystem_ownership_graph.json").resolve()
            ),
            "semantic_stream_path_relationships": str(
                (output_dir / "semantic_stream_path_relationships.json").resolve()
            ),
            "semantic_backend_frontend_dai_graph": str(
                (output_dir / "semantic_backend_frontend_dai_graph.json").resolve()
            ),
            "semantic_inter_driver_dependency_graph": str(
                (output_dir / "semantic_inter_driver_dependency_graph.json").resolve()
            ),
            "semantic_behavioral_state_graph": str(
                (output_dir / "semantic_behavioral_state_graph.json").resolve()
            ),
            "semantic_activation_order_graph": str(
                (output_dir / "semantic_activation_order_graph.json").resolve()
            ),
            "semantic_runtime_causality_graph": str(
                (output_dir / "semantic_runtime_causality_graph.json").resolve()
            ),
            "semantic_power_sequence_graph": str(
                (output_dir / "semantic_power_sequence_graph.json").resolve()
            ),
            "semantic_dapm_behavioral_model": str(
                (output_dir / "semantic_dapm_behavioral_model.json").resolve()
            ),
            "semantic_behavioral_replay_timeline": str(
                (output_dir / "semantic_behavioral_replay_timeline.json").resolve()
            ),
            "semantic_stream_intelligence_report": str(
                (output_dir / "semantic_stream_intelligence_report.json").resolve()
            ),
            "semantic_governance_confidence_report": str(
                (output_dir / "semantic_governance_confidence_report.json").resolve()
            ),
            "semantic_topology_model": str((output_dir / "semantic_topology_model.json").resolve()),
            "semantic_runtime_replay_simulation": str(
                (output_dir / "semantic_runtime_replay_simulation.json").resolve()
            ),
            "semantic_simulation_transition_log": str(
                (output_dir / "semantic_simulation_transition_log.json").resolve()
            ),
            "semantic_failure_diagnostics": str(
                (output_dir / "semantic_failure_diagnostics.json").resolve()
            ),
            "semantic_scaling_summary": str((output_dir / "semantic_scaling_summary.json").resolve()),
            **alias_paths,
        },
    }
    summary["deterministic_fingerprint"] = stable_sha256(summary)
    dump_canonical_json(output_dir / "semantic_scaling_ingestion_summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
