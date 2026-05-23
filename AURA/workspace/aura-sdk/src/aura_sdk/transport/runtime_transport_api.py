"""Runtime transport abstraction API.

Fail-closed by default. Commands are classified before execution, and
unsafe operations require explicit operator approval.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CommandClassification(str, Enum):
    SAFE_READ = "safe_read"
    REQUIRES_OPERATOR_APPROVAL = "requires_operator_approval"


class TransportConfidence(str, Enum):
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    PARTIAL_CONNECTIVITY = "partial_connectivity"
    TRANSPORT_READY = "transport_ready"
    CAPTURE_READY = "capture_ready"
    ADVISORY_ONLY = "advisory_only"
    ESCALATION_REQUIRED = "escalation_required"


class RuntimeState(str, Enum):
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    EXECUTED = "executed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    DISCONNECTED = "disconnected"
    INVALID = "invalid"


class TransportResponse(BaseModel):
    """Standard runtime transport response format."""

    transport: str = ""
    command: str = ""
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    timestamp: str = ""
    duration_ms: int = 0
    runtime_state: RuntimeState = RuntimeState.UNKNOWN
    confidence: TransportConfidence = TransportConfidence.UNKNOWN
    classification: CommandClassification = CommandClassification.SAFE_READ
    notes: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class TransportMetadata:
    transport: str
    target: str | None = None
    session_id: str | None = None
    capabilities: list[str] | None = None


class RuntimeTransportAPI(abc.ABC):
    """Abstract base class for transport adapters."""

    metadata: TransportMetadata

    def __init__(self, metadata: TransportMetadata):
        self.metadata = metadata

    @abc.abstractmethod
    def execute(
        self,
        command: str,
        *,
        timeout_ms: int = 10_000,
        classification: CommandClassification | None = None,
        operator_approved: bool = False,
    ) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def push_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def pull_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        raise NotImplementedError

    @abc.abstractmethod
    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        raise NotImplementedError


UNSAFE_TOKENS = (
    "reboot",
    "fastboot",
    "flash",
    "factory reset",
    "mkfs",
    "dd ",
    "setenforce",
    "getenforce",
    "stop ",
    "start ",
    "svc ",
    "kill",
    "rmmod",
    "modprobe -r",
    "insmod",
    "mount -o remount",
    ">/sys",
    "> /sys",
    ">/proc",
    "> /proc",
    "tee /sys",
    "tee /proc",
)


def classify_command(command: str) -> CommandClassification:
    lowered = command.lower()
    if lowered.startswith("aura_adb_push "):
        return CommandClassification.REQUIRES_OPERATOR_APPROVAL
    for token in UNSAFE_TOKENS:
        if token in lowered:
            return CommandClassification.REQUIRES_OPERATOR_APPROVAL
    return CommandClassification.SAFE_READ


def make_blocked_response(
    transport: str,
    command: str,
    classification: CommandClassification,
    reason: str,
) -> TransportResponse:
    return TransportResponse(
        transport=transport,
        command=command,
        exit_code=-1,
        stdout="",
        stderr=reason,
        timestamp=str(time.time()),
        duration_ms=0,
        runtime_state=RuntimeState.BLOCKED,
        confidence=TransportConfidence.UNKNOWN,
        classification=classification,
        notes={"blocked": True, "reason": reason},
    )
