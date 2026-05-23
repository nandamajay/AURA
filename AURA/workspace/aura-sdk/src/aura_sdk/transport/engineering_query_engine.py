"""Engineering Investigation and Query Reasoning Layer orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.causality_query_planner import (
    CausalityQueryPlanResult,
    plan_causality_query,
)
from aura_sdk.transport.engineering_query_history import (
    EngineeringQueryHistoryResult,
    update_engineering_query_history,
)
from aura_sdk.transport.investigation_reasoner import (
    InvestigationReasoningResult,
    synthesize_investigation_reasoning,
)
from aura_sdk.transport.migration_question_resolver import (
    MigrationQuestionResolutionResult,
    resolve_migration_question,
)
from aura_sdk.transport.patch_reasoning_resolver import (
    PatchReasoningResolutionResult,
    resolve_patch_reasoning_question,
)
from aura_sdk.transport.plugins import TargetPluginLoader
from aura_sdk.transport.reasoning_lineage_tracker import (
    ReasoningLineageResult,
    build_reasoning_lineage,
)
from aura_sdk.transport.replay_evidence_resolver import (
    ReplayEvidenceResolutionResult,
    resolve_replay_evidence_question,
)
from aura_sdk.transport.runtime_question_resolver import (
    RuntimeQuestionResolutionResult,
    resolve_runtime_question,
)
from aura_sdk.transport.semantic_fingerprint import stable_fingerprint
from aura_sdk.transport.topology_question_resolver import (
    TopologyQuestionResolutionResult,
    resolve_topology_question,
)


@dataclass(frozen=True)
class EngineeringQueryEngineResult:
    investigation_bundle: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
            "ok",
            "pass",
            "success",
            "supported",
        }
    return False


def _governance_clean(governance_state: Mapping[str, Any]) -> bool:
    governance = _as_dict(governance_state)
    if not bool(governance.get("fail_closed_posture", True)):
        return False
    for flag in (
        "autonomous_patching_allowed",
        "autonomous_topology_rewrite_allowed",
        "autonomous_runtime_mutation_allowed",
        "autonomous_upstream_generation_allowed",
    ):
        if _is_true(governance.get(flag, False)):
            return False
    return True


class EngineeringQueryEngine:
    """Pluggable, deterministic engineering investigation engine."""

    def __init__(self, plugin_loader: TargetPluginLoader | None = None):
        self._plugins = plugin_loader or TargetPluginLoader()

    def analyze(
        self,
        *,
        target_id: str,
        session_id: str,
        lineage_id: str,
        question: str,
        runtime_artifacts: Mapping[str, Any],
        topology_artifacts: Mapping[str, Any],
        migration_artifacts: Mapping[str, Any],
        patch_artifacts: Mapping[str, Any],
        semantic_artifacts: Mapping[str, Any],
        structural_artifacts: Mapping[str, Any],
        incident_artifacts: Mapping[str, Any],
        fusion_artifacts: Mapping[str, Any],
        replay_artifacts: Mapping[str, Any],
        confidence_artifacts: Mapping[str, Any],
        governance_state: Mapping[str, Any],
        replay_traces: Mapping[str, Any],
        plugin_capability_state: Mapping[str, Any],
        evidence_references: list[str] | None,
        previous_query_history: list[Mapping[str, Any]] | None,
        previous_reasoning_lineage: list[Mapping[str, Any]] | None,
    ) -> EngineeringQueryEngineResult:
        plugin = self._plugins.load_plugin(target_id)

        runtime_adapter = _as_dict(
            plugin.runtime_evidence_adapter(
                {
                    "runtime_evidence": _as_dict(runtime_artifacts.get("runtime_truth_graph")),
                    "pcm_activity": _as_dict(runtime_artifacts.get("pcm_lifecycle_trace")),
                    "mixer_state": _as_dict(runtime_artifacts.get("pcm_runtime_state")),
                    "replay_traces": dict(replay_traces),
                    "governance_decisions": dict(governance_state),
                }
            )
        )
        topology_adapter = _as_dict(
            plugin.topology_evidence_adapter(
                {
                    "topology_cognition": _as_dict(topology_artifacts.get("topology_runtime_graph")),
                    "dts_cognition": _as_dict(semantic_artifacts.get("dts_topology_graph")),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )
        semantic_adapter = _as_dict(
            plugin.semantic_evidence_adapter(
                {
                    "semantic_cognition": _as_dict(semantic_artifacts.get("semantic_confidence_report")),
                    "regression_history": _as_list(previous_query_history or []),
                    "plugin_capability_state": dict(plugin_capability_state),
                }
            )
        )

        evidence = [str(item) for item in (evidence_references or []) if str(item).strip()]

        available_domains = {
            "runtime": _as_dict(runtime_artifacts),
            "topology": _as_dict(topology_artifacts),
            "migration": _as_dict(migration_artifacts),
            "patch": _as_dict(patch_artifacts),
            "semantic": _as_dict(semantic_artifacts),
            "structural": _as_dict(structural_artifacts),
            "replay": _as_dict(replay_artifacts),
        }

        plan_result: CausalityQueryPlanResult = plan_causality_query(
            question=str(question),
            governance_state=governance_state,
            available_domains=available_domains,
            evidence_references=evidence,
        )
        plan = plan_result.causality_query_plan

        resolver_outputs: dict[str, dict[str, Any]] = {}

        if "runtime_question_resolver" in _as_list(plan.get("resolver_order")):
            runtime_result: RuntimeQuestionResolutionResult = resolve_runtime_question(
                target_id=target_id,
                question=str(question),
                runtime_artifacts=runtime_artifacts,
                incident_artifacts=incident_artifacts,
                evidence_references=evidence,
            )
            resolver_outputs["runtime_question_resolver"] = runtime_result.runtime_question_resolution

        if "migration_question_resolver" in _as_list(plan.get("resolver_order")):
            migration_result: MigrationQuestionResolutionResult = resolve_migration_question(
                target_id=target_id,
                question=str(question),
                migration_artifacts=migration_artifacts,
                evidence_references=evidence,
            )
            resolver_outputs["migration_question_resolver"] = migration_result.migration_question_resolution

        if "topology_question_resolver" in _as_list(plan.get("resolver_order")):
            topology_result: TopologyQuestionResolutionResult = resolve_topology_question(
                target_id=target_id,
                question=str(question),
                topology_artifacts=topology_artifacts,
                runtime_artifacts=runtime_artifacts,
                incident_artifacts=incident_artifacts,
                evidence_references=evidence,
            )
            resolver_outputs["topology_question_resolver"] = topology_result.topology_question_resolution

        if "patch_reasoning_resolver" in _as_list(plan.get("resolver_order")):
            patch_result: PatchReasoningResolutionResult = resolve_patch_reasoning_question(
                target_id=target_id,
                question=str(question),
                patch_artifacts=patch_artifacts,
                incident_artifacts=incident_artifacts,
                evidence_references=evidence,
            )
            resolver_outputs["patch_reasoning_resolver"] = patch_result.patch_reasoning_resolution

        if "replay_evidence_resolver" in _as_list(plan.get("resolver_order")):
            replay_result: ReplayEvidenceResolutionResult = resolve_replay_evidence_question(
                target_id=target_id,
                question=str(question),
                replay_artifacts=replay_artifacts,
                confidence_artifacts=confidence_artifacts,
                evidence_references=evidence,
            )
            resolver_outputs["replay_evidence_resolver"] = replay_result.replay_evidence_resolution

        reason_result: InvestigationReasoningResult = synthesize_investigation_reasoning(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            question=str(question),
            query_plan=plan,
            resolver_outputs=resolver_outputs,
            governance_state=governance_state,
            replay_lineage={
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            evidence_references=evidence,
        )

        reasoning = reason_result.investigation_reasoning
        answer_entries = _as_list(_as_dict(reasoning.get("engineering_answer_trace")).get("answers"))

        query_history_result: EngineeringQueryHistoryResult = update_engineering_query_history(
            session_id=session_id,
            previous_history=[row for row in _as_list(previous_query_history or []) if isinstance(row, dict)],
            answer_entries=[_as_dict(item) for item in answer_entries],
        )

        lineage_result: ReasoningLineageResult = build_reasoning_lineage(
            target_id=target_id,
            session_id=session_id,
            lineage_id=lineage_id,
            previous_lineage=[row for row in _as_list(previous_reasoning_lineage or []) if isinstance(row, dict)],
            answer_entries=[_as_dict(item) for item in answer_entries],
            evidence_references=evidence,
        )

        artifacts = {
            "investigation_reasoning_graph": _as_dict(reasoning.get("investigation_reasoning_graph")),
            "engineering_answer_trace": _as_dict(reasoning.get("engineering_answer_trace")),
            "causality_resolution_report": _as_dict(reasoning.get("causality_resolution_report")),
            "migration_blocker_reasoning": _as_dict(reasoning.get("migration_blocker_reasoning")),
            "runtime_question_lineage": lineage_result.runtime_question_lineage,
        }

        artifact_fingerprints = {
            name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
            for name, payload in sorted(artifacts.items())
        }

        replay_history = [
            {
                "lineage_id": str(lineage_id),
                "session_id": str(session_id),
                "classification": str(reasoning.get("classification", "UNKNOWN")),
                "artifact_fingerprints": artifact_fingerprints,
            }
        ]
        replay_score = round(
            max(
                0.0,
                min(
                    1.0,
                    0.40 * (1.0 if bool(str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")).strip()) else 0.0)
                    + 0.35 * min(1.0, len(artifact_fingerprints) / 6.0)
                    + 0.25 * (1.0 if str(reasoning.get("classification", "")) != "FAIL_CLOSED" else 0.0),
                ),
            ),
            3,
        )
        deterministic_investigation_replay = {
            "schema_version": "1.0",
            "report_name": "deterministic_investigation_replay",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "classification": "PASS" if replay_score >= 0.72 else "ADVISORY_ONLY",
            "replay_score": replay_score,
            "artifact_fingerprints": artifact_fingerprints,
            "query_plan_fingerprint": str(plan.get("deterministic_fingerprint", "")),
            "replay_signal": {
                "deterministic_event_ordering": bool(_as_dict(replay_traces).get("deterministic_event_ordering", False)),
                "deterministic_replay_fingerprint": str(_as_dict(replay_traces).get("deterministic_replay_fingerprint", "")),
            },
            "lineage_history": replay_history,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "evidence_references": evidence,
        }
        deterministic_investigation_replay["deterministic_fingerprint"] = stable_fingerprint(
            deterministic_investigation_replay
        )
        artifacts["deterministic_investigation_replay"] = deterministic_investigation_replay

        governance_ok = _governance_clean(governance_state)
        classification = str(reasoning.get("classification", "UNKNOWN"))
        if not governance_ok:
            classification = "FAIL_CLOSED"

        bundle = {
            "schema_version": "1.0",
            "phase": "ENGINEERING_INVESTIGATION_QUERY_REASONING_LAYER",
            "target_id": str(target_id),
            "session_id": str(session_id),
            "lineage_id": str(lineage_id),
            "question": str(question).strip(),
            "classification": classification,
            "runtime_truth_precedence": True,
            "advisory_only_behavior": True,
            "plugin_isolation": True,
            "governance_state": dict(governance_state),
            "plugin_adapters": {
                "runtime": runtime_adapter,
                "topology": topology_adapter,
                "semantic": semantic_adapter,
            },
            "query_plan": dict(plan),
            "resolver_outputs": resolver_outputs,
            "engineering_query_history": query_history_result.engineering_query_history,
            "evidence_references": evidence,
            "artifacts": artifacts,
        }

        bundle["engineering_investigation_fingerprint"] = stable_fingerprint(
            {
                "target_id": str(target_id),
                "session_id": str(session_id),
                "lineage_id": str(lineage_id),
                "classification": classification,
                "query_plan_fingerprint": str(plan.get("deterministic_fingerprint", "")),
                "resolver_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(resolver_outputs.items())
                },
                "artifact_fingerprints": {
                    name: str(_as_dict(payload).get("deterministic_fingerprint", ""))
                    for name, payload in sorted(artifacts.items())
                },
                "history_fingerprint": str(query_history_result.deterministic_fingerprint),
                "lineage_fingerprint": str(lineage_result.deterministic_fingerprint),
            }
        )

        return EngineeringQueryEngineResult(investigation_bundle=bundle)
