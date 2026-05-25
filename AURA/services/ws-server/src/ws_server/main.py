"""WebSocket + SSE Server — FastAPI app."""

import asyncio
import json
import os
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from aura_sdk.logging.logger import configure_logging, get_logger
from aura_sdk.transport.runtime_execution_contract import resolve_runtime_contract
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
_BUFFER_PER_DOMAIN_MAX = max(50, int(os.environ.get("BUFFER_PER_DOMAIN_MAX", "250")))
_sse_clients: dict[str, dict[str, object]] = {}
_BROADCAST_LOCK = asyncio.Lock()
_ORDERING_POLICY_VERSION = "p2.1"
_SEEN_EVENT_ID_MAX = 20000
_RETRY_STREAM_MAX = 5000
_SEQ_STREAM_MAX = 10000
_event_ingest_sequence = 0
_seen_event_ids: OrderedDict[str, int] = OrderedDict()
_retry_attempt_state: OrderedDict[str, int] = OrderedDict()
_stream_sequence_state: OrderedDict[str, int] = OrderedDict()
_buffer_evictions_total = 0
_buffer_evictions_by_domain: Counter[str] = Counter()
_sse_drop_total = 0
_sse_drop_by_domain: Counter[str] = Counter()
_domain_ingest_count: Counter[str] = Counter()
_domain_ws_delivery_count: Counter[str] = Counter()
_domain_sse_delivery_count: Counter[str] = Counter()
_channel_broadcast_count: Counter[str] = Counter()


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


def _event_domain(payload: dict[str, object]) -> str:
    domain = payload.get("plugin_domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip().lower()
    scope = payload.get("runtime_cell_scope")
    if isinstance(scope, str) and scope.startswith("domain:"):
        parsed = scope.split(":", 1)[1].strip().lower()
        if parsed:
            return parsed
    return ""


def _routed_channels(base_channel: str, payload: dict[str, object]) -> list[str]:
    domain = _event_domain(payload)
    channels = [base_channel]
    if domain:
        channels.append(f"{base_channel}:{domain}")
    return channels


def _stream_key(channel: str, payload: dict[str, object]) -> str:
    marker = str(payload.get("marker") or "")
    kind = str(payload.get("kind") or "")
    op = str(payload.get("op") or "")
    domain = _event_domain(payload)
    run_id = str(payload.get("run_id") or "")
    retry_scope = str(payload.get("retry_scope") or "")
    if op:
        return f"{channel}:{kind}:{domain}:{run_id}:{marker}:{op}:{retry_scope}"
    return f"{channel}:{kind}:{domain}:{run_id}:{marker}:{retry_scope}"


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
        domain = _event_domain(payload)
        if domain:
            payload.setdefault("plugin_domain", domain)
            payload.setdefault("runtime_cell_scope", f"domain:{domain}")
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
            payload["retry_scope"] = retry_key
            _ordered_put(_retry_attempt_state, retry_key, expected_attempt, _RETRY_STREAM_MAX)
            metadata["retry_scope"] = retry_key

        processed["payload"] = payload

    processed["_ordering"] = metadata
    return processed, False


def _buffer_domain(event: dict[str, object]) -> str:
    payload = event.get("payload")
    if isinstance(payload, dict):
        return _event_domain(payload)
    return ""


def _append_buffer_event(event: dict) -> None:
    global _buffer_evictions_total
    event_domain = _buffer_domain(event)
    if len(_event_buffer) >= _BUFFER_SIZE:
        evict_index = 0
        if event_domain:
            domain_count = sum(1 for existing in _event_buffer if _buffer_domain(existing) == event_domain)
            if domain_count >= _BUFFER_PER_DOMAIN_MAX:
                for idx, existing in enumerate(_event_buffer):
                    if _buffer_domain(existing) == event_domain:
                        evict_index = idx
                        break
        evicted = _event_buffer.pop(evict_index)
        evicted_domain = _buffer_domain(evicted)
        _buffer_evictions_total += 1
        _buffer_evictions_by_domain[evicted_domain or "default"] += 1
    _event_buffer.append(event)


def _queue_sse_event(event: dict) -> None:
    """Fan-out a broadcast event to subscribed SSE clients."""
    global _sse_drop_total
    event_channels = event.get("channels", [])
    if isinstance(event_channels, list):
        channel_set = {str(x) for x in event_channels if isinstance(x, str) and x}
    else:
        channel_set = set()
    if not channel_set:
        channel = event.get("channel")
        if isinstance(channel, str) and channel:
            channel_set = {channel}
    event_domain = _buffer_domain(event) or "default"

    for client in list(_sse_clients.values()):
        channels = client["channels"]
        if channels and not set(channels).intersection(channel_set):
            continue
        queue = client["queue"]
        assert isinstance(queue, asyncio.Queue)
        try:
            queue.put_nowait(event)
            _domain_sse_delivery_count[event_domain] += 1
        except asyncio.QueueFull:
            try:
                _ = queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event)
                _domain_sse_delivery_count[event_domain] += 1
            except asyncio.QueueFull:
                # Drop event if queue remains full.
                _sse_drop_total += 1
                _sse_drop_by_domain[event_domain] += 1


