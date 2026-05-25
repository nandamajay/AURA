"""Dependency-aware deterministic runtime pipeline orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from aura_sdk.transport.deterministic_serialization import stable_sha256


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


@dataclass(frozen=True)
class RuntimePipelineStage:
    name: str
    dependencies: tuple[str, ...]
    outputs: tuple[str, ...]
    runtime_sensitive: bool = False


class RuntimePipelineOrchestrator:
    """Plan deterministic queue order with fail-closed dependency checks."""

    def __init__(self, stages: list[RuntimePipelineStage] | None = None) -> None:
        self._stages: dict[str, RuntimePipelineStage] = {}
        for stage in (stages or []):
            self.register_stage(stage)

    def register_stage(self, stage: RuntimePipelineStage) -> None:
        self._stages[stage.name] = stage

    def stage_names(self) -> list[str]:
        return sorted(self._stages.keys())

    def resolve_order(self, requested_stages: list[str] | None = None) -> dict[str, Any]:
        targets = requested_stages[:] if requested_stages else self.stage_names()
        visited: set[str] = set()
        visiting: set[str] = set()
        ordered: list[str] = []
        fail_reasons: list[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                fail_reasons.append(f"dependency_cycle:{name}")
                return
            stage = self._stages.get(name)
            if stage is None:
                fail_reasons.append(f"unknown_stage:{name}")
                return
            visiting.add(name)
            for dep in stage.dependencies:
                visit(dep)
            visiting.remove(name)
            visited.add(name)
            ordered.append(name)

        for name in targets:
            visit(name)

        classification = "FAIL_CLOSED" if fail_reasons else "PASS"
        return {
            "schema_version": "1.0",
            "report_name": "runtime_pipeline_execution_order",
            "generated_at": _utc_now_iso(),
            "classification": classification,
            "fail_closed_reasons": sorted(set(fail_reasons)),
            "ordered_stages": ordered,
            "requested_stages": targets,
            "deterministic_fingerprint": stable_sha256(
                {
                    "ordered_stages": ordered,
                    "requested_stages": sorted(targets),
                    "fail_closed_reasons": sorted(set(fail_reasons)),
                }
            ),
        }

    def incremental_rebuild_plan(
        self,
        *,
        changed_artifacts: list[str],
        cached_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        changed = sorted({str(item) for item in changed_artifacts if str(item).strip()})
        cache = _as_dict(cached_state)
        output_to_stage: dict[str, str] = {}
        for stage in self._stages.values():
            for output in stage.outputs:
                output_to_stage[output] = stage.name

        directly_impacted: set[str] = set()
        for item in changed:
            stage_name = output_to_stage.get(item)
            if stage_name:
                directly_impacted.add(stage_name)

        dependents: dict[str, set[str]] = {name: set() for name in self._stages.keys()}
        for stage in self._stages.values():
            for dep in stage.dependencies:
                dependents.setdefault(dep, set()).add(stage.name)

        queue = list(directly_impacted)
        impacted = set(directly_impacted)
        while queue:
            node = queue.pop(0)
            for dep in sorted(dependents.get(node, set())):
                if dep not in impacted:
                    impacted.add(dep)
                    queue.append(dep)

        order_report = self.resolve_order(sorted(impacted)) if impacted else self.resolve_order([])
        replay_regeneration_required = any(
            stage_name in impacted and self._stages[stage_name].runtime_sensitive for stage_name in impacted
        )

        cache_drift_reasons: list[str] = []
        cache_fingerprint = str(cache.get("deterministic_fingerprint", ""))
        if cache and not cache_fingerprint:
            cache_drift_reasons.append("cache_state_missing_fingerprint")

        classification = "FAIL_CLOSED" if cache_drift_reasons else "PASS"
        return {
            "schema_version": "1.0",
            "report_name": "runtime_incremental_rebuild_plan",
            "generated_at": _utc_now_iso(),
            "classification": classification,
            "fail_closed_reasons": cache_drift_reasons,
            "changed_artifacts": changed,
            "directly_impacted_stages": sorted(directly_impacted),
            "impacted_stages": sorted(impacted),
            "replay_regeneration_required": replay_regeneration_required,
            "execution_order": _as_list(order_report.get("ordered_stages")),
            "cache_state_present": bool(cache),
            "deterministic_fingerprint": stable_sha256(
                {
                    "changed_artifacts": changed,
                    "directly_impacted_stages": sorted(directly_impacted),
                    "impacted_stages": sorted(impacted),
                    "replay_regeneration_required": replay_regeneration_required,
                    "execution_order": _as_list(order_report.get("ordered_stages")),
                    "fail_closed_reasons": cache_drift_reasons,
                }
            ),
        }

    def default_stage_blueprint(self) -> dict[str, Any]:
        stages = []
        for name in self.stage_names():
            stage = self._stages[name]
            stages.append(
                {
                    "name": stage.name,
                    "dependencies": list(stage.dependencies),
                    "outputs": list(stage.outputs),
                    "runtime_sensitive": stage.runtime_sensitive,
                }
            )
        return {
            "schema_version": "1.0",
            "report_name": "runtime_pipeline_stage_blueprint",
            "generated_at": _utc_now_iso(),
            "stages": stages,
            "deterministic_fingerprint": stable_sha256({"stages": stages}),
        }


def build_default_runtime_orchestrator() -> RuntimePipelineOrchestrator:
    orchestrator = RuntimePipelineOrchestrator()
    orchestrator.register_stage(
        RuntimePipelineStage(
            name="runtime_trace_ingestion",
            dependencies=(),
            outputs=("runtime_trace_ingestion_baseline.json", "runtime_trace_ingestion_transformed.json"),
            runtime_sensitive=True,
        )
    )
    orchestrator.register_stage(
        RuntimePipelineStage(
            name="runtime_equivalence",
            dependencies=("runtime_trace_ingestion",),
            outputs=(
                "runtime_equivalence_report.json",
                "runtime_divergence_report.json",
                "runtime_confidence_report.json",
                "runtime_equivalence_fingerprint.json",
                "deterministic_runtime_replay.json",
                "hardware_truth_graph.json",
                "ipc_topology_map.json",
            ),
            runtime_sensitive=True,
        )
    )
    orchestrator.register_stage(
        RuntimePipelineStage(
            name="runtime_governance",
            dependencies=("runtime_equivalence",),
            outputs=(
                "runtime_governance_decision.json",
                "runtime_escalation_report.json",
                "runtime_risk_report.json",
                "runtime_replay_registry.json",
                "replay_consistency_report.json",
            ),
            runtime_sensitive=True,
        )
    )
    orchestrator.register_stage(
        RuntimePipelineStage(
            name="semantic_extraction",
            dependencies=("runtime_governance",),
            outputs=(
                "semantic_entity_graph.json",
                "semantic_relationship_map.json",
                "semantic_ontology.json",
                "semantic_confidence_report.json",
            ),
            runtime_sensitive=False,
        )
    )
    orchestrator.register_stage(
        RuntimePipelineStage(
            name="simulation_governance",
            dependencies=("runtime_governance",),
            outputs=("runtime_promotion_eligibility.json",),
            runtime_sensitive=True,
        )
    )
    return orchestrator
