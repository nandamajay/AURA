"""Bounded serial request-block executor for the Windows serial agent."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from aura_sdk.transport.runtime_protocol import (
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    RESPONSE_STATUS_EXECUTED,
    RESPONSE_STATUS_FAILED,
    RESPONSE_STATUS_PARTIAL_RESPONSE,
    RESPONSE_STATUS_TIMEOUT,
    RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
    RuntimeExecutionState,
    build_rejected_malformed_response,
    compute_response_integrity,
    validate_request_block,
)
from aura_sdk.transport.serial_prompt_detector import SerialPromptDetector


MARKER_PREFIX = "__AURA_RC:"
DEFAULT_MAX_CAPTURE_BYTES = MAX_STDOUT_BYTES


@dataclass(frozen=True)
class SerialAgentConfig:
    com_port: str
    baudrate: int = 115200
    timeout_seconds: int = 10
    prompt_regex: str = r"root@.*[#$]"
    reconnect_policy: str = "fail_closed"


class RuntimeSerialExecutor:
    """Execute-only worker that runs approved commands exactly as received."""

    def __init__(
        self,
        config: SerialAgentConfig,
        *,
        max_capture_bytes: int = DEFAULT_MAX_CAPTURE_BYTES,
        evidence_log_path: str | Path | None = None,
    ):
        self._config = config
        self._max_capture_bytes = max_capture_bytes
        self._prompt_detector = SerialPromptDetector(config.prompt_regex)
        self._serial: Any | None = None
        self._evidence_log_path = Path(evidence_log_path) if evidence_log_path else None
        self._heartbeat_counter = 0
        self._executor_id = hashlib.sha256(
            f"{config.com_port}:{config.baudrate}:{config.prompt_regex}".encode("utf-8")
        ).hexdigest()[:16]
        if self._evidence_log_path:
            self._evidence_log_path.parent.mkdir(parents=True, exist_ok=True)

    def execute_request_block(self, request_block: dict[str, Any]) -> dict[str, Any]:
        received_at = str(time.time())
        request_id = str(request_block.get("request_id", ""))
        request_sequence = int(request_block.get("request_sequence", 1))

        valid, reason = validate_request_block(request_block)
        if not valid:
            response = build_rejected_malformed_response(
                request_id,
                request_sequence=request_sequence,
                reason=reason,
                transport=str(request_block.get("transport", "remote_serial")),
                execution_mode=str(request_block.get("execution_mode", "worker_execute_only")),
            )
            response["executor_identity"] = self._executor_identity()
            response["executor_heartbeat"] = self._heartbeat(connection_state="rejected")
            response["transport_metadata"] = {
                "com_port": self._config.com_port,
                "baudrate": self._config.baudrate,
                "reconnect_policy": self._config.reconnect_policy,
            }
            response["response_integrity_sha256"] = compute_response_integrity(response)
            self._persist_evidence(response)
            return response

        transport_metadata = {
            "com_port": self._config.com_port,
            "baudrate": self._config.baudrate,
            "reconnect_policy": self._config.reconnect_policy,
            "target_transport": str(request_block.get("transport", "remote_serial")),
        }

        if not self._ensure_serial_connected():
            now = str(time.time())
            response = {
                "protocol_version": request_block["protocol_version"],
                "request_id": request_id,
                "request_sequence": request_sequence,
                "approved_commands": list(request_block["approved_commands"]),
                "timeout_seconds": int(request_block["timeout_seconds"]),
                "transport": str(request_block["transport"]),
                "execution_mode": str(request_block["execution_mode"]),
                "timestamps": {
                    "received_at": received_at,
                    "started_at": now,
                    "finished_at": now,
                },
                "execution_status": RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
                "raw_output": "",
                "stderr": "serial_connection_unavailable",
                "command_results": [],
                "request_integrity_sha256": str(request_block["request_integrity_sha256"]),
                "transport_metadata": transport_metadata,
                "executor_identity": self._executor_identity(),
                "executor_heartbeat": self._heartbeat(connection_state="disconnected"),
                "governance_verdict_chain": [RuntimeExecutionState.UNKNOWN.value],
            }
            response["response_integrity_sha256"] = compute_response_integrity(response)
            self._persist_evidence(response)
            return response

        started_at = str(time.time())
        timeout_seconds = int(request_block["timeout_seconds"])
        command_results: list[dict[str, Any]] = []

        for approved_command in request_block["approved_commands"]:
            command_results.append(
                self._execute_single_command(str(approved_command), timeout_seconds=timeout_seconds)
            )

        finished_at = str(time.time())

        combined_output = "\n".join(
            result["raw_output"] for result in command_results if result["raw_output"]
        )
        combined_stderr = "\n".join(
            result["stderr"] for result in command_results if result["stderr"]
        )

        combined_output, output_truncated = self._truncate_text(combined_output, MAX_STDOUT_BYTES)
        combined_stderr, stderr_truncated = self._truncate_text(combined_stderr, MAX_STDERR_BYTES)

        statuses = {result["execution_status"] for result in command_results}
        if RESPONSE_STATUS_TIMEOUT in statuses:
            execution_status = RESPONSE_STATUS_TIMEOUT
        elif RESPONSE_STATUS_TRANSPORT_DISCONNECTED in statuses:
            execution_status = RESPONSE_STATUS_TRANSPORT_DISCONNECTED
        elif RESPONSE_STATUS_PARTIAL_RESPONSE in statuses:
            execution_status = RESPONSE_STATUS_PARTIAL_RESPONSE
        elif RESPONSE_STATUS_FAILED in statuses:
            execution_status = RESPONSE_STATUS_FAILED
        else:
            execution_status = RESPONSE_STATUS_EXECUTED

        if output_truncated or stderr_truncated:
            execution_status = RESPONSE_STATUS_PARTIAL_RESPONSE
            combined_stderr = (combined_stderr + "\n" if combined_stderr else "") + "output_truncated"

        response = {
            "protocol_version": request_block["protocol_version"],
            "request_id": request_id,
            "request_sequence": request_sequence,
            "approved_commands": list(request_block["approved_commands"]),
            "timeout_seconds": timeout_seconds,
            "transport": str(request_block["transport"]),
            "execution_mode": str(request_block["execution_mode"]),
            "timestamps": {
                "received_at": received_at,
                "started_at": started_at,
                "finished_at": finished_at,
            },
            "execution_status": execution_status,
            "raw_output": combined_output,
            "stderr": combined_stderr,
            "command_results": command_results,
            "request_integrity_sha256": str(request_block["request_integrity_sha256"]),
            "transport_metadata": transport_metadata,
            "executor_identity": self._executor_identity(),
            "executor_heartbeat": self._heartbeat(connection_state="connected"),
            "governance_verdict_chain": [
                RuntimeExecutionState.EXECUTING.value,
                self._state_for_status(execution_status),
            ],
        }
        response["response_integrity_sha256"] = compute_response_integrity(response)
        self._persist_evidence(response)
        return response

    def close(self) -> None:
        if self._serial is None:
            return
        try:
            self._serial.close()
        finally:
            self._serial = None

    def _ensure_serial_connected(self) -> bool:
        if self._serial is not None and bool(getattr(self._serial, "is_open", False)):
            return True
        try:
            import serial  # type: ignore

            self._serial = serial.Serial(
                port=self._config.com_port,
                baudrate=self._config.baudrate,
                timeout=0.2,
                write_timeout=1.0,
            )
            return True
        except Exception:
            self._serial = None
            return False

    def _execute_single_command(self, command: str, *, timeout_seconds: int) -> dict[str, Any]:
        started_at = str(time.time())
        raw_output = ""
        stderr_text = ""
        execution_status = RESPONSE_STATUS_EXECUTED
        exit_code = -1

        try:
            if self._serial is None:
                return {
                    "command": command,
                    "raw_output": "",
                    "stderr": "serial_connection_unavailable",
                    "exit_code": -1,
                    "timestamps": {
                        "started_at": started_at,
                        "finished_at": str(time.time()),
                    },
                    "execution_status": RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
                }

            wrapped_command = f"{command}; printf '\\n{MARKER_PREFIX}%s\\n' $?"
            self._serial.reset_input_buffer()
            self._serial.write((wrapped_command + "\n").encode("utf-8"))
            self._serial.flush()

            deadline = time.time() + float(timeout_seconds)
            captured = bytearray()
            prompt_seen = False

            while time.time() < deadline:
                chunk = self._serial.read(512)
                if not chunk:
                    time.sleep(0.05)
                    continue

                captured.extend(chunk)
                if len(captured) >= self._max_capture_bytes:
                    execution_status = RESPONSE_STATUS_PARTIAL_RESPONSE
                    stderr_text = "capture_limit_reached"
                    break

                decoded = captured.decode("utf-8", errors="replace")
                analysis = self._prompt_detector.analyze(decoded)
                prompt_seen = analysis.prompt_seen

                if analysis.panic_detected:
                    execution_status = RESPONSE_STATUS_FAILED
                    stderr_text = "kernel_panic_signature_detected"
                    break

                if prompt_seen and MARKER_PREFIX in decoded:
                    break

            raw_output = captured.decode("utf-8", errors="replace")
            raw_output, truncated = self._truncate_text(raw_output, MAX_STDOUT_BYTES)
            if truncated:
                execution_status = RESPONSE_STATUS_PARTIAL_RESPONSE
                stderr_text = "capture_limit_reached"

            exit_code = self._extract_exit_code(raw_output)

            if not raw_output:
                execution_status = RESPONSE_STATUS_PARTIAL_RESPONSE
                stderr_text = "no_serial_output"
            elif execution_status == RESPONSE_STATUS_EXECUTED and not prompt_seen:
                execution_status = RESPONSE_STATUS_TIMEOUT
                stderr_text = "prompt_not_detected"
            elif execution_status == RESPONSE_STATUS_EXECUTED and exit_code not in (0, -1):
                execution_status = RESPONSE_STATUS_FAILED

        except Exception as exc:
            execution_status = RESPONSE_STATUS_FAILED
            stderr_text = f"serial_execution_error:{exc}"

        stderr_text, _ = self._truncate_text(stderr_text, MAX_STDERR_BYTES)
        return {
            "command": command,
            "raw_output": raw_output,
            "stderr": stderr_text,
            "exit_code": exit_code,
            "timestamps": {
                "started_at": started_at,
                "finished_at": str(time.time()),
            },
            "execution_status": execution_status,
        }

    def _extract_exit_code(self, output: str) -> int:
        parsed_exit_code = -1
        for line in output.splitlines():
            stripped = line.strip()
            if not stripped.startswith(MARKER_PREFIX):
                continue
            code_text = stripped[len(MARKER_PREFIX) :]
            try:
                parsed_exit_code = int(code_text)
            except ValueError:
                parsed_exit_code = -1
        return parsed_exit_code

    def _truncate_text(self, text: str, max_bytes: int) -> tuple[str, bool]:
        encoded = text.encode("utf-8", errors="replace")
        if len(encoded) <= max_bytes:
            return text, False
        truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
        return truncated, True

    def _executor_identity(self) -> dict[str, Any]:
        return {
            "executor_id": self._executor_id,
            "executor_type": "windows_serial_agent",
            "com_port": self._config.com_port,
            "baudrate": self._config.baudrate,
        }

    def _heartbeat(self, *, connection_state: str) -> dict[str, Any]:
        self._heartbeat_counter += 1
        return {
            "heartbeat_counter": self._heartbeat_counter,
            "heartbeat_timestamp": str(time.time()),
            "connection_state": connection_state,
        }

    def _state_for_status(self, execution_status: str) -> str:
        if execution_status == RESPONSE_STATUS_EXECUTED:
            return RuntimeExecutionState.COMPLETED.value
        if execution_status == RESPONSE_STATUS_TIMEOUT:
            return RuntimeExecutionState.TIMEOUT.value
        if execution_status == RESPONSE_STATUS_PARTIAL_RESPONSE:
            return RuntimeExecutionState.PARTIAL.value
        if execution_status == RESPONSE_STATUS_TRANSPORT_DISCONNECTED:
            return RuntimeExecutionState.UNKNOWN.value
        return RuntimeExecutionState.PARTIAL.value

    def _persist_evidence(self, payload: dict[str, Any]) -> None:
        if not self._evidence_log_path:
            return
        line = dict(payload)
        line["logged_at"] = str(time.time())
        line["agent_config"] = asdict(self._config)
        with self._evidence_log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line, sort_keys=True) + "\n")