@app.on_event("startup")
async def startup():
    execution_contract = resolve_runtime_contract("ws-server")
    logger.info(
        "runtime_execution_contract",
        classification=execution_contract.classification,
        python_version=execution_contract.python_version,
        containerized=execution_contract.containerized,
        fail_closed_reasons=execution_contract.fail_closed_reasons,
    )
    if execution_contract.classification != "PASS":
        raise RuntimeError(
            "ws-server runtime execution contract failed: "
            + ",".join(execution_contract.fail_closed_reasons)
        )
    logger.info("ws_server.startup")


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ws-server",
        "version": "0.1.0",
        "connections": manager.connection_count,
    }


@app.get("/metrics/coexistence")
async def coexistence_metrics():
    domain_buffer_counts: Counter[str] = Counter()
    for event in _event_buffer:
        domain_buffer_counts[_buffer_domain(event) or "default"] += 1
    return {
        "policy_version": _ORDERING_POLICY_VERSION,
        "event_ingest_sequence": _event_ingest_sequence,
        "event_buffer_size": len(_event_buffer),
        "event_buffer_capacity": _BUFFER_SIZE,
        "event_buffer_per_domain_max": _BUFFER_PER_DOMAIN_MAX,
        "buffer_evictions_total": _buffer_evictions_total,
        "buffer_evictions_by_domain": dict(_buffer_evictions_by_domain),
        "buffer_counts_by_domain": dict(domain_buffer_counts),
        "sse_drop_total": _sse_drop_total,
        "sse_drop_by_domain": dict(_sse_drop_by_domain),
        "domain_ingest_count": dict(_domain_ingest_count),
        "domain_ws_delivery_count": dict(_domain_ws_delivery_count),
        "domain_sse_delivery_count": dict(_domain_sse_delivery_count),
        "channel_broadcast_count": dict(_channel_broadcast_count),
        "retry_scope_tracked": len(_retry_attempt_state),
        "retry_scope_sample": list(_retry_attempt_state.items())[:20],
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
            event_channels_raw = event.get("channels", [])
            event_channels = (
                {str(x) for x in event_channels_raw if isinstance(x, str)}
                if isinstance(event_channels_raw, list)
                else set()
            )
            if not event_channels and isinstance(event_channel, str):
                event_channels = {event_channel}
            if not channels or channels.intersection(event_channels):
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

        payload = _event_payload(processed_event)
        routed_channels = _routed_channels(channel, payload)
        event_domain = _event_domain(payload) or "default"
        _domain_ingest_count[event_domain] += 1
        for routed in routed_channels:
            _channel_broadcast_count[routed] += 1

        routing = processed_event.get("_routing")
        if not isinstance(routing, dict):
            routing = {}
        routing["base_channel"] = channel
        routing["channels"] = routed_channels
        routing["plugin_domain"] = event_domain
        processed_event["_routing"] = routing

        # Buffer for SSE replay
        buffered_event = {**processed_event, "channel": channel, "channels": routed_channels}
        _append_buffer_event(buffered_event)
        _queue_sse_event(buffered_event)

        # Broadcast to WebSocket clients
        sent = await manager.broadcast(processed_event, channels=set(routed_channels))
        _domain_ws_delivery_count[event_domain] += int(sent)

        return {
            "broadcast": True,
            "recipients": sent,
            "dropped_duplicate": False,
            "routed_channels": routed_channels,
            "plugin_domain": event_domain,
            "ordering": processed_event.get("_ordering", {}),
        }
