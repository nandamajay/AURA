"""WebSocket + SSE Server — FastAPI app."""

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aura_sdk.logging.logger import configure_logging, get_logger
from aura_sdk.bus.channels import ALL_CHANNELS
from ws_server.connection_manager import ConnectionManager

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
MAX_CONNECTIONS = int(os.environ.get("MAX_CONNECTIONS", "100"))

configure_logging(LOG_LEVEL)
logger = get_logger("ws_server")

# Service state
manager = ConnectionManager(max_connections=MAX_CONNECTIONS)
app = FastAPI(title="AURA WebSocket Server", version="0.1.0")

# Event buffer for SSE replay
_event_buffer: list[dict] = []
_BUFFER_SIZE = 1000
_sse_clients: dict[str, dict[str, object]] = {}


class BroadcastRequest(BaseModel):
    """Validated request body for internal event broadcast endpoint."""

    channel: str = Field(min_length=1)
    event: dict[str, object] = Field(default_factory=dict)


def _queue_sse_event(channel: str, event: dict) -> None:
    """Fan-out a broadcast event to subscribed SSE clients."""
    for client in list(_sse_clients.values()):
        channels = client["channels"]
        if channels and channel not in channels:
            continue
        queue = client["queue"]
        assert isinstance(queue, asyncio.Queue)
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                _ = queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event if queue remains full.
                pass


@app.on_event("startup")
async def startup():
    logger.info("ws_server.startup")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ws-server",
        "version": "0.1.0",
        "connections": manager.connection_count,
    }


# ── WebSocket Endpoint ──

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming.

    Protocol:
        Client -> Server:
            {"action": "subscribe", "channels": ["agent.lifecycle", "task.orchestration"]}
            {"action": "unsubscribe", "channels": ["simulation"]}
            {"action": "ping"}

        Server -> Client:
            {"event_type": "agent.spawned", "payload": {...}, "timestamp": "..."}
            {"action": "pong"}
    """
    conn_id = f"ws_{id(websocket)}"
    accepted = await manager.connect(conn_id, websocket)
    if not accepted:
        return  # Connection limit reached, already closed

    try:
        # Send available channels
        await websocket.send_json({
            "action": "connected",
            "channels": list(ALL_CHANNELS.keys()),
            "connection_id": conn_id,
        })

        while True:
            try:
                data = await websocket.receive_json()
                action = data.get("action", "")

                if action == "subscribe":
                    channels = data.get("channels", [])
                    manager.subscribe(conn_id, channels)
                    await websocket.send_json({
                        "action": "subscribed",
                        "channels": list(manager._subscriptions.get(conn_id, [])),
                    })

                elif action == "unsubscribe":
                    channels = data.get("channels", [])
                    manager.unsubscribe(conn_id, channels)
                    await websocket.send_json({
                        "action": "unsubscribed",
                        "channels": list(manager._subscriptions.get(conn_id, [])),
                    })

                elif action == "ping":
                    await websocket.send_json({"action": "pong"})

                else:
                    await websocket.send_json({
                        "action": "error",
                        "message": f"Unknown action: {action}",
                    })

            except Exception as e:
                logger.warning("ws_message_error", conn_id=conn_id, error=str(e))
                break

    except WebSocketDisconnect:
        logger.info("ws_disconnect", conn_id=conn_id)
    finally:
        manager.disconnect(conn_id)


# ── SSE Endpoint ──

@app.get("/events")
async def events(request: Request):
    """Server-Sent Events endpoint (WebSocket fallback).

    Streams events as text/event-stream.
    Query params:
        channels: Comma-separated channel names
        since: Unix timestamp to replay events from
    """
    channels_param = request.query_params.get("channels", "")
    channels = {c.strip() for c in channels_param.split(",") if c.strip()}

    async def event_stream():
        client_id = f"sse_{uuid4().hex[:8]}"
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=200)
        _sse_clients[client_id] = {
            "queue": queue,
            "channels": channels,
        }
        logger.info("sse_connected", client_id=client_id, channels=sorted(channels))

        # Replay buffered events matching channels
        for event in _event_buffer:
            event_channel = event.get("channel", "")
            if not channels or event_channel in channels:
                yield f"data: {json.dumps(event)}\n\n"

        # Send keepalive
        yield f":ok\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Keep connection alive for proxies/clients.
                    heartbeat = {
                        "event_type": "system.heartbeat",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "payload": {},
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_clients.pop(client_id, None)
            logger.info("sse_disconnected", client_id=client_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ── Internal: Broadcast endpoint (called by aura-core) ──

@app.post("/broadcast")
async def broadcast_event(body: BroadcastRequest):
    """Internal endpoint for aura-core to broadcast events.

    Body: {"channel": "agent.lifecycle", "event": {...}}
    """
    channel = body.channel
    event = body.event

    # Buffer for SSE replay
    buffered_event = {**event, "channel": channel, "channels": [channel]}
    _event_buffer.append(buffered_event)
    if len(_event_buffer) > _BUFFER_SIZE:
        _event_buffer.pop(0)
    _queue_sse_event(channel, buffered_event)

    # Broadcast to WebSocket clients
    sent = await manager.broadcast(event, channel=channel)

    return {"broadcast": True, "recipients": sent}
