"""Windows-hosted serial agent entrypoint for distributed transport bridging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aura_sdk.transport.runtime_serial_executor import RuntimeSerialExecutor, SerialAgentConfig
from aura_sdk.transport.tcp_runtime_bridge import TcpRuntimeBridge


def _load_config(path: str | Path) -> SerialAgentConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("serial_agent_config_must_be_json_object")
    return SerialAgentConfig(
        com_port=str(payload.get("com_port", "COM5")),
        baudrate=int(payload.get("baudrate", 115200)),
        timeout_seconds=int(payload.get("timeout_seconds", 10)),
        prompt_regex=str(payload.get("prompt_regex", r"root@.*[#$]")),
        reconnect_policy=str(payload.get("reconnect_policy", "fail_closed")),
    )


def _build_bridge(executor: RuntimeSerialExecutor) -> TcpRuntimeBridge:
    def _execute(request: dict[str, object]) -> dict[str, object]:
        return executor.execute_request_block(request)

    return TcpRuntimeBridge(_execute)


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA Windows Serial Agent")
    parser.add_argument("--config", required=True, help="Path to serial_agent_config.json")
    parser.add_argument("--host", default="0.0.0.0", help="TCP bind host")
    parser.add_argument("--port", type=int, default=54888, help="TCP bind port")
    parser.add_argument(
        "--log",
        default="windows_serial_agent_execution.jsonl",
        help="Evidence log path",
    )
    args = parser.parse_args()

    config = _load_config(args.config)
    executor = RuntimeSerialExecutor(config, evidence_log_path=args.log)
    bridge = _build_bridge(executor)

    try:
        bridge.serve_forever(args.host, args.port)
    finally:
        executor.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
