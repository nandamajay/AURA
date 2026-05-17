"""Event channel definitions — group related event types."""

from aura_sdk.models.event import EventType

# Channel → EventType mappings

AGENT_LIFECYCLE: list[EventType] = [
    EventType.AGENT_REGISTERED,
    EventType.AGENT_SPAWNED,
    EventType.AGENT_HEARTBEAT,
    EventType.AGENT_COMPLETED,
    EventType.AGENT_FAILED,
    EventType.AGENT_TIMEOUT,
    EventType.AGENT_KILLED,
]

TASK_ORCHESTRATION: list[EventType] = [
    EventType.TASK_CREATED,
    EventType.TASK_QUEUED,
    EventType.TASK_STARTED,
    EventType.TASK_PROGRESS,
    EventType.TASK_COMPLETED,
    EventType.TASK_CANCELLED,
]

SIMULATION: list[EventType] = [
    EventType.SIM_STARTED,
    EventType.SIM_PROGRESS,
    EventType.SIM_COMPLETED,
    EventType.SIM_FAILED,
]

GOVERNANCE: list[EventType] = [
    EventType.APPROVAL_REQUIRED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_REJECTED,
    EventType.ESCALATION_TRIGGERED,
]

LLM: list[EventType] = [
    EventType.LLM_REQUEST,
    EventType.LLM_RESPONSE,
    EventType.LLM_ERROR,
    EventType.LLM_CACHE_HIT,
]

SYSTEM: list[EventType] = [
    EventType.SERVICE_STARTED,
    EventType.SERVICE_STOPPED,
    EventType.CIRCUIT_BREAKER_STATE,
]

ALL_CHANNELS: dict[str, list[EventType]] = {
    "agent.lifecycle": AGENT_LIFECYCLE,
    "task.orchestration": TASK_ORCHESTRATION,
    "simulation": SIMULATION,
    "governance": GOVERNANCE,
    "llm": LLM,
    "system": SYSTEM,
}
