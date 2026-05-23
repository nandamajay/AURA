"""Portability blocker classifier for downstream to upstream conversion cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class PortabilityBlockerResult:
    portability_blockers: dict[str, Any]
    portability_score: float
    deterministic_fingerprint: str


@dataclass(frozen=True)
class GovernedPortabilityBlockerReportResult:
    portability_blocker_report: dict[str, Any]
    risk_score: float
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


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def classify_portability_blockers(
    *,
    target_id: str,
    downstream_driver_graph: Mapping[str, Any],
    upstream_equivalence_map: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
) -> PortabilityBlockerResult:
    graph = _as_dict(downstream_driver_graph)
    extracted = _as_dict(graph.get("extracted"))
    map_payload = _as_dict(upstream_equivalence_map)
    runtime = _as_dict(runtime_evidence)
    governance = _as_dict(governance_state)
    adapter = _as_dict(adapter_payload)

    entries = [item for item in _as_list(map_payload.get("entries")) if isinstance(item, dict)]

    blockers: list[dict[str, Any]] = []
    replay_safe: list[str] = [str(item) for item in _as_list(adapter.get("replay_safe_transformations")) if str(item).strip()]
    advisory_only: list[str] = [str(item) for item in _as_list(adapter.get("advisory_only_transformations")) if str(item).strip()]
    forbidden: list[str] = [str(item) for item in _as_list(adapter.get("forbidden_autonomous_transformations")) if str(item).strip()]

    if not replay_safe:
        replay_safe = [
            "normalize_vendor_identifiers",
            "normalize_fe_be_labels",
            "normalize_pcm_route_signatures",
        ]
    if not advisory_only:
        advisory_only = [
            "manual_driver_ops_refactor_review",
            "manual_dai_link_portability_review",
            "manual_runtime_hook_replacement_review",
        ]

    forbidden.extend(
        [
            "autonomous_patch_generation",
            "autonomous_topology_mutation",
            "unsafe_runtime_rewrite",
        ]
    )
    forbidden = sorted({item for item in forbidden if item})

    unresolved = [
        row
        for row in entries
        if str(_as_dict(row).get("equivalence_status", "")).strip().upper() == "UNRESOLVED"
    ]
    if unresolved:
        blockers.append(
            {
                "code": "downstream_only_apis",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": {
                    "count": len(unresolved),
                    "examples": [str(_as_dict(row).get("downstream_construct", "")) for row in unresolved[:20]],
                },
            }
        )

    vendor_extensions = [str(item) for item in _as_list(extracted.get("vendor_extensions")) if str(item).strip()]
    proprietary_hooks = [str(item) for item in _as_list(extracted.get("proprietary_runtime_hooks")) if str(item).strip()]
    if vendor_extensions or proprietary_hooks:
        blockers.append(
            {
                "code": "vendor_private_abstractions",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": {
                    "vendor_extension_count": len(vendor_extensions),
                    "proprietary_hook_count": len(proprietary_hooks),
                },
            }
        )

    dependencies = _as_dict(extracted.get("dependencies"))
    if _is_true(dependencies.get("timing_dependencies")):
        blockers.append(
            {
                "code": "timing_dependencies",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": "Downstream source contains explicit sleep/delay timing dependencies.",
            }
        )

    if not _is_true(runtime.get("process_success", runtime.get("playback_completion", False))):
        blockers.append(
            {
                "code": "unsupported_runtime_assumptions",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Runtime evidence is not stable enough for conversion planning.",
            }
        )

    replay_ok = _is_true(runtime.get("deterministic_event_ordering")) or bool(
        str(runtime.get("deterministic_replay_fingerprint", "")).strip()
    )
    if not replay_ok:
        blockers.append(
            {
                "code": "replay_compatibility_missing",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Deterministic replay evidence missing for translation safety.",
            }
        )

    autonomous_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
        ]
    )
    if autonomous_violation:
        blockers.append(
            {
                "code": "governance_violation",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Autonomous mutation is enabled in governance state.",
            }
        )

    blocked_unsafe = [row for row in blockers if str(row.get("classification", "")) == "blocked_unsafe"]
    advisory = [row for row in blockers if str(row.get("classification", "")) == "advisory_only"]

    penalty = 0.25 * len(blocked_unsafe) + 0.08 * len(advisory)
    score = round(max(0.0, min(1.0, 1.0 - penalty)), 3)

    classification = "PASS"
    if blocked_unsafe:
        classification = "FAIL_CLOSED"
    elif blockers:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "portability_blockers",
        "target_id": str(target_id),
        "classification": classification,
        "portability_score": score,
        "detected": blockers,
        "transformation_classes": {
            "replay_safe": replay_safe,
            "advisory_only": advisory_only,
            "blocked_unsafe": [str(item.get("code", "")) for item in blocked_unsafe],
            "forbidden_autonomous_transformations": forbidden,
        },
        "summary": {
            "blocked_unsafe_count": len(blocked_unsafe),
            "advisory_count": len(advisory),
            "total_detected": len(blockers),
        },
    }

    fingerprint = stable_fingerprint(
        {
            "target_id": str(target_id),
            "classification": classification,
            "portability_score": score,
            "detected": blockers,
            "transformations": payload["transformation_classes"],
        }
    )
    payload["deterministic_fingerprint"] = fingerprint

    return PortabilityBlockerResult(
        portability_blockers=payload,
        portability_score=score,
        deterministic_fingerprint=fingerprint,
    )


def classify_governed_portability_blockers(
    *,
    target_id: str,
    vendor_dependency_graph: Mapping[str, Any],
    lifecycle_incompatibility_report: Mapping[str, Any],
    abstraction_gap_report: Mapping[str, Any],
    runtime_portability_analysis: Mapping[str, Any],
    upstream_equivalence_confidence: Mapping[str, Any],
    governance_state: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> GovernedPortabilityBlockerReportResult:
    vendor = _as_dict(vendor_dependency_graph)
    lifecycle = _as_dict(lifecycle_incompatibility_report)
    gaps = _as_dict(abstraction_gap_report)
    runtime = _as_dict(runtime_portability_analysis)
    confidence = _as_dict(upstream_equivalence_confidence)
    governance = _as_dict(governance_state)

    blockers: list[dict[str, Any]] = []

    dsp_coupling = [str(item) for item in _as_list(vendor.get("dsp_coupling")) if str(item).strip()]
    if dsp_coupling:
        blockers.append(
            {
                "code": "dsp_coupling",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": dsp_coupling[:120],
            }
        )

    vendor_assumptions = [
        str(item)
        for item in _as_list(vendor.get("vendor_specific_assumptions"))
        if str(item).strip()
    ]
    if vendor_assumptions:
        blockers.append(
            {
                "code": "vendor_specific_assumptions",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": vendor_assumptions[:160],
            }
        )

    proprietary_hooks = [
        str(item)
        for item in _as_list(vendor.get("unsupported_proprietary_hooks"))
        if str(item).strip()
    ]
    if proprietary_hooks:
        blockers.append(
            {
                "code": "unsupported_proprietary_hooks",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": proprietary_hooks[:160],
            }
        )

    soundwire_gaps = [
        str(item)
        for item in _as_list(vendor.get("soundwire_portability_gaps"))
        if str(item).strip()
    ]
    if soundwire_gaps:
        blockers.append(
            {
                "code": "soundwire_portability_gaps",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": soundwire_gaps[:120],
            }
        )

    callback_deps = [
        str(item)
        for item in _as_list(vendor.get("downstream_only_callback_dependencies"))
        if str(item).strip()
    ]
    if callback_deps:
        blockers.append(
            {
                "code": "downstream_callback_dependencies",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": callback_deps[:160],
            }
        )

    scheduler_assumptions = [
        str(item)
        for item in _as_list(vendor.get("scheduler_assumptions"))
        if str(item).strip()
    ]
    if scheduler_assumptions:
        blockers.append(
            {
                "code": "scheduler_assumptions",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": scheduler_assumptions[:80],
            }
        )

    lifecycle_rows = [
        row
        for row in _as_list(lifecycle.get("lifecycle_incompatibilities"))
        if isinstance(row, dict)
    ]
    lifecycle_mismatches = [
        row
        for row in lifecycle_rows
        if str(row.get("type", "")) in {"component_lifecycle_mismatch", "ops_lifecycle_mismatch"}
    ]
    if lifecycle_mismatches:
        blockers.append(
            {
                "code": "lifecycle_mismatches",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": lifecycle_mismatches,
            }
        )

    api_drift = [
        row
        for row in lifecycle_rows
        if str(row.get("type", "")) == "api_drift"
    ]
    if api_drift:
        blockers.append(
            {
                "code": "api_drift",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": api_drift,
            }
        )

    abstraction_rows = [row for row in _as_list(gaps.get("gaps")) if isinstance(row, dict)]
    topology_incompat = [
        row for row in abstraction_rows if str(row.get("type", "")) == "topology_incompatibilities"
    ]
    if topology_incompat:
        blockers.append(
            {
                "code": "topology_incompatibilities",
                "severity": "MEDIUM",
                "classification": "advisory_only",
                "details": topology_incompat,
            }
        )

    dpcm_blockers = [
        row
        for row in abstraction_rows
        if str(row.get("type", "")) == "dpcm_fe_be_migration_blockers"
    ]
    if dpcm_blockers:
        blockers.append(
            {
                "code": "dpcm_fe_be_migration_blockers",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": dpcm_blockers,
            }
        )

    runtime_blockers = [
        row
        for row in _as_list(runtime.get("runtime_portability_blockers"))
        if isinstance(row, dict)
    ]
    if runtime_blockers:
        blockers.append(
            {
                "code": "unsupported_runtime_dependencies",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": runtime_blockers,
            }
        )

    overall_conf = _to_float(_as_dict(confidence.get("scores")).get("overall_confidence", 0.0))
    if overall_conf < 0.45:
        blockers.append(
            {
                "code": "low_upstream_equivalence_confidence",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": {"overall_confidence": overall_conf},
            }
        )

    autonomous_violation = any(
        [
            _is_true(governance.get("autonomous_patching_allowed", False)),
            _is_true(governance.get("autonomous_topology_rewrite_allowed", False)),
            _is_true(governance.get("autonomous_runtime_mutation_allowed", False)),
            _is_true(governance.get("autonomous_upstream_generation_allowed", False)),
        ]
    )
    if autonomous_violation:
        blockers.append(
            {
                "code": "governance_violation",
                "severity": "HIGH",
                "classification": "blocked_unsafe",
                "details": "Autonomous mutation flags are not permitted.",
            }
        )

    blocked_unsafe = [row for row in blockers if str(row.get("classification", "")) == "blocked_unsafe"]
    advisory = [row for row in blockers if str(row.get("classification", "")) == "advisory_only"]
    risk_score = round(max(0.0, min(1.0, 1.0 - 0.22 * len(blocked_unsafe) - 0.08 * len(advisory))), 3)

    risk_classification = "LOW"
    if blocked_unsafe or risk_score < 0.45:
        risk_classification = "HIGH"
    elif advisory or risk_score < 0.7:
        risk_classification = "MEDIUM"

    classification = "PASS"
    if blocked_unsafe:
        classification = "FAIL_CLOSED"
    elif advisory:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "portability_blocker_report",
        "target_id": str(target_id),
        "classification": classification,
        "risk_classification": risk_classification,
        "risk_score": risk_score,
        "portability_blockers": blockers,
        "summary": {
            "blocked_unsafe_count": len(blocked_unsafe),
            "advisory_count": len(advisory),
            "total_detected": len(blockers),
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return GovernedPortabilityBlockerReportResult(
        portability_blocker_report=payload,
        risk_score=risk_score,
        deterministic_fingerprint=fingerprint,
    )
