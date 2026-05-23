#!/usr/bin/env bash
# Runtime readiness verifier with evidence output.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE_DIR="${ROOT_DIR}/evidence/startup"
mkdir -p "${EVIDENCE_DIR}"

ENV_FILE="${ROOT_DIR}/.env"
COMPOSE_ARGS=()
WAIT_SECONDS=120

usage() {
  cat <<USAGE
Usage: ./scripts/runtime-verify.sh [--env-file <path>] [--wait-seconds <n>]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --wait-seconds)
      WAIT_SECONDS="$2"
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

if [[ -f "${ENV_FILE}" ]]; then
  COMPOSE_ARGS+=(--env-file "${ENV_FILE}")
else
  echo "[WARN] env file not found: ${ENV_FILE}; continuing with current compose environment"
fi

wait_for_endpoint() {
  local url="$1"
  local timeout="$2"
  local started
  started=$(date +%s)
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    now=$(date +%s)
    if (( now - started >= timeout )); then
      return 1
    fi
    sleep 2
  done
}

json_escape() {
  python3 - <<'PY' "$1"
import json,sys
print(json.dumps(sys.argv[1]))
PY
}

echo "[INFO] Verifying runtime endpoints"

if ! wait_for_endpoint "http://localhost:8000/health/ready" "${WAIT_SECONDS}"; then
  echo "[FAIL] core readiness endpoint failed within ${WAIT_SECONDS}s"
  echo "       impact: replay/governance/runtime validation not trustworthy"
  exit 1
fi

for endpoint in \
  "http://localhost:8000/health/live" \
  "http://localhost:8002/health" \
  "http://localhost:8001/health" \
  "http://localhost:3000"; do
  if curl -fsS "$endpoint" >/dev/null 2>&1; then
    echo "[PASS] $endpoint"
  else
    echo "[FAIL] $endpoint unreachable"
    echo "       impact: operator observability and runtime introspection degraded"
    exit 1
  fi
done

# Login + auth-protected endpoint checks
AUTH_JSON=$(python3 - <<'PY' "${ENV_FILE}"
import json, os, sys
from pathlib import Path

env_file = Path(sys.argv[1])
values = {}
if env_file.exists():
    for raw in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")

print(json.dumps({
    "email": values.get("ADMIN_EMAIL", "admin@aura.local"),
    "password": values.get("ADMIN_PASSWORD", "admin123"),
}))
PY
)

TOKEN=$(python3 - <<'PY' "${AUTH_JSON}"
import json,sys,urllib.request

auth = json.loads(sys.argv[1])
req = urllib.request.Request(
    "http://localhost:8000/api/v1/auth/login",
    data=json.dumps(auth).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=15) as resp:
    payload = json.loads(resp.read().decode())
print(payload.get("access_token", ""))
PY
)

if [[ -z "${TOKEN}" ]]; then
  echo "[FAIL] admin login produced empty token"
  echo "       impact: governance/replay protected verification unavailable"
  exit 1
fi

for protected in \
  "http://localhost:8000/health/runtime-overview" \
  "http://localhost:8000/api/v1/charter/summary" \
  "http://localhost:8000/api/v1/tasks/queue/stats"; do
  code=$(curl -s -o /tmp/aura_verify_body -w "%{http_code}" -H "Authorization: Bearer ${TOKEN}" "$protected")
  if [[ "$code" != "200" ]]; then
    echo "[FAIL] ${protected} returned HTTP ${code}"
    echo "       impact: operator control and runtime evidence visibility incomplete"
    exit 1
  fi
  echo "[PASS] ${protected}"
done

# DB and migrations verification through core container context
MIGRATION_COUNT=$(docker compose "${COMPOSE_ARGS[@]}" exec -T aura-core python - <<'PY'
import sqlite3
con = sqlite3.connect('/data/aura.db')
cur = con.cursor()
cur.execute("SELECT COUNT(*) FROM _migrations")
print(cur.fetchone()[0])
con.close()
PY
)

if [[ -z "${MIGRATION_COUNT}" || "${MIGRATION_COUNT}" == "0" ]]; then
  echo "[FAIL] migration table is empty"
  echo "       impact: schema reproducibility and replay/governance correctness unverified"
  exit 1
fi

echo "[PASS] migration count=${MIGRATION_COUNT}"

RUN_TS=$(date -u +"%Y%m%dT%H%M%SZ")
REPORT_PATH="${EVIDENCE_DIR}/${RUN_TS}-runtime-verify.json"

RUNTIME_OVERVIEW=$(curl -fsS -H "Authorization: Bearer ${TOKEN}" "http://localhost:8000/health/runtime-overview")
READY=$(curl -fsS "http://localhost:8000/health/ready")
WS_HEALTH=$(curl -fsS "http://localhost:8001/health")
LLM_HEALTH=$(curl -fsS "http://localhost:8002/health")

python3 - <<'PY' "${REPORT_PATH}" "${MIGRATION_COUNT}" "${RUNTIME_OVERVIEW}" "${READY}" "${WS_HEALTH}" "${LLM_HEALTH}"
import json, sys
from datetime import datetime, timezone

report_path, migration_count, runtime_overview, ready, ws_health, llm_health = sys.argv[1:7]
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "migration_count": int(migration_count),
    "core_ready": json.loads(ready),
    "runtime_overview": json.loads(runtime_overview),
    "ws_health": json.loads(ws_health),
    "llm_health": json.loads(llm_health),
    "status": "pass",
}
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
print(report_path)
PY

echo "[PASS] runtime verification evidence written"
echo "       ${REPORT_PATH}"
