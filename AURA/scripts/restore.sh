#!/usr/bin/env bash
# AURA Restore Script — restore SQLite from compressed backup
# Usage: ./scripts/restore.sh <backup_file_or_name>

set -euo pipefail

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AURA_DIR}/data/backups"
SERVICE_NAME="aura-core"

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup_file_or_name>"
    echo "Example: $0 aura_backup_20260515_201500.db.gz"
    exit 1
fi

INPUT_BACKUP="$1"
if [[ "${INPUT_BACKUP}" = /* ]]; then
    BACKUP_FILE="${INPUT_BACKUP}"
elif [ -f "${INPUT_BACKUP}" ]; then
    BACKUP_FILE="$(cd "$(dirname "${INPUT_BACKUP}")" && pwd)/$(basename "${INPUT_BACKUP}")"
else
    BACKUP_FILE="${BACKUP_DIR}/${INPUT_BACKUP}"
fi

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file not found: ${BACKUP_FILE}"
    echo ""
    echo "Available backups:"
    ls -1 "${BACKUP_DIR}"/*.db.gz 2>/dev/null || echo "  (none)"
    exit 1
fi

mkdir -p "${AURA_DIR}/data" "${BACKUP_DIR}"

TMP_DIR="$(mktemp -d "${AURA_DIR}/data/.aura_restore_tmp_XXXXXX")"
TMP_DB="${TMP_DIR}/restore.db"
TMP_EMPTY="${TMP_DIR}/empty"

cleanup() {
    rm -rf "${TMP_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

echo "AURA Database Restore"
echo "====================="
echo "Backup source: ${BACKUP_FILE}"
echo ""

gunzip -c "${BACKUP_FILE}" > "${TMP_DB}"

python - "${TMP_DB}" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
conn = sqlite3.connect(path)
result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
conn.close()
if str(result).lower() != "ok":
    raise SystemExit(f"restore source integrity check failed: {result}")
PY

PRE_RESTORE_NAME="aura_pre_restore_$(date +"%Y%m%d_%H%M%S").db"
PRE_RESTORE_HOST="${BACKUP_DIR}/${PRE_RESTORE_NAME}"
PRE_RESTORE_CONTAINER="/tmp/${PRE_RESTORE_NAME}"

echo "Creating pre-restore snapshot: ${PRE_RESTORE_HOST}.gz"
docker compose exec -T "${SERVICE_NAME}" python - "${PRE_RESTORE_CONTAINER}" <<'PY'
import sqlite3
import sys

dst_path = sys.argv[1]
source = sqlite3.connect("/data/aura.db", timeout=30)
target = sqlite3.connect(dst_path)

with target:
    source.backup(target)

integrity = target.execute("PRAGMA integrity_check;").fetchone()[0]
target.close()
source.close()

if str(integrity).lower() != "ok":
    raise SystemExit(f"pre-restore snapshot integrity check failed: {integrity}")
PY
docker cp "${SERVICE_NAME}:${PRE_RESTORE_CONTAINER}" "${PRE_RESTORE_HOST}"
docker compose exec -T "${SERVICE_NAME}" python - "${PRE_RESTORE_CONTAINER}" <<'PY'
import os
import sys

path = sys.argv[1]
try:
    os.remove(path)
except FileNotFoundError:
    pass
PY
chmod 600 "${PRE_RESTORE_HOST}"
gzip -f "${PRE_RESTORE_HOST}"
chmod 600 "${PRE_RESTORE_HOST}.gz"

echo "Stopping ${SERVICE_NAME}..."
docker compose stop "${SERVICE_NAME}" >/dev/null

docker cp "${TMP_DB}" "${SERVICE_NAME}:/data/aura.db"
: > "${TMP_EMPTY}"
docker cp "${TMP_EMPTY}" "${SERVICE_NAME}:/data/aura.db-wal"
docker cp "${TMP_EMPTY}" "${SERVICE_NAME}:/data/aura.db-shm"

echo "Starting ${SERVICE_NAME}..."
docker compose start "${SERVICE_NAME}" >/dev/null

echo "Waiting for health check..."
for _ in $(seq 1 60); do
    if curl -sf "http://localhost:8000/health/ready" >/dev/null; then
        break
    fi
    sleep 1
done

if ! curl -sf "http://localhost:8000/health/ready" >/dev/null; then
    echo "ERROR: ${SERVICE_NAME} did not become healthy after restore."
    exit 1
fi

docker compose exec -T "${SERVICE_NAME}" python - <<'PY'
import sqlite3

conn = sqlite3.connect("/data/aura.db")
result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
conn.close()
if str(result).lower() != "ok":
    raise SystemExit(f"post-restore integrity check failed: {result}")
PY

echo "Restore complete."
echo "Pre-restore snapshot: ${PRE_RESTORE_HOST}.gz"
