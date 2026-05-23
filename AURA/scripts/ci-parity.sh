#!/usr/bin/env bash
# Shared CI/local parity validation pipeline.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.12}"
MODE="auto"

usage() {
  cat <<USAGE
Usage: ./scripts/ci-parity.sh [--mode auto|local|docker] [--python <bin>]

Modes:
  auto   Run locally when Python is available; otherwise run in dockerized Python 3.12
  local  Run locally (requires Python 3.12 available on host)
  docker Run inside python:3.12-slim container using mounted repo workspace
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
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

run_local() {
  if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "[FAIL] ${PYTHON_BIN} not found" >&2
    echo "       run with --mode docker or install Python 3.12 locally" >&2
    exit 1
  fi

  echo "[INFO] Deterministic dependency sync (no virtualenv in CI mode)"
  "${ROOT_DIR}/scripts/env-sync.sh" --no-venv --python "${PYTHON_BIN}"

  echo "[INFO] Architecture enforcement"
  "${PYTHON_BIN}" "${ROOT_DIR}/scripts/architecture-enforce.py"

  echo "[INFO] Governance/replay hard-fail tests"
  local pytest_cache_dir
  pytest_cache_dir="${PYTEST_CACHE_DIR:-/tmp/aura-pytest-cache}"
  PYTHONPATH="${ROOT_DIR}/agents/src:${ROOT_DIR}/services/core/src:${ROOT_DIR}/workspace/aura-sdk/src" \
    "${PYTHON_BIN}" -m pytest -q \
    -o "cache_dir=${pytest_cache_dir}" \
    "${ROOT_DIR}/services/core/tests/test_governance_stabilization.py" \
    "${ROOT_DIR}/services/core/tests/test_event_audit_persistence.py" \
    "${ROOT_DIR}/services/core/tests/test_task_queue_retry_ordering.py" \
    "${ROOT_DIR}/services/core/tests/test_operational_interface_endpoints.py" \
    "${ROOT_DIR}/workspace/aura-sdk/tests/test_replay.py" \
    "${ROOT_DIR}/workspace/aura-sdk/tests/test_architecture_enforcer.py" \
    "${ROOT_DIR}/agents/tests/test_base_agent_replay_hooks.py"

  echo "[INFO] Determinism gate"
  PYTHONPATH="${ROOT_DIR}/workspace/aura-sdk/src" \
    "${PYTHON_BIN}" "${ROOT_DIR}/scripts/determinism-gate.py"

  echo "[PASS] CI/runtime parity validation complete"
}

run_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "[FAIL] docker not found for docker parity mode" >&2
    exit 1
  fi

  echo "[INFO] Running CI/runtime parity in dockerized Python 3.12"
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "${ROOT_DIR}:/workspace/AURA" \
    -w /workspace/AURA \
    -e HOME=/tmp \
    -e PYTHON_BIN=python3.12 \
    python:3.12-slim \
    bash -lc "./scripts/ci-parity.sh --mode local --python python3.12"
}

case "${MODE}" in
  auto)
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      run_local
    else
      echo "[INFO] ${PYTHON_BIN} not found locally; falling back to docker parity mode"
      run_docker
    fi
    ;;
  local)
    run_local
    ;;
  docker)
    run_docker
    ;;
  *)
    echo "Invalid mode: ${MODE}" >&2
    usage
    exit 2
    ;;
esac
