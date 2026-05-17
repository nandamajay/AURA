#!/usr/bin/env bash
# AURA Infrastructure Hardening Check
# Usage: ./scripts/hardening-check.sh

set -euo pipefail

AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="aura-core"
FAILURES=0
WARNINGS=0

pass() {
    echo "[PASS] $1"
}

fail() {
    echo "[FAIL] $1"
    FAILURES=$((FAILURES + 1))
}

warn() {
    echo "[WARN] $1"
    WARNINGS=$((WARNINGS + 1))
}

echo "AURA Infrastructure Hardening Check"
echo "==================================="
echo "Workspace: ${AURA_DIR}"
echo ""

if ! docker compose ps --status running --services 2>/dev/null | grep -qx "${SERVICE_NAME}"; then
    fail "${SERVICE_NAME} is not running"
    echo ""
    echo "Start stack first: make up"
    exit 1
fi
pass "${SERVICE_NAME} is running"

# H-01: Container user should be non-root.
CONTAINER_UID="$(docker compose exec -T "${SERVICE_NAME}" sh -lc 'id -u' 2>/dev/null || echo "unknown")"
if [[ "${CONTAINER_UID}" =~ ^[0-9]+$ ]] && [ "${CONTAINER_UID}" -ne 0 ]; then
    pass "H-01 non-root container user (uid=${CONTAINER_UID})"
else
    fail "H-01 container runs as root (uid=${CONTAINER_UID})"
fi

# H-02: no-new-privileges should be enabled.
SECURITY_OPT="$(docker inspect "${SERVICE_NAME}" --format '{{json .HostConfig.SecurityOpt}}' 2>/dev/null || echo "[]")"
if echo "${SECURITY_OPT}" | grep -q "no-new-privileges:true"; then
    pass "H-02 no-new-privileges enabled"
else
    fail "H-02 no-new-privileges not enabled"
fi

# H-04: capabilities dropped.
CAP_DROP="$(docker inspect "${SERVICE_NAME}" --format '{{json .HostConfig.CapDrop}}' 2>/dev/null || echo "[]")"
if echo "${CAP_DROP}" | grep -q "ALL"; then
    pass "H-04 capabilities dropped (ALL)"
else
    fail "H-04 capabilities are not fully dropped"
fi

# H-13: ws-server should be localhost-bound.
WS_BIND="$(docker compose port ws-server 8000 2>/dev/null || true)"
if echo "${WS_BIND}" | grep -q "127.0.0.1:"; then
    pass "H-13 ws-server bound to localhost (${WS_BIND})"
else
    fail "H-13 ws-server is not localhost-bound (${WS_BIND:-unavailable})"
fi

# H-18: data directory permissions.
if [ -d "${AURA_DIR}/data" ]; then
    DATA_PERM="$(stat -c '%a' "${AURA_DIR}/data" 2>/dev/null || echo "unknown")"
    if [ "${DATA_PERM}" = "700" ]; then
        pass "H-18 data directory permissions are 700"
    else
        fail "H-18 data directory permissions are ${DATA_PERM} (expected 700)"
    fi
else
    fail "H-18 data directory missing"
fi

# H-19: backup file permissions.
BACKUP_DIR="${AURA_DIR}/data/backups"
if [ -d "${BACKUP_DIR}" ]; then
    BAD_BACKUPS="$(find "${BACKUP_DIR}" -type f ! -perm 600 | wc -l | tr -d ' ')"
    if [ "${BAD_BACKUPS}" = "0" ]; then
        pass "H-19 backup file permissions are restricted"
    else
        fail "H-19 found ${BAD_BACKUPS} backup file(s) not set to 600"
    fi
else
    warn "H-19 backup directory not present yet (${BACKUP_DIR})"
fi

# H-23: secrets directory permissions (if used).
SECRETS_DIR="${AURA_DIR}/secrets"
if [ -d "${SECRETS_DIR}" ]; then
    BAD_SECRETS="$(find "${SECRETS_DIR}" -type f ! -perm 600 | wc -l | tr -d ' ')"
    if [ "${BAD_SECRETS}" = "0" ]; then
        pass "H-23 secrets file permissions are restricted"
    else
        fail "H-23 found ${BAD_SECRETS} secret file(s) not set to 600"
    fi
else
    warn "H-23 secrets directory not present (using env-based configuration)"
fi

echo ""
echo "Results"
echo "-------"
echo "Failures: ${FAILURES}"
echo "Warnings: ${WARNINGS}"

if [ "${FAILURES}" -gt 0 ]; then
    exit 1
fi

echo "All enforced hardening checks passed."
