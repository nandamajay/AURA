#!/usr/bin/env bash
# AURA Backup Script — Docker-volume-aware SQLite backup
# Usage: ./scripts/backup.sh [retention_days]

set -euo pipefail

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${AURA_DIR}/data/backups"
RETENTION_DAYS="${1:-30}"
SERVICE_NAME="aura-core"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
CONTAINER_TMP_DB="/tmp/aura_backup_${TIMESTAMP}.db"
HOST_TMP_DB=""
BACKUP_FILE="${BACKUP_DIR}/aura_backup_${TIMESTAMP}.db"

cleanup() {
    if [ -n "${HOST_TMP_DB}" ]; then
        rm -f "${HOST_TMP_DB}" 2>/dev/null || true
    fi
    docker compose exec -T "${SERVICE_NAME}" python - "${CONTAINER_TMP_DB}" <<'PY' >/dev/null 2>&1 || true
import os
import sys

path = sys.argv[1]
try:
    os.remove(path)
except FileNotFoundError:
    pass
PY
}
trap cleanup EXIT

if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]]; then
    echo "ERROR: retention_days must be a positive integer."
    exit 1
fi

mkdir -p "${AURA_DIR}/data" "${BACKUP_DIR}"
HOST_TMP_DB="$(mktemp "${AURA_DIR}/data/.aura_backup_tmp_XXXXXX.db")"

if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE_NAME}"; then
    echo "ERROR: ${SERVICE_NAME} is not running."
    echo "Start stack first: make up"
    exit 1
fi

echo "AURA Database Backup"
echo "===================="
echo "Service: ${SERVICE_NAME}"
echo "Backup:  ${BACKUP_FILE}.gz"
echo ""

docker compose exec -T "${SERVICE_NAME}" python - "${CONTAINER_TMP_DB}" <<'PY'
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
    raise SystemExit(f"backup integrity check failed: {integrity}")
PY

docker cp "${SERVICE_NAME}:${CONTAINER_TMP_DB}" "${HOST_TMP_DB}"

python - "${HOST_TMP_DB}" <<'PY'
import sqlite3
import sys

path = sys.argv[1]
conn = sqlite3.connect(path)
result = conn.execute("PRAGMA integrity_check;").fetchone()[0]
conn.close()
if str(result).lower() != "ok":
    raise SystemExit(f"host integrity check failed: {result}")
PY

mv "${HOST_TMP_DB}" "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"
gzip -f "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}.gz"

DELETED="$(find "${BACKUP_DIR}" -name "aura_backup_*.db.gz" -mtime +"${RETENTION_DAYS}" -delete -print | wc -l)"
if [ "${DELETED}" -gt 0 ]; then
    echo "Removed ${DELETED} backup(s) older than ${RETENTION_DAYS} day(s)."
fi

BACKUP_SIZE="$(du -h "${BACKUP_FILE}.gz" | awk '{print $1}')"
echo "Backup complete: ${BACKUP_FILE}.gz (${BACKUP_SIZE})"
