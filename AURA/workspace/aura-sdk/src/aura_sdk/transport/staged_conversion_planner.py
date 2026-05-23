"""Staged conversion planner for incremental migration orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class StagedMigrationPlanResult:
    staged_migration_plan: dict[str, Any]
    plan_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_staged_migration_plan(
    *,
    target_id: str,
    migration_dependency_graph: Mapping[str, Any],
    runtime_stability_gate_report: Mapping[str, Any],
    portability_transition_state: Mapping[str, Any],
    portability_blocker_report: Mapping[str, Any],
    incremental_equivalence_report: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> StagedMigrationPlanResult:
    dependencies = _as_dict(migration_dependency_graph)
    runtime_gate = _as_dict(runtime_stability_gate_report)
    transitions = _as_dict(portability_transition_state)
    blockers = _as_dict(portability_blocker_report)
    incremental = _as_dict(incremental_equivalence_report)

    transition_rows = [row for row in _as_list(transitions.get("transitions")) if isinstance(row, dict)]
    transition_map = {str(row.get("transition_id", "")): str(row.get("state", "PENDING")) for row in transition_rows}

    incremental_score = _to_float(incremental.get("incremental_equivalence_score", 0.0))
    runtime_score = _to_float(runtime_gate.get("stability_score", 0.0))
    blocker_risk = str(blockers.get("risk_classification", "UNKNOWN"))

    phase_definitions = [
        {
            "phase_id": "phase_1_fe_be_staging",
            "covers": ["fe_be_separation_staging", "topology_portability_sequencing"],
            "goal": "establish FE/BE separation boundaries and portable topology sequencing",
        },
        {
            "phase_id": "phase_2_dpcm_and_callback_alignment",
            "covers": ["dpcm_lifecycle_migration", "callback_migration_ordering"],
            "goal": "migrate DPCM lifecycle and callback ordering with runtime-safe gates",
        },
        {
            "phase_id": "phase_3_soundwire_vendor_unwind",
            "covers": ["soundwire_abstraction_replacement", "vendor_hook_elimination", "dsp_dependency_reduction"],
            "goal": "replace SoundWire vendor abstraction and reduce DSP/vendor dependencies",
        },
        {
            "phase_id": "phase_4_registration_parity",
            "covers": ["component_registration_migration", "upstream_api_compatibility_windows"],
            "goal": "align component registration and API compatibility windows",
        },
        {
            "phase_id": "phase_5_runtime_capability_parity",
            "covers": ["runtime_capability_parity"],
            "goal": "validate runtime capability parity under deterministic replay",
        },
    ]

    phases: list[dict[str, Any]] = []
    irreversible_transitions: list[str] = []
    high_risk_transitions: list[str] = []

    for phase in phase_definitions:
        covers = [str(item) for item in _as_list(phase.get("covers")) if str(item).strip()]
        covered_states = [transition_map.get(item, "PENDING") for item in covers]

        if covered_states and all(state == "COMPLETED" for state in covered_states):
            status = "COMPLETED"
        elif any(state == "BLOCKED" for state in covered_states):
            status = "BLOCKED"
        elif any(state == "IN_PROGRESS" for state in covered_states):
            status = "IN_PROGRESS"
        else:
            status = "PENDING"

        if any(item in {"vendor_hook_elimination", "component_registration_migration"} for item in covers):
            irreversible_transitions.extend(covers)

        if any(item in {"dsp_dependency_reduction", "upstream_api_compatibility_windows", "runtime_capability_parity"} for item in covers):
            high_risk_transitions.extend(covers)

        phases.append(
            {
                "phase_id": str(phase.get("phase_id", "")),
                "goal": str(phase.get("goal", "")),
                "covers": covers,
                "status": status,
                "entry_requirements": [
                    "runtime_stability_gate_pass_or_advisory",
                    "deterministic_replay_signal_present",
                    "governance_fail_closed_enabled",
                ],
                "exit_requirements": [
                    "covered_transitions_non_blocked",
                    "no_new_high_severity_regression",
                    "lineage_checkpoint_persisted",
                ],
            }
        )

    phases.sort(key=lambda row: str(row.get("phase_id", "")))

    blocked_phases = len([row for row in phases if str(row.get("status", "")) == "BLOCKED"])
    in_progress_phases = len([row for row in phases if str(row.get("status", "")) == "IN_PROGRESS"])
    completed_phases = len([row for row in phases if str(row.get("status", "")) == "COMPLETED"])

    plan_score = round(
        max(
            0.0,
            min(
                1.0,
                0.35 * incremental_score
                + 0.35 * runtime_score
                + 0.2 * (completed_phases / max(1, len(phases)))
                + 0.1 * (1.0 if blocker_risk == "LOW" else (0.5 if blocker_risk == "MEDIUM" else 0.2)),
            ),
        ),
        3,
    )

    classification = "PASS"
    if blocked_phases > 0 or str(runtime_gate.get("classification", "")) == "FAIL_CLOSED" or str(blockers.get("classification", "")) == "FAIL_CLOSED":
        classification = "FAIL_CLOSED"
    elif in_progress_phases > 0 or blocker_risk in {"MEDIUM", "HIGH"}:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "staged_migration_plan",
        "target_id": str(target_id),
        "classification": classification,
        "plan_score": plan_score,
        "phases": phases,
        "dependency_reference": str(_as_dict(dependencies).get("deterministic_fingerprint", "")),
        "irreversible_high_risk_transitions": {
            "irreversible": sorted({item for item in irreversible_transitions if item}),
            "high_risk": sorted({item for item in high_risk_transitions if item}),
        },
        "summary": {
            "completed_phases": completed_phases,
            "in_progress_phases": in_progress_phases,
            "blocked_phases": blocked_phases,
            "total_phases": len(phases),
            "runtime_gate_classification": str(runtime_gate.get("classification", "UNKNOWN")),
            "portability_risk_classification": blocker_risk,
            "incremental_equivalence_score": incremental_score,
        },
        "advisory_only_orchestration": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }

    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return StagedMigrationPlanResult(
        staged_migration_plan=payload,
        plan_score=plan_score,
        deterministic_fingerprint=fingerprint,
    )
