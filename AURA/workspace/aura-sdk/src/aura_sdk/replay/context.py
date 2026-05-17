"""DeterministicContext — seeded RNG and pinned model versions."""

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DeterministicContext:
    """Provides deterministic execution environment.

    Seeded RNG ensures reproducible decisions.
    Pinned model version ensures consistent LLM responses.
    """

    seed: int = 42
    model_version: str = "gpt-4o-2024-08-06"
    temperature: float = 0.1

    def __post_init__(self):
        self._rng = random.Random(self.seed)

    def llm_params(self) -> dict[str, Any]:
        """Return LLM parameters for deterministic execution."""
        return {
            "seed": self.seed,
            "temperature": self.temperature,
            "model": self.model_version,
        }

    def random_choice(self, options: list) -> Any:
        """Deterministic random choice."""
        if not options:
            return None
        return self._rng.choice(options)

    def random_sample(self, population: list, k: int) -> list:
        """Deterministic random sample."""
        if not population:
            return []
        return self._rng.sample(population, min(k, len(population)))

    def deterministic_sort[T](self, items: list[T], key=None) -> list[T]:
        """Sort items deterministically (stable sort with string key)."""
        return sorted(items, key=lambda x: str(key(x)) if key else str(x))

    def random_int(self, min_val: int = 0, max_val: int = 100) -> int:
        """Deterministic random integer."""
        return self._rng.randint(min_val, max_val)

    def random_float(self, min_val: float = 0.0, max_val: float = 1.0) -> float:
        """Deterministic random float."""
        return self._rng.uniform(min_val, max_val)
