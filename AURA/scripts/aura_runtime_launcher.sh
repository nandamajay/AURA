#!/usr/bin/env bash
# Unified deterministic launcher for runtime/test/governance execution paths.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="${ROOT_DIR}/scripts/aura_container_exec.sh"
MODE="command"
BUILD_IMAGE=0
NO_TTY=1
ARGS=()

usage() {
  cat <<USAGE
Usage: ./scripts/aura_runtime_launcher.sh [options] -- [command...]

Modes:
  --mode command        Run arbitrary command (default; requires -- ...)
  --mode pytest         Run pytest with deterministic container runtime
  --mode runtime-pipeline
                        Run runtime ingestion -> equivalence -> governance
  --mode semantic       Run semantic extraction script
  --mode simulation     Run upstream acceptance simulation script

Options:
  --build-image         Rebuild deterministic image before run
  --tty                 Enable TTY passthrough
  --help                Show this message

Examples:
  ./scripts/aura_runtime_launcher.sh --mode pytest -- workspace/aura-sdk/tests/test_runtime_replay_static.py
  ./scripts/aura_runtime_launcher.sh --mode runtime-pipeline
  ./scripts/aura_runtime_launcher.sh --mode command -- python scripts/aura_validation.py
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --build-image)
      BUILD_IMAGE=1
      shift
      ;;
    --tty)
      NO_TTY=0
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        ARGS+=("$1")
        shift
      done
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -x "${WRAPPER}" ]]; then
  echo "[FAIL] Missing wrapper: ${WRAPPER}" >&2
  exit 1
fi

WRAPPER_ARGS=()
if [[ "${BUILD_IMAGE}" -eq 1 ]]; then
  WRAPPER_ARGS+=(--build)
fi
if [[ "${NO_TTY}" -eq 1 ]]; then
  WRAPPER_ARGS+=(--no-tty)
fi

run_wrapped() {
  local command="$1"
  "${WRAPPER}" "${WRAPPER_ARGS[@]}" -- "${command}"
}

case "${MODE}" in
  command)
    if [[ "${#ARGS[@]}" -eq 0 ]]; then
      echo "[FAIL] --mode command requires a command after --" >&2
      exit 2
    fi
    printf -v CMD '%q ' "${ARGS[@]}"
    run_wrapped "${CMD% }"
    ;;
  pytest)
    if [[ "${#ARGS[@]}" -eq 0 ]]; then
      ARGS=("workspace/aura-sdk/tests")
    fi
    printf -v PYTEST_CMD '%q ' python -m pytest -q "${ARGS[@]}"
    run_wrapped "${PYTEST_CMD% }"
    ;;
  runtime-pipeline)
    run_wrapped "python scripts/aura-runtime-trace-ingestion.py --variant baseline"
    run_wrapped "python scripts/aura-runtime-trace-ingestion.py --variant transformed"
    run_wrapped "python scripts/aura-runtime-equivalence.py"
    run_wrapped "python scripts/aura-runtime-governance.py"
    ;;
  semantic)
    run_wrapped "python scripts/aura-kernel-semantic-knowledge-layer.py"
    ;;
  simulation)
    run_wrapped "python scripts/aura-upstream-acceptance-simulation.py"
    ;;
  *)
    echo "[FAIL] Unsupported mode: ${MODE}" >&2
    usage
    exit 2
    ;;
esac
