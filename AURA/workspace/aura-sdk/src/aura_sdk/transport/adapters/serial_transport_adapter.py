"""Serial/UART transport adapter (read-first, fail-closed)."""

from __future__ import annotations

import time

from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    RuntimeState,
    TransportConfidence,
    TransportMetadata,
    TransportResponse,
    make_blocked_response,
)


class SerialTransportAdapter:
    def __init__(self, port: str, baudrate: int = 115200):
        self.metadata = TransportMetadata(transport="serial", target=port)
        self._port = port
        self._baudrate = baudrate

    def _pyserial_available(self) -> bool:
        try:
            import serial  # noqa: F401
            return True
        except Exception:
            return False

    def execute(
        self,
        command: str,
        *,
        timeout_ms: int = 10_000,
        classification: CommandClassification | None = None,
        operator_approved: bool = False,
    ) -> TransportResponse:
        if not self._pyserial_available():
            return make_blocked_response(self.metadata.transport, command, CommandClassification.REQUIRES_OPERATOR_APPROVAL, "pyserial_unavailable")
        return make_blocked_response(self.metadata.transport, command, CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_execute_requires_operator")

    def push_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"push {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_push_not_supported")

    def pull_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"pull {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_pull_not_supported")

    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "capture_stream", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_stream_capture_requires_operator")

    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "wait_for_prompt", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_prompt_wait_requires_operator")

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        start = time.time()
        return TransportResponse(
            transport=self.metadata.transport,
            command="check_connectivity",
            exit_code=0,
            stdout="serial_adapter_loaded",
            stderr="",
            timestamp=str(start),
            duration_ms=0,
            runtime_state=RuntimeState.UNKNOWN,
            confidence=TransportConfidence.UNKNOWN,
            classification=CommandClassification.SAFE_READ,
        )

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "collect_environment_metadata", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "serial_metadata_requires_operator")
