#!/usr/bin/env bash
# Phase-0 shared-folder bridge handshake (Linux governance side, fail-closed).

set -euo pipefail

BRIDGE_ROOT="${BRIDGE_ROOT:-/local/mnt/workspace/AURA_V1/bridge}"
OUTPUT_DIR="${OUTPUT_DIR:-/local/mnt/workspace/AURA_V1/docs/operations/transport}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-45}"
POLL_SECONDS="${POLL_SECONDS:-1}"
COMMAND="echo AURA_BRIDGE_PING"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/linux-bridge-handshake.sh [options]

Options:
  --bridge-root <path>      Shared bridge root (default: /local/mnt/workspace/AURA_V1/bridge)
  --output-dir <path>       Evidence output directory
  --timeout-seconds <n>     Timeout waiting for response (default: 45)
  --poll-seconds <n>        Poll interval (default: 1)
  --help                    Show help

Classification (fail-closed):
  - response_hash_mismatch -> INVALID
  - duplicate_response_hash -> BLOCKED
  - replayed_request_id -> REJECTED
  - timeout_waiting_response -> UNKNOWN
  - partial_response -> ADVISORY_ONLY
  - valid_handshake -> CONNECTED
USAGE
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
      POLL_SECONDS="$2"
      shift 2
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

REQUEST_ID="$(python3 - <<'PY'
import uuid
print(str(uuid.uuid4()))
PY
)"
SEQ_FILE="${LOGS_DIR}/linux_last_request_sequence.txt"
last_seq=0
if [[ -f "${SEQ_FILE}" ]]; then
  raw="$(cat "${SEQ_FILE}" || true)"
  if [[ "${raw}" =~ ^[0-9]+$ ]]; then
    last_seq="${raw}"
  fi
fi
REQUEST_SEQUENCE="$((last_seq + 1))"
printf "%s\n" "${REQUEST_SEQUENCE}" > "${SEQ_FILE}"

REQUEST_ID_LOG="${LOGS_DIR}/linux_seen_request_ids.txt"
touch "${REQUEST_ID_LOG}"
if grep -Fxq "${REQUEST_ID}" "${REQUEST_ID_LOG}"; then
  echo "replayed request_id: ${REQUEST_ID}" >&2
  exit 3
fi
printf "%s\n" "${REQUEST_ID}" >> "${REQUEST_ID_LOG}"

REQUEST_PATH="${REQUESTS_DIR}/${REQUEST_ID}.json"
REQUEST_TMP="${REQUEST_PATH}.tmp.$$"
RESPONSE_PATH="${RESPONSES_DIR}/${REQUEST_ID}.json"
REQUEST_COPY="${OUTPUT_DIR}/bridge_handshake_request_${REQUEST_ID}.json"
RESPONSE_COPY="${OUTPUT_DIR}/bridge_handshake_response_${REQUEST_ID}.json"
LINEAGE_PATH="${OUTPUT_DIR}/bridge_handshake_lineage_${REQUEST_ID}.json"
REPORT_PATH="${OUTPUT_DIR}/bridge_handshake_report_${REQUEST_ID}.md"

python3 - <<'PY' "${REQUEST_TMP}" "${REQUEST_ID}" "${REQUEST_SEQUENCE}" "${TIMEOUT_SECONDS}" "${COMMAND}"
import hashlib
import json
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
request_id = sys.argv[2]
request_sequence = int(sys.argv[3])
timeout_seconds = int(sys.argv[4])
command = sys.argv[5]
execution_mode = "governed_read_only"
transport = "shared_folder"

digest_input = "\n".join(
    [
        request_id,
        str(request_sequence),
        str(timeout_seconds),
        execution_mode,
        transport,
        command,
    ]
)
request_integrity = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
payload = {
    "protocol_version": "bridge-v1",
    "request_id": request_id,
    "request_sequence": request_sequence,
    "approved_commands": [command],
    "command_entries": [
        {
            "original_command": command,
            "normalized_command": command,
        }
    ],
    "timeout_seconds": timeout_seconds,
    "transport": transport,
    "execution_mode": execution_mode,
    "request_timestamp": str(time.time()),
    "request_integrity_sha256": request_integrity,
    "transport_expansion_trace": {
        "linux_emission": "canonical_target_command_only",
        "executor_expansion_rule": "adb.exe shell <normalized_command>",
        "forbidden": [
            "nested adb shell",
            "linux shell wrapper leakage",
            "transport prefix duplication",
        ],
    },
}
path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

mv "${REQUEST_TMP}" "${REQUEST_PATH}"
cp "${REQUEST_PATH}" "${REQUEST_COPY}"

start_epoch="$(date +%s)"
deadline_epoch="$((start_epoch + TIMEOUT_SECONDS))"

while [[ ! -f "${RESPONSE_PATH}" ]]; do
  now_epoch="$(date +%s)"
  if (( now_epoch >= deadline_epoch )); then
    python3 - <<'PY' "${LINEAGE_PATH}" "${REPORT_PATH}" "${REQUEST_ID}" "${REQUEST_SEQUENCE}"
import json
import sys
from pathlib import Path

