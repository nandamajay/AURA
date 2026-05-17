"""Abstract base for validation tools."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ValidationTool(ABC):
    """Base class for validation tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name."""
        raise NotImplementedError

    @abstractmethod
    async def run(self, target: Path, context: dict[str, Any]) -> dict[str, Any]:
        """Run the validation tool.

        Returns:
            Dict with keys: passed (bool), findings (list), confidence (float)
        """
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the tool is installed and available."""
        raise NotImplementedError
