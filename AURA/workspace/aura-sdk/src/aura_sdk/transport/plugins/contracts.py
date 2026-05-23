"""Portable target plugin contracts for AURA transport cognition runtime.

The contract intentionally keeps core runtime generic and pushes target
intelligence into plugin-provided providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

ProviderPayload = Mapping[str, Any]
ProviderResult = dict[str, Any]
ProviderFn = Callable[[ProviderPayload], ProviderResult]


class TargetPluginContract(Protocol):
    """Required contract for target plugins.

    All target-specific intelligence must be provided through these providers.
    """

    target_id: str
    topology_provider: ProviderFn
    mixer_provider: ProviderFn
    pcm_provider: ProviderFn
    route_provider: ProviderFn
    evidence_provider: ProviderFn
    capability_provider: ProviderFn
    validation_provider: ProviderFn
    dts_adapter: ProviderFn
    topology_adapter: ProviderFn
    vendor_api_adapter: ProviderFn
    subsystem_descriptor_provider: ProviderFn
    runtime_evidence_adapter: ProviderFn
    topology_evidence_adapter: ProviderFn
    semantic_evidence_adapter: ProviderFn
    downstream_upstream_adapter: ProviderFn
    topology_translation_adapter: ProviderFn
    runtime_conversion_adapter: ProviderFn


@dataclass(frozen=True)
class PluginNegotiationRequest:
    fingerprint: Mapping[str, Any]
    target_profile: Mapping[str, Any]
    capability_registry: Mapping[str, Any]
    governance_state: Mapping[str, Any]


@dataclass(frozen=True)
class PluginNegotiationResult:
    classification: str
    selected_target_id: str
    confidence: float
    reasons: list[str]
    candidate_scores: list[dict[str, Any]]
    governance_posture: str


def assert_plugin_contract(plugin: Any) -> None:
    """Fail-closed contract validation for plugin objects."""

    required_fields = (
        "target_id",
        "topology_provider",
        "mixer_provider",
        "pcm_provider",
        "route_provider",
        "evidence_provider",
        "capability_provider",
        "validation_provider",
        "dts_adapter",
        "topology_adapter",
        "vendor_api_adapter",
        "subsystem_descriptor_provider",
        "runtime_evidence_adapter",
        "topology_evidence_adapter",
        "semantic_evidence_adapter",
        "downstream_upstream_adapter",
        "topology_translation_adapter",
        "runtime_conversion_adapter",
    )

    missing: list[str] = []
    non_callable: list[str] = []

    for field in required_fields:
        if not hasattr(plugin, field):
            missing.append(field)
            continue
        if field == "target_id":
            continue
        if not callable(getattr(plugin, field)):
            non_callable.append(field)

    if missing:
        raise TypeError(f"plugin_contract_missing_fields:{','.join(sorted(missing))}")
    if non_callable:
        raise TypeError(f"plugin_contract_non_callable_fields:{','.join(sorted(non_callable))}")

    target = str(getattr(plugin, "target_id", "")).strip()
    if not target:
        raise TypeError("plugin_contract_invalid_target_id")
