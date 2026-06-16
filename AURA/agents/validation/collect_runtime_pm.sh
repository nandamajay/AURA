#!/usr/bin/env bash
set -euo pipefail

OUTDIR=""
DURATION=900
STRESS_CMD=""
TARGET_REGEX='lpass|va.*macro|qcom.*va|snd.*soc.*va'
TRACEFS=""

usage() {
  cat <<USAGE
Usage: $0 --output DIR [--duration SEC] [--stress-cmd CMD] [--target-regex REGEX]

Collect runtime PM traces, device runtime PM state snapshots, and kernel error deltas.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTDIR="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --stress-cmd) STRESS_CMD="$2"; shift 2 ;;
    --target-regex) TARGET_REGEX="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "$OUTDIR" ]]; then
  usage; exit 1
fi

require_cmd() {
  local cmd="$1"
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing dependency: $cmd" >&2
    exit 3
  }
}

detect_tracefs() {
  if [[ -n "${TRACEFS:-}" && -d "$TRACEFS" ]]; then
    echo "$TRACEFS"
    return 0
  fi
  for p in /sys/kernel/tracing /sys/kernel/debug/tracing; do
    if [[ -d "$p" ]]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

preflight() {
  require_cmd dmesg
  require_cmd find
  require_cmd grep
  require_cmd tail
  require_cmd cp
  require_cmd dirname
  require_cmd date

  TRACEFS="$(detect_tracefs)" || {
    echo "Tracefs not found. Checked: /sys/kernel/tracing, /sys/kernel/debug/tracing" >&2
    exit 3
  }

  for n in tracing_on current_tracer trace set_event; do
    if [[ ! -w "$TRACEFS/$n" ]]; then
      echo "Tracefs control is not writable: $TRACEFS/$n (run as root)" >&2
      exit 3
    fi
  done

  dmesg >/dev/null 2>&1 || {
    echo "Cannot read dmesg (kernel.dmesg_restrict or permissions)." >&2
    exit 3
  }
}

preflight
mkdir -p "$OUTDIR"

RUNTIME_BEFORE="$OUTDIR/runtime_pm_before.txt"
RUNTIME_AFTER="$OUTDIR/runtime_pm_after.txt"
TRACE_LOG="$OUTDIR/runtime_pm_trace.txt"
DMESG_DELTA="$OUTDIR/dmesg_delta.txt"
SUMMARY="$OUTDIR/runtime_pm_summary.txt"
GENPD_SUMMARY="$OUTDIR/pm_genpd_summary.txt"

if [[ -r /sys/kernel/debug/pm_genpd/summary ]]; then
  cp /sys/kernel/debug/pm_genpd/summary "$GENPD_SUMMARY" || true
fi

collect_runtime_snapshot() {
  local out="$1"
  {
    echo "timestamp=$(date -Is)"
    find /sys/devices -type f -name runtime_status 2>/dev/null | grep -Ei "$TARGET_REGEX" | while read -r f; do
      d=$(dirname "$f")
      echo "[device] $d"
      for k in runtime_status runtime_usage runtime_active_time runtime_suspended_time runtime_enabled control autosuspend_delay_ms; do
        [[ -r "$d/$k" ]] && echo "  $k=$(cat "$d/$k" 2>/dev/null || echo NA)"
      done
    done
  } > "$out"
}

collect_runtime_snapshot "$RUNTIME_BEFORE"

before_lines=$(dmesg | wc -l)

# Reset tracing
if [[ -d "$TRACEFS" ]]; then
  echo 0 > "$TRACEFS/tracing_on"
  echo nop > "$TRACEFS/current_tracer"
  : > "$TRACEFS/trace"
  : > "$TRACEFS/set_event"
fi

enable_event() {
  local grp="$1"
  local ev="$2"
  local p="$TRACEFS/events/$grp/$ev/enable"
  [[ -w "$p" ]] && echo 1 > "$p"
}

# Required power events
enable_event power pm_runtime_suspend
enable_event power pm_runtime_resume
enable_event power pm_runtime_idle

# Optional ASoC and SoundWire events
for p in "$TRACEFS/events/asoc"/*/enable "$TRACEFS/events/snd_soc"/*/enable "$TRACEFS/events/soundwire"/*/enable "$TRACEFS/events/sdw"/*/enable; do
  [[ -w "$p" ]] && echo 1 > "$p"
done

stress_pid=""
if [[ -n "$STRESS_CMD" ]]; then
  bash -lc "$STRESS_CMD" > "$OUTDIR/stress_stdout.log" 2> "$OUTDIR/stress_stderr.log" &
  stress_pid=$!
fi

echo 1 > "$TRACEFS/tracing_on"
sleep "$DURATION"
echo 0 > "$TRACEFS/tracing_on"

[[ -n "$stress_pid" ]] && kill "$stress_pid" >/dev/null 2>&1 || true

cp "$TRACEFS/trace" "$TRACE_LOG"

collect_runtime_snapshot "$RUNTIME_AFTER"

after_lines=$(dmesg | wc -l)
if (( after_lines > before_lines )); then
  dmesg | tail -n +$((before_lines + 1)) > "$DMESG_DELTA"
else
  : > "$DMESG_DELTA"
fi

warn_count=$(grep -Eic 'WARNING:|\bWARN\b' "$DMESG_DELTA" || true)
oops_count=$(grep -Eic 'Oops:' "$DMESG_DELTA" || true)
bug_count=$(grep -Eic '\bBUG:' "$DMESG_DELTA" || true)
calltrace_count=$(grep -Eic 'Call Trace:' "$DMESG_DELTA" || true)
pm_suspend_events=$(grep -c 'pm_runtime_suspend' "$TRACE_LOG" || true)
pm_resume_events=$(grep -c 'pm_runtime_resume' "$TRACE_LOG" || true)

{
  echo "WARN_COUNT=$warn_count"
  echo "OOPS_COUNT=$oops_count"
  echo "BUG_COUNT=$bug_count"
  echo "CALL_TRACE_COUNT=$calltrace_count"
  echo "PM_RUNTIME_SUSPEND_EVENTS=$pm_suspend_events"
  echo "PM_RUNTIME_RESUME_EVENTS=$pm_resume_events"
  echo "TRACE_LOG=$TRACE_LOG"
} > "$SUMMARY"

echo "Runtime PM collection complete: $OUTDIR"
