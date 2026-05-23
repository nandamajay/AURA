"""TCP client for remote runtime transport requests."""

from __future__ import annotations

import json
import socket
import time
from typing import Any

from aura_sdk.transport.runtime_protocol import (
    PROTOCOL_VERSION,
    RESPONSE_STATUS_PARTIAL_RESPONSE,
    RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
    compute_response_integrity,
)


class RuntimeTransportClient:
    """Simple deterministic TCP/JSON request client."""

    def __init__(self, host: str, port: int, *, connect_timeout_seconds: float = 3.0):
        self._host = host
        self._port = port
        self._connect_timeout_seconds = connect_timeout_seconds

    @property
    def endpoint(self) -> str:
        return f"{self._host}:{self._port}"

    def execute(self, request: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=self._connect_timeout_seconds
            ) as sock:
                sock.settimeout(timeout_seconds)
                payload = json.dumps(request, sort_keys=True).encode("utf-8") + b"\n"
                sock.sendall(payload)

                response_chunks: list[bytes] = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_chunks.append(chunk)
                    if b"\n" in chunk:
                        break

            response_text = b"".join(response_chunks).decode("utf-8", errors="replace")
            first_line = response_text.splitlines()[0] if response_text else ""
            if not first_line:
                return self._failure_response(
                    request,
                    execution_status=RESPONSE_STATUS_PARTIAL_RESPONSE,
                    stderr="empty_response",
                )

            parsed = json.loads(first_line)
            if not isinstance(parsed, dict):
                raise ValueError("response_not_json_object")
            return parsed

        except Exception as exc:
            return self._failure_response(
                request,
                execution_status=RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
                stderr=f"transport_client_error:{exc}",
            )

    def _failure_response(
        self,
        request: dict[str, Any],
        *,
        execution_status: str,
        stderr: str,
    ) -> dict[str, Any]:
        now = str(time.time())
        response = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": str(request.get("request_id", "")),
            "request_sequence": int(request.get("request_sequence", 1)),
            "approved_commands": list(request.get("approved_commands", [])),
            "timeout_seconds": int(request.get("timeout_seconds", 0)),
            "transport": str(request.get("transport", "remote_serial")),
            "execution_mode": str(request.get("execution_mode", "governed_read_only")),
            "timestamps": {
                "received_at": now,
                "started_at": now,
                "finished_at": now,
            },
            "execution_status": execution_status,
            "raw_output": "",
            "stderr": stderr,
            "command_results": [],
            "request_integrity_sha256": str(request.get("request_integrity_sha256", "")),
            "transport_metadata": {
                "endpoint": self.endpoint,
            },
            "executor_identity": {
                "executor_id": "unknown",
                "executor_type": "transport_client_fallback",
            },
            "executor_heartbeat": {
                "heartbeat_counter": 0,
                "heartbeat_timestamp": now,
                "connection_state": "disconnected",
            },
            "governance_verdict_chain": ["UNKNOWN"],
        }
        response["response_integrity_sha256"] = compute_response_integrity(response)
        return response
