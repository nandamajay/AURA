#!/usr/bin/env bash
# Capture deterministic dependency fingerprint for reproducibility evidence.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
OUT_DIR="${ROOT_DIR}/evidence/startup"
mkdir -p "${OUT_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
FREEZE_FILE="${OUT_DIR}/${TS}-pip-freeze.txt"
REPORT_FILE="${OUT_DIR}/${TS}-dependency-integrity.json"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[FAIL] Python not found: ${PYTHON_BIN}" >&2
  exit 1
fi

"${PYTHON_BIN}" -m pip freeze | LC_ALL=C sort > "${FREEZE_FILE}"
HASH=$(sha256sum "${FREEZE_FILE}" | awk '{print $1}')

python3 - <<'PY' "${REPORT_FILE}" "${FREEZE_FILE}" "${HASH}"
import json
import sys
from datetime import datetime, timezone

report_path, freeze_file, hash_value = sys.argv[1:4]
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "freeze_file": freeze_file,
    "sha256": hash_value,
    "status": "pass",
}
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
print(report_path)
PY

echo "[PASS] dependency fingerprint captured"
echo "       freeze: ${FREEZE_FILE}"
echo "       report: ${REPORT_FILE}"
