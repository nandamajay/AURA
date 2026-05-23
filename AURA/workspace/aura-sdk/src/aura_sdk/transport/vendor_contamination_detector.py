"""Vendor contamination detection for governed upstream patch cognition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.semantic_fingerprint import stable_fingerprint


@dataclass(frozen=True)
class VendorContaminationResult:
    vendor_contamination_report: dict[str, Any]
    contamination_score: float
    deterministic_fingerprint: str


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _is_vendor_token(value: str) -> bool:
    token = str(value).strip().lower()
    if not token:
        return False
    markers = (
        "qcom",
        "msm",
        "apr",
        "adsp",
        "qdsp",
        "wcd",
        "bolero",
        "lpass",
        "audioreach",
        "audio_prm",
    )
    return any(marker in token for marker in markers)


def _dedupe_sorted_strings(values: list[Any]) -> list[str]:
    return sorted({str(item).strip() for item in values if str(item).strip()})


def detect_vendor_contamination(
    *,
    target_id: str,
    downstream_driver_graph: Mapping[str, Any],
    downstream_hook_inventory: Mapping[str, Any],
    semantic_cognition: Mapping[str, Any],
    adapter_payload: Mapping[str, Any] | None,
    evidence_references: list[str] | None,
) -> VendorContaminationResult:
    graph = _as_dict(downstream_driver_graph)
    hooks = _as_dict(downstream_hook_inventory)
    semantic = _as_dict(semantic_cognition)
    adapter = _as_dict(adapter_payload)

    extracted = _as_dict(graph.get("extracted"))
    inventory = _as_dict(hooks.get("inventory"))

    vendor_extensions = _dedupe_sorted_strings(
        _as_list(extracted.get("vendor_extensions"))
        + _as_list(inventory.get("vendor_tokens"))
        + _as_list(_as_dict(adapter.get("semantic_driver")).get("downstream_only_apis"))
    )
    proprietary_hooks = _dedupe_sorted_strings(
        _as_list(extracted.get("proprietary_hooks"))
        + _as_list(inventory.get("proprietary_runtime_hooks"))
        + _as_list(_as_dict(adapter.get("semantic_driver")).get("vendor_hooks"))
    )
    downstream_only_apis = _dedupe_sorted_strings(
        _as_list(inventory.get("downstream_only_apis"))
        + _as_list(_as_dict(adapter.get("semantic_driver")).get("downstream_only_apis"))
    )

    token_pool = vendor_extensions + proprietary_hooks + downstream_only_apis
    vendor_marker_hits = [token for token in token_pool if _is_vendor_token(token)]

    semantic_scores = _as_dict(_as_dict(semantic.get("classification")).get("scores"))
    vendor_coupled_score = float(semantic_scores.get("vendor_coupled", 0.0) or 0.0)

    extension_count = len(vendor_extensions)
    hook_count = len(proprietary_hooks)
    downstream_only_count = len(downstream_only_apis)
    marker_count = len(vendor_marker_hits)

    contamination_score = round(
        min(
            1.0,
            0.30 * min(1.0, extension_count / 80.0)
            + 0.30 * min(1.0, hook_count / 40.0)
            + 0.25 * min(1.0, downstream_only_count / 80.0)
            + 0.10 * min(1.0, marker_count / 160.0)
            + 0.05 * min(1.0, vendor_coupled_score),
        ),
        3,
    )

    high_signals = []
    if downstream_only_count > 0:
        high_signals.append("downstream_only_apis")
    if hook_count > 0:
        high_signals.append("proprietary_runtime_hooks")

    classification = "PASS"
    if contamination_score >= 0.75 or downstream_only_count > 25:
        classification = "FAIL_CLOSED"
    elif contamination_score >= 0.35:
        classification = "ADVISORY_ONLY"

    payload = {
        "schema_version": "1.0",
        "report_name": "vendor_contamination_report",
        "target_id": str(target_id),
        "classification": classification,
        "contamination_score": contamination_score,
        "high_risk_signals": sorted(high_signals),
        "summary": {
            "vendor_extension_count": extension_count,
            "proprietary_hook_count": hook_count,
            "downstream_only_api_count": downstream_only_count,
            "vendor_marker_hits": marker_count,
        },
        "detected": {
            "vendor_extensions": vendor_extensions[:400],
            "proprietary_runtime_hooks": proprietary_hooks[:400],
            "downstream_only_apis": downstream_only_apis[:400],
        },
        "adapter_hints": {
            "provider": str(adapter.get("provider", "")),
            "fingerprint": str(adapter.get("fingerprint", "")),
        },
        "advisory_only_behavior": True,
        "runtime_truth_precedence": True,
        "evidence_references": [str(item) for item in (evidence_references or []) if str(item).strip()],
    }
    fingerprint = stable_fingerprint(payload)
    payload["deterministic_fingerprint"] = fingerprint

    return VendorContaminationResult(
        vendor_contamination_report=payload,
        contamination_score=contamination_score,
        deterministic_fingerprint=fingerprint,
    )
