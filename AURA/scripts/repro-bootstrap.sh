#!/usr/bin/env bash
# Single-command deterministic runtime bootstrap.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
WAIT_SECONDS=120
RUN_ENV_SYNC=0
STRICT_DOCTOR=0

usage() {
  cat <<USAGE
Usage: ./scripts/repro-bootstrap.sh [options]

Options:
  --env-file <path>      Compose env file (default: .env)
  --wait-seconds <n>     Health wait timeout (default: 120)
  --sync-local-env       Run deterministic local dependency sync before startup
  --strict-doctor        Fail when diagnostics produce warnings
  --help                 Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    --sync-local-env)
      RUN_ENV_SYNC=1
      shift
      ;;
    --strict-doctor)
      STRICT_DOCTOR=1
      shift
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

echo "[INFO] Running failure-first environment diagnostics"
if [[ "${STRICT_DOCTOR}" -eq 1 ]]; then
  "${ROOT_DIR}/scripts/env-doctor.sh" --strict
else
  "${ROOT_DIR}/scripts/env-doctor.sh"
fi

if [[ "${RUN_ENV_SYNC}" -eq 1 ]]; then
  echo "[INFO] Syncing deterministic local Python environment"
  "${ROOT_DIR}/scripts/env-sync.sh"
fi

COMPOSE_ARGS=()
if [[ -f "${ENV_FILE}" ]]; then
  COMPOSE_ARGS+=(--env-file "${ENV_FILE}")
fi

echo "[INFO] Starting docker compose stack"
docker compose "${COMPOSE_ARGS[@]}" up --build -d

echo "[INFO] Running runtime verification"
"${ROOT_DIR}/scripts/runtime-verify.sh" --env-file "${ENV_FILE}" --wait-seconds "${WAIT_SECONDS}"

echo "[PASS] deterministic bootstrap completed"
echo "       dashboard: http://localhost:3000"
echo "       api:       http://localhost:8000"
