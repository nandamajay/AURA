"""Dispatcher helpers for distributed remote serial transport registration."""

from __future__ import annotations

from pathlib import Path

from aura_sdk.transport.adapters.remote_serial_transport_adapter import (
    RemoteSerialTransportAdapter,
)
from aura_sdk.transport.runtime_command_dispatcher import RuntimeCommandDispatcher


def build_remote_dispatcher(
    host: str,
    port: int,
    *,
    name: str = "remote_serial",
    target: str | None = None,
    log_path: str | Path | None = None,
) -> RuntimeCommandDispatcher:
    dispatcher = RuntimeCommandDispatcher(log_path=log_path)
    adapter = RemoteSerialTransportAdapter(host=host, port=port, target=target)
    dispatcher.register(name, adapter)
    return dispatcher
