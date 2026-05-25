#!/usr/bin/env bash
# Container-authoritative pytest runner for deterministic Python 3.12 execution.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="${ROOT_DIR}/scripts/aura_runtime_launcher.sh"

if [[ ! -x "${LAUNCHER}" ]]; then
  echo "[FAIL] Missing runtime launcher: ${LAUNCHER}" >&2
  exit 1
fi

"${LAUNCHER}" --mode pytest "$@"
