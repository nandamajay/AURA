#!/usr/bin/env bash
# Unified stabilization validation runner (container-authoritative Python 3.12).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WRAPPER="${ROOT_DIR}/scripts/aura_container_exec.sh"
BUILD_IMAGE=1
VALIDATOR_ARGS=()

usage() {
  cat <<USAGE
Usage: ./scripts/aura_validate.sh [options] [-- <validator args>]

Runs (inside deterministic Python 3.12 container):
- environment validation
- runtime contract validation
- replay integrity hardening checks
- dashboard build validation

Options:
  --no-image-build      Do not rebuild container image before run
  --python <bin>        Deprecated; host python is not used
  --help                Show this message

Artifacts:
- docs/operations/transport/*.json
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-image-build)
      BUILD_IMAGE=0
      shift
      ;;
    --python)
      echo "[WARN] --python is ignored. Validation always runs in container Python 3.12."
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        VALIDATOR_ARGS+=("$1")
        shift
      done
      ;;
    *)
      VALIDATOR_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -x "${WRAPPER}" ]]; then
  echo "[FAIL] Missing deterministic wrapper: ${WRAPPER}" >&2
  exit 1
fi

VALIDATOR_CMD=(python scripts/aura_validation.py "${VALIDATOR_ARGS[@]}")
printf -v QUOTED_CMD '%q ' "${VALIDATOR_CMD[@]}"

WRAPPER_ARGS=()
if [[ "${BUILD_IMAGE}" -eq 1 ]]; then
  WRAPPER_ARGS+=(--build)
fi

echo "[INFO] validator runtime: container python3.12"
"${WRAPPER}" "${WRAPPER_ARGS[@]}" -- "${QUOTED_CMD% }"
echo "[INFO] reports written under: ${ROOT_DIR}/../docs/operations/transport"
