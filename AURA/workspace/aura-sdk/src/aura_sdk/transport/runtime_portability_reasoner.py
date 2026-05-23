"""Runtime portability reasoner for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimePortabilityReasoningResult:
    runtime_portability_analysis: dict[str, Any]
    runtime_portability_score: float
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
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success", "supported"}
    return False


def reason_runtime_portability(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    runtime_source_correlation: Mapping[str, Any],
    plugin_capability_state: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> RuntimePortabilityReasoningResult:
    runtime = _as_dict(runtime_evidence)
    source_corr = _as_dict(runtime_source_correlation)
    capabilities = _as_dict(plugin_capability_state)
    governance = _as_dict(governance_state)
    adapter = _as_dict(adapter_payload)

    deps = [
        str(item)
        for item in _as_list(adapter.get("downstream_runtime_dependencies"))
        if str(item).strip()
    ]

    if not deps:
        deps = [
            dep
            for dep in (
                "vendor_amixer_sequence" if _as_list(runtime.get("command_sequence")) else "",
                "vendor_route_fingerprint" if str(runtime.get("route_fingerprint", "")).strip() else "",
                "vendor_codec_dependency" if str(runtime.get("classification", "")).strip() else "",
            )
            if dep
        ]

    blockers: list[dict[str, Any]] = []

    if not _is_true(runtime.get("process_success", runtime.get("playback_completion", False))):
        blockers.append(
            {
                "code": "unstable_runtime_evidence",
                "severity": "HIGH",
                "details": "Runtime evidence does not satisfy stable execution precondition.",
            }
        )

    replay_ok = _is_true(runtime.get("deterministic_event_ordering")) or bool(
        str(runtime.get("deterministic_replay_fingerprint", "")).strip()
    )
    if not replay_ok:
        blockers.append(
            {
                "code": "missing_replay_signal",
                "severity": "HIGH",
                "details": "Deterministic replay signal missing from runtime evidence.",
            }
        )

    correlation_confidence = float(source_corr.get("correlation_confidence", 0.0) or 0.0)
    if correlation_confidence < 0.3:
        blockers.append(
            {
                "code": "runtime_source_correlation_gap",
                "severity": "MEDIUM",
                "details": f"Runtime/source correlation confidence too low: {correlation_confidence}.",
            }
        )

    if "supported" in capabilities and not _is_true(capabilities.get("supported", True)):
        blockers.append(
            {
                "code": "unsupported_runtime_capabilities",
                "severity": "HIGH",
                "details": "Plugin capability state is unsupported for governed conversion.",
            }
        )

    governance_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )
    if governance_violation:
        blockers.append(
            {
                "code": "governance_violation",
                "severity": "HIGH",
                "details": "Autonomous mutation flags detected in governance state.",
            }
        )

    classification = "PASS"
    if any(str(item.get("severity", "")).upper() == "HIGH" for item in blockers):
        classification = "FAIL_CLOSED"
    elif blockers:
        classification = "ADVISORY_ONLY"

    runtime_portability_score = round(
        max(0.0, min(1.0, 1.0 - 0.2 * len([item for item in blockers if str(item.get("severity", "")).upper() == "HIGH"]) - 0.08 * len([item for item in blockers if str(item.get("severity", "")).upper() == "MEDIUM"]))),
        3,
    )

    payload = {
        "schema_version": "1.0",
        "report_name": "runtime_portability_analysis",
        "target_id": str(target_id),
        "classification": classification,
        "runtime_truth_precedence": True,
        "unsupported_runtime_dependencies": deps,
        "runtime_portability_blockers": blockers,
        "scheduler_assumptions": [
            dep
            for dep in deps
            if "timing" in dep.lower() or "sched" in dep.lower() or "latency" in dep.lower()
        ],
        "runtime_portability_score": runtime_portability_score,
        "summary": {
            "dependency_count": len(deps),
            "blocker_count": len(blockers),
            "replay_ok": replay_ok,
            "source_correlation_confidence": correlation_confidence,
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return RuntimePortabilityReasoningResult(
        runtime_portability_analysis=payload,
        runtime_portability_score=runtime_portability_score,
        deterministic_fingerprint=fingerprint,
    )
