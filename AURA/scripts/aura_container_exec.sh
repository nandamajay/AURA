#!/usr/bin/env bash
# Deterministic Python 3.12 execution wrapper for AURA.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "${ROOT_DIR}/.." && pwd)"
IMAGE_TAG="${AURA_RUNTIME_EXEC_IMAGE:-aura-runtime-exec:py312}"
BUILD_IMAGE=0
NO_TTY=0

usage() {
  cat <<USAGE
Usage: ./scripts/aura_container_exec.sh [options] -- <command>

Options:
  --build                 Build deterministic execution image before run
  --image <tag>           Override image tag (default: aura-runtime-exec:py312)
  --no-tty                Disable -t for docker run
  --help                  Show this message

Examples:
  ./scripts/aura_container_exec.sh --build -- "python --version"
  ./scripts/aura_container_exec.sh -- "pytest services/core/tests/test_runtime_contracts_static.py"
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)
      BUILD_IMAGE=1
      shift
      ;;
    --image)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --no-tty)
      NO_TTY=1
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ $# -eq 0 ]]; then
  echo "[FAIL] Missing command after --" >&2
  usage
  exit 2
fi

if [[ "${BUILD_IMAGE}" -eq 1 ]] || ! docker image inspect "${IMAGE_TAG}" >/dev/null 2>&1; then
  echo "[INFO] Building deterministic runtime image: ${IMAGE_TAG}"
  docker build \
    -f "${ROOT_DIR}/docker/runtime-exec.Dockerfile" \
    -t "${IMAGE_TAG}" \
    "${ROOT_DIR}"
fi

IMAGE_ID="$(docker image inspect "${IMAGE_TAG}" --format '{{.Id}}')"
TTY_FLAG=""
if [[ "${NO_TTY}" -ne 1 && -t 1 ]]; then
  TTY_FLAG="-t"
fi

COMMAND="$*"
echo "[INFO] image=${IMAGE_TAG}"
echo "[INFO] image_id=${IMAGE_ID}"

docker run --rm ${TTY_FLAG} \
  -e "AURA_EXECUTION_CONTAINER_HASH=${IMAGE_ID}" \
  -e "AURA_RUNTIME_EXECUTION_MODE=container" \
  -e "AURA_REPO_ROOT=/workspace" \
  -e "PYTHONHASHSEED=0" \
  -e "TZ=UTC" \
  -e "LC_ALL=C.UTF-8" \
  -e "LANG=C.UTF-8" \
  -e "PYTHONPATH=/workspace/AURA/services/core/src:/workspace/AURA/workspace/aura-sdk/src:/workspace/AURA/services/llm-gateway/src:/workspace/AURA/services/ws-server/src:/workspace/AURA/agents/src" \
  -v "${WORKSPACE_ROOT}:/workspace" \
  -w "/workspace/AURA" \
  "${IMAGE_TAG}" \
  bash -lc "${COMMAND}"
