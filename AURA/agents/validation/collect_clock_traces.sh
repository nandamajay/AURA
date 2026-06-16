#!/usr/bin/env bash
set -euo pipefail

OUTDIR=""
DURATION=900
STRESS_CMD=""
TRACEFS=""

usage() {
  cat <<USAGE
Usage: $0 --output DIR [--duration SEC] [--stress-cmd CMD]

Collect clock framework traces and related PM/ASoC/SoundWire tracepoints.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTDIR="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --stress-cmd) STRESS_CMD="$2"; shift 2 ;;
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
  require_cmd grep
  require_cmd cp
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
}

preflight
mkdir -p "$OUTDIR"

TRACE_LOG="$OUTDIR/clock_trace.txt"
SUMMARY="$OUTDIR/clock_trace_summary.txt"

[[ -r /sys/kernel/debug/clk/clk_summary ]] && cp /sys/kernel/debug/clk/clk_summary "$OUTDIR/clk_summary_before.txt" || true
[[ -r /sys/kernel/debug/pm_genpd/summary ]] && cp /sys/kernel/debug/pm_genpd/summary "$OUTDIR/pm_genpd_before.txt" || true
[[ -r /sys/kernel/debug/regulator/regulator_summary ]] && cp /sys/kernel/debug/regulator/regulator_summary "$OUTDIR/regulator_before.txt" || true

if [[ -d /sys/kernel/debug/soundwire ]]; then
  mkdir -p "$OUTDIR/soundwire_before"
  cp -r /sys/kernel/debug/soundwire/* "$OUTDIR/soundwire_before/" 2>/dev/null || true
fi

# Reset trace config
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

# Required clock + power events
enable_event clk clk_enable
enable_event clk clk_disable
enable_event clk clk_set_rate
enable_event clk clk_set_parent
enable_event power pm_runtime_suspend
enable_event power pm_runtime_resume
enable_event power pm_runtime_idle

# Optional ASoC + SoundWire events
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

[[ -r /sys/kernel/debug/clk/clk_summary ]] && cp /sys/kernel/debug/clk/clk_summary "$OUTDIR/clk_summary_after.txt" || true
[[ -r /sys/kernel/debug/pm_genpd/summary ]] && cp /sys/kernel/debug/pm_genpd/summary "$OUTDIR/pm_genpd_after.txt" || true
[[ -r /sys/kernel/debug/regulator/regulator_summary ]] && cp /sys/kernel/debug/regulator/regulator_summary "$OUTDIR/regulator_after.txt" || true

if [[ -d /sys/kernel/debug/soundwire ]]; then
  mkdir -p "$OUTDIR/soundwire_after"
  cp -r /sys/kernel/debug/soundwire/* "$OUTDIR/soundwire_after/" 2>/dev/null || true
fi

en_count=$(grep -c 'clk_enable' "$TRACE_LOG" || true)
dis_count=$(grep -c 'clk_disable' "$TRACE_LOG" || true)
set_rate_count=$(grep -c 'clk_set_rate' "$TRACE_LOG" || true)
set_parent_count=$(grep -c 'clk_set_parent' "$TRACE_LOG" || true)
pm_suspend_count=$(grep -c 'pm_runtime_suspend' "$TRACE_LOG" || true)
pm_resume_count=$(grep -c 'pm_runtime_resume' "$TRACE_LOG" || true)

{
  echo "CLK_ENABLE_COUNT=$en_count"
  echo "CLK_DISABLE_COUNT=$dis_count"
  echo "CLK_SET_RATE_COUNT=$set_rate_count"
  echo "CLK_SET_PARENT_COUNT=$set_parent_count"
  echo "PM_RUNTIME_SUSPEND_COUNT=$pm_suspend_count"
  echo "PM_RUNTIME_RESUME_COUNT=$pm_resume_count"
  echo "TRACE_LOG=$TRACE_LOG"
} > "$SUMMARY"

echo "Clock trace collection complete: $OUTDIR"
