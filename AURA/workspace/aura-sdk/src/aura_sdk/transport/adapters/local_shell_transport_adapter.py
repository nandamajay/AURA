"""Local shell transport adapter (read-first)."""

from __future__ import annotations

import subprocess
import time

from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    RuntimeState,
    TransportConfidence,
    TransportMetadata,
    TransportResponse,
    classify_command,
    make_blocked_response,
)


class LocalShellTransportAdapter:
    def __init__(self, metadata: TransportMetadata | None = None):
        self.metadata = metadata or TransportMetadata(transport="local")

    def execute(
        self,
        command: str,
        *,
        timeout_ms: int = 10_000,
        classification: CommandClassification | None = None,
        operator_approved: bool = False,
    ) -> TransportResponse:
        classification = classification or classify_command(command)
        if classification == CommandClassification.REQUIRES_OPERATOR_APPROVAL and not operator_approved:
            return make_blocked_response(self.metadata.transport, command, classification, "operator_approval_required")

        start = time.time()
        try:
            proc = subprocess.run(
                command,
                shell=True,
                executable="/bin/bash",
                text=True,
                capture_output=True,
                timeout=timeout_ms / 1000.0,
            )
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            confidence = TransportConfidence.CAPTURE_READY if proc.returncode == 0 else TransportConfidence.ADVISORY_ONLY
            return TransportResponse(
                transport=self.metadata.transport,
                command=command,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=confidence,
                classification=classification,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start) * 1000)
            return TransportResponse(
                transport=self.metadata.transport,
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "timeout",
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=RuntimeState.TIMEOUT,
                confidence=TransportConfidence.UNKNOWN,
                classification=classification,
            )

    def push_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"push {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "push_not_supported_in_local_adapter")

    def pull_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, f"pull {src} {dst}", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "pull_not_supported_in_local_adapter")

    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "capture_stream", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "stream_capture_not_supported")

    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "wait_for_prompt", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "prompt_wait_not_applicable")

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return TransportResponse(
            transport=self.metadata.transport,
            command="check_connectivity",
            exit_code=0,
            stdout="local_shell_ready",
            stderr="",
            timestamp=str(time.time()),
            duration_ms=0,
            runtime_state=RuntimeState.EXECUTED,
            confidence=TransportConfidence.CONNECTED,
            classification=CommandClassification.SAFE_READ,
        )

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute("uname -a && id", timeout_ms=timeout_ms, classification=CommandClassification.SAFE_READ)
