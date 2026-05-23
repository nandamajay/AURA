#!/usr/bin/env bash
# Deterministic demo runtime mode (seeded, reproducible, evidence-preserving).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_ENV="${ROOT_DIR}/.env"
DEMO_ENV="${ROOT_DIR}/.env.demo"

usage() {
  cat <<USAGE
Usage: ./scripts/demo-mode.sh <prepare|up|verify|workload|down>

Commands:
  prepare   Generate deterministic .env.demo from .env with demo overrides
  up        Start stack using .env.demo
  verify    Run runtime verification using .env.demo
  workload  Run deterministic seeded demo workload and capture evidence
  down      Stop stack started with .env.demo
USAGE
}

prepare_env() {
  if [[ ! -f "${BASE_ENV}" ]]; then
    echo "[FAIL] ${BASE_ENV} missing" >&2
    exit 1
  fi

  cp "${BASE_ENV}" "${DEMO_ENV}"

  upsert() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "${DEMO_ENV}"; then
      sed -i "s#^${key}=.*#${key}=${value}#" "${DEMO_ENV}"
    else
      echo "${key}=${value}" >> "${DEMO_ENV}"
    fi
  }

  upsert "LLM_MOCK_MODE" "true"
  upsert "LOG_LEVEL" "INFO"
  upsert "MAX_CONCURRENT_AGENTS" "20"
  upsert "AGENT_TIMEOUT_SECONDS" "180"
  upsert "TOKEN_BUDGET_DAILY" "250000"
  upsert "DEMO_MODE" "true"
  upsert "DEMO_SEED" "42"

  echo "[PASS] wrote ${DEMO_ENV}"
}

cmd="${1:-}"
case "${cmd}" in
  prepare)
    prepare_env
    ;;
  up)
    [[ -f "${DEMO_ENV}" ]] || prepare_env
    docker compose --env-file "${DEMO_ENV}" up --build -d
    ;;
  verify)
    "${ROOT_DIR}/scripts/runtime-verify.sh" --env-file "${DEMO_ENV}" --wait-seconds 120
    ;;
  workload)
    python3 "${ROOT_DIR}/scripts/demo-seeded-workload.py" --env-file "${DEMO_ENV}" --seed 42 --timeout 300
    ;;
  down)
    docker compose --env-file "${DEMO_ENV}" down
    ;;
  *)
    usage
    exit 2
    ;;
esac
