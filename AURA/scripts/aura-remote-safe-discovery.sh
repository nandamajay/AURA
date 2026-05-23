#!/usr/bin/env bash
# Governed SAFE_READ_ONLY discovery runner (Linux/AURA governance side).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AURA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${AURA_ROOT}/.." && pwd)"
SDK_SRC="${AURA_ROOT}/workspace/aura-sdk/src"

REMOTE_HOST=""
REMOTE_PORT=54888
ADB_SERIAL=""
TIMEOUT_MS=10000
OUTPUT_DIR="${REPO_ROOT}/docs/operations/transport"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/aura-remote-safe-discovery.sh [options]

Options:
  --remote-host <host>   Remote Windows serial agent host (optional)
  --remote-port <port>   Remote Windows serial agent port (default: 54888)
  --adb-serial <serial>  Optional adb device serial
  --timeout-ms <ms>      Command timeout in milliseconds (default: 10000)
  --output-dir <path>    Evidence output directory
  --help                 Show this help

Notes:
  - This runs only SAFE_READ_ONLY discovery commands from the built-in allowlist.
  - No runtime write/mutation commands are executed by this runner.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-host)
      REMOTE_HOST="$2"
      shift 2
      ;;
    --remote-port)
      REMOTE_PORT="$2"
      shift 2
      ;;
    --adb-serial)
      ADB_SERIAL="$2"
      shift 2
      ;;
    --timeout-ms)
      TIMEOUT_MS="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

if [[ ! -d "${SDK_SRC}" ]]; then
  echo "aura-sdk source not found: ${SDK_SRC}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"

export PYTHONPATH="${SDK_SRC}:${PYTHONPATH:-}"
export AURA_REMOTE_HOST="${REMOTE_HOST}"
export AURA_REMOTE_PORT="${REMOTE_PORT}"
export AURA_ADB_SERIAL="${ADB_SERIAL}"
export AURA_TIMEOUT_MS="${TIMEOUT_MS}"
export AURA_OUTPUT_DIR="${OUTPUT_DIR}"

python3 - <<'PY'
import json
import os
from aura_sdk.transport.safe_read_only_discovery import DiscoveryConfig, SafeReadOnlyDiscoveryRunner

remote_host = os.environ.get("AURA_REMOTE_HOST", "").strip() or None
adb_serial = os.environ.get("AURA_ADB_SERIAL", "").strip() or None
remote_port = int(os.environ["AURA_REMOTE_PORT"])
timeout_ms = int(os.environ["AURA_TIMEOUT_MS"])
output_dir = os.environ["AURA_OUTPUT_DIR"]

runner = SafeReadOnlyDiscoveryRunner(
    DiscoveryConfig(
        output_dir=output_dir,
        adb_serial=adb_serial,
        remote_host=remote_host,
        remote_port=remote_port,
        timeout_ms=timeout_ms,
    )
)
evidence = runner.run()
summary = evidence.get("summary", {})
result = {
    "execution_mode": evidence.get("execution_mode"),
    "governance_posture": evidence.get("governance_posture"),
    "final_classification": summary.get("final_classification"),
    "final_status": summary.get("final_status"),
    "counts": summary.get("counts", {}),
    "output_dir": output_dir,
}
print(json.dumps(result, indent=2, sort_keys=True))
PY

echo "Evidence written to: ${OUTPUT_DIR}"

