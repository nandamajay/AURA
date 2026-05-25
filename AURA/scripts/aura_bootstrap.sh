#!/usr/bin/env bash
# Deterministic environment bootstrap (container-authoritative execution).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="${ROOT_DIR}/scripts/aura_container_exec.sh"
RUN_FRONTEND_SYNC=1
RUN_VALIDATION=1
STRICT_DOCTOR=1
BUILD_IMAGE=1

usage() {
  cat <<USAGE
Usage: ./scripts/aura_bootstrap.sh [options]

Options:
  --python <bin>          Deprecated; host python is not used for execution
  --skip-env-sync         Deprecated; no-op for compatibility
  --skip-frontend-sync    Skip dashboard npm ci
  --skip-validate         Skip stabilization validation run
  --no-image-build        Skip deterministic runtime image rebuild
  --no-strict-doctor      Run env-doctor in non-strict mode
  --help                  Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-image-build)
      BUILD_IMAGE=0
      shift
      ;;
    --python)
      echo "[WARN] --python is ignored. Container Python 3.12 is authoritative."
      shift 2
      ;;
    --skip-env-sync)
      echo "[WARN] --skip-env-sync is deprecated and ignored."
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

if [[ ! -x "${WRAPPER}" ]]; then
  echo "[FAIL] Missing deterministic wrapper: ${WRAPPER}" >&2
  exit 1
fi

WRAPPER_ARGS=()
if [[ "${BUILD_IMAGE}" -eq 1 ]]; then
  WRAPPER_ARGS+=(--build)
fi
echo "[INFO] Verifying deterministic runtime container (Python 3.12)"
"${WRAPPER}" "${WRAPPER_ARGS[@]}" -- "python --version"

if [[ "${RUN_FRONTEND_SYNC}" -eq 1 ]]; then
  echo "[INFO] Installing deterministic dashboard dependencies"
  (cd "${ROOT_DIR}/dashboard" && npm ci)
fi

if [[ "${RUN_VALIDATION}" -eq 1 ]]; then
  echo "[INFO] Executing stabilization validation"
  "${ROOT_DIR}/scripts/aura_validate.sh"
fi

echo "[PASS] AURA bootstrap completed"
