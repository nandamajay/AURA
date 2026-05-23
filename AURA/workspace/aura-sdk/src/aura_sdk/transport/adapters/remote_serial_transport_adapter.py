"""AURA-side authoritative governance adapter for remote serial execution."""

from __future__ import annotations

import time
from typing import Any, Iterable

from aura_sdk.transport.runtime_protocol import (
    HEARTBEAT_STALENESS_SECONDS,
    MAX_COMMANDS_PER_BATCH,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    RESPONSE_STATUS_EXECUTED,
    RESPONSE_STATUS_FAILED,
    RESPONSE_STATUS_INVALID,
    RESPONSE_STATUS_PARTIAL_RESPONSE,
    RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST,
    RESPONSE_STATUS_TIMEOUT,
    RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
    RuntimeExecutionState,
    build_request_block,
    validate_response_block,
)
from aura_sdk.transport.runtime_transport_api import (
    CommandClassification,
    RuntimeState,
    RuntimeTransportAPI,
    TransportConfidence,
    TransportMetadata,
    TransportResponse,
    classify_command,
    make_blocked_response,
)
from aura_sdk.transport.runtime_transport_client import RuntimeTransportClient

DEFAULT_ALLOWLIST = {
    "echo AURA_REMOTE_TEST",
    "uname -a",
    "cat /proc/version",
    "pwd",
    "whoami",
}

FORBIDDEN_PATTERNS = (
    ">/sys",
    "> /sys",
    ">/proc",
    "> /proc",
    "tee /sys",
    "tee /proc",
    "reboot",
    "shutdown",
    "mount -o remount",
    "rmmod",
    "insmod",
    "modprobe -r",
)


