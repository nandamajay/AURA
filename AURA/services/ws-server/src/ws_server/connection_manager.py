"""WebSocket connection manager — tracks active connections."""

from fastapi import WebSocket

from aura_sdk.logging.logger import get_logger

logger = get_logger("ws_server")

MAX_CONNECTIONS = 100


class ConnectionManager:
    """Manages WebSocket connections from dashboard clients.

    Features:
    - Connection limit enforcement (max 100)
    - Per-connection subscription tracking
    - Broadcast to all or filtered by channel
    """

    def __init__(self, max_connections: int = MAX_CONNECTIONS):
        self.max_connections = max_connections
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[str]] = {}  # conn_id -> {channel}

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    @property
    def subscriber_counts(self) -> dict[str, int]:
        """Count subscribers per channel."""
        counts: dict[str, int] = {}
        for subs in self._subscriptions.values():
            for ch in subs:
                counts[ch] = counts.get(ch, 0) + 1
        return counts

    async def connect(self, conn_id: str, websocket: WebSocket) -> bool:
        """Accept a new connection. Returns False if limit reached."""
        if len(self._connections) >= self.max_connections:
            logger.warning("connection_limit_rejected", current=len(self._connections))
            return False

        await websocket.accept()
        self._connections[conn_id] = websocket
        self._subscriptions[conn_id] = set()
        logger.info("ws_connected", conn_id=conn_id, total=self.connection_count)
        return True

    def disconnect(self, conn_id: str) -> None:
        """Remove a connection."""
        self._connections.pop(conn_id, None)
        self._subscriptions.pop(conn_id, None)
        logger.info("ws_disconnected", conn_id=conn_id, total=self.connection_count)

    def subscribe(self, conn_id: str, channels: list[str]) -> None:
        """Subscribe a connection to channels."""
        if conn_id in self._subscriptions:
            self._subscriptions[conn_id].update(channels)

    def unsubscribe(self, conn_id: str, channels: list[str]) -> None:
        """Unsubscribe a connection from channels."""
        if conn_id in self._subscriptions:
            self._subscriptions[conn_id].difference_update(channels)

    async def broadcast(
        self,
        message: dict,
        channel: str | None = None,
        channels: set[str] | list[str] | None = None,
    ) -> int:
        """Broadcast a message to connections.

        Args:
            message: JSON-serializable dict.
            channel: If set, only send to subscribers of this channel.
            channels: Optional channel-set match; any intersection receives message.

        Returns:
            Number of connections that received the message.
        """
        sent = 0
        dead = []
        requested_channels = set(channels or [])
        if channel:
            requested_channels.add(channel)

        for conn_id, ws in self._connections.items():
            # Check channel subscription
            if requested_channels and conn_id in self._subscriptions:
                if not self._subscriptions[conn_id].intersection(requested_channels):
                    continue

            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                dead.append(conn_id)

        # Clean up dead connections
        for conn_id in dead:
            self.disconnect(conn_id)

        return sent

    async def send_to(self, conn_id: str, message: dict) -> bool:
        """Send a message to a specific connection."""
        ws = self._connections.get(conn_id)
        if ws is None:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            self.disconnect(conn_id)
            return False
