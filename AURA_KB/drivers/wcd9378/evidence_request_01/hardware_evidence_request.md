# WCD9378 Hardware Evidence Request 01

Date: 2026-06-20  
Owner: AURA conversion governance  
Status: REQUIRED before WCD9378 conversion start (current state: NO-GO)

## Scope
This request is to resolve current fail-closed blockers from:
- `AURA_KB/drivers/wcd9378/blocker_burndown_01/conversion_gate_preconditions.json`
- `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/*.json`

Please collect the exact evidence below and return raw logs plus command history.

## Delivery Package
Please provide a single bundle containing:
- `commands.txt` (exact commands run)
- `kernel_version.txt` (`uname -a`)
- `dmesg_boot.log`
- `dmesg_runtime.log`
- `sysfs_soundwire_snapshot.txt`
- `trace_sdw_paging.log`
- `trace_clsh.log`
- `regmap_before_after/` dumps
- `board_dts.patch`
- `runtime_playback_capture_report.md`

## Evidence Requests

### WCD9378-EVID-001: SoundWire boot enumeration + identity
Blockers resolved:
- `SDW_SLAVE_ENTRY(0x0217, 0x110, 0)` justification (UNCHANGED_FAIL_CLOSED)
- `sdw20217011000` compatible justification (UNCHANGED_FAIL_CLOSED)
- SDW numeric identity precondition (FAIL_CLOSED)

Why required:
- Current blockers require hardware-proven SDW manufacturer/part/class data before upstream ID table or compatible values can be accepted.

Exact outputs requested:
```bash
uname -a > kernel_version.txt
journalctl -b -k > dmesg_boot.log

grep -Ei "soundwire|sdw|wcd9378|wcd" dmesg_boot.log > dmesg_boot_sdw_extract.log

{
  echo "== /sys/bus/soundwire/devices snapshot =="
  for d in /sys/bus/soundwire/devices/*; do
    [ -d "$d" ] || continue
    echo "## $d"
    ls -1 "$d"
    for f in modalias mfg_id manf_id part_id class_id version_id sdw_version dev_num unique_id; do
      [ -f "$d/$f" ] && echo "$f=$(cat "$d/$f")"
    done
  done
} > sysfs_soundwire_snapshot.txt
```

Acceptance criteria:
- Logs show RX/TX WCD9378 SoundWire devices from boot.
- At least one source provides manufacturer ID + part ID + class/version/dev_num or equivalent tuple information.
- Enough data exists to derive and defend final `SDW_SLAVE_ENTRY(...)` and DT-compatible string mapping.

### WCD9378-EVID-002: SDW paging transaction proof (> 0xffff)
Blockers resolved:
- Paging requirement for high addresses (`0x40180000+`) (NOT_COVERED_BY_DATASHEET)
- `pdev->prop.paging_support = true` justification (NOT_COVERED_BY_DATASHEET)

Why required:
- Datasheet did not provide software-visible paging/register-domain proof; conversion must use runtime evidence.

Exact outputs requested:
```bash
# 1) Enable tracing
mount -t debugfs none /sys/kernel/debug 2>/dev/null || true

echo nop > /sys/kernel/debug/tracing/current_tracer
echo 0 > /sys/kernel/debug/tracing/tracing_on
: > /sys/kernel/debug/tracing/trace

# 2) Capture function path used by SDW message build + controller xfer
for f in sdw_fill_msg qcom_swrm_xfer_msg; do
  echo "$f" >> /sys/kernel/debug/tracing/set_ftrace_filter
done

echo function > /sys/kernel/debug/tracing/current_tracer
echo 1 > /sys/kernel/debug/tracing/tracing_on

# 3) Run one playback + one capture cycle that triggers codec register traffic
# (use actual working commands for your board)
# aplay ...
# arecord ...

echo 0 > /sys/kernel/debug/tracing/tracing_on
cat /sys/kernel/debug/tracing/trace > trace_sdw_paging.log
```

Also provide any regmap dump proving accesses above `0xffff` (before/after runtime activity).

Acceptance criteria:
- Trace includes `sdw_fill_msg` and `qcom_swrm_xfer_msg` during WCD9378 traffic.
- Evidence includes high-address transactions requiring paging semantics.
- Evidence is sufficient to decide if `paging_support=true` is mandatory.

