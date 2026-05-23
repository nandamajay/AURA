"""Governance boundaries for Kernel Semantic Knowledge Layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "lookup",
    "infer",
    "recommend",
    "replay",
    "trace",
]

_FORBIDDEN_ACTIONS = [
    "autonomous_runtime_mutation",
    "autonomous_patch_generation",
    "autonomous_topology_mutation",
    "autonomous_upstream_generation",
    "direct_runtime_execution_from_semantics",
]


@dataclass(frozen=True)
class SemanticGovernanceBoundaryResult:
    governance_boundary: dict[str, Any]
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
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success"}
    return False


def evaluate_semantic_governance_boundary(
    *,
    governance_state: Mapping[str, Any],
    requested_actions: list[str] | None,
) -> SemanticGovernanceBoundaryResult:
    state = _as_dict(governance_state)
    actions = sorted({str(item).strip() for item in _as_list(requested_actions) if str(item).strip()})

    autonomous_flags = {
        "autonomous_patching_allowed": _is_true(state.get("autonomous_patching_allowed", False)),
        "autonomous_topology_rewrite_allowed": _is_true(state.get("autonomous_topology_rewrite_allowed", False)),
        "autonomous_upstream_generation_allowed": _is_true(state.get("autonomous_upstream_generation_allowed", False)),
        "autonomous_runtime_mutation_allowed": _is_true(state.get("autonomous_runtime_mutation_allowed", False)),
    }

    blocked_actions = [action for action in actions if action not in set(_ALLOWED_ACTIONS)]
    autonomous_violations = [key for key, value in autonomous_flags.items() if value]

    classification = "PASS"
    if autonomous_violations or blocked_actions:
        classification = "FAIL_CLOSED"

    payload = {
        "schema_version": "1.0",
        "report_name": "semantic_governance_boundary",
        "classification": classification,
        "fail_closed_posture": bool(state.get("fail_closed_posture", True)),
        "advisory_only": True,
        "runtime_mutation_permitted": False,
        "allowed_actions": list(_ALLOWED_ACTIONS),
        "forbidden_actions": list(_FORBIDDEN_ACTIONS),
        "requested_actions": actions,
        "blocked_requested_actions": blocked_actions,
        "autonomous_flags": autonomous_flags,
        "autonomous_violations": autonomous_violations,
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return SemanticGovernanceBoundaryResult(
        governance_boundary=payload,
        deterministic_fingerprint=fingerprint,
    )
