"""Plugin registry — discovery, loading, and validation."""

import importlib
import importlib.util
import pkgutil
from pathlib import Path
from typing import Any

from aura_sdk.plugins.interface import SubsystemPlugin


class PluginRegistry:
    """Registry for subsystem plugins.

    Scans plugin directories, validates, and makes plugins available.
    Thread-safe — plugins are immutable after loading.
    """

    def __init__(self):
        self._plugins: dict[str, SubsystemPlugin] = {}

    def register(self, name: str, plugin: SubsystemPlugin) -> None:
        """Register a plugin instance."""
        self._plugins[name] = plugin

    def get(self, name: str) -> SubsystemPlugin | None:
        """Get a plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def get_metadata(self, name: str) -> dict[str, Any] | None:
        """Get plugin metadata."""
        plugin = self._plugins.get(name)
        if plugin is None:
            return None
        m = plugin.metadata
        return {
            "name": m.name,
            "display_name": m.display_name,
            "version": m.version,
            "description": m.description,
            "capabilities": [c.value for c in m.capabilities],
            "kernel_subsystems": m.kernel_subsystems,
        }

    async def scan_directory(self, plugins_path: Path) -> int:
        """Scan a directory for plugins and register them.

        Each subdirectory should be a Python package with a plugin.py
        that exports a Plugin class inheriting from SubsystemPlugin.

        Returns:
            Number of plugins loaded.
        """
        count = 0
        if not plugins_path.exists():
            return 0

        for item in plugins_path.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                try:
                    plugin = self._load_plugin_package(item)
                    if plugin:
                        self.register(plugin.metadata.name, plugin)
                        count += 1
                except Exception as e:
                    print(f"Failed to load plugin from {item}: {e}")

        return count

    def _load_plugin_package(self, path: Path) -> SubsystemPlugin | None:
        """Load a plugin from a package directory."""
        spec = importlib.util.spec_from_file_location(
            path.name, path / "__init__.py"
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Look for Plugin class
        if hasattr(module, "Plugin") and isinstance(module.Plugin, type):
            instance = module.Plugin()
            if isinstance(instance, SubsystemPlugin):
                return instance

        return None


def discover_plugins(plugins_path: str | Path) -> list[dict[str, Any]]:
    """Discover available plugins without loading them.

    Returns:
        List of plugin metadata dictionaries.
    """
    path = Path(plugins_path)
    results = []
    if not path.exists():
        return results

    for item in path.iterdir():
        if item.is_dir() and (item / "__init__.py").exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    item.name, item / "__init__.py"
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "Plugin"):
                        instance = module.Plugin()
                        m = instance.metadata
                        results.append({
                            "name": m.name,
                            "display_name": m.display_name,
                            "version": m.version,
                            "capabilities": [c.value for c in m.capabilities],
                        })
            except Exception:
                pass  # Skip unloadable plugins

    return results
