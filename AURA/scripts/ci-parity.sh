#!/usr/bin/env bash
# Shared CI/runtime parity validation pipeline (container-authoritative).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="auto"
LAUNCHER="${ROOT_DIR}/scripts/aura_runtime_launcher.sh"

usage() {
  cat <<USAGE
Usage: ./scripts/ci-parity.sh [--mode auto|container]

Modes:
  auto      Alias for container mode
  container Run inside deterministic runtime container (Python 3.12)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="$2"
      shift 2
      ;;
    --python)
      echo "[WARN] --python is ignored; container Python 3.12 is authoritative."
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

run_container() {
  if [[ ! -x "${LAUNCHER}" ]]; then
    echo "[FAIL] missing launcher: ${LAUNCHER}" >&2
    exit 1
  fi
  echo "[INFO] Deterministic dependency sync in container"
  "${ROOT_DIR}/scripts/env-sync.sh"

  echo "[INFO] Architecture enforcement"
  "${LAUNCHER}" --mode command -- python scripts/architecture-enforce.py

  echo "[INFO] Governance/replay hard-fail tests"
  "${LAUNCHER}" --mode pytest -- \
    services/core/tests/test_governance_stabilization.py \
    services/core/tests/test_event_audit_persistence.py \
    services/core/tests/test_task_queue_retry_ordering.py \
    services/core/tests/test_operational_interface_endpoints.py \
    workspace/aura-sdk/tests/test_replay.py \
    workspace/aura-sdk/tests/test_architecture_enforcer.py \
    agents/tests/test_base_agent_replay_hooks.py

  echo "[INFO] Determinism gate"
  "${LAUNCHER}" --mode command -- python scripts/determinism-gate.py

  echo "[PASS] CI/runtime parity validation complete"
}

case "${MODE}" in
  auto)
    run_container
    ;;
  local)
    echo "[WARN] local mode is deprecated; redirecting to container mode."
    run_container
    ;;
  docker|container)
    run_container
    ;;
  *)
    echo "Invalid mode: ${MODE}" >&2
    usage
    exit 2
    ;;
esac
