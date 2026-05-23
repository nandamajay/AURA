#!/usr/bin/env bash
set -u -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SLEEP_SECS="${AURA_QUARANTINE_SLEEP_SECS:-20}"

cd "${REPO_ROOT}"

while true; do
  echo "[$(date -Is)] [quarantine-loop] running aura_event_quarantine_tests"
  if ! python3 scripts/aura_event_quarantine_tests.py; then
    echo "[$(date -Is)] [quarantine-loop] command failed" >&2
  fi
  sleep "${SLEEP_SECS}"
done
