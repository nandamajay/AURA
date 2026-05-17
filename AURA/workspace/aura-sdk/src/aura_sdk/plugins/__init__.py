"""Plugin system — subsystem extension interface."""

from aura_sdk.plugins.interface import SubsystemPlugin, PluginMetadata, PluginCapability
from aura_sdk.plugins.marketplace import PluginMarketplace, PluginPackage
from aura_sdk.plugins.registry import PluginRegistry, discover_plugins
from aura_sdk.plugins.transfer import CrossSubsystemTransfer

__all__ = [
    "SubsystemPlugin",
    "PluginMetadata",
    "PluginCapability",
    "PluginPackage",
    "PluginMarketplace",
    "CrossSubsystemTransfer",
    "PluginRegistry",
    "discover_plugins",
]
