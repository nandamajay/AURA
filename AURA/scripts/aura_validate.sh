#!/usr/bin/env bash
# Unified stabilization validation runner.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VALIDATOR="${ROOT_DIR}/scripts/aura_validation.py"
PYTHON_BIN=""

usage() {
  cat <<USAGE
Usage: ./scripts/aura_validate.sh [--python <bin>]

Runs:
- environment validation
- runtime contract validation
- replay integrity hardening checks
- dashboard build validation

Artifacts:
- docs/operations/transport/*.json
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
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

if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
  elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN="python3.12"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
    echo "[WARN] python3.12 unavailable; running validator with ${PYTHON_BIN} for diagnostics only."
  else
    echo "[FAIL] No Python runtime available for validation." >&2
    exit 1
  fi
fi

echo "[INFO] validator python: ${PYTHON_BIN}"
"${PYTHON_BIN}" "${VALIDATOR}"

echo "[INFO] reports written under: ${ROOT_DIR}/../docs/operations/transport"
