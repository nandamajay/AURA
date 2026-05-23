"""Governance gate for upstream readiness reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


_ALLOWED_ACTIONS = [
    "analyze",
    "classify",
    "correlate",
    "plan",
    "recommend",
    "replay",
]

_FORBIDDEN_ACTIONS = [
    "autonomous_patch_submission",
    "autonomous_patch_generation",
    "autonomous_topology_mutation",
    "autonomous_runtime_mutation",
    "governance_override",
]


@dataclass(frozen=True)
class UpstreamGovernanceGateResult:
    upstream_governance_gate: dict[str, Any]
    gate_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success", "supported"}
    return False


def evaluate_upstream_governance_gate(
    *,
    target_id: str,
    governance_state: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> UpstreamGovernanceGateResult:
    governance = _as_dict(governance_state)
    replay = _as_dict(replay_traces)

    blocked_by_state: list[str] = []

    if _is_true(governance.get("autonomous_patching_allowed", False)):
        blocked_by_state.append("autonomous_patch_generation")
    if _is_true(governance.get("autonomous_topology_rewrite_allowed", False)) or _is_true(
        governance.get("autonomous_mixer_mutation_allowed", False)
    ):
        blocked_by_state.append("autonomous_topology_mutation")
    if _is_true(governance.get("autonomous_runtime_mutation_allowed", False)):
        blocked_by_state.append("autonomous_runtime_mutation")
    if _is_true(governance.get("autonomous_upstream_generation_allowed", False)):
        blocked_by_state.append("autonomous_patch_submission")

    replay_ok = _is_true(replay.get("deterministic_event_ordering", False)) or bool(
        str(replay.get("deterministic_replay_fingerprint", "")).strip()
    )

    fail_closed = bool(governance.get("fail_closed_posture", True))
    gate_score = round(max(0.0, min(1.0, (1.0 if fail_closed else 0.0) * (1.0 if replay_ok else 0.5) * (1.0 if not blocked_by_state else 0.0))), 3)

    classification = "PASS"
    if blocked_by_state or not fail_closed:
        classification = "FAIL_CLOSED"
    elif not replay_ok:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "upstream_governance_gate",
        "target_id": str(target_id),
        "classification": classification,
        "gate_score": gate_score,
        "allowed_actions": list(_ALLOWED_ACTIONS),
        "forbidden_actions": list(_FORBIDDEN_ACTIONS),
        "blocked_by_state": sorted(set(blocked_by_state)),
        "summary": {
            "fail_closed_posture": fail_closed,
            "replay_signal_present": replay_ok,
            "blocked_count": len(set(blocked_by_state)),
        },
        "governance_state": dict(governance),
        "runtime_truth_precedence": True,
        "advisory_only_behavior": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return UpstreamGovernanceGateResult(
        upstream_governance_gate=payload,
        gate_score=gate_score,
        deterministic_fingerprint=fingerprint,
    )
