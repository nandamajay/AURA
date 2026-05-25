#!/usr/bin/env bash
# Linux authoritative governance submitter for shared-folder Windows worker bridge.
# Fail-closed, normalization-first.

set -euo pipefail

BRIDGE_ROOT="${BRIDGE_ROOT:-/local/mnt/workspace/AURA_V1/bridge}"
OUTPUT_DIR="${OUTPUT_DIR:-/local/mnt/workspace/AURA_V1/docs/operations/transport}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-45}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-1}"
MAX_STDOUT_BYTES="${MAX_STDOUT_BYTES:-131072}"
MAX_STDERR_BYTES="${MAX_STDERR_BYTES:-32768}"
ALLOW_WRITE_OPS="${ALLOW_WRITE_OPS:-0}"
EXECUTION_MODE="${EXECUTION_MODE:-governed_read_only}"
REQUEST_ID=""
REQUEST_SEQUENCE=""

REQUESTS_DIR=""
RESPONSES_DIR=""
DELIVERED_DIR=""
LOGS_DIR=""

declare -a COMMANDS=()
declare -a DEFAULT_SAFE_COMMANDS=(
  "getprop ro.build.fingerprint"
  "cat /proc/version"
  "cat /proc/asound/cards"
)

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/linux-bridge-submit.sh [options]

Options:
  --bridge-root <path>        Shared bridge root (default: /local/mnt/workspace/AURA_V1/bridge)
  --output-dir <path>         Output evidence directory
  --timeout-seconds <n>       Response wait timeout (default: 45)
  --poll-seconds <n>          Poll interval (default: 1)
  --request-id <id>           Optional explicit request_id
  --request-sequence <n>      Optional explicit request sequence
  --command "<cmd>"           Add approved command (repeatable)
  --commands-file <file>      File containing one approved command per line
  --execution-mode <mode>     governed_read_only | governed_write_approved
  --allow-write-ops           Allow governed write operations (e.g., AURA_ADB_PUSH)
  --help                      Show help

Notes:
  - Linux emits canonical target commands only.
  - Windows worker must expand to adb.exe shell <normalized_command>.
USAGE
}

append_commands_from_file() {
  local file_path="$1"
  if [[ ! -f "${file_path}" ]]; then
    echo "commands file not found: ${file_path}" >&2
    exit 2
  fi
  while IFS= read -r line; do
    local stripped="${line#"${line%%[![:space:]]*}"}"
    stripped="${stripped%"${stripped##*[![:space:]]}"}"
    [[ -z "${stripped}" ]] && continue
    [[ "${stripped}" == \#* ]] && continue
    COMMANDS+=("${stripped}")
  done < "${file_path}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bridge-root)
      BRIDGE_ROOT="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --timeout-seconds)
      TIMEOUT_SECONDS="$2"
      shift 2
      ;;
    --poll-seconds)
      POLL_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --request-id)
      REQUEST_ID="$2"
      shift 2
      ;;
    --request-sequence)
      REQUEST_SEQUENCE="$2"
      shift 2
      ;;
    --command)
      COMMANDS+=("$2")
      shift 2
      ;;
    --commands-file)
      append_commands_from_file "$2"
      shift 2
      ;;
    --execution-mode)
      EXECUTION_MODE="$2"
      shift 2
      ;;
    --allow-write-ops)
      ALLOW_WRITE_OPS="1"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required" >&2
  exit 1
fi

REQUESTS_DIR="${BRIDGE_ROOT}/requests"
RESPONSES_DIR="${BRIDGE_ROOT}/responses"
DELIVERED_DIR="${BRIDGE_ROOT}/delivered"
LOGS_DIR="${BRIDGE_ROOT}/logs"
mkdir -p "${REQUESTS_DIR}" "${RESPONSES_DIR}" "${DELIVERED_DIR}" "${LOGS_DIR}" "${OUTPUT_DIR}"

