#!/usr/bin/env python3
"""Runtime consolidation runner for deterministic contracts/orchestration."""

from __future__ import annotations

import argparse
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
from aura_sdk.transport.runtime_ingestion_contracts import (
    DeterministicCacheSchema,
    RuntimeEvidenceSchema,
    RuntimeGraphSchema,
    RuntimeParserInputContract,
    RuntimeParserOutputContract,
    RuntimeReplaySchema,
)
from aura_sdk.transport.runtime_observability import RuntimeObservabilityCollector
from aura_sdk.transport.runtime_pipeline_orchestrator import build_default_runtime_orchestrator


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in str(value).split(",") if part.strip()]


def main() -> int:
    enforce_runtime_contract("aura-runtime-consolidation")
    parser = argparse.ArgumentParser(description="Generate deterministic runtime consolidation artifacts")
    parser.add_argument(
        "--output-dir",
        default=str((REPO_ROOT.parent / "docs" / "operations" / "transport").resolve()),
    )
    parser.add_argument(
        "--changed-artifacts",
        default="runtime_trace_ingestion_baseline.json,runtime_trace_ingestion_transformed.json",
        help="Comma-separated changed artifacts for incremental plan",
    )
    parser.add_argument(
        "--cache-state",
        default=str((REPO_ROOT.parent / "docs" / "operations" / "transport" / "runtime_deterministic_cache_state.json").resolve()),
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    changed = _split_csv(args.changed_artifacts)
    cache_state = _read_json(Path(args.cache_state))
    collector = RuntimeObservabilityCollector()
    orchestrator = build_default_runtime_orchestrator()

    stage_blueprint = orchestrator.default_stage_blueprint()
    order_report = orchestrator.resolve_order()
    incremental_plan = orchestrator.incremental_rebuild_plan(
        changed_artifacts=changed,
        cached_state=cache_state,
    )

    for item in changed:
        collector.record(
            event_type="ingestion_change_detected",
            severity="INFO",
            component="runtime_orchestrator",
            detail=item,
        )

    if order_report.get("classification") != "PASS":
        collector.record(
            event_type="dependency_scheduler_failure",
            severity="ERROR",
            component="runtime_orchestrator",
            detail=";".join(order_report.get("fail_closed_reasons", [])) or "unknown",
        )

    if incremental_plan.get("classification") != "PASS":
        collector.record(
            event_type="cache_invalidation_failure",
            severity="ERROR",
            component="runtime_orchestrator",
            detail=";".join(incremental_plan.get("fail_closed_reasons", [])) or "unknown",
        )

    replay_triggers = {
        "schema_version": "1.0",
        "report_name": "runtime_replay_regeneration_triggers",
        "classification": "PASS",
        "changed_artifacts": changed,
        "replay_regeneration_required": bool(incremental_plan.get("replay_regeneration_required", False)),
        "triggered_by_stages": list(incremental_plan.get("impacted_stages", [])),
    }
    replay_triggers["deterministic_fingerprint"] = stable_sha256(
        {
            "changed_artifacts": replay_triggers["changed_artifacts"],
            "replay_regeneration_required": replay_triggers["replay_regeneration_required"],
            "triggered_by_stages": replay_triggers["triggered_by_stages"],
        }
    )

    graph_invalidation = {
        "schema_version": "1.0",
        "report_name": "runtime_graph_invalidation_report",
        "classification": "PASS",
        "invalidation_targets": [
            artifact
            for artifact in changed
            if artifact
            in {
                "runtime_trace_ingestion_baseline.json",
                "runtime_trace_ingestion_transformed.json",
                "runtime_equivalence_report.json",
                "hardware_truth_graph.json",
            }
        ],
    }
    graph_invalidation["graph_rebuild_required"] = bool(graph_invalidation["invalidation_targets"])
    graph_invalidation["deterministic_fingerprint"] = stable_sha256(
        {
            "invalidation_targets": graph_invalidation["invalidation_targets"],
            "graph_rebuild_required": graph_invalidation["graph_rebuild_required"],
        }
    )

    contracts_catalog = {
        "schema_version": "1.0",
        "report_name": "runtime_ingestion_contract_catalog",
        "classification": "PASS",
        "contracts": {
            "RuntimeParserInputContract": RuntimeParserInputContract.model_json_schema(),
            "RuntimeParserOutputContract": RuntimeParserOutputContract.model_json_schema(),
            "RuntimeGraphSchema": RuntimeGraphSchema.model_json_schema(),
            "RuntimeEvidenceSchema": RuntimeEvidenceSchema.model_json_schema(),
            "RuntimeReplaySchema": RuntimeReplaySchema.model_json_schema(),
            "DeterministicCacheSchema": DeterministicCacheSchema.model_json_schema(),
        },
    }
    contracts_catalog["deterministic_fingerprint"] = stable_sha256(
        {"contracts": contracts_catalog["contracts"]}
    )

    cache_schema = {
        "schema_version": "1.0",
        "report_name": "runtime_deterministic_cache_schema",
        "classification": "PASS",
        "model_schema": DeterministicCacheSchema.model_json_schema(),
    }
    cache_schema["deterministic_fingerprint"] = stable_sha256(
        {"model_schema": cache_schema["model_schema"]}
    )

    observability = collector.as_report()

    dump_canonical_json(output_dir / "runtime_stage_blueprint.json", stage_blueprint)
    dump_canonical_json(output_dir / "runtime_execution_order.json", order_report)
    dump_canonical_json(output_dir / "runtime_incremental_rebuild_plan.json", incremental_plan)
    dump_canonical_json(output_dir / "runtime_replay_regeneration_triggers.json", replay_triggers)
    dump_canonical_json(output_dir / "runtime_graph_invalidation_report.json", graph_invalidation)
    dump_canonical_json(output_dir / "runtime_ingestion_contract_catalog.json", contracts_catalog)
    dump_canonical_json(output_dir / "runtime_deterministic_cache_schema.json", cache_schema)
    dump_canonical_json(output_dir / "runtime_observability_report.json", observability)

    summary = {
        "schema_version": "1.0",
        "report_name": "runtime_consolidation_summary",
        "classification": "FAIL_CLOSED"
        if (
            order_report.get("classification") != "PASS"
            or incremental_plan.get("classification") != "PASS"
            or observability.get("classification") != "PASS"
        )
        else "PASS",
        "artifacts": {
            "runtime_stage_blueprint": str((output_dir / "runtime_stage_blueprint.json").resolve()),
            "runtime_execution_order": str((output_dir / "runtime_execution_order.json").resolve()),
            "runtime_incremental_rebuild_plan": str((output_dir / "runtime_incremental_rebuild_plan.json").resolve()),
            "runtime_replay_regeneration_triggers": str((output_dir / "runtime_replay_regeneration_triggers.json").resolve()),
            "runtime_graph_invalidation_report": str((output_dir / "runtime_graph_invalidation_report.json").resolve()),
            "runtime_ingestion_contract_catalog": str((output_dir / "runtime_ingestion_contract_catalog.json").resolve()),
            "runtime_deterministic_cache_schema": str((output_dir / "runtime_deterministic_cache_schema.json").resolve()),
            "runtime_observability_report": str((output_dir / "runtime_observability_report.json").resolve()),
        },
    }
    summary["deterministic_fingerprint"] = stable_sha256(summary)
    dump_canonical_json(output_dir / "runtime_consolidation_summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