### WCD9378-EVID-003: Qualcomm SoundWire controller change necessity
Blockers resolved:
- Need for `drivers/soundwire/qcom.c` changes (UNCHANGED_FAIL_CLOSED)

Why required:
- We cannot upstream controller changes unless there is reproducible failure evidence on upstream path.

Exact outputs requested:
```bash
# During the same run as EVID-002, capture controller errors/timeouts
journalctl -b -k | grep -Ei "soundwire|swrm|timeout|irq|xfer|nack|error" > dmesg_swrm_errors.log
```
If available, include controller tracepoint output for transfer failures/retries.

Acceptance criteria:
- Either: no controller failures observed (supports no core patch requirement), or
- Reproducible controller failures with clear signature and steps (supports core patch need).

### WCD9378-EVID-004: Class-H runtime register trace
Blockers resolved:
- WCD9378 Class-H enum/base decision (FAIL_CLOSED)
- Dynamic `ana_base` claim (UNCHANGED_FAIL_CLOSED)
- WCD9378-specific Class-H register-domain proof (NOT_COVERED_BY_DATASHEET)

Why required:
- Datasheet confirms Class-H features but not software-visible register base/domain mapping used by Linux class-h logic.

Exact outputs requested:
```bash
# Capture dmesg while toggling headphone path / Class-H related controls
journalctl -kf > dmesg_runtime.log

# In a second shell: run board-specific amixer sequence for HPH + playback on/off
# amixer -c <card> ...
# aplay -D <device> <audio.wav>
# stop playback

# Capture regmap snapshots before/after sequence
mkdir -p regmap_before_after
# Replace with actual regmap debugfs paths for WCD9378
# cat /sys/kernel/debug/regmap/<wcd9378-node>/registers > regmap_before_after/registers_before.txt
# cat /sys/kernel/debug/regmap/<wcd9378-node>/registers > regmap_before_after/registers_after.txt
```

Acceptance criteria:
- Trace/dump shows concrete register writes for Class-H/flyback/HPH enable and disable transitions.
- Data is sufficient to determine whether existing `WCD937X` class-h path is reusable or WCD9378-specific enum/base handling is needed.

### WCD9378-EVID-005: Runtime playback/capture/mute validation
Blockers resolved:
- Runtime evidence precondition (MISSING)
- Unresolved mute-path issue

Why required:
- Conversion cannot claim behavior or lifecycle correctness without runtime proof.

Exact outputs requested:
```bash
# Save full control state before and after
amixer -c <card> contents > amixer_before.txt

# Playback test
aplay -D <playback_dev> -r 48000 -c 2 -f S16_LE <known_audio.wav> > playback.log 2>&1

# Capture test (AMIC1 path)
arecord -D <capture_dev> -r 48000 -c 1 -f S16_LE -d 10 amic1.wav > capture.log 2>&1

amixer -c <card> contents > amixer_after.txt
```
Also include pass/fail notes for mute persistence and exact reproduction steps.

Acceptance criteria:
- Deterministic playback and capture results with corresponding logs.
- Mute issue status explicitly documented as PASS/FAIL/INTERMITTENT with reproduction steps.

### WCD9378-EVID-006: Board DTS/DTSI proof package
Blockers resolved:
- Board DTS inputs precondition (MISSING)
- Binding compatibility finalization (PARTIAL/FAIL_CLOSED)

Why required:
- Current blockers require separation of board-specific wiring from generic upstream driver requirements.

Exact outputs requested:
```bash
# Provide exact DTS/DTSI patch used for bring-up
# (if under git)
git diff -- '*.dts' '*.dtsi' > board_dts.patch

# If not under git, provide full DTS snippets in dts_snippets.txt
```
Include exact nodes/properties for:
- reset GPIO
- supplies
- `qcom,rx-device` / `qcom,tx-device`
- RX/TX port mapping
- DAI links
- pinctrl for RX/TX SWR

Acceptance criteria:
- Patch/snippets are complete enough to replay board configuration.
- Board-only properties are clearly distinguished from upstream-generic binding requirements.

## Completion Rule
If any P0 evidence item is missing or inconclusive, conversion remains NO-GO and blockers stay fail-closed.
