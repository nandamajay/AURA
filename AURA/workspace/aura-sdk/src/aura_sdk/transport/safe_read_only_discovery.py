"""Governed SAFE_READ_ONLY distributed runtime discovery execution."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aura_sdk.transport.adapters.adb_transport_adapter import AdbTransportAdapter
from aura_sdk.transport.adapters.remote_serial_transport_adapter import (
    RemoteSerialTransportAdapter,
)
from aura_sdk.transport.adapters.serial_transport_adapter import SerialTransportAdapter
from aura_sdk.transport.runtime_command_dispatcher import RuntimeCommandDispatcher
from aura_sdk.transport.runtime_transport_api import CommandClassification, RuntimeState


SAFE_READ_ONLY_COMMANDS = (
    "getprop ro.build.fingerprint",
    "getprop ro.product.device",
    "cat /proc/version",
    "cat /proc/asound/cards",
    "cat /proc/asound/pcm",
    "dmesg | tail -50",
)

ALLOWED_PIPE_COMMAND = "dmesg | tail -50"
FORBIDDEN_OPERATOR_TOKENS = (";", "&&", "||", "`", "$(", ">", "<")
INTERACTIVE_TOKENS = (
    " bash",
    " sh",
    " zsh",
    " vi",
    " vim",
    " nano",
    " top",
    " less",
    " more",
    " tail -f",
)


@dataclass(frozen=True)
class DiscoveryConfig:
    output_dir: str
    adb_serial: str | None = None
    serial_port: str = "COM5"
    serial_baudrate: int = 115200
    remote_host: str | None = None
    remote_port: int = 54888
    timeout_ms: int = 10_000


class SafeReadOnlyDiscoveryRunner:
    def __init__(self, config: DiscoveryConfig):
        self._config = config
        self._output_dir = Path(config.output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._dispatcher = RuntimeCommandDispatcher(
            log_path=self._output_dir / "runtime_discovery_dispatcher.jsonl"
        )
        self._adb_adapter = AdbTransportAdapter(serial=config.adb_serial)
        self._serial_adapter = SerialTransportAdapter(
            port=config.serial_port,
            baudrate=config.serial_baudrate,
        )
        self._remote_adapter: RemoteSerialTransportAdapter | None = None
        if config.remote_host:
            self._remote_adapter = RemoteSerialTransportAdapter(
                host=config.remote_host,
                port=config.remote_port,
                allowlisted_commands=SAFE_READ_ONLY_COMMANDS,
            )

        self._dispatcher.register("adb", self._adb_adapter)
        if self._remote_adapter:
            self._dispatcher.register("remote_serial", self._remote_adapter)

        self._sequence = 0

    def run(self) -> dict[str, Any]:
        started_at = str(time.time())
        trace_entries: list[dict[str, Any]] = []
        command_log_entries: list[dict[str, Any]] = []

        transports = ["adb"]
        if self._remote_adapter:
            transports.append("remote_serial")

        for transport_name in transports:
            for command in SAFE_READ_ONLY_COMMANDS:
                command_validation = self._validate_command(command)
                command_log_entries.append(
                    {**command_validation, "transport": transport_name}
                )

                if not command_validation["allowed"]:
                    trace_entries.append(
                        self._blocked_trace_entry(
                            command,
                            transport=transport_name,
                            reason=command_validation["reason"],
                        )
                    )
                    continue

                self._sequence += 1
                request_id = str(uuid.uuid4())
                dispatched_at = str(time.time())

                response = self._dispatcher.execute(
                    transport_name,
                    command,
                    timeout_ms=self._config.timeout_ms,
                    classification=CommandClassification.SAFE_READ,
                    operator_approved=False,
                )

                trace_entry = self._build_trace_entry(
                    request_id=request_id,
                    sequence=self._sequence,
                    command=command,
                    transport=transport_name,
                    dispatched_at=dispatched_at,
                    response=response,
                )
                trace_entries.append(trace_entry)

        finished_at = str(time.time())

        transport_metadata = {
            "adb": {
                "transport": self._adb_adapter.metadata.transport,
                "target": self._adb_adapter.metadata.target,
            },
            "serial": {
                "transport": self._serial_adapter.metadata.transport,
                "target": self._serial_adapter.metadata.target,
                "baudrate": self._config.serial_baudrate,
                "connectivity_state": self._serial_adapter.check_connectivity().runtime_state.value,
            },
            "remote_serial": {
                "transport": "remote_serial",
                "target": (
                    f"{self._config.remote_host}:{self._config.remote_port}"
                    if self._config.remote_host
                    else "not_configured"
                ),
                "connectivity_state": "unknown" if self._config.remote_host else "not_configured",
            },
        }

        overall = self._summarize(trace_entries)
        evidence = {
            "execution_mode": "SAFE_READ_ONLY_DISCOVERY_ONLY",
            "started_at": started_at,
            "finished_at": finished_at,
            "transport_metadata": transport_metadata,
            "trace": trace_entries,
            "summary": overall,
            "governance_posture": "ADVISORY_ONLY",
            "claims": {
                "runtime_parity": "NOT_CLAIMED",
                "behavioral_equivalence": "NOT_CLAIMED",
                "merge_readiness": "NOT_CLAIMED",
            },
        }

        self._write_artifacts(
            evidence=evidence,
            trace_entries=trace_entries,
            command_log_entries=command_log_entries,
        )
        return evidence

    def _validate_command(self, command: str) -> dict[str, Any]:
        if command not in SAFE_READ_ONLY_COMMANDS:
            return {"command": command, "allowed": False, "reason": "not_allowlisted"}

        lowered = f" {command.lower()} "
        for token in INTERACTIVE_TOKENS:
            if token in lowered:
                return {"command": command, "allowed": False, "reason": "interactive_command_blocked"}

        for token in FORBIDDEN_OPERATOR_TOKENS:
            if token in command:
                if token == "|" and command == ALLOWED_PIPE_COMMAND:
                    continue
                return {
                    "command": command,
                    "allowed": False,
                    "reason": f"forbidden_operator:{token}",
                }

        return {"command": command, "allowed": True, "reason": "allowlisted_safe_read"}

    def _blocked_trace_entry(
        self,
        command: str,
        *,
        transport: str,
        reason: str,
    ) -> dict[str, Any]:
        now = str(time.time())
        request_id = str(uuid.uuid4())
        raw = {
            "request_id": request_id,
            "sequence": self._sequence,
            "transport": transport,
            "command": command,
            "stdout": "",
            "stderr": reason,
            "runtime_state": RuntimeState.BLOCKED.value,
            "status": "BLOCKED",
            "dispatched_at": now,
            "completed_at": now,
            "governance_verdict_chain": ["APPROVED", "INVALID"],
        }
        raw["response_sha256"] = self._sha256_json(raw)
        return raw

    def _build_trace_entry(
        self,
        *,
        request_id: str,
        sequence: int,
        command: str,
        transport: str,
        dispatched_at: str,
        response: Any,
    ) -> dict[str, Any]:
        response_state = str(response.runtime_state.value)
        status = self._classify_status(
            response_state=response_state,
            stderr=response.stderr,
        )

        notes = response.notes if isinstance(response.notes, dict) else {}
        executor_identity = notes.get("executor_identity", {})

        raw = {
            "request_id": request_id,
            "sequence": sequence,
            "transport": transport,
            "command": command,
            "stdout": response.stdout,
            "stderr": response.stderr,
            "runtime_state": response_state,
            "status": status,
            "dispatched_at": dispatched_at,
            "completed_at": str(time.time()),
            "duration_ms": int(response.duration_ms),
            "response_hash_source": {
                "transport": response.transport,
                "execution_mode": notes.get("execution_mode", ""),
            },
            "executor_identity": {
                "executor_type": executor_identity.get(
                    "executor_type", f"{transport}_adapter"
                ),
                "target": executor_identity.get("target"),
            },
            "executor_heartbeat": notes.get(
                "executor_heartbeat",
                {
                    "heartbeat_counter": sequence,
                    "heartbeat_timestamp": str(time.time()),
                    "connection_state": "connected" if status == "COMPLETED" else "unknown",
                },
            ),
            "governance_verdict_chain": self._verdict_chain_for_status(status),
        }
        raw["response_sha256"] = self._sha256_json(raw)
        return raw

    def _classify_status(self, *, response_state: str, stderr: str) -> str:
        lowered_err = (stderr or "").lower()
        if response_state == RuntimeState.INVALID.value:
            return "INVALID"
        if response_state == RuntimeState.TIMEOUT.value:
            return "ADVISORY_ONLY"
        if response_state == RuntimeState.BLOCKED.value:
            return "BLOCKED"
        if response_state == RuntimeState.DISCONNECTED.value:
            return "UNKNOWN"
        if response_state == RuntimeState.UNKNOWN.value:
            return "UNKNOWN"
        if response_state == RuntimeState.FAILED.value:
            if (
                "no devices/emulators found" in lowered_err
                or "transport_client_error" in lowered_err
                or "command not found" in lowered_err
                or "device offline" in lowered_err
                or "cannot connect" in lowered_err
            ):
                return "UNKNOWN"
            return "ADVISORY_ONLY"
        if response_state == RuntimeState.PARTIAL.value:
            return "ADVISORY_ONLY"
        if response_state in {RuntimeState.EXECUTED.value, RuntimeState.COMPLETED.value}:
            return "COMPLETED"
        return "UNKNOWN"

    def _verdict_chain_for_status(self, status: str) -> list[str]:
        if status == "COMPLETED":
            return ["APPROVED", "EXECUTING", "COMPLETED"]
        if status == "BLOCKED":
            return ["APPROVED", "INVALID"]
        if status == "INVALID":
            return ["APPROVED", "EXECUTING", "INVALID"]
        if status == "ADVISORY_ONLY":
            return ["APPROVED", "EXECUTING", "PARTIAL"]
        if status == "UNKNOWN":
            return ["APPROVED", "EXECUTING", "UNKNOWN"]
        return ["UNKNOWN"]

    def _summarize(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        counts = {
            "COMPLETED": 0,
            "ADVISORY_ONLY": 0,
            "UNKNOWN": 0,
            "INVALID": 0,
            "BLOCKED": 0,
        }
        for entry in entries:
            status = str(entry.get("status", "UNKNOWN"))
            counts[status] = counts.get(status, 0) + 1

        if counts["INVALID"] > 0:
            final_status = "INVALID"
        elif counts["UNKNOWN"] > 0:
            final_status = "UNKNOWN"
        elif counts["ADVISORY_ONLY"] > 0:
            final_status = "ADVISORY_ONLY"
        elif counts["BLOCKED"] > 0:
            final_status = "BLOCKED"
        else:
            final_status = "COMPLETED"

        return {
            "counts": counts,
            "final_status": final_status,
            "final_classification": "SAFE_READ_ONLY_DISCOVERY_ONLY",
        }

    def _write_artifacts(
        self,
        *,
        evidence: dict[str, Any],
        trace_entries: list[dict[str, Any]],
        command_log_entries: list[dict[str, Any]],
    ) -> None:
        evidence_path = self._output_dir / "runtime_discovery_evidence.json"
        trace_path = self._output_dir / "transport_execution_trace.json"
        command_log_path = self._output_dir / "safe_runtime_command_log.md"
        validation_path = self._output_dir / "live_transport_validation.md"
        report_path = self._output_dir / "runtime_discovery_execution_report.md"

        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        trace_path.write_text(
            json.dumps(trace_entries, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        command_log_lines = [
            "# Safe Runtime Command Log",
            "",
            "| Transport | Command | Allowed | Reason |",
            "|---|---|---|---|",
        ]
        for row in command_log_entries:
            command_log_lines.append(
                f"| `{row['transport']}` | `{row['command']}` | `{row['allowed']}` | `{row['reason']}` |"
            )
        command_log_path.write_text("\n".join(command_log_lines) + "\n", encoding="utf-8")

        summary = evidence["summary"]
        validation_lines = [
            "# Live Transport Validation",
            "",
            "- mode: `SAFE_READ_ONLY_DISCOVERY_ONLY`",
            f"- final_status: `{summary['final_status']}`",
            f"- completed: `{summary['counts'].get('COMPLETED', 0)}`",
            f"- advisory_only: `{summary['counts'].get('ADVISORY_ONLY', 0)}`",
            f"- unknown: `{summary['counts'].get('UNKNOWN', 0)}`",
            f"- invalid: `{summary['counts'].get('INVALID', 0)}`",
            f"- blocked: `{summary['counts'].get('BLOCKED', 0)}`",
            "",
            "No runtime parity, behavioral equivalence, or merge-readiness claims are made.",
        ]
        validation_path.write_text("\n".join(validation_lines) + "\n", encoding="utf-8")

        report_lines = [
            "# Runtime Discovery Execution Report",
            "",
            "- execution_goal: validate distributed execution pipeline and immutable evidence capture",
            "- governance_mode: linux_authoritative_windows_execute_only",
            "- runtime_policy: SAFE_READ_ONLY",
            f"- classification: `{summary['final_classification']}`",
            f"- status: `{summary['final_status']}`",
            "- posture: `ADVISORY_ONLY`",
            "",
            "## Evidence",
            "- `runtime_discovery_evidence.json`",
            "- `transport_execution_trace.json`",
            "- `safe_runtime_command_log.md`",
            "- `live_transport_validation.md`",
        ]
        report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    def _sha256_json(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
