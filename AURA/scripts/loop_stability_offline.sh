#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REGISTRY_DIR="${AURA_REGISTRY_DIR:-/local/mnt/workspace/AURA_V1/docs/operations/transport}"
SLEEP_SECS="${AURA_STABILITY_SLEEP_SECS:-10}"
ITERATIONS="${AURA_STABILITY_ITERATIONS:-1}"

cd "${REPO_ROOT}"

while true; do
  echo "[$(date -Is)] [stability-loop] running aura_stability_harness offline"
  if ! python3 scripts/aura_stability_harness.py \
    --mode offline_replay_validation \
    --registry "${REGISTRY_DIR}" \
    --iterations "${ITERATIONS}"; then
    echo "[$(date -Is)] [stability-loop] command failed" >&2
  fi
  sleep "${SLEEP_SECS}"
done
