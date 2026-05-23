#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="${1:-aura_tests}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is not installed. Please install tmux or run loop scripts manually." >&2
  exit 1
fi

cd "${REPO_ROOT}"

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  echo "tmux session '${SESSION_NAME}' already exists. Attach with: tmux attach -t ${SESSION_NAME}"
  exit 0
fi

tmux new-session -d -s "${SESSION_NAME}" -n "boot" "bash scripts/loop_cognition_boot.sh"
tmux new-window -t "${SESSION_NAME}" -n "stability" "bash scripts/loop_stability_offline.sh"
tmux new-window -t "${SESSION_NAME}" -n "quarantine" "bash scripts/loop_event_quarantine.sh"

echo "Started tmux session '${SESSION_NAME}' with 3 windows: boot, stability, quarantine"
echo "Attach: tmux attach -t ${SESSION_NAME}"
echo "Stop all: tmux kill-session -t ${SESSION_NAME}"