class RemoteSerialTransportAdapter(RuntimeTransportAPI):
    """Linux-side governance authority for remote Windows serial execution."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        target: str | None = None,
        allowlisted_commands: Iterable[str] | None = None,
        execution_mode: str = "governed_read_only",
        max_commands_per_batch: int = MAX_COMMANDS_PER_BATCH,
        max_stdout_bytes: int = MAX_STDOUT_BYTES,
        max_stderr_bytes: int = MAX_STDERR_BYTES,
        heartbeat_staleness_seconds: int = HEARTBEAT_STALENESS_SECONDS,
    ):
        super().__init__(
            TransportMetadata(
                transport="remote_serial",
                target=target or f"{host}:{port}",
                capabilities=["execute", "check_connectivity", "collect_environment_metadata"],
            )
        )
        self._client = RuntimeTransportClient(host, port)
        self._execution_mode = execution_mode
        self._allowlisted_commands = {
            command.strip() for command in (allowlisted_commands or DEFAULT_ALLOWLIST) if command
        }
        self._max_commands_per_batch = max_commands_per_batch
        self._max_stdout_bytes = max_stdout_bytes
        self._max_stderr_bytes = max_stderr_bytes
        self._heartbeat_staleness_seconds = heartbeat_staleness_seconds

        self._request_sequence = 0
        self._issued_request_ids: set[str] = set()
        self._completed_request_ids: set[str] = set()
        self._seen_response_hashes: set[str] = set()
        self._last_response_sequence = 0
        self._lineage: dict[str, dict[str, Any]] = {}

    def execute(
        self,
        command: str,
        *,
        timeout_ms: int = 10_000,
        classification: CommandClassification | None = None,
        operator_approved: bool = False,
    ) -> TransportResponse:
        normalized_command = command.strip()
        classification = classification or classify_command(normalized_command)
        return self._execute_commands(
            [normalized_command],
            timeout_ms=timeout_ms,
            classification=classification,
            operator_approved=operator_approved,
        )

    def execute_batch(
        self,
        commands: list[str],
        *,
        timeout_ms: int = 10_000,
        operator_approved: bool = False,
    ) -> TransportResponse:
        normalized = [command.strip() for command in commands if command and command.strip()]
        return self._execute_commands(
            normalized,
            timeout_ms=timeout_ms,
            classification=CommandClassification.SAFE_READ,
            operator_approved=operator_approved,
        )

    def push_file(
        self,
        src: str,
        dst: str,
        *,
        timeout_ms: int = 10_000,
    ) -> TransportResponse:
        return make_blocked_response(
            self.metadata.transport,
            f"push {src} {dst}",
            CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            "remote_serial_push_not_supported",
        )

    def pull_file(
        self,
        src: str,
        dst: str,
        *,
        timeout_ms: int = 10_000,
    ) -> TransportResponse:
        return make_blocked_response(
            self.metadata.transport,
            f"pull {src} {dst}",
            CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            "remote_serial_pull_not_supported",
        )

    def capture_stream(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(
            self.metadata.transport,
            "capture_stream",
            CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            "remote_serial_stream_requires_operator",
        )

    def wait_for_prompt(self, *, timeout_ms: int = 10_000) -> TransportResponse:
        return make_blocked_response(
            self.metadata.transport,
            "wait_for_prompt",
            CommandClassification.REQUIRES_OPERATOR_APPROVAL,
            "remote_serial_prompt_requires_operator",
        )

    def check_connectivity(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute(
            "echo AURA_REMOTE_TEST",
            timeout_ms=timeout_ms,
            classification=CommandClassification.SAFE_READ,
        )

    def collect_environment_metadata(self, *, timeout_ms: int = 5_000) -> TransportResponse:
        return self.execute(
            "uname -a",
            timeout_ms=timeout_ms,
            classification=CommandClassification.SAFE_READ,
        )

    def get_lineage_snapshot(self) -> dict[str, dict[str, Any]]:
        return {key: dict(value) for key, value in self._lineage.items()}

    def _execute_commands(
        self,
        commands: list[str],
        *,
        timeout_ms: int,
        classification: CommandClassification,
        operator_approved: bool,
    ) -> TransportResponse:
        start = time.time()

        governance_error = self._validate_governance(
            commands,
            classification=classification,
            operator_approved=operator_approved,
        )
        representative_command = commands[0] if commands else ""
        if governance_error:
            return make_blocked_response(
                self.metadata.transport,
                representative_command,
                classification,
                governance_error,
            )

        self._request_sequence += 1
        request = build_request_block(
            commands,
            timeout_seconds=max(1, int(timeout_ms / 1000)),
            transport=self.metadata.transport,
            execution_mode=self._execution_mode,
            request_sequence=self._request_sequence,
            transport_metadata={
                "target": self.metadata.target,
                "transport": self.metadata.transport,
            },
            governance_verdict_chain=[RuntimeExecutionState.APPROVED.value],
        )

        request_id = str(request["request_id"])
        if request_id in self._issued_request_ids:
            return self._rejected_response(
                command=representative_command,
                classification=classification,
                reason="replayed_request_id",
                start=start,
            )

        self._issued_request_ids.add(request_id)
        self._lineage[request_id] = {
            "request": request,
            "request_timestamp": str(start),
            "request_integrity_sha256": request["request_integrity_sha256"],
            "governance_verdict_chain": [RuntimeExecutionState.APPROVED.value],
            "transport_metadata": request.get("transport_metadata", {}),
            "status": "request_sent",
        }

        raw_response = self._client.execute(
            request, timeout_seconds=max(1.0, timeout_ms / 1000.0)
        )
        return self._interpret_response(
            command=representative_command,
            classification=classification,
            request=request,
            payload=raw_response,
            start=start,
        )

    def _validate_governance(
        self,
        commands: list[str],
        *,
        classification: CommandClassification,
        operator_approved: bool,
    ) -> str | None:
        if not commands:
            return "empty_command_batch"
        if len(commands) > self._max_commands_per_batch:
            return "max_command_count_exceeded"

        for command in commands:
            if command not in self._allowlisted_commands:
                return "allowlist_violation"

            lowered = command.lower()
            if any(pattern in lowered for pattern in FORBIDDEN_PATTERNS):
                return "forbidden_pattern_detected"

            computed_classification = classify_command(command)
            if (
                computed_classification == CommandClassification.REQUIRES_OPERATOR_APPROVAL
                or classification == CommandClassification.REQUIRES_OPERATOR_APPROVAL
            ) and not operator_approved:
                return "operator_approval_required"

        return None

    def _interpret_response(
        self,
        *,
        command: str,
        classification: CommandClassification,
        request: dict[str, Any],
        payload: dict[str, Any],
        start: float,
    ) -> TransportResponse:
        request_id = str(request["request_id"])
        request_sequence = int(request["request_sequence"])
        lineage = self._lineage.get(request_id, {})

        valid_response, reason = validate_response_block(payload)
        if not valid_response:
            return self._invalid_response(
                command=command,
                classification=classification,
                reason=f"invalid_response:{reason}",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        if payload.get("request_id") != request_id:
            return self._invalid_response(
                command=command,
                classification=classification,
                reason="invalid_response:request_id_mismatch",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        if int(payload.get("request_sequence", 0)) != request_sequence:
            return self._invalid_response(
                command=command,
                classification=classification,
                reason="invalid_response:request_sequence_mismatch",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        if payload.get("request_integrity_sha256") != request.get("request_integrity_sha256"):
            return self._invalid_response(
                command=command,
                classification=classification,
                reason="invalid_response:request_integrity_mismatch",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        response_hash = str(payload.get("response_integrity_sha256", ""))
        if response_hash in self._seen_response_hashes:
            return self._blocked_response(
                command=command,
                classification=classification,
                reason="duplicate_response_detected",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        if request_id in self._completed_request_ids:
            return self._blocked_response(
                command=command,
                classification=classification,
                reason="duplicate_response_for_request",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        response_sequence = int(payload.get("request_sequence", 0))
        if response_sequence <= self._last_response_sequence:
            return self._blocked_response(
                command=command,
                classification=classification,
                reason="out_of_order_response_detected",
                start=start,
                request_id=request_id,
                lineage=lineage,
            )

        execution_status = str(payload.get("execution_status", RESPONSE_STATUS_INVALID))
        runtime_state, confidence, state_label = self._map_execution_status(execution_status)

        stdout_text = str(payload.get("raw_output", ""))
        stderr_text = str(payload.get("stderr", ""))

        oversized_output = False
        if len(stdout_text.encode("utf-8", errors="replace")) > self._max_stdout_bytes:
            oversized_output = True
        if len(stderr_text.encode("utf-8", errors="replace")) > self._max_stderr_bytes:
            oversized_output = True
        if oversized_output:
            runtime_state = RuntimeState.PARTIAL
            confidence = TransportConfidence.ADVISORY_ONLY
            state_label = RuntimeExecutionState.PARTIAL.value
            if stderr_text:
                stderr_text += "\n"
            stderr_text += "oversized_output_detected"

        heartbeat_state = self._evaluate_heartbeat(payload.get("executor_heartbeat"))
        if heartbeat_state == "stale":
            confidence = TransportConfidence.ADVISORY_ONLY
        elif heartbeat_state == "missing":
            confidence = TransportConfidence.ADVISORY_ONLY

        notes = {
            "governance": "linux_authoritative",
            "request_id": request_id,
            "request_sequence": request_sequence,
            "execution_status": execution_status,
            "response_integrity": "validated",
            "execution_mode": payload.get("execution_mode", ""),
            "transport_metadata": payload.get("transport_metadata", {}),
            "executor_identity": payload.get("executor_identity", {}),
            "executor_heartbeat": payload.get("executor_heartbeat", {}),
            "governance_verdict_chain": [
                RuntimeExecutionState.APPROVED.value,
                RuntimeExecutionState.EXECUTING.value,
                state_label,
            ],
            "heartbeat_state": heartbeat_state,
        }

        if execution_status == RESPONSE_STATUS_EXECUTED:
            command_results = payload.get("command_results")
            if isinstance(command_results, list) and command_results:
                exit_code = int(command_results[0].get("exit_code", -1))
            else:
                exit_code = 0
        else:
            exit_code = -1

        self._seen_response_hashes.add(response_hash)
        self._completed_request_ids.add(request_id)
        self._last_response_sequence = response_sequence

        lineage["response"] = payload
        lineage["response_integrity_sha256"] = response_hash
        lineage["response_timestamp"] = str(time.time())
        lineage["governance_verdict_chain"] = notes["governance_verdict_chain"]
        lineage["status"] = state_label
        self._lineage[request_id] = lineage

        timestamp = str(start)
        timestamps = payload.get("timestamps")
        if isinstance(timestamps, dict):
            timestamp = str(timestamps.get("started_at", timestamp))

        return TransportResponse(
            transport=self.metadata.transport,
            command=command,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            timestamp=timestamp,
            duration_ms=int((time.time() - start) * 1000),
            runtime_state=runtime_state,
            confidence=confidence,
            classification=classification,
            notes=notes,
        )

    def _evaluate_heartbeat(self, heartbeat: Any) -> str:
        if not isinstance(heartbeat, dict):
            return "missing"
        raw_ts = heartbeat.get("heartbeat_timestamp")
        if not isinstance(raw_ts, str) or not raw_ts:
            return "missing"
        try:
            heartbeat_ts = float(raw_ts)
        except ValueError:
            return "missing"

        if (time.time() - heartbeat_ts) > float(self._heartbeat_staleness_seconds):
            return "stale"
        return "fresh"

    def _map_execution_status(
        self, execution_status: str
    ) -> tuple[RuntimeState, TransportConfidence, str]:
        if execution_status == RESPONSE_STATUS_EXECUTED:
            return (
                RuntimeState.COMPLETED,
                TransportConfidence.CAPTURE_READY,
                RuntimeExecutionState.COMPLETED.value,
            )
        if execution_status == RESPONSE_STATUS_TIMEOUT:
            return (
                RuntimeState.TIMEOUT,
                TransportConfidence.UNKNOWN,
                RuntimeExecutionState.TIMEOUT.value,
            )
        if execution_status == RESPONSE_STATUS_PARTIAL_RESPONSE:
            return (
                RuntimeState.PARTIAL,
                TransportConfidence.ADVISORY_ONLY,
                RuntimeExecutionState.PARTIAL.value,
            )
        if execution_status == RESPONSE_STATUS_TRANSPORT_DISCONNECTED:
            return (
                RuntimeState.UNKNOWN,
                TransportConfidence.UNKNOWN,
                RuntimeExecutionState.UNKNOWN.value,
            )
        if execution_status == RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST:
            return (
                RuntimeState.REJECTED,
                TransportConfidence.ESCALATION_REQUIRED,
                RuntimeExecutionState.REJECTED.value,
            )
        if execution_status == RESPONSE_STATUS_INVALID:
            return (
                RuntimeState.INVALID,
                TransportConfidence.ESCALATION_REQUIRED,
                RuntimeExecutionState.INVALID.value,
            )
        if execution_status == RESPONSE_STATUS_FAILED:
            return (
                RuntimeState.PARTIAL,
                TransportConfidence.ADVISORY_ONLY,
                RuntimeExecutionState.PARTIAL.value,
            )
        return (
            RuntimeState.UNKNOWN,
            TransportConfidence.UNKNOWN,
            RuntimeExecutionState.UNKNOWN.value,
        )

    def _invalid_response(
        self,
        *,
        command: str,
        classification: CommandClassification,
        reason: str,
        start: float,
        request_id: str,
        lineage: dict[str, Any],
    ) -> TransportResponse:
        lineage["status"] = RuntimeExecutionState.INVALID.value
        lineage["invalid_reason"] = reason
        lineage["governance_verdict_chain"] = [
            RuntimeExecutionState.APPROVED.value,
            RuntimeExecutionState.EXECUTING.value,
            RuntimeExecutionState.INVALID.value,
        ]
        self._lineage[request_id] = lineage
        return TransportResponse(
            transport=self.metadata.transport,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=reason,
            timestamp=str(start),
            duration_ms=int((time.time() - start) * 1000),
            runtime_state=RuntimeState.INVALID,
            confidence=TransportConfidence.ESCALATION_REQUIRED,
            classification=classification,
            notes={
                "governance": "fail_closed",
                "request_id": request_id,
                "governance_verdict_chain": lineage["governance_verdict_chain"],
            },
        )

    def _blocked_response(
        self,
        *,
        command: str,
        classification: CommandClassification,
        reason: str,
        start: float,
        request_id: str,
        lineage: dict[str, Any],
    ) -> TransportResponse:
        lineage["status"] = "BLOCKED"
        lineage["blocked_reason"] = reason
        lineage["governance_verdict_chain"] = [
            RuntimeExecutionState.APPROVED.value,
            RuntimeExecutionState.EXECUTING.value,
            RuntimeExecutionState.INVALID.value,
        ]
        self._lineage[request_id] = lineage
        return TransportResponse(
            transport=self.metadata.transport,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=reason,
            timestamp=str(start),
            duration_ms=int((time.time() - start) * 1000),
            runtime_state=RuntimeState.BLOCKED,
            confidence=TransportConfidence.ESCALATION_REQUIRED,
            classification=classification,
            notes={
                "governance": "fail_closed",
                "request_id": request_id,
                "governance_verdict_chain": lineage["governance_verdict_chain"],
            },
        )

    def _rejected_response(
        self,
        *,
        command: str,
        classification: CommandClassification,
        reason: str,
        start: float,
    ) -> TransportResponse:
        return TransportResponse(
            transport=self.metadata.transport,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=reason,
            timestamp=str(start),
            duration_ms=int((time.time() - start) * 1000),
            runtime_state=RuntimeState.REJECTED,
            confidence=TransportConfidence.ESCALATION_REQUIRED,
            classification=classification,
            notes={
                "governance": "linux_authoritative",
                "governance_verdict_chain": [
                    RuntimeExecutionState.REJECTED.value,
                ],
            },
        )
