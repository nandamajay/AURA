#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${AURA_OUTPUT_DIR:-/local/mnt/workspace/AURA_V1/docs/operations/transport}"
SLEEP_SECS="${AURA_BOOT_SLEEP_SECS:-5}"

cd "${REPO_ROOT}"

while true; do
  echo "[$(date -Is)] [boot-loop] running aura-cognition-boot"
  if ! python3 scripts/aura-cognition-boot.py --output-dir "${OUT_DIR}"; then
    echo "[$(date -Is)] [boot-loop] command failed" >&2
  fi
  sleep "${SLEEP_SECS}"
done
