"""Immutable protocol primitives for governed distributed runtime transport."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from enum import Enum
from typing import Any


PROTOCOL_VERSION = "1.1"

MAX_COMMANDS_PER_BATCH = 8
MAX_STDOUT_BYTES = 128 * 1024
MAX_STDERR_BYTES = 32 * 1024
HEARTBEAT_STALENESS_SECONDS = 60

RESPONSE_STATUS_EXECUTED = "executed"
RESPONSE_STATUS_TIMEOUT = "timeout"
RESPONSE_STATUS_PARTIAL_RESPONSE = "partial_response"
RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST = "rejected_malformed_request"
RESPONSE_STATUS_TRANSPORT_DISCONNECTED = "transport_disconnected"
RESPONSE_STATUS_INVALID = "invalid"
RESPONSE_STATUS_FAILED = "failed"


class RuntimeExecutionState(str, Enum):
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    TIMEOUT = "TIMEOUT"
    INVALID = "INVALID"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hashable_request(request: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(request)
    cleaned.pop("request_integrity_sha256", None)
    return cleaned


def _hashable_response(response: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(response)
    cleaned.pop("response_integrity_sha256", None)
    return cleaned


def compute_request_integrity(request: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(_hashable_request(request)))


def compute_response_integrity(response: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(_hashable_response(response)))


def build_request_block(
    approved_commands: list[str],
    *,
    timeout_seconds: int,
    transport: str,
    execution_mode: str,
    request_sequence: int,
    request_id: str | None = None,
    transport_metadata: dict[str, Any] | None = None,
    governance_verdict_chain: list[str] | None = None,
) -> dict[str, Any]:
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id or str(uuid.uuid4()),
        "request_sequence": int(request_sequence),
        "approved_commands": approved_commands,
        "timeout_seconds": int(timeout_seconds),
        "transport": transport,
        "execution_mode": execution_mode,
        "request_timestamp": str(time.time()),
        "transport_metadata": transport_metadata or {},
        "governance_verdict_chain": governance_verdict_chain
        or [RuntimeExecutionState.APPROVED.value],
    }
    request["request_integrity_sha256"] = compute_request_integrity(request)
    return request


def validate_request_block(request: dict[str, Any]) -> tuple[bool, str]:
    required = {
        "protocol_version",
        "request_id",
        "request_sequence",
        "approved_commands",
        "timeout_seconds",
        "transport",
        "execution_mode",
        "request_timestamp",
        "request_integrity_sha256",
        "transport_metadata",
        "governance_verdict_chain",
    }
    missing = sorted(required - set(request.keys()))
    if missing:
        return False, f"missing_fields:{','.join(missing)}"

    if request.get("protocol_version") != PROTOCOL_VERSION:
        return False, "unsupported_protocol_version"

    request_id = request.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return False, "request_id_invalid"

    request_sequence = request.get("request_sequence")
    if not isinstance(request_sequence, int) or request_sequence < 1:
        return False, "request_sequence_invalid"

    approved_commands = request.get("approved_commands")
    if not isinstance(approved_commands, list) or not approved_commands:
        return False, "approved_commands_invalid"
    if len(approved_commands) > MAX_COMMANDS_PER_BATCH:
        return False, "max_command_count_exceeded"
    if any((not isinstance(command, str) or not command.strip()) for command in approved_commands):
        return False, "approved_commands_invalid"

    timeout_seconds = request.get("timeout_seconds")
    if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        return False, "timeout_invalid"

    if not isinstance(request.get("transport_metadata"), dict):
        return False, "transport_metadata_invalid"

    verdict_chain = request.get("governance_verdict_chain")
    if not isinstance(verdict_chain, list) or not verdict_chain:
        return False, "governance_verdict_chain_invalid"

    integrity = request.get("request_integrity_sha256")
    if not isinstance(integrity, str) or len(integrity) != 64:
        return False, "request_integrity_missing_or_invalid"

    computed = compute_request_integrity(request)
    if integrity != computed:
        return False, "request_integrity_mismatch"

    return True, "ok"


def validate_response_block(response: dict[str, Any]) -> tuple[bool, str]:
    required = {
        "protocol_version",
        "request_id",
        "request_sequence",
        "approved_commands",
        "timeout_seconds",
        "transport",
        "execution_mode",
        "timestamps",
        "execution_status",
        "raw_output",
        "stderr",
        "request_integrity_sha256",
        "response_integrity_sha256",
        "transport_metadata",
        "executor_identity",
        "executor_heartbeat",
        "governance_verdict_chain",
    }
    missing = sorted(required - set(response.keys()))
    if missing:
        return False, f"missing_fields:{','.join(missing)}"

    if response.get("protocol_version") != PROTOCOL_VERSION:
        return False, "unsupported_protocol_version"

    request_id = response.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        return False, "request_id_invalid"

    request_sequence = response.get("request_sequence")
    if not isinstance(request_sequence, int) or request_sequence < 1:
        return False, "request_sequence_invalid"

    if response.get("execution_status") not in {
        RESPONSE_STATUS_EXECUTED,
        RESPONSE_STATUS_TIMEOUT,
        RESPONSE_STATUS_PARTIAL_RESPONSE,
        RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST,
        RESPONSE_STATUS_TRANSPORT_DISCONNECTED,
        RESPONSE_STATUS_INVALID,
        RESPONSE_STATUS_FAILED,
    }:
        return False, "execution_status_invalid"

    timestamps = response.get("timestamps")
    if not isinstance(timestamps, dict):
        return False, "timestamps_invalid"
    for key in ("received_at", "started_at", "finished_at"):
        value = timestamps.get(key)
        if not isinstance(value, str) or not value:
            return False, f"timestamps_missing:{key}"

    if not isinstance(response.get("raw_output"), str):
        return False, "raw_output_invalid"
    if not isinstance(response.get("stderr"), str):
        return False, "stderr_invalid"

    if not isinstance(response.get("transport_metadata"), dict):
        return False, "transport_metadata_invalid"
    if not isinstance(response.get("executor_identity"), dict):
        return False, "executor_identity_invalid"
    if not isinstance(response.get("executor_heartbeat"), dict):
        return False, "executor_heartbeat_invalid"

    verdict_chain = response.get("governance_verdict_chain")
    if not isinstance(verdict_chain, list) or not verdict_chain:
        return False, "governance_verdict_chain_invalid"

    response_integrity = response.get("response_integrity_sha256")
    if not isinstance(response_integrity, str) or len(response_integrity) != 64:
        return False, "response_integrity_missing_or_invalid"

    computed = compute_response_integrity(response)
    if response_integrity != computed:
        return False, "response_integrity_mismatch"

    return True, "ok"


def build_rejected_malformed_response(
    request_id: str,
    *,
    request_sequence: int = 1,
    reason: str,
    transport: str = "remote_serial",
    execution_mode: str = "worker_execute_only",
) -> dict[str, Any]:
    now = str(time.time())
    response = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id or str(uuid.uuid4()),
        "request_sequence": request_sequence,
        "approved_commands": [],
        "timeout_seconds": 0,
        "transport": transport,
        "execution_mode": execution_mode,
        "timestamps": {
            "received_at": now,
            "started_at": now,
            "finished_at": now,
        },
        "execution_status": RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST,
        "raw_output": "",
        "stderr": reason,
        "command_results": [],
        "request_integrity_sha256": "",
        "transport_metadata": {},
        "executor_identity": {"executor_id": "unknown"},
        "executor_heartbeat": {
            "heartbeat_counter": 0,
            "heartbeat_timestamp": now,
            "connection_state": "unknown",
        },
        "governance_verdict_chain": [RuntimeExecutionState.REJECTED.value],
    }
    response["response_integrity_sha256"] = compute_response_integrity(response)
    return response


def map_status_to_execution_state(execution_status: str) -> RuntimeExecutionState:
    if execution_status == RESPONSE_STATUS_EXECUTED:
        return RuntimeExecutionState.COMPLETED
    if execution_status == RESPONSE_STATUS_TIMEOUT:
        return RuntimeExecutionState.TIMEOUT
    if execution_status == RESPONSE_STATUS_PARTIAL_RESPONSE:
        return RuntimeExecutionState.PARTIAL
    if execution_status == RESPONSE_STATUS_REJECTED_MALFORMED_REQUEST:
        return RuntimeExecutionState.REJECTED
    if execution_status == RESPONSE_STATUS_INVALID:
        return RuntimeExecutionState.INVALID
    if execution_status == RESPONSE_STATUS_TRANSPORT_DISCONNECTED:
        return RuntimeExecutionState.UNKNOWN
    if execution_status == RESPONSE_STATUS_FAILED:
        return RuntimeExecutionState.PARTIAL
    return RuntimeExecutionState.UNKNOWN
