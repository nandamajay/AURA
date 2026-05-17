"""SubsystemPlugin ABC — contract for all subsystem plugins.

Defines 7 extension points that any subsystem can implement.
Only audio-qualcomm is implemented in P0; the interface supports all 8 subsystems.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class PluginCapability(StrEnum):
    """Capabilities a plugin can advertise."""

    RULE_DISCOVERY = "rule_discovery"  # Can discover migration rules
    PATTERN_MATCHING = "pattern_matching"  # Can match downstream→upstream patterns
    HEURISTIC_VALIDATION = "heuristic_validation"  # Can validate with heuristics
    SIMULATION = "simulation"  # Can run subsystem simulations
    MAINTAINER_LOOKUP = "maintainer_lookup"  # Can find subsystem maintainers
    CODE_GENERATION = "code_generation"  # Can generate upstream-ready code
    PATCH_REVIEW = "patch_review"  # Can review patches for subsystem


@dataclass
class PluginMetadata:
    """Metadata describing a subsystem plugin."""

    name: str = ""  # Machine name, e.g. "audio-qualcomm"
    display_name: str = ""  # Human name, e.g. "Qualcomm Audio"
    version: str = "0.1.0"
    description: str = ""
    capabilities: list[PluginCapability] = field(default_factory=list)
    author: str = ""
    kernel_subsystems: list[str] = field(default_factory=list)
    # e.g. ["sound/soc/codecs", "sound/soc/qcom"]


class SubsystemPlugin(ABC):
    """Abstract base class for all subsystem plugins.

    Implementations must be stateless — all state in the database.
    Agents call plugin methods during execution.
    """

    def __init__(self):
        self.metadata = self._init_metadata()

    @abstractmethod
    def _init_metadata(self) -> PluginMetadata:
        """Return plugin metadata. Called during __init__."""
        raise NotImplementedError

    @abstractmethod
    async def load_rules(self, rules_path: Path) -> list[dict[str, Any]]:
        """Load migration rules for this subsystem.

        Args:
            rules_path: Directory containing rule files.

        Returns:
            List of rule dictionaries.
        """
        raise NotImplementedError

    @abstractmethod
    async def validate_patch(self, patch_path: Path, context: dict[str, Any]) -> dict[str, Any]:
        """Validate a patch using subsystem-specific heuristics.

        Args:
            patch_path: Path to the patch file.
            context: Additional context (target version, config, etc.)

        Returns:
            Validation result with findings and confidence.
        """
        raise NotImplementedError

    @abstractmethod
    async def suggest_fix(self, issue: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Suggest a fix for a validation issue.

        Args:
            issue: The issue to fix (from validate_patch).
            context: Additional context.

        Returns:
            Suggestion with code changes and confidence.
        """
        raise NotImplementedError

    def get_capabilities(self) -> list[PluginCapability]:
        """Return capabilities this plugin provides."""
        return self.metadata.capabilities

    def has_capability(self, capability: PluginCapability) -> bool:
        """Check if plugin provides a specific capability."""
        return capability in self.metadata.capabilities
