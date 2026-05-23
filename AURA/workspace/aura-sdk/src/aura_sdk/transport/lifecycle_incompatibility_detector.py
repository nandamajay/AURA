"""Lifecycle incompatibility detection for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class LifecycleIncompatibilityResult:
    lifecycle_incompatibility_report: dict[str, Any]
    lifecycle_risk_score: float
    deterministic_fingerprint: str


_EXPECTED_COMPONENT_CALLBACKS = {"probe", "remove"}
_EXPECTED_OPS_CALLBACKS = {"startup", "hw_params", "trigger", "shutdown"}


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _dedupe_sorted(items: list[str]) -> list[str]:
    return sorted({str(item).strip() for item in items if str(item).strip()})


def detect_lifecycle_incompatibilities(
    *,
    target_id: str,
    driver_registration_graph: Mapping[str, Any],
    callback_chain_graph: Mapping[str, Any],
    upstream_equivalence_trace: Mapping[str, Any],
    evidence_references: list[str] | None,
) -> LifecycleIncompatibilityResult:
    registration = _as_dict(driver_registration_graph)
    callback_graph = _as_dict(callback_chain_graph)
    upstream_trace = _as_dict(upstream_equivalence_trace)

    component_rows = [row for row in _as_list(registration.get("component_lifecycle")) if isinstance(row, dict)]
    ops_rows = [row for row in _as_list(registration.get("ops_lifecycle")) if isinstance(row, dict)]

    incompatibilities: list[dict[str, Any]] = []

    for row in component_rows:
        callbacks = {
            str(item.get("callback", "")).strip()
            for item in _as_list(row.get("callbacks"))
            if isinstance(item, dict) and str(item.get("callback", "")).strip()
        }
        missing = sorted(_EXPECTED_COMPONENT_CALLBACKS.difference(callbacks))
        if missing:
            incompatibilities.append(
                {
                    "type": "component_lifecycle_mismatch",
                    "severity": "MEDIUM",
                    "component_driver": str(row.get("component_driver", "")),
                    "missing_callbacks": missing,
                }
            )

    for row in ops_rows:
        callbacks = {
            str(item.get("callback", "")).strip()
            for item in _as_list(row.get("callbacks"))
            if isinstance(item, dict) and str(item.get("callback", "")).strip()
        }
        missing = sorted(_EXPECTED_OPS_CALLBACKS.difference(callbacks))
        if missing:
            incompatibilities.append(
                {
                    "type": "ops_lifecycle_mismatch",
                    "severity": "MEDIUM",
                    "ops_structure": str(row.get("ops_structure", "")),
                    "missing_callbacks": missing,
                }
            )

    callback_names = [
        str(row.get("id", "")).replace("callback:", "", 1)
        for row in _as_list(callback_graph.get("nodes"))
        if isinstance(row, dict) and str(row.get("kind", "")) == "callback_function"
    ]
    vendor_callbacks = _dedupe_sorted(
        [
            name
            for name in callback_names
            if name.startswith("msm_")
            or name.startswith("qcom_")
            or name.startswith("vendor_")
            or name.startswith("q6_")
        ]
    )
    if vendor_callbacks:
        incompatibilities.append(
            {
                "type": "downstream_callback_dependency",
                "severity": "HIGH",
                "callbacks": vendor_callbacks,
            }
        )

    unresolved_entries = [
        row
        for row in _as_list(upstream_trace.get("entries"))
        if isinstance(row, dict)
        and str(row.get("equivalence_status", "")).upper() == "UNRESOLVED"
    ]
    unresolved_constructs = {
        str(row.get("downstream_construct", "")).strip()
        for row in unresolved_entries
        if str(row.get("downstream_construct", "")).strip()
    }

    api_drift = _dedupe_sorted(
        [
            name
            for name in unresolved_constructs
            if name.endswith("_ops")
            or "register" in name.lower()
            or name.startswith("msm_")
            or name.startswith("qcom_")
        ]
    )
    if api_drift:
        incompatibilities.append(
            {
                "type": "api_drift",
                "severity": "HIGH",
                "constructs": api_drift[:120],
            }
        )

    risk = round(
        min(
            1.0,
            0.2 * len([item for item in incompatibilities if str(item.get("severity", "")).upper() == "HIGH"])
            + 0.08 * len([item for item in incompatibilities if str(item.get("severity", "")).upper() == "MEDIUM"]),
        ),
        3,
    )

    classification = "PASS"
    if any(str(item.get("severity", "")).upper() == "HIGH" for item in incompatibilities):
        classification = "FAIL_CLOSED"
    elif incompatibilities:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "lifecycle_incompatibility_report",
        "target_id": str(target_id),
        "classification": classification,
        "lifecycle_incompatibilities": incompatibilities,
        "summary": {
            "component_driver_count": len(component_rows),
            "ops_structure_count": len(ops_rows),
            "vendor_callback_count": len(vendor_callbacks),
            "api_drift_count": len(api_drift),
            "incompatibility_count": len(incompatibilities),
        },
        "lifecycle_risk_score": risk,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return LifecycleIncompatibilityResult(
        lifecycle_incompatibility_report=payload,
        lifecycle_risk_score=risk,
        deterministic_fingerprint=fingerprint,
    )
