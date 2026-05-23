#!/usr/bin/env bash
# Deterministic local/CI dependency sync for AURA.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSTRAINTS_FILE="${ROOT_DIR}/constraints/py312.txt"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="python3.12"
USE_VENV=1

usage() {
  cat <<USAGE
Usage: ./scripts/env-sync.sh [options]

Options:
  --python <bin>      Python binary to use (default: python3.12)
  --venv <dir>        Virtualenv directory (default: .venv)
  --no-venv           Install into current Python environment
  --help              Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --venv)
      VENV_DIR="$2"
      shift 2
      ;;
    --no-venv)
      USE_VENV=0
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

if [[ ! -f "${CONSTRAINTS_FILE}" ]]; then
  echo "[FAIL] Constraints file missing: ${CONSTRAINTS_FILE}" >&2
  exit 1
fi

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "[FAIL] Python binary not found: ${PYTHON_BIN}" >&2
  echo "       Install Python 3.12 and rerun." >&2
  exit 1
fi

if [[ "${USE_VENV}" -eq 1 ]]; then
  echo "[INFO] Creating deterministic virtualenv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
  ACTIVE_PY="python"
else
  ACTIVE_PY="${PYTHON_BIN}"
fi

echo "[INFO] Python: $(${ACTIVE_PY} --version)"

"${ACTIVE_PY}" -m pip install --upgrade \
  pip==24.2 \
  setuptools==75.1.0 \
  wheel==0.44.0

install_editable() {
  local target="$1"
  echo "[INFO] Installing ${target}"
  "${ACTIVE_PY}" -m pip install --constraint "${CONSTRAINTS_FILE}" --editable "${target}"
}

install_editable "${ROOT_DIR}/workspace/aura-sdk[all,dev]"
install_editable "${ROOT_DIR}/agents"
install_editable "${ROOT_DIR}/services/core"
install_editable "${ROOT_DIR}/services/llm-gateway"
install_editable "${ROOT_DIR}/services/ws-server"

"${ACTIVE_PY}" -m pip install --constraint "${CONSTRAINTS_FILE}" \
  pytest==8.3.2 \
  pytest-asyncio==0.24.0

echo "[INFO] Verifying critical imports"
"${ACTIVE_PY}" - <<'PY'
import importlib
modules = [
    "fastapi",
    "aiosqlite",
    "httpx",
    "aura_sdk",
    "core.main",
    "llm_gateway.main",
    "ws_server.main",
]
missing = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append((name, str(exc)))

if missing:
    for module, error in missing:
        print(f"[FAIL] import {module}: {error}")
    raise SystemExit(1)

print("[PASS] Deterministic dependency sync complete")
PY

if [[ "${USE_VENV}" -eq 1 ]]; then
  echo "[INFO] Activate with: source ${VENV_DIR}/bin/activate"
fi

if [[ -x "${ROOT_DIR}/scripts/dependency-integrity.sh" ]]; then
  PYTHON_BIN="${ACTIVE_PY}" "${ROOT_DIR}/scripts/dependency-integrity.sh"
fi
