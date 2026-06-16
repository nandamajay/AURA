#!/usr/bin/env bash
set -euo pipefail

OUTDIR=""
DURATION=600
INTERVAL_MS=200
SENSOR_FILE=""

usage() {
  cat <<USAGE
Usage: $0 --output DIR [--duration SEC] [--interval-ms MS] [--sensor-file FILE]

Collect power samples from available sysfs power sensors.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTDIR="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --interval-ms) INTERVAL_MS="$2"; shift 2 ;;
    --sensor-file) SENSOR_FILE="$2"; shift 2 ;;
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

preflight() {
  require_cmd find
  require_cmd awk
  require_cmd sort
  require_cmd date
  require_cmd cat
}

preflight

mkdir -p "$OUTDIR"
CSV="$OUTDIR/power_samples.csv"
META="$OUTDIR/power_metadata.txt"

mapfile -t sensors < <(
  {
    if [[ -n "$SENSOR_FILE" && -f "$SENSOR_FILE" ]]; then
      cat "$SENSOR_FILE"
    fi
    find /sys/class/power_supply -type f -name power_now 2>/dev/null || true
    find /sys/bus/iio/devices -type f -name 'in_power*_input' 2>/dev/null || true
    find /sys/class/hwmon -type f -name 'power*_input' 2>/dev/null || true
  } | awk 'NF' | sort -u
)

if [[ ${#sensors[@]} -eq 0 ]]; then
  echo "No power sensors found." >&2
  exit 2
fi

{
  echo "timestamp: $(date -Is)"
  echo "kernel: $(uname -a)"
  echo "duration_sec: $DURATION"
  echo "interval_ms: $INTERVAL_MS"
  echo "sensors_count: ${#sensors[@]}"
  echo "sensors:"
  printf '  %s\n' "${sensors[@]}"
  echo "cpufreq_governors:"
  find /sys/devices/system/cpu -type f -name scaling_governor 2>/dev/null | while read -r g; do
    echo "  $g=$(cat "$g" 2>/dev/null || echo NA)"
  done
  echo "thermal_zones:"
  find /sys/class/thermal -maxdepth 2 -type f -name temp 2>/dev/null | while read -r t; do
    echo "  $t=$(cat "$t" 2>/dev/null || echo NA)"
  done
} > "$META"

echo "timestamp_ms,sensor_path,value_raw" > "$CSV"

start_ns=$(date +%s%N)
end_ns=$(( start_ns + DURATION * 1000000000 ))
interval_ns=$(( INTERVAL_MS * 1000000 ))

while (( $(date +%s%N) < end_ns )); do
  ts_ms=$(date +%s%3N)
  for s in "${sensors[@]}"; do
    if [[ -r "$s" ]]; then
      v=$(cat "$s" 2>/dev/null || echo NA)
      echo "$ts_ms,$s,$v" >> "$CSV"
    fi
  done
  sleep_sec=$(awk -v n="$interval_ns" 'BEGIN{printf "%.6f", n/1000000000}')
  sleep "$sleep_sec"
done

echo "Collected power samples: $(wc -l < "$CSV") lines"
