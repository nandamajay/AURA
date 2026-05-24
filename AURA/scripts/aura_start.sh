#!/usr/bin/env bash
# Unified startup sequencing for backend + dashboard runtime stack.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
WAIT_SECONDS=120
SKIP_BOOTSTRAP=0
RUN_VALIDATION=0
NO_BUILD=0

usage() {
  cat <<USAGE
Usage: ./scripts/aura_start.sh [options]

Options:
  --env-file <path>       Compose env file (default: .env)
  --wait-seconds <n>      Runtime verification timeout (default: 120)
  --skip-bootstrap        Skip aura_bootstrap preflight
  --validate              Run aura_validate after runtime verification
  --no-build              Use docker compose up without --build
  --help                  Show this message
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
    --skip-bootstrap)
      SKIP_BOOTSTRAP=1
      shift
      ;;
    --validate)
      RUN_VALIDATION=1
      shift
      ;;
    --no-build)
      NO_BUILD=1
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

if [[ "${SKIP_BOOTSTRAP}" -ne 1 ]]; then
  "${ROOT_DIR}/scripts/aura_bootstrap.sh" --skip-validate --skip-frontend-sync
fi

COMPOSE_ARGS=()
if [[ -f "${ENV_FILE}" ]]; then
  COMPOSE_ARGS+=(--env-file "${ENV_FILE}")
fi

UP_ARGS=("up" "-d")
if [[ "${NO_BUILD}" -ne 1 ]]; then
  UP_ARGS+=("--build")
fi

echo "[INFO] Starting backend services first (aura-core, ws-server, llm-gateway)"
docker compose "${COMPOSE_ARGS[@]}" "${UP_ARGS[@]}" aura-core ws-server llm-gateway

echo "[INFO] Waiting for backend readiness"
for endpoint in \
  "http://localhost:8000/health/ready" \
  "http://localhost:8001/health" \
  "http://localhost:8002/health"; do
  started="$(date +%s)"
  while true; do
    if curl -fsS "${endpoint}" >/dev/null 2>&1; then
      echo "[PASS] ${endpoint}"
      break
    fi
    now="$(date +%s)"
    if (( now - started >= WAIT_SECONDS )); then
      echo "[FAIL] timed out waiting for ${endpoint}" >&2
      exit 1
    fi
    sleep 2
  done
done

echo "[INFO] Starting dashboard after backend readiness"
docker compose "${COMPOSE_ARGS[@]}" "${UP_ARGS[@]}" dashboard

echo "[INFO] Running runtime verification"
"${ROOT_DIR}/scripts/runtime-verify.sh" --env-file "${ENV_FILE}" --wait-seconds "${WAIT_SECONDS}"

if [[ "${RUN_VALIDATION}" -eq 1 ]]; then
  echo "[INFO] Running post-start stabilization validation"
  "${ROOT_DIR}/scripts/aura_validate.sh"
fi

echo "[PASS] AURA unified startup completed"
