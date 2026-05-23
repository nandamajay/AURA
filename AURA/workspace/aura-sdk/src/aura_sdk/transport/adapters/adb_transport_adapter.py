"""ADB transport adapter (read-first)."""

from __future__ import annotations

import shlex
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


class AdbTransportAdapter:
    def __init__(self, serial: str | None = None):
        self.metadata = TransportMetadata(transport="adb", target=serial)
        self._serial = serial

    def _adb_prefix(self) -> str:
        return f"adb -s {self._serial} " if self._serial else "adb "

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
        cmd = f"{self._adb_prefix()}shell {shlex.quote(command)}"
        try:
            proc = subprocess.run(
                cmd,
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
        start = time.time()
        cmd = f"{self._adb_prefix()}push {src} {dst}"
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            confidence = TransportConfidence.ADVISORY_ONLY
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=confidence,
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
        start = time.time()
        cmd = f"{self._adb_prefix()}pull {src} {dst}"
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            confidence = TransportConfidence.ADVISORY_ONLY
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=confidence,
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
        return make_blocked_response(self.metadata.transport, "wait_for_prompt", CommandClassification.REQUIRES_OPERATOR_APPROVAL, "prompt_wait_not_supported_in_adb")

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        cmd = f"{self._adb_prefix()}devices"
        start = time.time()
        try:
            proc = subprocess.run(cmd, shell=True, executable="/bin/bash", text=True, capture_output=True, timeout=timeout_ms/1000.0)
            duration_ms = int((time.time() - start) * 1000)
            state = RuntimeState.EXECUTED if proc.returncode == 0 else RuntimeState.FAILED
            confidence = TransportConfidence.CONNECTED if proc.returncode == 0 else TransportConfidence.UNKNOWN
            return TransportResponse(
                transport=self.metadata.transport,
                command=cmd,
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                timestamp=str(start),
                duration_ms=duration_ms,
                runtime_state=state,
                confidence=confidence,
                classification=CommandClassification.SAFE_READ,
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
                classification=CommandClassification.SAFE_READ,
            )

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute("getprop ro.product.model && getprop ro.build.fingerprint", timeout_ms=timeout_ms)
