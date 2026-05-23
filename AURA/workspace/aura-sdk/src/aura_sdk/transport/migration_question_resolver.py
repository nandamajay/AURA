"""Migration investigation question resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class MigrationQuestionResolutionResult:
    migration_question_resolution: dict[str, Any]
    confidence: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def resolve_migration_question(
    *,
    target_id: str,
    question: str,
    migration_artifacts: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> MigrationQuestionResolutionResult:
    migration = _as_dict(migration_artifacts)
    lowered = str(question).strip().lower()

    blockers = _as_dict(migration.get("portability_blockers", migration.get("portability_blocker_report")))
    alignment = _as_dict(migration.get("migration_runtime_alignment"))
    phase_plan = _as_dict(migration.get("migration_phase_plan", migration.get("staged_migration_plan")))
    equivalence = _as_dict(migration.get("upstream_equivalence_map", migration.get("upstream_equivalence_confidence")))

    blocked = int(_as_dict(blockers.get("summary")).get("blocked_unsafe_count", 0) or 0)
    advisory = int(_as_dict(blockers.get("summary")).get("advisory_only_count", 0) or 0)
    unresolved = 0
    for row in _as_list(equivalence.get("entries", equivalence.get("mappings"))):
        status = str(_as_dict(row).get("equivalence_status", _as_dict(row).get("status", ""))).upper()
        if status in {"UNRESOLVED", "MISSING", "INCOMPATIBLE"}:
            unresolved += 1

    phase_count = len([row for row in _as_list(phase_plan.get("phases", phase_plan.get("plan"))) if isinstance(row, dict)])

    evidence_sources = []
    if _as_dict(blockers):
        evidence_sources.append("artifact://portability_blockers")
    if _as_dict(alignment):
        evidence_sources.append("artifact://migration_runtime_alignment")
    if _as_dict(phase_plan):
        evidence_sources.append("artifact://migration_phase_plan")
    if _as_dict(equivalence):
        evidence_sources.append("artifact://upstream_equivalence_map")

    answer = "Insufficient migration evidence to answer the question."
    causality_chain: list[dict[str, Any]] = []

    if "fail-closed" in lowered or "why is migration" in lowered:
        answer = (
            f"Migration is fail-closed because blocked_unsafe_count={blocked}, "
            f"unresolved_upstream_mappings={unresolved}, and alignment_classification="
            f"{str(alignment.get('classification', 'UNKNOWN'))}."
        )
        causality_chain = [
            {"node": "portability_blockers", "relation": "introduces_blockers", "weight": 0.87},
            {"node": "upstream_equivalence_map", "relation": "reveals_unresolved_mappings", "weight": 0.83},
            {"node": "migration_runtime_alignment", "relation": "drives_fail_closed", "weight": 0.79},
        ]
    elif "upstream abstraction" in lowered or "missing" in lowered:
        answer = f"Upstream abstraction gaps remain with unresolved mapping count={unresolved}."
        causality_chain = [
            {"node": "upstream_equivalence_map", "relation": "contains_missing_abstractions", "weight": 0.82},
            {"node": "migration_blockers", "relation": "constrains_migration", "weight": 0.77},
        ]
    else:
        answer = (
            f"Migration blockers currently include blocked_unsafe_count={blocked}, advisory_only_count={advisory}, "
            f"planned_phases={phase_count}."
        )
        causality_chain = [
            {"node": "migration_phase_plan", "relation": "stages_conversion", "weight": 0.71},
            {"node": "portability_blockers", "relation": "limits_progress", "weight": 0.8},
        ]

    confidence = round(
        max(
            0.0,
            min(
                1.0,
                0.45 * min(1.0, len(evidence_sources) / 4.0)
                + 0.25 * min(1.0, len(causality_chain) / 3.0)
                + 0.20 * (1.0 if blocked or unresolved or advisory else 0.0)
                + 0.10 * min(1.0, phase_count / 5.0),
            ),
        ),
        3,
    )

    classification = "PASS"
    fail_closed_justification = ""
    if not evidence_sources:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "insufficient_migration_evidence"
    elif confidence < 0.6:
        classification = "FAIL_CLOSED"
        fail_closed_justification = "migration_evidence_confidence_below_threshold"

    payload = {
        "schema_version": "1.0",
        "resolver": "migration_question_resolver",
        "target_id": str(target_id),
        "question": str(question).strip(),
        "classification": classification,
        "answer": answer,
        "confidence_score": confidence,
        "evidence_sources": sorted(set(evidence_sources + [str(item) for item in (evidence_references or []) if str(item).strip()])),
        "causality_chain": causality_chain,
        "fail_closed_justification": fail_closed_justification,
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return MigrationQuestionResolutionResult(
        migration_question_resolution=payload,
        confidence=confidence,
        deterministic_fingerprint=fingerprint,
    )