lineage_path = Path(sys.argv[1])
report_path = Path(sys.argv[2])
request_id = sys.argv[3]
request_sequence = int(sys.argv[4])
lineage = {
  "request_id": request_id,
  "request_sequence": request_sequence,
  "classification": "UNKNOWN",
  "reason": "timeout_waiting_response",
  "governance_verdict_chain": ["APPROVED", "EXECUTING", "UNKNOWN"],
}
lineage_path.write_text(json.dumps(lineage, indent=2, sort_keys=True), encoding="utf-8")
report_path.write_text(
  "# Bridge Handshake Report\n\n"
  "- classification: UNKNOWN\n"
  "- reason: timeout_waiting_response\n"
  "- posture: ADVISORY_ONLY\n",
  encoding="utf-8"
)
PY
    python3 - <<'PY' "${REQUEST_ID}" "${REPORT_PATH}"
import json
import sys
print(json.dumps({
  "request_id": sys.argv[1],
  "classification": "UNKNOWN",
  "reason": "timeout_waiting_response",
  "report": sys.argv[2],
}, indent=2))
PY
    exit 4
  fi
  sleep "${POLL_SECONDS}"
done

cp "${RESPONSE_PATH}" "${RESPONSE_COPY}"

VALIDATION_JSON="$(python3 - <<'PY' "${REQUEST_COPY}" "${RESPONSE_PATH}" "${LOGS_DIR}"
import hashlib
import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
response = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
logs_dir = Path(sys.argv[3])

required = [
    "request_id",
    "request_sequence",
    "execution_status",
    "raw_output",
    "stderr",
    "timestamps",
    "request_integrity_sha256",
    "response_integrity_sha256",
]
for key in required:
    if key not in response:
        print(json.dumps({"classification": "INVALID", "reason": f"missing_field:{key}"}))
        raise SystemExit(0)

if response["request_id"] != request["request_id"]:
    print(json.dumps({"classification": "INVALID", "reason": "request_id_mismatch"}))
    raise SystemExit(0)

if int(response["request_sequence"]) != int(request["request_sequence"]):
    print(json.dumps({"classification": "INVALID", "reason": "request_sequence_mismatch"}))
    raise SystemExit(0)

if response["request_integrity_sha256"] != request["request_integrity_sha256"]:
    print(json.dumps({"classification": "INVALID", "reason": "request_integrity_mismatch"}))
    raise SystemExit(0)

finished_at = str((response.get("timestamps") or {}).get("finished_at", ""))
digest_input = "\n".join(
    [
        str(response.get("request_id", "")),
        str(response.get("request_sequence", "")),
        str(response.get("request_integrity_sha256", "")),
        str(response.get("execution_status", "")),
        str(response.get("raw_output", "")),
        str(response.get("stderr", "")),
        finished_at,
        str(response.get("transport", "")),
    ]
)
computed = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
if computed != response.get("response_integrity_sha256"):
    print(json.dumps({"classification": "INVALID", "reason": "response_hash_mismatch"}))
    raise SystemExit(0)

hash_log = logs_dir / "linux_seen_response_hashes.txt"
seen = set()
if hash_log.exists():
    seen = {line.strip() for line in hash_log.read_text(encoding="utf-8").splitlines() if line.strip()}
if computed in seen:
    print(json.dumps({"classification": "BLOCKED", "reason": "duplicate_response_hash"}))
    raise SystemExit(0)
with hash_log.open("a", encoding="utf-8") as f:
    f.write(computed + "\n")

seq_log = logs_dir / "linux_last_response_sequence.txt"
last_seq = 0
if seq_log.exists():
    raw = seq_log.read_text(encoding="utf-8").strip()
    if raw.isdigit():
        last_seq = int(raw)
if int(response["request_sequence"]) < last_seq:
    print(json.dumps({"classification": "BLOCKED", "reason": "out_of_order_response"}))
    raise SystemExit(0)
seq_log.write_text(str(int(response["request_sequence"])), encoding="utf-8")

status = str(response.get("execution_status", "")).lower()
if status in {"partial_response", "partial"}:
    print(json.dumps({"classification": "ADVISORY_ONLY", "reason": "partial_response"}))
    raise SystemExit(0)
if status in {"timeout"}:
    print(json.dumps({"classification": "UNKNOWN", "reason": "executor_timeout"}))
    raise SystemExit(0)
if status in {"transport_disconnected", "disconnect"}:
    print(json.dumps({"classification": "UNKNOWN", "reason": "transport_disconnect"}))
    raise SystemExit(0)
if status in {"rejected", "rejected_malformed_request"}:
    print(json.dumps({"classification": "REJECTED", "reason": status}))
    raise SystemExit(0)
if status in {"invalid"}:
    print(json.dumps({"classification": "INVALID", "reason": status}))
    raise SystemExit(0)
if status in {"executed", "completed"}:
    print(json.dumps({"classification": "CONNECTED", "reason": "valid_handshake"}))
    raise SystemExit(0)

print(json.dumps({"classification": "UNKNOWN", "reason": f"unrecognized_execution_status:{status}"}))
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
  "# Bridge Handshake Report\n\n"
  f"- request_id: {request['request_id']}\n"
  f"- request_sequence: {request['request_sequence']}\n"
  f"- classification: {classification}\n"
  f"- reason: {reason}\n"
  "- posture: ADVISORY_ONLY\n"
  "- runtime_parity: NOT_CLAIMED\n"
  "- behavioral_equivalence: NOT_CLAIMED\n"
  "- merge_readiness: NOT_CLAIMED\n",
  encoding="utf-8"
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
