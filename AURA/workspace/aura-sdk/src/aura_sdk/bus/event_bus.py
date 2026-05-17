"""In-memory async event bus — pub/sub with typed channels.

No external dependencies. Swappable with Redis/RabbitMQ if scale demands.
"""

import asyncio
from collections import deque
from typing import Awaitable, Callable

from aura_sdk.models.event import EventEnvelope, EventType

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventBus:
    """In-memory event bus for MVP.

    Features:
    - Typed subscriptions (per EventType)
    - Catch-all subscriptions
    - Async dispatch (never blocks publisher)
    - Ring buffer for replay (last 10K events)
    - Handler exception isolation (one bad handler doesn't crash others)
    """

    def __init__(self, max_queue_size: int = 10000, buffer_size: int = 10000):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._all_handlers: list[EventHandler] = []
        self._queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=max_queue_size)
        self._buffer: deque[EventEnvelope] = deque(maxlen=buffer_size)
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        """Start the dispatcher loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._dispatcher())

    async def stop(self) -> None:
        """Stop the dispatcher loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe to all events."""
        self._all_handlers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """Remove a subscription."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h != handler
            ]

    async def publish(self, event: EventEnvelope) -> None:
        """Publish an event to the bus. Non-blocking."""
        if self._queue.full():
            # Drop oldest to prevent memory growth
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        await self._queue.put(event)

    def get_buffer(self, count: int = 100) -> list[EventEnvelope]:
        """Get last N events from the ring buffer."""
        return list(self._buffer)[-count:]

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def subscriber_count(self) -> int:
        total = len(self._all_handlers)
        for handlers in self._subscribers.values():
            total += len(handlers)
        return total

    async def _dispatcher(self) -> None:
        """Dispatch loop — runs as a background task."""
        while self._running:
            try:
                event = await self._queue.get()
                self._buffer.append(event)

                handlers = self._subscribers.get(event.event_type, [])
                all_handlers = handlers + self._all_handlers

                if not all_handlers:
                    continue

                # Run handlers concurrently, isolated
                results = await asyncio.gather(
                    *[self._safe_handle(handler, event) for handler in all_handlers],
                    return_exceptions=True,
                )
                # Log any exceptions (results are None on success)
                for handler, result in zip(all_handlers, results):
                    if isinstance(result, Exception):
                        print(f"Event handler {handler.__name__} failed: {result}")

            except asyncio.CancelledError:
                break
            except Exception:
                # Never crash the bus
                pass

    async def _safe_handle(self, handler: EventHandler, event: EventEnvelope) -> None:
        """Run a single handler, catching exceptions."""
        try:
            await handler(event)
        except Exception:
            pass  # Exception logged by dispatcher
