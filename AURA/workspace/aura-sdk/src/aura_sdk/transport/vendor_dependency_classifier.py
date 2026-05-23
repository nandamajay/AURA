"""Vendor dependency classifier for governed conversion reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class VendorDependencyGraphResult:
    vendor_dependency_graph: dict[str, Any]
    dependency_risk_score: float
    deterministic_fingerprint: str


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


def classify_vendor_dependencies(
    *,
    target_id: str,
    downstream_hook_inventory: Mapping[str, Any],
    callback_chain_graph: Mapping[str, Any],
    semantic_cognition: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> VendorDependencyGraphResult:
    hooks = _as_dict(downstream_hook_inventory)
    inventory = _as_dict(hooks.get("inventory"))
    adapter = _as_dict(adapter_payload)
    semantic = _as_dict(semantic_cognition)

    vendor_hooks = [str(item) for item in _as_list(inventory.get("downstream_vendor_hooks")) if str(item).strip()]
    downstream_only_apis = [str(item) for item in _as_list(inventory.get("downstream_only_apis")) if str(item).strip()]
    vendor_tokens = [str(item) for item in _as_list(inventory.get("vendor_tokens")) if str(item).strip()]

    callback_nodes = [
        row
        for row in _as_list(_as_dict(callback_chain_graph).get("nodes"))
        if isinstance(row, dict) and str(row.get("kind", "")) == "callback_function"
    ]
    callback_names = [str(row.get("id", "")).replace("callback:", "", 1) for row in callback_nodes]

    dsp_coupling = _dedupe_sorted(
        [
            token
            for token in vendor_tokens + vendor_hooks + callback_names
            if token.startswith("q6_")
            or token.startswith("apr_")
            or token.startswith("gpr_")
            or "audioreach" in token.lower()
            or "qdsp" in token.lower()
        ]
    )

    scheduler_assumptions = _dedupe_sorted(
        [
            token
            for token in downstream_only_apis + callback_names
            if "sched" in token.lower()
            or "thread" in token.lower()
            or "workqueue" in token.lower()
            or "latency" in token.lower()
            or "timing" in token.lower()
        ]
    )

    proprietary_hooks = _dedupe_sorted(
        [
            token
            for token in vendor_hooks
            if token.startswith("vendor_hook_")
            or token.startswith("trace_android_vh_")
            or token.startswith("msm_audio_")
            or token.startswith("qcom_snd_")
        ]
    )

    soundwire_gaps = _dedupe_sorted(
        [
            token
            for token in vendor_tokens + downstream_only_apis
            if token.startswith("swr_")
            or token.startswith("sdw_")
            or "soundwire" in token.lower()
        ]
    )

    downstream_callback_dependencies = _dedupe_sorted(
        [
            name
            for name in callback_names
            if name.startswith("msm_")
            or name.startswith("qcom_")
            or name.startswith("vendor_")
            or name.startswith("q6_")
            or name.startswith("apr_")
            or name.startswith("gpr_")
        ]
    )

    vendor_assumptions = _dedupe_sorted(
        downstream_only_apis
        + [
            token
            for token in vendor_tokens
            if token.startswith("msm_")
            or token.startswith("qcom_")
            or token.startswith("wcd")
            or token.startswith("lpass_")
            or token.startswith("spf_")
        ]
    )

    semantic_scores = _as_dict(_as_dict(semantic.get("classification", {})).get("scores", {}))
    vendor_coupled_score = float(semantic_scores.get("vendor_coupled", 0.4) or 0.4)

    weighted_risk = (
        0.2 * min(1.0, len(vendor_assumptions) / 30.0)
        + 0.2 * min(1.0, len(proprietary_hooks) / 20.0)
        + 0.15 * min(1.0, len(dsp_coupling) / 12.0)
        + 0.1 * min(1.0, len(soundwire_gaps) / 12.0)
        + 0.1 * min(1.0, len(downstream_callback_dependencies) / 20.0)
        + 0.1 * min(1.0, len(scheduler_assumptions) / 8.0)
        + 0.15 * max(0.0, min(1.0, vendor_coupled_score))
    )
    dependency_risk_score = round(min(1.0, weighted_risk), 3)

    classification = "PASS"
    if dependency_risk_score >= 0.7:
        classification = "HIGH_RISK"
    elif dependency_risk_score >= 0.4:
        classification = "MODERATE_RISK"

    payload = {
        "schema_version": "1.0",
        "graph_name": "vendor_dependency_graph",
        "target_id": str(target_id),
        "classification": classification,
        "vendor_specific_assumptions": vendor_assumptions,
        "unsupported_proprietary_hooks": proprietary_hooks,
        "dsp_coupling": dsp_coupling,
        "soundwire_portability_gaps": soundwire_gaps,
        "scheduler_assumptions": scheduler_assumptions,
        "downstream_only_callback_dependencies": downstream_callback_dependencies,
        "adapter_hints": {
            "upstream_equivalent_hints": _as_dict(adapter.get("upstream_equivalent_hints")),
            "portability_blocker_patterns": [
                str(item) for item in _as_list(adapter.get("portability_blocker_patterns")) if str(item).strip()
            ],
        },
        "dependency_risk_score": dependency_risk_score,
        "summary": {
            "vendor_assumption_count": len(vendor_assumptions),
            "proprietary_hook_count": len(proprietary_hooks),
            "dsp_coupling_count": len(dsp_coupling),
            "soundwire_gap_count": len(soundwire_gaps),
            "callback_dependency_count": len(downstream_callback_dependencies),
            "scheduler_assumption_count": len(scheduler_assumptions),
        },
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return VendorDependencyGraphResult(
        vendor_dependency_graph=payload,
        dependency_risk_score=dependency_risk_score,
        deterministic_fingerprint=fingerprint,
    )
