"""Simulation engine models."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class SimulationType(StrEnum):
    """Types of audio subsystem simulations."""

    PROBE_FLOW = "probe_flow"
    DAPM = "dapm"
    PCM = "pcm"
    SOUNDWIRE = "soundwire"
    RUNTIME_PM = "runtime_pm"
    DSP = "dsp"
    DMA_IRQ = "dma_irq"


class FidelityMode(StrEnum):
    """Simulation fidelity levels."""

    STATE_MACHINE = "state_machine"
    QEMU = "qemu"


class SimulationStatus(StrEnum):
    """Simulation execution states."""

    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class SimulationResult(BaseModel):
    """Result of a subsystem simulation."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    patch_id: str = ""
    simulation_type: SimulationType = SimulationType.DAPM
    fidelity_mode: FidelityMode = FidelityMode.STATE_MACHINE
    status: SimulationStatus = SimulationStatus.PENDING
    findings: dict[str, Any] = Field(default_factory=dict)
    failure_predictions: list[str] = Field(default_factory=list)
    confidence_impact: float = 0.0
    duration_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
