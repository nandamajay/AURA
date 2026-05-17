"""Core event bridge: EventBus -> ws-server broadcast."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import FastAPI, Request

from aura_sdk.bus.channels import ALL_CHANNELS
from aura_sdk.bus.event_bus import EventBus
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventSource, EventType

logger = get_logger("core.events")


_EVENT_CHANNEL_MAP: dict[EventType, str] = {}
for channel_name, event_types in ALL_CHANNELS.items():
    for event_type in event_types:
        _EVENT_CHANNEL_MAP[event_type] = channel_name


async def start_event_bus(app: FastAPI, ws_server_url: str) -> EventBus:
    """Initialize and start the in-memory EventBus with ws forwarder."""
    event_bus = EventBus()

    async def _forward_to_ws(event: EventEnvelope) -> None:
        channel = _EVENT_CHANNEL_MAP.get(event.event_type, "system")
        payload = {
            "channel": channel,
            "event": {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "timestamp": event.timestamp.isoformat(),
                "source": event.source.model_dump(),
                "payload": event.payload,
                "trace_id": event.trace_id,
                "version": event.version,
            },
        }
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(f"{ws_server_url}/broadcast", json=payload)
                if resp.status_code >= 400:
                    logger.warning(
                        "event_forward_failed",
                        status=resp.status_code,
                        event_type=event.event_type.value,
                        channel=channel,
                    )
        except Exception as exc:
            logger.warning(
                "event_forward_error",
                error=str(exc),
                event_type=event.event_type.value,
                channel=channel,
            )

    event_bus.subscribe_all(_forward_to_ws)
    await event_bus.start()
    app.state.event_bus = event_bus
    logger.info("event_bus_started")
    return event_bus


async def stop_event_bus(app: FastAPI) -> None:
    """Stop EventBus if running."""
    event_bus: EventBus | None = getattr(app.state, "event_bus", None)
    if event_bus is not None:
        await event_bus.stop()
        logger.info("event_bus_stopped")


async def publish_event(
    app_or_request: FastAPI | Request,
    event_type: EventType,
    payload: dict[str, Any] | None = None,
    *,
    task_id: str = "",
    agent_type: str = "",
    agent_id: str = "",
    trace_id: str = "",
) -> bool:
    """Publish an event through core EventBus if available."""
    app = app_or_request.app if isinstance(app_or_request, Request) else app_or_request
    event_bus: EventBus | None = getattr(app.state, "event_bus", None)
    if event_bus is None:
        return False

    envelope = EventEnvelope(
        event_type=event_type,
        source=EventSource(
            subsystem="S1",
            service="core",
            task_id=task_id,
            agent_type=agent_type,
            agent_id=agent_id,
        ),
        payload=payload or {},
        trace_id=trace_id,
    )
    await event_bus.publish(envelope)
    return True
