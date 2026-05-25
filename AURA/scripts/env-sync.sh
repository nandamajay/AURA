#!/usr/bin/env bash
# Deterministic dependency sync (container-authoritative Python 3.12).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="${ROOT_DIR}/scripts/aura_container_exec.sh"
BUILD_IMAGE=1
IMAGE_TAG=""

usage() {
  cat <<USAGE
Usage: ./scripts/env-sync.sh [options]

Options:
  --no-image-build    Reuse existing deterministic execution image
  --image <tag>       Override deterministic execution image tag
  --python <bin>      Deprecated; host python is not used
  --venv <dir>        Deprecated; host venv sync disabled
  --no-venv           Deprecated; host venv sync disabled
  --help              Show this message
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-image-build)
      BUILD_IMAGE=0
      shift
      ;;
    --image)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --python|--venv|--no-venv)
      echo "[WARN] $1 is deprecated. Host Python sync is disabled; using deterministic container runtime."
      if [[ "$1" == "--python" || "$1" == "--venv" ]]; then
        shift 2
      else
        shift
      fi
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

if [[ ! -x "${WRAPPER}" ]]; then
  echo "[FAIL] Missing deterministic wrapper: ${WRAPPER}" >&2
  exit 1
fi

WRAPPER_ARGS=()
if [[ "${BUILD_IMAGE}" -eq 1 ]]; then
  WRAPPER_ARGS+=(--build)
fi
if [[ -n "${IMAGE_TAG}" ]]; then
  WRAPPER_ARGS+=(--image "${IMAGE_TAG}")
fi

echo "[INFO] Validating deterministic Python runtime/imports in container"
"${WRAPPER}" "${WRAPPER_ARGS[@]}" -- "python --version && python - <<'PY'
import importlib
modules = [
    'fastapi',
    'uvicorn',
    'jose',
    'passlib',
    'httpx',
    'aura_sdk',
    'core.main',
    'llm_gateway.main',
    'ws_server.main',
]
missing = []
for name in modules:
    try:
        importlib.import_module(name)
    except Exception as exc:
        missing.append((name, str(exc)))
if missing:
    for mod, err in missing:
        print(f'[FAIL] import {mod}: {err}')
    raise SystemExit(1)
print('[PASS] Deterministic container dependency sync complete')
PY"

if [[ -x "${ROOT_DIR}/scripts/dependency-integrity.sh" ]]; then
  "${WRAPPER}" "${WRAPPER_ARGS[@]}" -- "./scripts/dependency-integrity.sh"
fi
