"""Deterministic TCP/JSON bridge for remote serial execution."""

from __future__ import annotations

import json
import socketserver
from typing import Any, Callable

from aura_sdk.transport.runtime_protocol import (
    build_rejected_malformed_response,
    validate_request_block,
)

ExecuteHandler = Callable[[dict[str, Any]], dict[str, Any]]


class _BridgeRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: "TcpRuntimeBridgeServer" = self.server  # type: ignore[assignment]
        raw_line = self.rfile.readline()
        if not raw_line:
            return

        try:
            request = json.loads(raw_line.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request_must_be_json_object")
        except Exception as exc:
            response = build_rejected_malformed_response(
                "",
                request_sequence=1,
                reason=f"invalid_json:{exc}",
            )
            self._write_response(response)
            return

        response = server.bridge.execute_request(request)
        self._write_response(response)

    def _write_response(self, payload: dict[str, Any]) -> None:
        self.wfile.write((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))


class TcpRuntimeBridgeServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        bridge: "TcpRuntimeBridge",
    ):
        self.bridge = bridge
        super().__init__(server_address, _BridgeRequestHandler)


class TcpRuntimeBridge:
    """Single-process TCP runtime bridge with deterministic request sequencing."""

    def __init__(self, execute_handler: ExecuteHandler):
        self._execute_handler = execute_handler

    def execute_request(self, request: dict[str, Any]) -> dict[str, Any]:
        request_id = str(request.get("request_id", ""))
        request_sequence = int(request.get("request_sequence", 1))
        valid, reason = validate_request_block(request)
        if not valid:
            return build_rejected_malformed_response(
                request_id, request_sequence=request_sequence, reason=reason
            )
        response = self._execute_handler(request)
        if not isinstance(response, dict):
            return build_rejected_malformed_response(
                request_id,
                request_sequence=request_sequence,
                reason="executor_response_not_object",
            )
        return response

    def serve_forever(self, host: str, port: int) -> None:
        with TcpRuntimeBridgeServer((host, port), self) as server:
            server.serve_forever()
