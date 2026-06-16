#!/usr/bin/env bash
set -euo pipefail

ROOT="/local/mnt/workspace/AURA_V1_upstream"
AURA_ROOT="${ROOT}/AURA"
AGENTS_DIR="${AURA_ROOT}/agents"

cd "${ROOT}"
git switch aura_upstream_learning

if [[ ! -f "${AURA_ROOT}/.env" ]]; then
  echo "[WARN] ${AURA_ROOT}/.env not found. Creating from .env.example"
  cp "${AURA_ROOT}/.env.example" "${AURA_ROOT}/.env"
fi

cat > "${AGENTS_DIR}/aura_cmd.sh" <<'EOS'
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
EOS

chmod +x "${AGENTS_DIR}/aura_cmd.sh"

echo "[OK] Setup complete"
echo "[NEXT] cd ${AGENTS_DIR} && ./aura_cmd.sh status --limit 20"
