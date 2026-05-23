"""SSH transport adapter (read-first)."""

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


class SshTransportAdapter:
    def __init__(self, host: str, user: str | None = None, port: int = 22):
        target = f"{user + '@' if user else ''}{host}:{port}"
        self.metadata = TransportMetadata(transport="ssh", target=target)
        self._host = host
        self._user = user
        self._port = port

    def _prefix(self) -> str:
        user = f"{self._user}@" if self._user else ""
        return f"ssh -p {self._port} -o BatchMode=yes -o StrictHostKeyChecking=accept-new {user}{self._host}"

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
        cmd = f"{self._prefix()} {command}"
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
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
        cmd = f"scp -P {self._port} {src} {self._user + '@' if self._user else ''}{self._host}:{dst}"
        start = time.time()
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=TransportConfidence.ADVISORY_ONLY,
                classification=CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start) * 1000)
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "timeout",
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=RuntimeState.TIMEOUT,
                confidence=TransportConfidence.UNKNOWN,
                classification=CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            )

    def pull_file(self, src: str, dst: str, *, timeout_ms: int = 10_000) -> TransportResponse:
        cmd = f"scp -P {self._port} {self._user + '@' if self._user else ''}{self._host}:{src} {dst}"
        start = time.time()
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=TransportConfidence.ADVISORY_ONLY,
                classification=CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            )
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start) * 1000)
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "timeout",
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=RuntimeState.TIMEOUT,
                confidence=TransportConfidence.UNKNOWN,
                classification=CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            )

    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "capture_stream", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "stream_capture_requires_operator")

    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(self.metadata.transport, "wait_for_prompt", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "prompt_wait_not_supported_in_ssh")

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute("echo connected", timeout_ms=timeout_ms, classification=CommandClassification.SAFE_READ)

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute("uname -a && id", timeout_ms=timeout_ms, classification=CommandClassification.SAFE_READ)
