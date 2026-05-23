from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_DIR = REPO_ROOT / "src" / "aura_sdk" / "transport"
DOCS_DIR = REPO_ROOT.parents[2] / "docs" / "operations" / "transport"


def _load_runtime_protocol():
    module_path = TRANSPORT_DIR / "runtime_protocol.py"
    spec = importlib.util.spec_from_file_location("runtime_protocol_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_request_block_validation_and_limits() -> None:
    rp = _load_runtime_protocol()
    req = rp.build_request_block(
        ["echo AURA_REMOTE_TEST"],
        timeout_seconds=10,
        transport="remote_serial",
        execution_mode="governed_read_only",
        request_sequence=1,
    )
    ok, reason = rp.validate_request_block(req)
    assert ok, reason

    too_many = rp.build_request_block(
        [f"cmd_{i}" for i in range(rp.MAX_COMMANDS_PER_BATCH + 1)],
        timeout_seconds=10,
        transport="remote_serial",
        execution_mode="governed_read_only",
        request_sequence=2,
    )
    ok, reason = rp.validate_request_block(too_many)
    assert not ok
    assert reason == "max_command_count_exceeded"


def test_response_hash_mismatch_detected() -> None:
    rp = _load_runtime_protocol()
    req = rp.build_request_block(
        ["echo AURA_REMOTE_TEST"],
        timeout_seconds=10,
        transport="remote_serial",
        execution_mode="governed_read_only",
        request_sequence=1,
    )
    now = req["request_timestamp"]
    response = {
        "protocol_version": rp.PROTOCOL_VERSION,
        "request_id": req["request_id"],
        "request_sequence": req["request_sequence"],
        "approved_commands": req["approved_commands"],
        "timeout_seconds": req["timeout_seconds"],
        "transport": req["transport"],
        "execution_mode": req["execution_mode"],
        "timestamps": {
            "received_at": now,
            "started_at": now,
            "finished_at": now,
        },
        "execution_status": rp.RESPONSE_STATUS_EXECUTED,
        "raw_output": "ok",
        "stderr": "",
        "request_integrity_sha256": req["request_integrity_sha256"],
        "transport_metadata": {"target": "test"},
        "executor_identity": {"executor_id": "w1"},
        "executor_heartbeat": {
            "heartbeat_counter": 1,
            "heartbeat_timestamp": now,
            "connection_state": "connected",
        },
        "governance_verdict_chain": [rp.RuntimeExecutionState.EXECUTING.value],
        "response_integrity_sha256": "0" * 64,
    }

    ok, reason = rp.validate_response_block(response)
    assert not ok
    assert reason == "response_integrity_mismatch"


def test_protocol_schema_is_json() -> None:
    schema_path = DOCS_DIR / "runtime_protocol_schema.json"
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    assert payload["title"] == "AURA Distributed Runtime Protocol"


def test_replay_protection_hooks_present() -> None:
    adapter_path = TRANSPORT_DIR / "adapters" / "remote_serial_transport_adapter.py"
    source = adapter_path.read_text(encoding="utf-8")

    assert "duplicate_response_detected" in source
    assert "out_of_order_response_detected" in source
    assert "replayed_request_id" in source
    assert "_seen_response_hashes" in source
    assert "_completed_request_ids" in source


def test_safe_read_only_discovery_policy_hooks_present() -> None:
    discovery_path = TRANSPORT_DIR / "safe_read_only_discovery.py"
    source = discovery_path.read_text(encoding="utf-8")

    assert "SAFE_READ_ONLY_COMMANDS" in source
    assert "getprop ro.build.fingerprint" in source
    assert "cat /proc/asound/cards" in source
    assert "dmesg | tail -50" in source
    assert "not_allowlisted" in source
    assert "interactive_command_blocked" in source
    assert "forbidden_operator" in source
    assert "SAFE_READ_ONLY_DISCOVERY_ONLY" in source
