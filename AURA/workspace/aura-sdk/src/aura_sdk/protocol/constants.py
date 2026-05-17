"""Constants for the agent stdio protocol."""

from enum import IntEnum, StrEnum


class ExitCode(IntEnum):
    """Canonical agent exit codes.

    0: Success — normal completion, results valid
    1: Validation failed — output rejected by internal validation
    2: Unrecoverable — bad input, no retry
    3: Timeout — watchdog timeout, retryable
    4: Resource exhausted — OOM, disk full, retryable
    5: LLM unavailable — gateway down, retry with fallback
    """

    SUCCESS = 0
    VALIDATION_FAILED = 1
    UNRECOVERABLE = 2
    TIMEOUT = 3
    RESOURCE_EXHAUSTED = 4
    LLM_UNAVAILABLE = 5


class MessageType(StrEnum):
    """Message types on the stdio wire protocol."""

    TASK_ASSIGN = "task.assign"
    TASK_CANCEL = "task.cancel"
    PROGRESS = "progress"
    TASK_COMPLETE = "task.complete"
    HEARTBEAT = "heartbeat"
    ERROR = "error"


# Timing constants
HEARTBEAT_INTERVAL_SECONDS = 30
WATCHDOG_TIMEOUT_SECONDS = 90  # 3 missed heartbeats
WATCHDOG_SIGTERM_WAIT_SECONDS = 10