if [[ ${#COMMANDS[@]} -eq 0 ]]; then
  COMMANDS=("${DEFAULT_SAFE_COMMANDS[@]}")
fi

if [[ -z "${REQUEST_ID}" ]]; then
  REQUEST_ID="$(python3 - <<'PY'
import uuid
print(str(uuid.uuid4()))
PY
)"
fi

if [[ -z "${REQUEST_SEQUENCE}" ]]; then
  SEQ_FILE="${LOGS_DIR}/linux_last_request_sequence.txt"
  last_seq=0
  if [[ -f "${SEQ_FILE}" ]]; then
    raw="$(cat "${SEQ_FILE}" 2>/dev/null || echo 0)"
    if [[ "${raw}" =~ ^[0-9]+$ ]]; then
      last_seq="${raw}"
    fi
  fi
  REQUEST_SEQUENCE="$((last_seq + 1))"
  printf "%s\n" "${REQUEST_SEQUENCE}" > "${SEQ_FILE}"
fi

if [[ "${EXECUTION_MODE}" != "governed_read_only" && "${EXECUTION_MODE}" != "governed_write_approved" ]]; then
  echo "invalid execution mode: ${EXECUTION_MODE}" >&2
  exit 2
fi
if [[ "${ALLOW_WRITE_OPS}" == "1" && "${EXECUTION_MODE}" != "governed_write_approved" ]]; then
  echo "allow-write-ops requires --execution-mode governed_write_approved" >&2
  exit 2
fi
if [[ "${ALLOW_WRITE_OPS}" != "1" && "${EXECUTION_MODE}" == "governed_write_approved" ]]; then
  echo "governed_write_approved requires --allow-write-ops" >&2
  exit 2
fi

REQUEST_ID_LOG="${LOGS_DIR}/linux_seen_request_ids.txt"
touch "${REQUEST_ID_LOG}"
if grep -Fxq "${REQUEST_ID}" "${REQUEST_ID_LOG}"; then
  python3 - <<'PY' "${REQUEST_ID}" "${BRIDGE_ROOT}"
import json, sys
print(json.dumps({
  "request_id": sys.argv[1],
  "classification": "REJECTED",
  "reason": "replayed_request_id",
  "bridge_root": sys.argv[2],
}, indent=2))
PY
  exit 3
fi

export AURA_ALLOW_WRITE_OPS="${ALLOW_WRITE_OPS}"
NORMALIZATION_JSON="$(python3 - <<'PY' "${COMMANDS[@]}"
import json
import re
import sys
import os
import base64
import binascii

allowlist = {
    "echo AURA_BRIDGE_PING",
    "getprop ro.build.fingerprint",
    "logcat -d -t 200",
    "dumpsys media.audio_flinger",
    "cat /proc/version",
    "cat /proc/asound/cards",
    "cat /proc/asound/pcm",
    "cat /proc/interrupts",
    "cat /proc/interrupts | head -200",
    "cat /proc/cpuinfo",
    "uname -a",
    "dmesg",
    "dmesg | tail -200",
    "lsmod",
    "tinymix",
    "amixer",
    "ls /sys/kernel/debug",
    "ls /sys/kernel/debug/asoc",
    "cat /sys/kernel/debug/asoc/*/dapm",
    "systemctl --version",
}
allow_write_ops = os.environ.get("AURA_ALLOW_WRITE_OPS", "0") == "1"
push_command_prefix = "AURA_ADB_PUSH "
playback_aplay_prefix = "AURA_PLAYBACK_APLAY "
playback_tinyplay_prefix = "AURA_PLAYBACK_TINYPLAY "
tinymix_set_prefix = "AURA_TINYMIX_SET "
amixer_cset_prefix = "AURA_AMIXER_CSET "
amixer_name_set_prefix = "AURA_AMIXER_NAME_SET "
cleanup_prefix = "AURA_ADB_RM "
forbidden_tokens = [";", "&&", "||", "`", "$(", ">", "<", "\n", "\r"]
forbidden_prefixes = (
    "adb ",
    "adb.exe",
    "shell ",
    "sh -c",
    "bash -c",
    "cmd /c",
    "powershell",
)

def normalize(command: str) -> str:
    return " ".join(command.strip().split())

entries = []
for original in sys.argv[1:]:
    normalized = normalize(original)
    if not normalized:
        print(json.dumps({"ok": False, "reason": "empty_command_after_normalization"}))
        raise SystemExit(0)

    lowered = normalized.lower()
    if any(token in normalized for token in forbidden_tokens):
        print(json.dumps({"ok": False, "reason": "forbidden_operator_or_token"}))
        raise SystemExit(0)
    if lowered.startswith(forbidden_prefixes):
        print(json.dumps({"ok": False, "reason": "forbidden_transport_or_shell_prefix"}))
        raise SystemExit(0)
    if " adb " in f" {lowered} ":
        print(json.dumps({"ok": False, "reason": "nested_adb_reference_blocked"}))
        raise SystemExit(0)
    if normalized.startswith(push_command_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 5:
            print(json.dumps({"ok": False, "reason": "asset_push_format_invalid"}))
            raise SystemExit(0)
        source_rel, target_path, expected_sha256, overwrite_policy = parts[1], parts[2], parts[3], parts[4]
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", source_rel) or ".." in source_rel.split("/"):
            print(json.dumps({"ok": False, "reason": "asset_push_source_invalid"}))
            raise SystemExit(0)
        if not re.fullmatch(r"/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+", target_path):
            print(json.dumps({"ok": False, "reason": "asset_push_target_invalid"}))
            raise SystemExit(0)
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            print(json.dumps({"ok": False, "reason": "asset_push_sha256_invalid"}))
            raise SystemExit(0)
        if overwrite_policy not in {"no_overwrite", "allow_overwrite"}:
            print(json.dumps({"ok": False, "reason": "asset_push_overwrite_policy_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(playback_aplay_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 3:
            print(json.dumps({"ok": False, "reason": "playback_aplay_format_invalid"}))
            raise SystemExit(0)
        alsa_device, target_path = parts[1], parts[2]
        if not re.fullmatch(r"(hw|plughw):\d+,\d+", alsa_device):
            print(json.dumps({"ok": False, "reason": "playback_aplay_device_invalid"}))
            raise SystemExit(0)
        if not re.fullmatch(r"/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+", target_path):
            print(json.dumps({"ok": False, "reason": "playback_aplay_target_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(playback_tinyplay_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 4:
            print(json.dumps({"ok": False, "reason": "playback_tinyplay_format_invalid"}))
            raise SystemExit(0)
        target_path, card, device = parts[1], parts[2], parts[3]
        if not re.fullmatch(r"/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+", target_path):
            print(json.dumps({"ok": False, "reason": "playback_tinyplay_target_invalid"}))
            raise SystemExit(0)
        if not card.isdigit() or not device.isdigit():
            print(json.dumps({"ok": False, "reason": "playback_tinyplay_card_or_device_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(tinymix_set_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 3:
            print(json.dumps({"ok": False, "reason": "tinymix_set_format_invalid"}))
            raise SystemExit(0)
        control_id, value = parts[1], parts[2]
        if not control_id.isdigit() or not re.fullmatch(r"-?\d+", value):
            print(json.dumps({"ok": False, "reason": "tinymix_set_value_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(amixer_cset_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 3:
            print(json.dumps({"ok": False, "reason": "amixer_cset_format_invalid"}))
            raise SystemExit(0)
        numid, value = parts[1], parts[2]
        if not re.fullmatch(r"numid=\d+", numid) or not re.fullmatch(r"[A-Za-z0-9_+.,-]+", value):
            print(json.dumps({"ok": False, "reason": "amixer_cset_value_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(amixer_name_set_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 3:
            print(json.dumps({"ok": False, "reason": "amixer_name_set_format_invalid"}))
            raise SystemExit(0)
        encoded_name, value = parts[1], parts[2]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", encoded_name):
            print(json.dumps({"ok": False, "reason": "amixer_name_set_name_encoding_invalid"}))
            raise SystemExit(0)
        if not re.fullmatch(r"[A-Za-z0-9_+.,-]+", value):
            print(json.dumps({"ok": False, "reason": "amixer_name_set_value_invalid"}))
            raise SystemExit(0)
        padding = "=" * ((4 - (len(encoded_name) % 4)) % 4)
        try:
            decoded_name = base64.urlsafe_b64decode((encoded_name + padding).encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            print(json.dumps({"ok": False, "reason": "amixer_name_set_name_decode_invalid"}))
            raise SystemExit(0)
        if not re.fullmatch(r"[A-Za-z0-9 _+./-]+", decoded_name):
            print(json.dumps({"ok": False, "reason": "amixer_name_set_name_invalid"}))
            raise SystemExit(0)
    elif normalized.startswith(cleanup_prefix):
        if not allow_write_ops:
            print(json.dumps({"ok": False, "reason": "write_ops_not_enabled"}))
            raise SystemExit(0)
        parts = normalized.split()
        if len(parts) != 2:
            print(json.dumps({"ok": False, "reason": "cleanup_format_invalid"}))
            raise SystemExit(0)
        target_path = parts[1]
        if not re.fullmatch(r"/data/local/tmp/aura/audio/[A-Za-z0-9._/-]+", target_path):
            print(json.dumps({"ok": False, "reason": "cleanup_target_invalid"}))
            raise SystemExit(0)
    elif normalized not in allowlist:
        print(json.dumps({"ok": False, "reason": f"allowlist_violation:{normalized}"}))
        raise SystemExit(0)

    entries.append({
        "original_command": original,
        "normalized_command": normalized,
    })

print(json.dumps({
    "ok": True,
    "normalized": [e["normalized_command"] for e in entries],
    "entries": entries,
    "transport_expansion_trace": {
        "linux_emission": "canonical_target_command_only",
        "executor_expansion_rule": "adb.exe shell <normalized_command>",
        "forbidden": [
            "nested adb shell",
            "linux shell wrapper leakage",
            "transport prefix duplication",
        ],
    },
}))
PY
)"

NORMALIZATION_OK="$(python3 - <<'PY' "${NORMALIZATION_JSON}"
import json, sys
print(str(json.loads(sys.argv[1]).get("ok", False)).lower())
PY
)"

if [[ "${NORMALIZATION_OK}" != "true" ]]; then
  reason="$(python3 - <<'PY' "${NORMALIZATION_JSON}"
import json, sys
print(json.loads(sys.argv[1]).get("reason", "normalization_failed"))
PY
)"
  python3 - <<'PY' "${REQUEST_ID}" "${reason}" "${BRIDGE_ROOT}"
import json, sys
print(json.dumps({
  "request_id": sys.argv[1],
  "classification": "REJECTED",
  "reason": sys.argv[2],
  "bridge_root": sys.argv[3],
}, indent=2))
PY
  exit 5
fi

NORMALIZED_COMMANDS_JSON="$(python3 - <<'PY' "${NORMALIZATION_JSON}"
import json, sys
print(json.dumps(json.loads(sys.argv[1])["normalized"]))
PY
)"
COMMAND_ENTRIES_JSON="$(python3 - <<'PY' "${NORMALIZATION_JSON}"
import json, sys
print(json.dumps(json.loads(sys.argv[1])["entries"]))
PY
)"
TRANSPORT_EXPANSION_TRACE_JSON="$(python3 - <<'PY' "${NORMALIZATION_JSON}"
import json, sys
print(json.dumps(json.loads(sys.argv[1])["transport_expansion_trace"]))
PY
)"

REQUEST_PATH="${REQUESTS_DIR}/${REQUEST_ID}.json"
REQUEST_TMP="${REQUEST_PATH}.tmp.$$"
RESPONSE_PATH="${RESPONSES_DIR}/${REQUEST_ID}.json"
REQUEST_COPY="${OUTPUT_DIR}/bridge_request_${REQUEST_ID}.json"
RESPONSE_COPY="${OUTPUT_DIR}/bridge_response_${REQUEST_ID}.json"
LINEAGE_PATH="${OUTPUT_DIR}/bridge_lineage_${REQUEST_ID}.json"
REPORT_PATH="${OUTPUT_DIR}/bridge_execution_report_${REQUEST_ID}.md"

export BRIDGE_REQUEST_ID="${REQUEST_ID}"
export BRIDGE_REQUEST_SEQUENCE="${REQUEST_SEQUENCE}"
export BRIDGE_TIMEOUT_SECONDS="${TIMEOUT_SECONDS}"
export BRIDGE_EXECUTION_MODE="${EXECUTION_MODE}"
export BRIDGE_COMMANDS_JSON="${NORMALIZED_COMMANDS_JSON}"
export BRIDGE_COMMAND_ENTRIES_JSON="${COMMAND_ENTRIES_JSON}"
export BRIDGE_TRANSPORT_EXPANSION_TRACE_JSON="${TRANSPORT_EXPANSION_TRACE_JSON}"

python3 - <<'PY' "${REQUEST_TMP}"
import hashlib
import json
import os
import time
from pathlib import Path

path = Path(__import__("sys").argv[1])
request_id = os.environ["BRIDGE_REQUEST_ID"]
request_sequence = int(os.environ["BRIDGE_REQUEST_SEQUENCE"])
timeout_seconds = int(os.environ["BRIDGE_TIMEOUT_SECONDS"])
approved_commands = json.loads(os.environ["BRIDGE_COMMANDS_JSON"])
command_entries = json.loads(os.environ["BRIDGE_COMMAND_ENTRIES_JSON"])
transport_expansion_trace = json.loads(os.environ["BRIDGE_TRANSPORT_EXPANSION_TRACE_JSON"])
execution_mode = os.environ["BRIDGE_EXECUTION_MODE"]
transport = "shared_folder"
request_timestamp = str(time.time())

digest_input = "\n".join([
    request_id,
    str(request_sequence),
    str(timeout_seconds),
    execution_mode,
    transport,
    *approved_commands,
])
request_integrity = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

payload = {
    "protocol_version": "bridge-v1",
    "request_id": request_id,
    "request_sequence": request_sequence,
    "approved_commands": approved_commands,
    "command_entries": command_entries,
    "timeout_seconds": timeout_seconds,
    "transport": transport,
    "execution_mode": execution_mode,
    "request_timestamp": request_timestamp,
    "request_integrity_sha256": request_integrity,
    "transport_expansion_trace": transport_expansion_trace,
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

mv "${REQUEST_TMP}" "${REQUEST_PATH}"
printf "%s\n" "${REQUEST_ID}" >> "${REQUEST_ID_LOG}"
cp "${REQUEST_PATH}" "${REQUEST_COPY}"

started_epoch="$(date +%s)"
deadline_epoch="$((started_epoch + TIMEOUT_SECONDS))"

while [[ ! -f "${RESPONSE_PATH}" ]]; do
  now_epoch="$(date +%s)"
  if (( now_epoch >= deadline_epoch )); then
    python3 - <<'PY' "${LINEAGE_PATH}" "${REPORT_PATH}" "${REQUEST_ID}" "${REQUEST_SEQUENCE}" "${BRIDGE_ROOT}" "${REQUEST_COPY}" "${RESPONSE_PATH}"
import json
import sys
from pathlib import Path

lineage = {
    "request_id": sys.argv[3],
    "request_sequence": int(sys.argv[4]),
    "classification": "UNKNOWN",
    "reason": "timeout_waiting_response",
    "bridge_root": sys.argv[5],
    "request_path": sys.argv[6],
    "response_path": sys.argv[7],
}
Path(sys.argv[1]).write_text(json.dumps(lineage, indent=2, sort_keys=True), encoding="utf-8")
Path(sys.argv[2]).write_text(
    "# Bridge Execution Report\n\n"
    f"- request_id: {sys.argv[3]}\n"
    "- classification: UNKNOWN\n"
    "- reason: timeout_waiting_response\n"
    "- posture: ADVISORY_ONLY\n",
    encoding="utf-8",
)
PY
    python3 - <<'PY' "${REQUEST_ID}" "${REPORT_PATH}"
import json, sys
print(json.dumps({
    "request_id": sys.argv[1],
    "classification": "UNKNOWN",
    "reason": "timeout_waiting_response",
    "report": sys.argv[2],
}, indent=2))
PY
    exit 4
  fi
  sleep "${POLL_INTERVAL_SECONDS}"
done

cp "${RESPONSE_PATH}" "${RESPONSE_COPY}"

VALIDATION_JSON="$(python3 - <<'PY' "${REQUEST_COPY}" "${RESPONSE_PATH}" "${LOGS_DIR}" "${MAX_STDOUT_BYTES}" "${MAX_STDERR_BYTES}"
import hashlib
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
response = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
logs_dir = Path(sys.argv[3])
max_stdout_bytes = int(sys.argv[4])
max_stderr_bytes = int(sys.argv[5])

def classify(c, r):
    return {"classification": c, "reason": r}

required_fields = [
    "request_id",
    "request_sequence",
    "execution_status",
    "raw_output",
    "stderr",
    "timestamps",
    "request_integrity_sha256",
    "response_integrity_sha256",
    "executor_command_trace",
    "transport_expansion_trace",
    "raw_executor_invocation",
]
for field in required_fields:
    if field not in response:
        print(json.dumps(classify("INVALID", f"missing_field:{field}")))
        raise SystemExit(0)

if response.get("request_id") != request.get("request_id"):
    print(json.dumps(classify("INVALID", "request_id_mismatch")))
    raise SystemExit(0)

if int(response.get("request_sequence", -1)) != int(request.get("request_sequence", -2)):
    print(json.dumps(classify("INVALID", "request_sequence_mismatch")))
    raise SystemExit(0)

if response.get("request_integrity_sha256") != request.get("request_integrity_sha256"):
    print(json.dumps(classify("INVALID", "request_integrity_mismatch")))
    raise SystemExit(0)

response_digest_input = "\n".join([
    str(response.get("request_id", "")),
    str(response.get("request_sequence", "")),
    str(response.get("request_integrity_sha256", "")),
    str(response.get("execution_status", "")),
    str(response.get("raw_output", "")),
    str(response.get("stderr", "")),
    str((response.get("timestamps") or {}).get("finished_at", "")),
    str(response.get("transport", "")),
])
computed_response_hash = hashlib.sha256(response_digest_input.encode("utf-8")).hexdigest()
if computed_response_hash != response.get("response_integrity_sha256"):
    print(json.dumps(classify("INVALID", "response_hash_mismatch")))
    raise SystemExit(0)

seen_hashes_file = logs_dir / "linux_seen_response_hashes.txt"
seen_hashes_file.parent.mkdir(parents=True, exist_ok=True)
if seen_hashes_file.exists():
    seen_hashes = set(line.strip() for line in seen_hashes_file.read_text(encoding="utf-8").splitlines() if line.strip())
else:
    seen_hashes = set()
if computed_response_hash in seen_hashes:
    print(json.dumps(classify("BLOCKED", "duplicate_response_hash")))
    raise SystemExit(0)
with seen_hashes_file.open("a", encoding="utf-8") as f:
    f.write(computed_response_hash + "\n")

last_seq_file = logs_dir / "linux_last_response_sequence.txt"
last_seq = 0
if last_seq_file.exists():
    raw = last_seq_file.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        last_seq = int(raw)
current_seq = int(response.get("request_sequence", 0))
if current_seq < last_seq:
    print(json.dumps(classify("BLOCKED", "out_of_order_response")))
    raise SystemExit(0)
last_seq_file.write_text(str(current_seq), encoding="utf-8")

stdout_bytes = len(str(response.get("raw_output", "")).encode("utf-8"))
stderr_bytes = len(str(response.get("stderr", "")).encode("utf-8"))
if stdout_bytes > max_stdout_bytes or stderr_bytes > max_stderr_bytes:
    print(json.dumps(classify("ADVISORY_ONLY", "oversized_output")))
    raise SystemExit(0)

trace = response.get("executor_command_trace")
if not isinstance(trace, list):
    print(json.dumps(classify("INVALID", "executor_command_trace_invalid")))
    raise SystemExit(0)
expected = request.get("approved_commands", [])
if len(trace) != len(expected):
    print(json.dumps(classify("INVALID", "executor_command_trace_length_mismatch")))
    raise SystemExit(0)

nonzero = []
for idx, item in enumerate(trace):
    if not isinstance(item, dict):
        print(json.dumps(classify("INVALID", "executor_command_trace_item_invalid")))
        raise SystemExit(0)
    cmd = item.get("normalized_command")
    if cmd != expected[idx]:
        print(json.dumps(classify("INVALID", "normalized_command_mismatch")))
        raise SystemExit(0)
    if "raw_executor_invocation" not in item:
        print(json.dumps(classify("INVALID", "raw_executor_invocation_missing")))
        raise SystemExit(0)
    if "exit_code" not in item:
        print(json.dumps(classify("INVALID", "exit_code_missing")))
        raise SystemExit(0)
    try:
        ec = int(item.get("exit_code"))
    except Exception:
        print(json.dumps(classify("INVALID", "exit_code_not_int")))
        raise SystemExit(0)
    if ec != 0:
        nonzero.append({"command": cmd, "exit_code": ec})

status = str(response.get("execution_status", "")).lower()
if status in {"transport_disconnected", "disconnect"}:
    print(json.dumps(classify("UNKNOWN", "transport_disconnect")))
    raise SystemExit(0)
if status in {"partial_response", "partial"}:
    print(json.dumps(classify("ADVISORY_ONLY", "partial_response")))
    raise SystemExit(0)
if status in {"timeout"}:
    print(json.dumps(classify("UNKNOWN", "executor_timeout")))
    raise SystemExit(0)
if status in {"rejected_malformed_request", "rejected"}:
    print(json.dumps(classify("REJECTED", status)))
    raise SystemExit(0)
if status in {"invalid"}:
    print(json.dumps(classify("INVALID", status)))
    raise SystemExit(0)
if status in {"failed"}:
    if nonzero:
        print(json.dumps(classify("ADVISORY_ONLY", "nonzero_exit_code")))
    else:
        print(json.dumps(classify("ADVISORY_ONLY", "executor_failed")))
    raise SystemExit(0)
if status in {"executed", "completed"}:
    if nonzero:
        print(json.dumps(classify("ADVISORY_ONLY", "nonzero_exit_code")))
    else:
        print(json.dumps(classify("CAPTURE_READY", "response_validated")))
    raise SystemExit(0)

print(json.dumps(classify("UNKNOWN", f"unrecognized_execution_status:{status}")))
PY
)"

CLASSIFICATION="$(python3 - <<'PY' "${VALIDATION_JSON}"
import json, sys
print(json.loads(sys.argv[1])["classification"])
PY
)"
REASON="$(python3 - <<'PY' "${VALIDATION_JSON}"
import json, sys
print(json.loads(sys.argv[1])["reason"])
PY
)"

python3 - <<'PY' "${LINEAGE_PATH}" "${REPORT_PATH}" "${REQUEST_COPY}" "${RESPONSE_PATH}" "${CLASSIFICATION}" "${REASON}"
import json
import sys
from pathlib import Path

lineage_path = Path(sys.argv[1])
report_path = Path(sys.argv[2])
request = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
response = json.loads(Path(sys.argv[4]).read_text(encoding="utf-8"))
classification = sys.argv[5]
reason = sys.argv[6]
lineage = {
    "request_id": request["request_id"],
    "request_sequence": request["request_sequence"],
    "classification": classification,
    "reason": reason,
    "request": request,
    "response": response,
    "governance_verdict_chain": ["APPROVED", "EXECUTING", classification],
}
lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True), encoding="utf-8")
report_path.write_text(
    "# Bridge Execution Report\n\n"
    f"- request_id: {request['request_id']}\n"
    f"- request_sequence: {request['request_sequence']}\n"
    f"- classification: {classification}\n"
    f"- reason: {reason}\n"
    "- posture: ADVISORY_ONLY\n"
    "- runtime_parity: NOT_CLAIMED\n"
    "- behavioral_equivalence: NOT_CLAIMED\n"
    "- merge_readiness: NOT_CLAIMED\n",
    encoding="utf-8",
)
PY

python3 - <<'PY' "${REQUEST_ID}" "${REQUEST_SEQUENCE}" "${CLASSIFICATION}" "${REASON}" "${REQUEST_COPY}" "${RESPONSE_COPY}" "${LINEAGE_PATH}" "${REPORT_PATH}"
import json
import sys
print(json.dumps({
    "request_id": sys.argv[1],
    "request_sequence": int(sys.argv[2]),
    "classification": sys.argv[3],
    "reason": sys.argv[4],
    "request": sys.argv[5],
    "response": sys.argv[6],
    "lineage": sys.argv[7],
    "report": sys.argv[8],
}, indent=2))
PY
