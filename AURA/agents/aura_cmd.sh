#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AURA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

exec env PYTHONPATH="${SCRIPT_DIR}/src" \
  python3 -m aura_agents.aura_cli \
  --api-base "http://localhost:8000" \
  --env-file "${AURA_ROOT}/.env" \
  --db-path "${AURA_ROOT}/data/aura.db" \
  "$@"
