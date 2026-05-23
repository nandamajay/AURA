#!/usr/bin/env bash
# Failure-first environment diagnostics for deterministic AURA operation.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STRICT=0

usage() {
  cat <<USAGE
Usage: ./scripts/env-doctor.sh [--strict]

Checks:
- deterministic dependency prerequisites
- docker/compose availability
- Python 3.12 availability
- .env safety and runtime key configuration
- evidence/data directory presence
- optional local import sanity when .venv exists
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict)
      STRICT=1
      shift
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

FAIL_COUNT=0
WARN_COUNT=0

pass() {
  echo "[PASS] $1"
}

warn() {
  echo "[WARN] $1"
  WARN_COUNT=$((WARN_COUNT + 1))
}

fail() {
  echo "[FAIL] $1"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

impact_note() {
  echo "       impact: $1"
}

env_value() {
  local file="$1"
  local key="$2"
  local value
  value="$(awk -F'=' -v k="$key" '
    BEGIN { found="" }
    /^[[:space:]]*#/ { next }
    NF >= 2 {
      lhs=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", lhs)
      if (lhs == k) {
        $1=""
        sub(/^=/, "", $0)
        found=$0
      }
    }
    END { print found }
  ' "$file")"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  printf "%s" "${value}"
}

check_command() {
  local cmd="$1"
  local label="$2"
  local impact="$3"
  if command -v "$cmd" >/dev/null 2>&1; then
    pass "${label}"
  else
    fail "${label} missing (${cmd})"
    impact_note "${impact}"
  fi
}

echo "AURA Environment Doctor"
echo "======================="

echo "[INFO] root=${ROOT_DIR}"

check_command docker "Docker runtime available" "cannot boot deterministic runtime stack"

if docker compose version >/dev/null 2>&1; then
  pass "Docker Compose available"
else
  fail "Docker Compose unavailable"
  impact_note "single-command startup and CI/runtime parity cannot be validated"
fi

if command -v python3.12 >/dev/null 2>&1; then
  pass "Python 3.12 available"
else
  warn "Python 3.12 not found"
  impact_note "local validation parity will drift from required runtime; containerized runtime remains available"
fi

if [[ -f "${ROOT_DIR}/constraints/py312.txt" ]]; then
  pass "Deterministic constraints file present"
else
  fail "constraints/py312.txt missing"
  impact_note "dependency resolution may drift across environments"
fi

if [[ -f "${ROOT_DIR}/dashboard/package-lock.json" ]]; then
  pass "Frontend lockfile present"
else
  fail "dashboard/package-lock.json missing"
  impact_note "frontend build reproducibility is weakened"
fi

ENV_FILE="${ROOT_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  fail ".env missing"
  impact_note "runtime startup cannot be deterministic without explicit environment"
else
  pass ".env present"
  JWT_SECRET_VALUE="$(env_value "${ENV_FILE}" "JWT_SECRET")"
  LLM_MOCK_MODE_VALUE="$(env_value "${ENV_FILE}" "LLM_MOCK_MODE")"
  LLM_PROVIDER_VALUE="$(env_value "${ENV_FILE}" "LLM_PROVIDER")"
  OPENAI_API_KEY_VALUE="$(env_value "${ENV_FILE}" "OPENAI_API_KEY")"
  QGENIE_API_KEY_VALUE="$(env_value "${ENV_FILE}" "QGENIE_API_KEY")"
  QGENIE_CLI_HOME_VALUE="$(env_value "${ENV_FILE}" "QGENIE_CLI_HOME")"

  if [[ -z "${JWT_SECRET_VALUE}" || "${JWT_SECRET_VALUE}" == "change-me" ]]; then
    fail "JWT_SECRET missing or default"
    impact_note "governance/auth checks are unsafe"
  else
    pass "JWT secret configured"
  fi

  mock_mode="${LLM_MOCK_MODE_VALUE:-false}"
  provider="${LLM_PROVIDER_VALUE:-openai}"
  if [[ "${mock_mode}" == "true" ]]; then
    pass "LLM mock mode enabled (deterministic demo/test friendly)"
  else
    if [[ "${provider}" == "qgenie" ]]; then
      if [[ -n "${QGENIE_API_KEY_VALUE:-}" || ( -n "${QGENIE_CLI_HOME_VALUE:-}" && -d "${QGENIE_CLI_HOME_VALUE}" ) ]]; then
        pass "QGenie runtime credentials/config present"
      else
        fail "QGenie selected but no QGENIE_API_KEY and no QGENIE_CLI_HOME"
        impact_note "LLM calls will fail; replay evidence generation may be incomplete"
      fi
    else
      if [[ -n "${OPENAI_API_KEY_VALUE:-}" ]]; then
        pass "OpenAI API key present"
      else
        fail "OPENAI_API_KEY missing"
        impact_note "agent execution paths needing LLM will fail"
      fi
    fi
  fi
fi

EVIDENCE_DIR="${ROOT_DIR}/evidence"
if [[ ! -d "${EVIDENCE_DIR}" && -d "${ROOT_DIR}/../evidence" ]]; then
  EVIDENCE_DIR="${ROOT_DIR}/../evidence"
fi

for required_dir in "${EVIDENCE_DIR}" "${ROOT_DIR}/data" "${ROOT_DIR}/knowledge/schema"; do
  if [[ -d "${required_dir}" ]]; then
    pass "Directory present: ${required_dir}"
  else
    fail "Directory missing: ${required_dir}"
    impact_note "replay/governance/evidence lifecycle cannot be fully verified"
  fi
done

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  if "${ROOT_DIR}/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import fastapi, aiosqlite, httpx
print(fastapi.__version__)
PY
  then
    pass ".venv has core validation dependencies"
  else
    warn ".venv exists but core imports failed; run ./scripts/env-sync.sh"
    impact_note "local pytest and replay/governance checks may fail"
  fi
else
  warn ".venv missing; run ./scripts/env-sync.sh for deterministic local validation"
  impact_note "local CI parity checks will be unavailable"
fi

echo ""
echo "Summary: fails=${FAIL_COUNT} warnings=${WARN_COUNT}"

if [[ ${FAIL_COUNT} -gt 0 ]]; then
  exit 1
fi

if [[ ${STRICT} -eq 1 && ${WARN_COUNT} -gt 0 ]]; then
  echo "[FAIL] strict mode requires zero warnings"
  exit 1
fi

echo "[PASS] environment diagnostics completed"
