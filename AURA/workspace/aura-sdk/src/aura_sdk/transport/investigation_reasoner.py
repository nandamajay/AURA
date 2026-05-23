"""Investigation reasoning synthesis for engineering query responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class InvestigationReasoningResult:
    investigation_reasoning: dict[str, Any]
    deterministic_fingerprint: str


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


def _select_candidate(candidates: list[Mapping[str, Any]]) -> dict[str, Any]:
    ranked = sorted(
        [_as_dict(row) for row in candidates],
        key=lambda row: (
            0 if str(row.get("classification", "")).upper() == "PASS" else 1,
            -float(row.get("confidence_score", 0.0) or 0.0),
            str(row.get("resolver", "")),
        ),
    )
    if not ranked:
        return {}
    return _as_dict(ranked[0])


def synthesize_investigation_reasoning(
    *,
    target_id: str,
    session_id: str,
    lineage_id: str,
    question: str,
    query_plan: Mapping[str, Any],
    resolver_outputs: Mapping[str, Mapping[str, Any]],
    governance_state: Mapping[str, Any],
    replay_lineage: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> InvestigationReasoningResult:
    plan = _as_dict(query_plan)
    outputs = {
        str(name): _as_dict(payload)
        for name, payload in sorted(_as_dict(resolver_outputs).items())
        if _as_dict(payload)
    }

    candidates = [
        {
            "resolver": name,
            "classification": str(payload.get("classification", "UNKNOWN")),
            "confidence_score": float(payload.get("confidence_score", 0.0) or 0.0),
            "answer": str(payload.get("answer", "")),
            "evidence_sources": _as_list(payload.get("evidence_sources")),
            "causality_chain": _as_list(payload.get("causality_chain")),
            "fail_closed_justification": str(payload.get("fail_closed_justification", "")),
            "deterministic_fingerprint": str(payload.get("deterministic_fingerprint", "")),
        }
        for name, payload in outputs.items()
    ]

    selected = _select_candidate(candidates)
    selected_resolver = str(selected.get("resolver", ""))

    governance_ok = _governance_clean(governance_state)
    fail_closed_reason = ""
    classification = "PASS"
    if not governance_ok:
        classification = "FAIL_CLOSED"
        fail_closed_reason = "governance_policy_violation"
    elif not selected:
        classification = "FAIL_CLOSED"
        fail_closed_reason = "no_resolver_output_available"
    elif str(selected.get("classification", "")).upper() == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
        fail_closed_reason = str(selected.get("fail_closed_justification", "resolver_fail_closed"))
    elif float(selected.get("confidence_score", 0.0) or 0.0) < 0.62:
        classification = "FAIL_CLOSED"
        fail_closed_reason = "investigation_confidence_below_threshold"

    replay = _as_dict(replay_lineage)

    answer_entry = {
        "question_id": f"{lineage_id}:{stable_fingerprint({'q': question})[:8]}",
        "question": str(question).strip(),
        "selected_resolver": selected_resolver,
        "classification": classification,
        "answer": str(selected.get("answer", "Insufficient evidence to answer the question deterministically.")),
        "evidence_sources": _as_list(selected.get("evidence_sources")),
        "causality_chain": _as_list(selected.get("causality_chain")),
        "confidence_score": float(selected.get("confidence_score", 0.0) or 0.0),
        "replay_lineage": {
            "lineage_id": str(lineage_id),
            "replay_fingerprint": str(replay.get("deterministic_replay_fingerprint", "")),
        },
        "governance_state": dict(_as_dict(governance_state)),
        "fail_closed_justification": fail_closed_reason,
        "deterministic_fingerprint": str(selected.get("deterministic_fingerprint", "")),
    }

    nodes = [
        {"id": f"target:{target_id}", "kind": "target"},
        {"id": f"session:{session_id}", "kind": "session"},
        {"id": f"question:{answer_entry['question_id']}", "kind": "question"},
    ]
    edges = [
        {"from": f"target:{target_id}", "to": f"session:{session_id}", "relation": "investigates"},
        {"from": f"session:{session_id}", "to": f"question:{answer_entry['question_id']}", "relation": "asks"},
    ]

    for candidate in candidates:
        resolver_id = f"resolver:{str(candidate.get('resolver', 'unknown'))}"
        nodes.append({"id": resolver_id, "kind": "resolver"})
        edges.append(
            {
                "from": f"question:{answer_entry['question_id']}",
                "to": resolver_id,
                "relation": "resolved_by",
                "confidence": float(candidate.get("confidence_score", 0.0) or 0.0),
            }
        )

    investigation_graph = {
        "schema_version": "1.0",
        "graph_name": "investigation_reasoning_graph",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "nodes": nodes,
        "edges": edges,
        "query_plan_fingerprint": str(plan.get("deterministic_fingerprint", "")),
        "resolver_fingerprints": {
            name: str(payload.get("deterministic_fingerprint", ""))
            for name, payload in sorted(outputs.items())
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    investigation_graph["deterministic_fingerprint"] = stable_fingerprint(investigation_graph)

    answer_trace = {
        "schema_version": "1.0",
        "report_name": "engineering_answer_trace",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "answers": [answer_entry],
        "summary": {
            "question_count": 1,
            "selected_resolver": selected_resolver,
            "fail_closed": classification == "FAIL_CLOSED",
        },
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    answer_trace["deterministic_fingerprint"] = stable_fingerprint(answer_trace)

    causality_resolution = {
        "schema_version": "1.0",
        "report_name": "causality_resolution_report",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "selected_resolver": selected_resolver,
        "selected_causality_chain": _as_list(selected.get("causality_chain")),
        "resolver_candidates": candidates,
        "fail_closed_justification": fail_closed_reason,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    causality_resolution["deterministic_fingerprint"] = stable_fingerprint(causality_resolution)

    migration_blocker = _as_dict(outputs.get("migration_question_resolver"))
    migration_reasoning = {
        "schema_version": "1.0",
        "report_name": "migration_blocker_reasoning",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": str(migration_blocker.get("classification", "FAIL_CLOSED")),
        "answer": str(migration_blocker.get("answer", "Migration blocker evidence unavailable for this query.")),
        "evidence_sources": _as_list(migration_blocker.get("evidence_sources")),
        "confidence_score": float(migration_blocker.get("confidence_score", 0.0) or 0.0),
        "fail_closed_justification": str(
            migration_blocker.get("fail_closed_justification", "migration_resolver_not_selected_or_missing")
        ),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    migration_reasoning["deterministic_fingerprint"] = stable_fingerprint(migration_reasoning)

    payload = {
        "schema_version": "1.0",
        "report_name": "investigation_reasoning",
        "target_id": str(target_id),
        "session_id": str(session_id),
        "lineage_id": str(lineage_id),
        "classification": classification,
        "query_plan": dict(plan),
        "investigation_reasoning_graph": investigation_graph,
        "engineering_answer_trace": answer_trace,
        "causality_resolution_report": causality_resolution,
        "migration_blocker_reasoning": migration_reasoning,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return InvestigationReasoningResult(
        investigation_reasoning=payload,
        deterministic_fingerprint=fingerprint,
    )
