#!/usr/bin/env bash
# Deterministic environment bootstrap for runtime/governance stabilization.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="python3.12"
RUN_ENV_SYNC=1
RUN_FRONTEND_SYNC=1
RUN_VALIDATION=1
STRICT_DOCTOR=1

usage() {
  cat <<USAGE
Usage: ./scripts/aura_bootstrap.sh [options]

Options:
  --python <bin>          Python binary for env sync (default: python3.12)
  --skip-env-sync         Skip deterministic Python env sync
  --skip-frontend-sync    Skip dashboard npm ci
  --skip-validate         Skip stabilization validation run
  --no-strict-doctor      Run env-doctor in non-strict mode
  --help                  Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --skip-env-sync)
      RUN_ENV_SYNC=0
      shift
      ;;
    --skip-frontend-sync)
      RUN_FRONTEND_SYNC=0
      shift
      ;;
    --skip-validate)
      RUN_VALIDATION=0
      shift
      ;;
    --no-strict-doctor)
      STRICT_DOCTOR=0
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

echo "[INFO] Running environment diagnostics"
if [[ "${STRICT_DOCTOR}" -eq 1 ]]; then
  "${ROOT_DIR}/scripts/env-doctor.sh" --strict
else
  "${ROOT_DIR}/scripts/env-doctor.sh"
fi

if [[ "${RUN_ENV_SYNC}" -eq 1 ]]; then
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "[FAIL] Required python runtime missing: ${PYTHON_BIN}" >&2
    echo "       expected: Python >=3.12 for backend/runtime contract stabilization" >&2
    exit 1
  fi
  echo "[INFO] Syncing deterministic Python environment with ${PYTHON_BIN}"
  "${ROOT_DIR}/scripts/env-sync.sh" --python "${PYTHON_BIN}"
fi

if [[ "${RUN_FRONTEND_SYNC}" -eq 1 ]]; then
  echo "[INFO] Installing deterministic dashboard dependencies"
  (cd "${ROOT_DIR}/dashboard" && npm ci)
fi

if [[ "${RUN_VALIDATION}" -eq 1 ]]; then
  echo "[INFO] Executing stabilization validation"
  "${ROOT_DIR}/scripts/aura_validate.sh"
fi

echo "[PASS] AURA bootstrap completed"
