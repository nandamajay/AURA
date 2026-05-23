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
from aura_sdk.transport.plugins.loader import TargetPluginLoader
from aura_sdk.transport.plugins.rb3_plugin import RB3TargetPlugin, get_plugin as get_rb3_plugin

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
]
