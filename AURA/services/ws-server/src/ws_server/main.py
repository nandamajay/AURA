"""WebSocket + SSE Server — FastAPI app."""

import asyncio
import json
import os
from collections import OrderedDict
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
_BROADCAST_LOCK = asyncio.Lock()
_ORDERING_POLICY_VERSION = "p1.2"
_SEEN_EVENT_ID_MAX = 20000
_RETRY_STREAM_MAX = 5000
_SEQ_STREAM_MAX = 10000
_event_ingest_sequence = 0
_seen_event_ids: OrderedDict[str, int] = OrderedDict()
_retry_attempt_state: OrderedDict[str, int] = OrderedDict()
_stream_sequence_state: OrderedDict[str, int] = OrderedDict()


class BroadcastRequest(BaseModel):
    """Validated request body for internal event broadcast endpoint."""

    channel: str = Field(min_length=1)
    event: dict[str, object] = Field(default_factory=dict)


def _ordered_put(mapping: OrderedDict[str, int], key: str, value: int, limit: int) -> None:
    mapping[key] = value
    mapping.move_to_end(key)
    while len(mapping) > limit:
        mapping.popitem(last=False)


def _event_id(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""


def _event_payload(event: dict[str, object]) -> dict[str, object]:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return payload
    return {}


def _stream_key(channel: str, payload: dict[str, object]) -> str:
    marker = str(payload.get("marker") or "")
    kind = str(payload.get("kind") or "")
    op = str(payload.get("op") or "")
    if op:
        return f"{channel}:{kind}:{marker}:{op}"
    return f"{channel}:{kind}:{marker}"


def _to_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _apply_event_policy(channel: str, event: dict[str, object]) -> tuple[dict[str, object], bool]:
    """Apply deterministic ordering policy; returns (event, drop_duplicate)."""
    global _event_ingest_sequence

    _event_ingest_sequence += 1
    ingest_sequence = _event_ingest_sequence

    processed = dict(event)
    payload = dict(_event_payload(processed))
    metadata: dict[str, object] = {
        "policy_version": _ORDERING_POLICY_VERSION,
        "ingest_sequence": ingest_sequence,
    }

    event_id = _event_id(processed.get("event_id"))
    if event_id:
        first_seen = _seen_event_ids.get(event_id)
        if first_seen is not None:
            metadata["duplicate_event"] = True
            metadata["first_seen_sequence"] = first_seen
            processed["_ordering"] = metadata
            return processed, True
        _ordered_put(_seen_event_ids, event_id, ingest_sequence, _SEEN_EVENT_ID_MAX)

    if payload:
        stream_key = _stream_key(channel, payload)

        seq_value = _to_int(payload.get("seq"))
        if seq_value is not None and stream_key:
            last_seq = _stream_sequence_state.get(stream_key)
            if last_seq is not None:
                expected_seq = last_seq + 1
                if seq_value != expected_seq:
                    metadata["sequence_violation"] = True
                    metadata["expected_seq"] = expected_seq
                    metadata["received_seq"] = seq_value
            _ordered_put(_stream_sequence_state, stream_key, seq_value, _SEQ_STREAM_MAX)

        if str(payload.get("kind") or "") == "retry" and str(payload.get("op") or ""):
            retry_key = stream_key
            expected_attempt = _retry_attempt_state.get(retry_key, 0) + 1
            original_attempt = _to_int(payload.get("attempt"))
            if original_attempt != expected_attempt:
                metadata["retry_order_normalized"] = True
                metadata["retry_expected_attempt"] = expected_attempt
                metadata["retry_original_attempt"] = original_attempt
                payload["attempt_original"] = original_attempt
            payload["attempt"] = expected_attempt
            _ordered_put(_retry_attempt_state, retry_key, expected_attempt, _RETRY_STREAM_MAX)

        processed["payload"] = payload

    processed["_ordering"] = metadata
    return processed, False


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

    async with _BROADCAST_LOCK:
        processed_event, dropped_duplicate = _apply_event_policy(channel, event)
        if dropped_duplicate:
            ordering = processed_event.get("_ordering", {})
            return {
                "broadcast": True,
                "recipients": 0,
                "dropped_duplicate": True,
                "ordering": ordering,
            }

        # Buffer for SSE replay
        buffered_event = {**processed_event, "channel": channel, "channels": [channel]}
        _event_buffer.append(buffered_event)
        if len(_event_buffer) > _BUFFER_SIZE:
            _event_buffer.pop(0)
        _queue_sse_event(channel, buffered_event)

        # Broadcast to WebSocket clients
        sent = await manager.broadcast(processed_event, channel=channel)

        return {
            "broadcast": True,
            "recipients": sent,
            "dropped_duplicate": False,
            "ordering": processed_event.get("_ordering", {}),
        }
