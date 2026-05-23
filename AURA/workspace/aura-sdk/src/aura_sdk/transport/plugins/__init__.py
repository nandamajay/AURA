"""Target plugin abstractions for portable cognition runtime."""

from aura_sdk.transport.plugins.contracts import (
    PluginNegotiationRequest,
    PluginNegotiationResult,
    ProviderFn,
    ProviderPayload,
    ProviderResult,
    TargetPluginContract,
    assert_plugin_contract,
)
from aura_sdk.transport.plugins.drift import detect_plugin_drift
from aura_sdk.transport.plugins.isolation_validator import PluginIsolationValidator
from aura_sdk.transport.plugins.lifecycle import (
    PluginLifecycleOrchestrator,
    PluginLifecycleResult,
)
from aura_sdk.transport.plugins.loader import TargetPluginLoader
from aura_sdk.transport.plugins.rb3_plugin import RB3TargetPlugin, get_plugin as get_rb3_plugin
from aura_sdk.transport.plugins.simulation_plugins import (
    DegradedTargetGammaPlugin,
    FakeTargetAlphaPlugin,
    FakeTargetBetaPlugin,
    build_simulation_registry_payload,
    get_degraded_target_gamma_plugin,
    get_fake_target_alpha_plugin,
    get_fake_target_beta_plugin,
)

__all__ = [
    "ProviderFn",
    "ProviderPayload",
    "ProviderResult",
    "TargetPluginContract",
    "PluginNegotiationRequest",
    "PluginNegotiationResult",
    "assert_plugin_contract",
    "TargetPluginLoader",
    "RB3TargetPlugin",
    "get_rb3_plugin",
    "PluginIsolationValidator",
    "PluginLifecycleOrchestrator",
    "PluginLifecycleResult",
    "detect_plugin_drift",
    "FakeTargetAlphaPlugin",
    "FakeTargetBetaPlugin",
    "DegradedTargetGammaPlugin",
    "get_fake_target_alpha_plugin",
    "get_fake_target_beta_plugin",
    "get_degraded_target_gamma_plugin",
    "build_simulation_registry_payload",
]
