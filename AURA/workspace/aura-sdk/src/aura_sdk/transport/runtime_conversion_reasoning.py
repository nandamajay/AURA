"""Runtime conversion reasoning for downstream to upstream cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class RuntimeConversionReasoningResult:
    runtime_portability_analysis: dict[str, Any]
    portability_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "ok", "pass", "success"}
    return False


def analyze_runtime_conversion(
    *,
    target_id: str,
    runtime_evidence: Mapping[str, Any],
    plugin_capability_state: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    replay_traces: Mapping[str, Any],
    adapter_payload: Mapping[str, Any],
) -> RuntimeConversionReasoningResult:
    runtime = _as_dict(runtime_evidence)
    capabilities = _as_dict(plugin_capability_state)
    governance = _as_dict(governance_state)
    replay = _as_dict(replay_traces)
    adapter = _as_dict(adapter_payload)

    downstream_deps = [str(item) for item in _as_list(adapter.get("downstream_runtime_dependencies")) if str(item).strip()]
    if not downstream_deps:
        downstream_deps = [
            dep
            for dep in (
                "vendor_amixer_sequence" if _as_list(runtime.get("command_sequence")) else "",
                "vendor_route_fingerprint" if str(runtime.get("route_fingerprint", "")).strip() else "",
            )
            if dep
        ]

    portability_blockers: list[dict[str, Any]] = []

    if "supported" in capabilities and not _to_bool(capabilities.get("supported")):
        portability_blockers.append(
            {
                "code": "unsupported_plugin_capability",
                "severity": "HIGH",
                "details": "Plugin capability state indicates unsupported runtime features.",
            }
        )

    if not (_to_bool(replay.get("deterministic_event_ordering")) or bool(replay.get("deterministic_replay_fingerprint", ""))):
        portability_blockers.append(
            {
                "code": "replay_instability",
                "severity": "HIGH",
                "details": "Deterministic replay signal missing for conversion safety.",
            }
        )

    if not _to_bool(runtime.get("process_success", runtime.get("playback_completion", False))):
        portability_blockers.append(
            {
                "code": "runtime_unstable",
                "severity": "MEDIUM",
                "details": "Runtime evidence is not stable enough for confident translation.",
            }
        )

    replay_safe = [str(item) for item in _as_list(adapter.get("replay_safe_transformations")) if str(item).strip()]
    advisory_only = [str(item) for item in _as_list(adapter.get("advisory_only_transformations")) if str(item).strip()]
    forbidden_auto = [str(item) for item in _as_list(adapter.get("forbidden_autonomous_transformations")) if str(item).strip()]

    if not replay_safe:
        replay_safe = [
            "normalize_control_names",
            "normalize_route_labels",
            "derive_upstream_equivalent_identifiers",
        ]
    if not advisory_only:
        advisory_only = [
            "manual_dai_link_mapping_review",
            "manual_vendor_api_replacement_review",
        ]

    forbidden_defaults = [
        "autonomous_code_rewrite",
        "autonomous_dts_mutation",
        "autonomous_driver_mutation",
    ]
    forbidden_auto = sorted(set(forbidden_auto + forbidden_defaults))

    governance_violation = any(
        [
            _to_bool(governance.get("autonomous_patching_allowed", False)),
            _to_bool(governance.get("autonomous_topology_rewrite_allowed", False)),
            _to_bool(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )
    if governance_violation:
        portability_blockers.append(
            {
                "code": "governance_violation",
                "severity": "HIGH",
                "details": "Governance state permits autonomous mutation, incompatible with conversion guardrails.",
            }
        )

    blocker_penalty = 0.2 * len(portability_blockers)
    portability_score = round(max(0.0, min(1.0, 1.0 - blocker_penalty)), 3)

    classification = "PASS"
    if any(str(item.get("severity", "")).upper() == "HIGH" for item in portability_blockers):
        classification = "FAIL_CLOSED"
    elif portability_blockers:
        classification = "ADVISORY_ONLY"

    analysis = {
        "schema_version": "1.0",
        "report_name": "runtime_portability_analysis",
        "target_id": target_id,
        "downstream_only_runtime_dependencies": downstream_deps,
        "portability_blockers": portability_blockers,
        "transformation_classes": {
            "replay_safe_transformations": replay_safe,
            "advisory_only_transformations": advisory_only,
            "forbidden_autonomous_transformations": forbidden_auto,
        },
        "governance_classification": classification,
        "portability_score": portability_score,
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": target_id,
            "dependencies": downstream_deps,
            "blockers": portability_blockers,
            "transformations": analysis["transformation_classes"],
            "classification": classification,
            "portability_score": portability_score,
        }
    )
    analysis["deterministic_fingerprint"] = fingerprint

    return RuntimeConversionReasoningResult(
        runtime_portability_analysis=analysis,
        portability_score=portability_score,
        deterministic_fingerprint=fingerprint,
    )
