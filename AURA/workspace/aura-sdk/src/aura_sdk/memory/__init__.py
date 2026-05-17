"""Engineering Memory System — persistent context for all decisions.

AURA evolves as a traceable engineering system, not a stateless code generator.
Every major decision records: reasoning, tradeoffs, rejected alternatives,
operational implications, scalability implications, determinism implications.
"""

from aura_sdk.memory.models import (
    DecisionRecord,
    FailureRecord,
    ReplayIncident,
    ArchitectureDrift,
    OperationalIncident,
    StabilizationEntry,
    TechnicalDebt,
    DeferredScalability,
    KnownRisk,
    FutureMigration,
)
from aura_sdk.memory.persistence import MemoryStore

__all__ = [
    "DecisionRecord",
    "FailureRecord",
    "ReplayIncident",
    "ArchitectureDrift",
    "OperationalIncident",
    "StabilizationEntry",
    "TechnicalDebt",
    "DeferredScalability",
    "KnownRisk",
    "FutureMigration",
    "MemoryStore",
]
