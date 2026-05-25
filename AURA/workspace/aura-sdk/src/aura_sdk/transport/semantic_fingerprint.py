"""Deterministic semantic fingerprinting utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aura_sdk.transport.deterministic_serialization import stable_sha256


@dataclass(frozen=True)
class SemanticFingerprintResult:
    fingerprint: str
    payload: dict[str, Any]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def stable_fingerprint(payload: Mapping[str, Any]) -> str:
    return stable_sha256(dict(payload))


def build_vendor_dependency_fingerprint(
    *,
    target_id: str,
    dts_semantics: Mapping[str, Any],
    driver_semantics: Mapping[str, Any],
) -> SemanticFingerprintResult:
    dts = _as_dict(dts_semantics)
    drv = _as_dict(driver_semantics)

    payload = {
        "target_id": str(target_id),
        "vendor_only_nodes": sorted(str(item) for item in _as_list(dts.get("vendor_only_nodes"))),
        "downstream_only_apis": sorted(str(item) for item in _as_list(drv.get("downstream_only_apis"))),
        "vendor_hooks": sorted(str(item) for item in _as_list(drv.get("vendor_hooks"))),
        "wrapper_layers": sorted(str(item) for item in _as_list(drv.get("wrapper_layers"))),
        "codec_coupling": bool(drv.get("codec_coupling", False)),
        "platform_assumptions": sorted(str(item) for item in _as_list(drv.get("platform_assumptions"))),
    }
    return SemanticFingerprintResult(
        fingerprint=stable_fingerprint(payload),
        payload=payload,
    )
