"""Core event bridge: EventBus -> ws-server broadcast."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, Request

from aura_sdk.bus.channels import ALL_CHANNELS
from aura_sdk.bus.event_bus import EventBus
from aura_sdk.db.connection import get_db
from aura_sdk.logging.logger import get_logger
from aura_sdk.models.event import EventEnvelope, EventSource, EventType

logger = get_logger("core.events")


_EVENT_CHANNEL_MAP: dict[EventType, str] = {}
for channel_name, event_types in ALL_CHANNELS.items():
    for event_type in event_types:
        _EVENT_CHANNEL_MAP[event_type] = channel_name

_PERSIST_RETRY_BACKOFF_SECONDS: tuple[float, ...] = (0.05, 0.1, 0.2, 0.4, 0.8)
_PERSIST_RETRY_ATTEMPTS = len(_PERSIST_RETRY_BACKOFF_SECONDS) + 1
_WAL_CHECKPOINT_EVERY = max(0, int(os.environ.get("AURA_AUDIT_WAL_CHECKPOINT_EVERY", "200")))
_persist_success_count = 0
_checkpoint_lock = asyncio.Lock()


def _payload_domain(payload: dict[str, Any]) -> str:
    domain = payload.get("plugin_domain")
    if isinstance(domain, str) and domain.strip():
        return domain.strip().lower()
    scope = payload.get("runtime_cell_scope")
    if isinstance(scope, str) and scope.startswith("domain:"):
        parsed = scope.split(":", 1)[1].strip().lower()
        if parsed:
            return parsed
    return ""


def _resolve_ws_channels(event: EventEnvelope) -> tuple[str, list[str], str]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    base_channel = _EVENT_CHANNEL_MAP.get(event.event_type, "system")
    domain = _payload_domain(payload)
    channels = [base_channel]
    if domain:
        channels.append(f"{base_channel}:{domain}")
    return base_channel, channels, domain


def _resolve_audit_target(event: EventEnvelope) -> tuple[str, str]:
    event_value = event.event_type.value
    payload = event.payload if isinstance(event.payload, dict) else {}

    if event_value.startswith("task."):
        target_type = "task"
        target_id = str(payload.get("task_id") or event.source.task_id or event.trace_id or event.event_id)
        return target_type, target_id

    if event_value.startswith("agent."):
        target_type = "agent"
        target_id = str(payload.get("agent_id") or event.source.agent_id or event.source.task_id or event.event_id)
        return target_type, target_id

    if event_value.startswith("sim."):
        target_type = "simulation"
        target_id = str(payload.get("sim_id") or event.source.task_id or event.trace_id or event.event_id)
        return target_type, target_id

    if event_value.startswith("governance.") or event_value.startswith("approval."):
        target_type = "approval"
        target_id = str(payload.get("approval_id") or event.trace_id or event.event_id)
        return target_type, target_id

    if event_value.startswith("llm."):
        target_type = "llm"
        target_id = str(payload.get("request_id") or event.trace_id or event.event_id)
        return target_type, target_id

    target_type = "system"
    target_id = str(event.trace_id or event.event_id)
    return target_type, target_id


def _is_retryable_sqlite_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "database is locked" in message or "database table is locked" in message


async def _persist_event_to_audit(event: EventEnvelope) -> bool:
    global _persist_success_count

    target_type, target_id = _resolve_audit_target(event)
    source_data = event.source.model_dump(mode="json")
    before_state = json.dumps(
        {
            "event_id": event.event_id,
            "trace_id": event.trace_id,
            "source": source_data,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    after_object = {
        "event_id": event.event_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp.isoformat(),
        "trace_id": event.trace_id,
        "version": event.version,
        "source": source_data,
        "payload": event.payload,
    }
    after_state = json.dumps(after_object, sort_keys=True, separators=(",", ":"))
    evidence_hash = hashlib.sha256(after_state.encode("utf-8")).hexdigest()
    payload = event.payload if isinstance(event.payload, dict) else {}
    session_id = str(
        payload.get("session_id")
        or payload.get("requested_by")
        or payload.get("cancelled_by")
        or event.trace_id
        or "system:core.events"
    )
    user_id = payload.get("user_id")
    timestamp = int(event.timestamp.timestamp())

    for attempt in range(1, _PERSIST_RETRY_ATTEMPTS + 1):
        try:
            async with get_db() as db:
                try:
                    await db.execute("BEGIN IMMEDIATE")
                    await db.execute(
                        """INSERT INTO audit_ledger
                        (timestamp, user_id, session_id, event_type, target_type, target_id, before_state, after_state, evidence_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            timestamp,
                            user_id,
                            session_id,
                            event.event_type.value,
                            target_type,
                            target_id,
                            before_state,
                            after_state,
                            evidence_hash,
                        ),
                    )
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
            _persist_success_count += 1
            await _maybe_checkpoint_audit_wal()
            return True
        except Exception as exc:
            if attempt < _PERSIST_RETRY_ATTEMPTS and _is_retryable_sqlite_error(exc):
                retry_delay = _PERSIST_RETRY_BACKOFF_SECONDS[attempt - 1]
                await asyncio.sleep(retry_delay)
                continue
            logger.error(
                "event_audit_persist_failed",
                event_id=event.event_id,
                event_type=event.event_type.value,
                target_type=target_type,
                target_id=target_id,
                attempt=attempt,
                error=str(exc),
            )
            return False

    return False


