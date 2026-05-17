#!/usr/bin/env bash
# AURA Compliance Export Script
# Usage: ./scripts/compliance-export.sh

set -euo pipefail

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="aura-core"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
EXPORT_ROOT="${AURA_DIR}/data/exports"
OUTPUT_DIR="${EXPORT_ROOT}/compliance_${TIMESTAMP}"
ARCHIVE_PATH="${OUTPUT_DIR}.tar.gz"
CONTAINER_OUT="/tmp/aura_compliance_${TIMESTAMP}"

cleanup() {
    docker compose exec -T "${SERVICE_NAME}" python - "${CONTAINER_OUT}" <<'PY' >/dev/null 2>&1 || true
import shutil
import sys

path = sys.argv[1]
shutil.rmtree(path, ignore_errors=True)
PY
}
trap cleanup EXIT

mkdir -p "${EXPORT_ROOT}" "${OUTPUT_DIR}"

if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE_NAME}"; then
    echo "ERROR: ${SERVICE_NAME} is not running."
    echo "Start stack first: make up"
    exit 1
fi

echo "AURA Compliance Export"
echo "======================"
echo "Service: ${SERVICE_NAME}"
echo "Output:  ${OUTPUT_DIR}"
echo ""

docker compose exec -T "${SERVICE_NAME}" python - "${CONTAINER_OUT}" <<'PY'
import csv
import json
import os
import sqlite3
import sys
from datetime import datetime, UTC

output_dir = sys.argv[1]
os.makedirs(output_dir, exist_ok=True)

conn = sqlite3.connect("/data/aura.db")
tables = [
    "audit_ledger",
    "users",
    "approvals",
    "patches",
    "tasks",
]

counts: dict[str, int] = {}
missing: list[str] = []

for table in tables:
    try:
        cur = conn.execute(f"SELECT * FROM {table}")
    except sqlite3.Error:
        missing.append(table)
        continue

    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    counts[table] = len(rows)
    csv_path = os.path.join(output_dir, f"{table}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        writer.writerows(rows)

conn.close()

summary = {
    "generated_at": datetime.now(UTC).isoformat(),
    "tables_exported": sorted(counts.keys()),
    "table_counts": counts,
    "missing_tables": missing,
}
with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2, sort_keys=True)

with open(os.path.join(output_dir, "report.txt"), "w", encoding="utf-8") as fh:
    fh.write("AURA Compliance Report\n")
    fh.write(f"Generated: {summary['generated_at']}\n\n")
    for table in tables:
        if table in counts:
            fh.write(f"{table}: {counts[table]} rows\n")
        else:
            fh.write(f"{table}: MISSING\n")
PY

docker cp "${SERVICE_NAME}:${CONTAINER_OUT}/." "${OUTPUT_DIR}/"

find "${OUTPUT_DIR}" -type f -exec chmod 600 {} \;

tar -czf "${ARCHIVE_PATH}" -C "${EXPORT_ROOT}" "$(basename "${OUTPUT_DIR}")"
chmod 600 "${ARCHIVE_PATH}"

echo "Export complete:"
echo "  Directory: ${OUTPUT_DIR}"
echo "  Archive:   ${ARCHIVE_PATH}"
