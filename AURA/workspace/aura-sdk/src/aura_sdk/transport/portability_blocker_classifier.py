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
