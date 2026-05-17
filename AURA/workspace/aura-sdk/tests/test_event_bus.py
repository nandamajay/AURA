"""Tests for the event bus."""

import asyncio

import pytest

from aura_sdk.bus.event_bus import EventBus
from aura_sdk.models.event import EventEnvelope, EventType, EventSource


class TestEventBus:
    @pytest.fixture
    def bus(self):
        return EventBus(max_queue_size=100)

    @pytest.mark.asyncio
    async def test_start_stop(self, bus):
        await bus.start()
        assert bus.is_running
        await bus.stop()
        assert not bus.is_running

    @pytest.mark.asyncio
    async def test_publish_subscribe(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(EventType.AGENT_SPAWNED, handler)
        await bus.start()

        event = EventEnvelope(
            event_type=EventType.AGENT_SPAWNED,
            source=EventSource(subsystem="S1"),
            payload={"agent": "test"},
        )
        await bus.publish(event)

        # Wait for dispatch
        await asyncio.sleep(0.1)

        assert len(received) == 1
        assert received[0].payload["agent"] == "test"

        await bus.stop()

    @pytest.mark.asyncio
    async def test_catch_all(self, bus):
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe_all(handler)
        await bus.start()

        await bus.publish(EventEnvelope(
            event_type=EventType.TASK_CREATED,
            source=EventSource(subsystem="S1"),
        ))

        await asyncio.sleep(0.1)
        assert len(received) == 1

        await bus.stop()

    @pytest.mark.asyncio
    async def test_buffer(self, bus):
        await bus.start()

        for i in range(5):
            await bus.publish(EventEnvelope(
                event_type=EventType.AGENT_HEARTBEAT,
                source=EventSource(subsystem="S1"),
                payload={"seq": i},
            ))

        await asyncio.sleep(0.1)
        buffer = bus.get_buffer(3)
        assert len(buffer) == 3

        await bus.stop()