async def _run_audit_wal_checkpoint() -> None:
    async with get_db() as db:
        cursor = await db.execute("PRAGMA wal_checkpoint(PASSIVE)")
        row = await cursor.fetchone()
        await cursor.close()
    if row is None:
        logger.warning("audit_wal_checkpoint_missing_row")
        return
    logger.info(
        "audit_wal_checkpoint",
        checkpoint_status=int(row[0]),
        wal_pages=int(row[1]),
        checkpointed_pages=int(row[2]),
    )


async def _maybe_checkpoint_audit_wal() -> None:
    if _WAL_CHECKPOINT_EVERY <= 0:
        return
    if _persist_success_count % _WAL_CHECKPOINT_EVERY != 0:
        return

    async with _checkpoint_lock:
        if _persist_success_count % _WAL_CHECKPOINT_EVERY != 0:
            return
        try:
            await _run_audit_wal_checkpoint()
        except Exception as exc:
            logger.warning("audit_wal_checkpoint_failed", error=str(exc))


async def _forward_to_ws(event: EventEnvelope, ws_server_url: str) -> bool:
    channel, routed_channels, domain = _resolve_ws_channels(event)
    event_payload = dict(event.payload) if isinstance(event.payload, dict) else {}
    if domain:
        event_payload.setdefault("plugin_domain", domain)
        event_payload.setdefault("runtime_cell_scope", f"domain:{domain}")
    payload = {
        "channel": channel,
        "event": {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source.model_dump(),
            "payload": event_payload,
            "trace_id": event.trace_id,
            "version": event.version,
            "_routing": {
                "base_channel": channel,
                "channels": routed_channels,
                "plugin_domain": domain,
            },
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
                    routed_channels=routed_channels,
                    plugin_domain=domain,
                )
                return False
    except Exception as exc:
        logger.warning(
            "event_forward_error",
            error=str(exc),
            event_type=event.event_type.value,
            channel=channel,
            routed_channels=routed_channels,
            plugin_domain=domain,
        )
        return False
    return True


async def _persist_and_forward(event: EventEnvelope, ws_server_url: str) -> bool:
    persisted = await _persist_event_to_audit(event)
    if not persisted:
        logger.warning(
            "event_broadcast_skipped_unpersisted",
            event_id=event.event_id,
            event_type=event.event_type.value,
        )
        return False
    return await _forward_to_ws(event, ws_server_url)


async def start_event_bus(app: FastAPI, ws_server_url: str) -> EventBus:
    """Initialize and start the in-memory EventBus with ws forwarder."""
    event_bus = EventBus()

    async def _persist_and_forward_handler(event: EventEnvelope) -> None:
        await _persist_and_forward(event, ws_server_url)

    event_bus.subscribe_all(_persist_and_forward_handler)
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

    payload_data = dict(payload) if isinstance(payload, dict) else {}
    domain = _payload_domain(payload_data)
    if domain:
        payload_data.setdefault("plugin_domain", domain)
        payload_data.setdefault("runtime_cell_scope", f"domain:{domain}")

    envelope = EventEnvelope(
        event_type=event_type,
        source=EventSource(
            subsystem="S1",
            service="core",
            task_id=task_id,
            agent_type=agent_type,
            agent_id=agent_id,
        ),
        payload=payload_data,
        trace_id=trace_id,
    )
    await event_bus.publish(envelope)
    return True
