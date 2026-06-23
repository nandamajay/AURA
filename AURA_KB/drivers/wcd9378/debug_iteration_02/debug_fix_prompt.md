# Prompt: WCD9378 Playback Debug — Three Failure Signatures + Enhanced Diagnostics

## Objective

Analyze the three distinct failure signatures from the latest board log, produce
targeted code fixes for each, and add structured debug instrumentation so future
iterations produce actionable evidence instead of repeating the same loop.

All code changes go into:
  `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/`

No other source tree files are modified.

---

## AURA Governance Invariants

| Principle    | Enforcement |
|---|---|
| BOUNDED      | Read only the allowed sources listed below. |
| OBSERVABLE   | Every fix maps to a named failure signature. |
| EXPLAINABLE  | Every change cites the downstream or upstream reference line. |
| REPLAYABLE   | Deterministic JSON + code artifacts only. |
| INTERRUPTIBLE| If a fix requires runtime evidence not yet available, mark FAIL_CLOSED. |
| REVERSIBLE   | KB artifacts only; no kernel source tree modification. |

---

## Allowed Sources

| Source | Purpose |
|---|---|
| `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.c` | Current driver — fix target |
| `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378-sdw.c` | Current SDW driver — fix target |
| `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/wcd9378.h` | Current header — fix target |
| `AURA_KB/drivers/wcd9378/hardware_evidence_01/tx_unattached_rca.json` | Prior RCA |
| `track_b_corpora/audio-kernel-ar/asoc/codecs/wcd9378/wcd9378.c` | LA downstream reference |
| `track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c` | LE upstream reference |
| `track_b_corpora/linux-next/drivers/soundwire/qcom.c` | SWR controller reference |

---

## Forbidden Actions

- Do NOT modify any file outside `AURA_KB/`.
- Do NOT modify the kernel source tree.
- Do NOT claim playback/capture works until board re-test confirms it.
- Do NOT commit `AURA/Makefile`.

---

## Log Analysis — Three Failure Signatures

### Signature 1: TX Slave UNATTACHED (pre-existing, still present)

```
cat /sys/bus/soundwire/devices/sdw:3:0:0217:0110:00:3/status → UNATTACHED
```

TX slave (`sdw:3:0:0217:0110:00:3`) is still UNATTACHED at the time the
amixer/aplay sequence runs. This is the same root cause from `tx_unattached_rca.json`.
The prior fix (enumeration_complete wait + pm_runtime_resume_and_get) has not
yet resolved it. The TX slave is needed for MBHC and capture but NOT for
headset playback — however its UNATTACHED state may be causing the codec
component to be in a degraded state that affects RX path register access.

**Action required:** See Fix 1 below.

---

### Signature 2: WCD9378 HPH controls missing from ALSA mixer

```
amixer: Cannot find the given element from control sysdefault:0
```
for: `HPHL_RDAC Switch`, `HPHR_RDAC Switch`, `HPHL_COMP Switch`,
`HPHR_COMP Switch`, `HPHL Switch`, `HPHR Switch`, `CLSH PA Switch`,
`RX HPH Mode`, `HPHL Volume`, `HPHR Volume`

**Root cause:** The current `wcd9378.c` uses `wcd9378_stub_dapm_widgets[]`
which only has `IN1_HPHL`, `IN2_HPHR`, `IN3_AUX`, `HPHL_OUT`, `HPHR_OUT`,
`AUX_OUT` — it does NOT register the HPH analog path DAPM widgets or kcontrols
(`HPHL_RDAC`, `HPHR_RDAC`, `HPHL PGA`, `HPHR PGA`, `HPHL Switch`, `HPHR Switch`,
`CLSH PA Switch`, `RX HPH Mode`, `HPHL Volume`, `HPHR Volume`).

The downstream `wcd9378.c` registers these in `wcd9378_snd_controls[]` and
`wcd9378_dapm_widgets[]` (lines ~3371–3784). The upstream `wcd938x.c` has the
same pattern.

**Action required:** See Fix 2 below.

---

### Signature 3: SWR CMD error on RX SWR bus during aplay

```
[119.144069] wcd9378-codec sdw:2:0:0217:0110:00:4: sdw_hw_params: is_tx=0 active_ports=1 ch_count=3 rate=48000
[119.161283] wcd9378-codec sdw:2:0:0217:0110:00:4: sdw_hw_params: port[0] num=1 ch_mask=0x3
aplay: pcm_write:2127: write error: Input/output error
[122.944295] qcom-soundwire 6ad0000.soundwire: qcom_swrm_irq_handler: SWR CMD error, fifo status 0x4e00c00f, flushing fifo
```

**Decoded fifo_status 0x4e00c00f:**
- `WR_CMD_FIFO_CNT` (bits 12:8) = 0 — write FIFO empty
- `RD_CMD_FIFO_CNT` (bits 20:16) = 0 — read FIFO empty
- `bits 31:24` = 0x4e — controller internal state
- `INTERRUPT_STATUS` low bits = 0xf:
  - bit0 = `CMD_ERROR` (BIT(7) in interrupt register — a register read/write
    command to the slave failed)
  - The CMD_ERROR fires because the RX slave (`sdw:2`) is ATTACHED but the
    codec driver is trying to write HPH analog registers (RDAC, PA, CLSH) that
    are gated behind the HPH DAPM path — which is not properly enabled because
    the DAPM widgets are missing (Signature 2).

**Root cause chain:**
```
Missing HPH DAPM widgets (Sig 2)
  → amixer HPH controls not found → HPH path not enabled in DAPM
    → aplay triggers hw_params on RX SWR (ch_count=3 is suspicious — should be 2 for stereo HPH)
      → codec tries to write HPH analog regs via SWR CMD
        → SWR CMD fails (slave not ready for analog path) → CMD_ERROR → I/O error
```

**ch_count=3 anomaly:** `sdw_hw_params` reports `ch_count=3` for a stereo
playback. This suggests the port channel mask `0x3` is being interpreted as
3 channels instead of a 2-bit mask for channels 0+1. This needs investigation
in `wcd9378_sdw_hw_params()`.

**Action required:** See Fix 3 below.

---

## Fix 1: TX Slave UNATTACHED — Add Graceful Degraded-Mode Probe

**File:** `wcd9378.c`

**Problem:** The codec probe blocks on TX `initialization_complete` with a
5-second timeout. When TX is UNATTACHED the timeout fires and probe returns
`-ETIMEDOUT` (-110), which causes the sound card to fail instantiation.

**Fix strategy (upstream-acceptable):**
Instead of failing probe on TX timeout, allow the codec to probe in a
degraded mode (RX-only) and re-attempt TX initialization when TX attaches.
This is the pattern used by `wcd938x.c` — it does not hard-fail on TX timeout.

In `wcd9378_soc_codec_probe()` (or equivalent):

```c
/* Wait for TX slave to attach — non-fatal timeout */
ret = wait_for_completion_timeout(&wcd9378->tx_sdw_dev->initialization_complete,
                                  msecs_to_jiffies(WCD9378_SDW_INIT_TIMEOUT_MS));
if (!ret) {
    dev_warn(component->dev,
             "TX slave init timeout — probing in RX-only degraded mode\n");
    wcd9378->tx_slave_ready = false;
    /* Continue probe — TX-dependent paths will be gated by tx_slave_ready */
} else {
    wcd9378->tx_slave_ready = true;
}
```

Add `tx_slave_ready` bool to `struct wcd9378` in `wcd9378.h`.

Gate TX-dependent operations (MBHC init, TX DAPM widgets registration) behind
`wcd9378->tx_slave_ready`.

Reference: `wcd938x.c` probe pattern; downstream `wcd9378.c` lines ~4100–4200.

---

## Fix 2: Add HPH Analog Path DAPM Widgets and kcontrols

**File:** `wcd9378.c`

**Problem:** `wcd9378_stub_dapm_widgets[]` is missing the HPH analog path
widgets. The amixer commands for `HPHL_RDAC Switch`, `HPHR_RDAC Switch`,
`HPHL Switch`, `HPHR Switch`, `CLSH PA Switch`, `RX HPH Mode`, `HPHL Volume`,
`HPHR Volume` all fail with "Cannot find element".

**Fix:** Add the following to `wcd9378.c`, modelled on downstream
`wcd9378.c` lines 3371–3784 and upstream `wcd938x.c`:

### 2a — Add kcontrols array

```c
static const struct snd_kcontrol_new wcd9378_kcontrols[] = {
    SOC_SINGLE_EXT("HPHL_COMP Switch", SND_SOC_NOPM, 0, 1, 0,
                   wcd9378_get_compander, wcd9378_set_compander),
    SOC_SINGLE_EXT("HPHR_COMP Switch", SND_SOC_NOPM, 1, 1, 0,
                   wcd9378_get_compander, wcd9378_set_compander),
    SOC_ENUM_EXT("RX HPH Mode", wcd9378_hph_mode_enum,
                 wcd9378_rx_hph_mode_get, wcd9378_rx_hph_mode_put),
    SOC_SINGLE_TLV("HPHL Volume", WCD9378_CDC_HPH_GAIN_CTL,
                   WCD9378_HPHL_GAIN_SHIFT, WCD9378_HPH_GAIN_MAX, 0,
                   wcd9378_hph_gain_tlv),
    SOC_SINGLE_TLV("HPHR Volume", WCD9378_CDC_HPH_GAIN_CTL,
                   WCD9378_HPHR_GAIN_SHIFT, WCD9378_HPH_GAIN_MAX, 0,
                   wcd9378_hph_gain_tlv),
};
```

If the exact register/shift/max values are not yet in `wcd9378.h`, add them
from the downstream `wcd9378.h` / datasheet.

### 2b — Add HPH DAPM widgets

Add to `wcd9378_stub_dapm_widgets[]` (or replace stub with full widget list):

```c
/* HPH analog path widgets */
SND_SOC_DAPM_MIXER("HPHL_RDAC", SND_SOC_NOPM, 0, 0,
                   wcd9378_hphl_rdac_switch, ARRAY_SIZE(wcd9378_hphl_rdac_switch)),
SND_SOC_DAPM_MIXER("HPHR_RDAC", SND_SOC_NOPM, 0, 0,
                   wcd9378_hphr_rdac_switch, ARRAY_SIZE(wcd9378_hphr_rdac_switch)),
SND_SOC_DAPM_PGA_E("HPHL PGA", SND_SOC_NOPM, 0, 0, NULL, 0,
                   wcd9378_hphl_pga_event,
                   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
SND_SOC_DAPM_PGA_E("HPHR PGA", SND_SOC_NOPM, 0, 0, NULL, 0,
                   wcd9378_hphr_pga_event,
                   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
SND_SOC_DAPM_OUT_DRV_E("HPHL", SND_SOC_NOPM, 0, 0, NULL, 0,
                        wcd9378_hphl_pa_event,
                        SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMU |
                        SND_SOC_DAPM_PRE_PMD | SND_SOC_DAPM_POST_PMD),
SND_SOC_DAPM_OUT_DRV_E("HPHR", SND_SOC_NOPM, 0, 0, NULL, 0,
                        wcd9378_hphr_pa_event,
                        SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMU |
                        SND_SOC_DAPM_PRE_PMD | SND_SOC_DAPM_POST_PMD),
SND_SOC_DAPM_SUPPLY("CLSH PA", SND_SOC_NOPM, 0, 0,
                    wcd9378_clsh_pa_event,
                    SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
```

### 2c — Add DAPM routes for HPH path

```c
/* HPH playback routes */
{ "HPHL_RDAC", "Switch", "IN1_HPHL" },
{ "HPHL PGA",  NULL,     "HPHL_RDAC" },
{ "HPHL",      NULL,     "HPHL PGA" },
{ "HPHL",      NULL,     "CLSH PA" },
{ "HPHR_RDAC", "Switch", "IN2_HPHR" },
{ "HPHR PGA",  NULL,     "HPHR_RDAC" },
{ "HPHR",      NULL,     "HPHR PGA" },
{ "HPHR",      NULL,     "CLSH PA" },
```

### 2d — Implement event callbacks

Implement the following event callbacks in `wcd9378.c`, modelled on
downstream `wcd9378.c` lines 1546–1782 and upstream `wcd938x.c`:

- `wcd9378_hphl_pga_event()` — enable/disable HPHL RX path, RDAC clock,
  compander. Reference: downstream lines ~1546–1610.
- `wcd9378_hphr_pga_event()` — same for HPHR. Reference: downstream ~1614–1680.
- `wcd9378_hphl_pa_event()` — enable/disable HPHL PA, watchdog IRQ.
  Reference: downstream ~1681–1730.
- `wcd9378_hphr_pa_event()` — same for HPHR. Reference: downstream ~1737–1790.
- `wcd9378_clsh_pa_event()` — call `wcd_clsh_ctrl_set_state()` for HPH mode.
  Reference: downstream `wcd9378_enable_clsh()` ~line 640.
- `wcd9378_get_compander()` / `wcd9378_set_compander()` — get/set compander
  enable bit. Reference: downstream ~line 1408–1470.
- `wcd9378_rx_hph_mode_get()` / `wcd9378_rx_hph_mode_put()` — get/set HPH
  mode enum. Reference: downstream ~line 1469–1545.

**Key registers to use (from downstream wcd9378.h / datasheet):**
- `WCD9378_CDC_HPH_GAIN_CTL` — HPHL/HPHR RX enable bits and gain
- `WCD9378_HPH_RDAC_CLK_CTL1` — RDAC clock enable
- `WCD9378_CDC_COMP_CTL_0` — compander enable bits
- `WCD9378_ANA_HPH` — PA enable bits (HPHL_PA_EN, HPHR_PA_EN)

---

## Fix 3: Investigate ch_count=3 in sdw_hw_params

**File:** `wcd9378-sdw.c`

**Problem:** `sdw_hw_params` logs `ch_count=3` for a stereo (2-channel)
playback. The `ch_mask=0x3` is a bitmask (channels 0 and 1 = stereo), but
`ch_count` should be `hweight32(ch_mask) = 2`, not 3.

**Investigation:** In `wcd9378_sdw_hw_params()`, find where `ch_count` is
computed. Check if `hweight32()` is being called correctly on `ch_mask`, or
if `ch_count` is being set to `ch_mask` directly.

Reference: downstream `wcd9378.c` `wcd9378_sdw_hw_params()` ~line 119.

If `ch_count` is being passed as `ch_mask` (0x3) instead of
`hweight32(ch_mask)` (2), fix it:

```c
/* Wrong: */
ch_count = ch_mask;
/* Correct: */
ch_count = hweight32(ch_mask);
```

Also verify the port number `num=1` is correct for the HPH port. The HPH
port should be `WCD9378_HPH_PORT` (port 1 in the downstream). If it is
correct, record as PASS.

---

## Task 1: Read Current Driver State

Before making any changes, read and record the current state of:
1. `wcd9378.c` — current DAPM widget list, kcontrols list, probe function
2. `wcd9378-sdw.c` — current `wcd9378_sdw_hw_params()` implementation
3. `wcd9378.h` — current struct wcd9378 fields

Record in:
`AURA_KB/drivers/wcd9378/debug_iteration_02/pre_fix_state.json`

```json
{
  "dapm_widgets_count": 0,
  "kcontrols_count": 0,
  "hph_widgets_present": false,
  "hph_kcontrols_present": false,
  "tx_slave_ready_field_present": false,
  "ch_count_computation": "unknown | ch_mask | hweight32",
  "probe_tx_timeout_behavior": "hard_fail | degraded_mode"
}
```

---

## Task 2: Apply Fixes

Apply Fix 1, Fix 2, and Fix 3 to the converted driver files.

For each fix, record what was changed:
`AURA_KB/drivers/wcd9378/debug_iteration_02/fix_change_log.json`

```json
[
  {
    "fix_id": "FIX-1",
    "signature": "TX_SLAVE_UNATTACHED",
    "file": "wcd9378.c",
    "change_summary": "...",
    "reference": "wcd938x.c line X / downstream wcd9378.c line Y",
    "upstream_acceptable": true,
    "fail_closed_items": []
  }
]
```

---

## Task 3: Add Enhanced Debug Instrumentation

Add the following `dev_dbg` / `dev_err` statements to make future iterations
produce actionable evidence without needing multiple boot cycles.

### 3a — In `wcd9378_soc_codec_probe()` (wcd9378.c)

```c
dev_info(component->dev, "probe: tx_slave_ready=%d\n", wcd9378->tx_slave_ready);
dev_info(component->dev, "probe: registering %d DAPM widgets, %d kcontrols\n",
         component->driver->num_dapm_widgets,
         component->driver->num_controls);
```

### 3b — In `wcd9378_sdw_hw_params()` (wcd9378-sdw.c)

```c
dev_info(dev, "hw_params: is_tx=%d stream=%s rate=%u ch_mask=0x%x ch_count=%d\n",
         is_tx, stream->name, params_rate(params), ch_mask, ch_count);
for (i = 0; i < active_ports; i++)
    dev_info(dev, "hw_params: port[%d] num=%d ch_mask=0x%x\n",
             i, port_config[i].num, port_config[i].ch_mask);
```

### 3c — In HPH PA event callbacks (wcd9378.c)

```c
/* In wcd9378_hphl_pa_event() PRE_PMU: */
dev_info(component->dev, "HPHL PA: PRE_PMU hph_mode=%d\n", wcd9378->hph_mode);
/* In wcd9378_hphl_pa_event() POST_PMU: */
dev_info(component->dev, "HPHL PA: POST_PMU enabled\n");
/* In wcd9378_hphl_pa_event() POST_PMD: */
dev_info(component->dev, "HPHL PA: POST_PMD disabled\n");
```

Same pattern for HPHR.

### 3d — In `wcd9378_clsh_pa_event()` (wcd9378.c)

```c
dev_info(component->dev, "CLSH PA: event=%d hph_mode=%d\n", event, wcd9378->hph_mode);
```

### 3e — Add a one-shot diagnostic function

Add `wcd9378_dump_hph_state()` callable from probe and from HPH PA event:

```c
static void wcd9378_dump_hph_state(struct snd_soc_component *component)
{
    unsigned int val;

    snd_soc_component_read(component, WCD9378_ANA_HPH, &val);
    dev_info(component->dev, "HPH_STATE: ANA_HPH=0x%02x\n", val);
    snd_soc_component_read(component, WCD9378_CDC_HPH_GAIN_CTL, &val);
    dev_info(component->dev, "HPH_STATE: CDC_HPH_GAIN_CTL=0x%02x\n", val);
    snd_soc_component_read(component, WCD9378_HPH_RDAC_CLK_CTL1, &val);
    dev_info(component->dev, "HPH_STATE: HPH_RDAC_CLK_CTL1=0x%02x\n", val);
    snd_soc_component_read(component, WCD9378_CDC_COMP_CTL_0, &val);
    dev_info(component->dev, "HPH_STATE: CDC_COMP_CTL_0=0x%02x\n", val);
}
```

Call it at end of `wcd9378_soc_codec_probe()` and at start of
`wcd9378_hphl_pa_event()` PRE_PMU.

---

## Task 4: Validation Checklist JSON

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_02/fix_validation_checklist.json`

```json
[
  {
    "id": "DBG2-CHK-001",
    "check": "HPHL_RDAC Switch present in amixer after fix",
    "status": "PENDING_BOARD",
    "how_to_verify": "amixer -c 0 contents | grep HPHL"
  },
  {
    "id": "DBG2-CHK-002",
    "check": "HPHR_RDAC Switch present in amixer after fix",
    "status": "PENDING_BOARD",
    "how_to_verify": "amixer -c 0 contents | grep HPHR"
  },
  {
    "id": "DBG2-CHK-003",
    "check": "HPHL Switch, HPHR Switch, CLSH PA Switch present in amixer",
    "status": "PENDING_BOARD",
    "how_to_verify": "amixer -c 0 contents | grep -E 'HPHL Switch|HPHR Switch|CLSH'"
  },
  {
    "id": "DBG2-CHK-004",
    "check": "RX HPH Mode present in amixer",
    "status": "PENDING_BOARD",
    "how_to_verify": "amixer -c 0 contents | grep 'RX HPH Mode'"
  },
  {
    "id": "DBG2-CHK-005",
    "check": "ch_count=2 (not 3) in sdw_hw_params log for stereo playback",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep sdw_hw_params — expect ch_count=2 ch_mask=0x3"
  },
  {
    "id": "DBG2-CHK-006",
    "check": "No SWR CMD error during aplay after HPH path is properly enabled",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'SWR CMD error' — should be absent"
  },
  {
    "id": "DBG2-CHK-007",
    "check": "TX slave UNATTACHED does not prevent card probe (degraded mode)",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'TX slave init timeout' — card should still instantiate"
  },
  {
    "id": "DBG2-CHK-008",
    "check": "HPH_STATE register dump visible in dmesg at probe time",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep HPH_STATE"
  },
  {
    "id": "DBG2-CHK-009",
    "check": "HPHL PA PRE_PMU log visible during aplay",
    "status": "PENDING_BOARD",
    "how_to_verify": "dmesg | grep 'HPHL PA: PRE_PMU'"
  },
  {
    "id": "DBG2-CHK-010",
    "check": "No kernel source files modified",
    "status": "PASS",
    "how_to_verify": "git diff --name-only — only AURA_KB/ files"
  }
]
```

---

## Task 5: Enhanced Debug Commands for Next Board Run

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_02/board_debug_commands.md`

### Step 1 — Check card and controls at boot

```bash
# Confirm card instantiated
cat /proc/asound/cards

# Dump all mixer controls — save this output every iteration
amixer -c 0 contents 2>&1 | tee /tmp/mixer_dump.txt

# Check SDW slave status
cat /sys/bus/soundwire/devices/sdw:2:0:0217:0110:00:4/status
cat /sys/bus/soundwire/devices/sdw:3:0:0217:0110:00:3/status

# Check dmesg for probe messages
dmesg | grep -E "wcd9378|soundwire|HPH_STATE|HPHL|HPHR|CLSH|sdw_hw_params"
```

### Step 2 — Enable dynamic debug for targeted subsystems

```bash
# Enable all wcd9378 debug messages
echo "module snd_soc_wcd9378 +p" > /sys/kernel/debug/dynamic_debug/control

# Enable soundwire debug
echo "module snd_soc_qcom_soundwire +p" > /sys/kernel/debug/dynamic_debug/control

# Enable DAPM debug (shows widget power transitions)
echo "1" > /sys/kernel/debug/asoc/wcd9378-codec/dapm_pop_time
```

### Step 3 — Run playback with full dmesg capture

```bash
# Clear dmesg first
dmesg -C

# Run amixer sequence
amixer -c 0 cset name='RX_HPH PWR Mode' LOHIFI
amixer -c 0 cset name='RX_MACRO RX0 MUX' AIF1_PB
amixer -c 0 cset name='RX_MACRO RX1 MUX' AIF1_PB
amixer -c 0 cset name='RX INT0_1 MIX1 INP0' RX0
amixer -c 0 cset name='RX INT1_1 MIX1 INP0' RX1
amixer -c 0 cset name='RX INT0_1 INTERP' 'RX INT0_1 MIX1'
amixer -c 0 cset name='RX INT1_1 INTERP' 'RX INT1_1 MIX1'
amixer -c 0 cset name='RX INT0 DEM MUX' CLSH_DSM_OUT
amixer -c 0 cset name='RX INT1 DEM MUX' CLSH_DSM_OUT
amixer -c 0 cset name='RX_COMP1 Switch' 1
amixer -c 0 cset name='RX_COMP2 Switch' 1
amixer -c 0 cset name='RX_RX0 Digital Volume' 84
amixer -c 0 cset name='RX_RX1 Digital Volume' 84
# NEW — HPH analog path (should work after Fix 2)
amixer -c 0 cset name='HPHL_RDAC Switch' 1
amixer -c 0 cset name='HPHR_RDAC Switch' 1
amixer -c 0 cset name='HPHL_COMP Switch' 1
amixer -c 0 cset name='HPHR_COMP Switch' 1
amixer -c 0 cset name='HPHL Switch' 1
amixer -c 0 cset name='HPHR Switch' 1
amixer -c 0 cset name='CLSH PA Switch' 1
amixer -c 0 cset name='RX HPH Mode' CLS_H_ULP
amixer -c 0 cset name='HPHL Volume' 20
amixer -c 0 cset name='HPHR Volume' 20
amixer -c 0 cset iface=MIXER,name='RX_CODEC_DMA_RX_0 Audio Mixer MultiMedia1' 1

# Run aplay
aplay -D plughw:0,0 /test.wav -vv 2>&1 | tee /tmp/aplay_log.txt

# Capture dmesg immediately after
dmesg | tee /tmp/dmesg_after_aplay.txt
```

### Step 4 — Register dump after playback attempt

```bash
# Read key HPH registers via debugfs (if regmap debugfs is enabled)
cat /sys/kernel/debug/regmap/*/registers 2>/dev/null | \
  grep -E "^30[0-9a-f][0-9a-f]: " | head -40

# Or use devmem2 if regmap debugfs not available
# WCD9378 registers are accessed via SWR — use amixer to read back
amixer -c 0 cget name='HPHL Volume'
amixer -c 0 cget name='HPHR Volume'
amixer -c 0 cget name='RX HPH Mode'
```

### Step 5 — What to send back for next iteration

Collect and share:
1. `amixer -c 0 contents` full output (before amixer sequence)
2. `dmesg` from boot to after aplay (full, not truncated)
3. `cat /sys/bus/soundwire/devices/sdw:*/status` for all slaves
4. `aplay` output with `-vv`
5. Any `HPH_STATE:` lines from dmesg (from new debug instrumentation)
6. Any `HPHL PA:` / `HPHR PA:` lines from dmesg

---

## Task 6: PM Summary

Create:
`AURA_KB/drivers/wcd9378/debug_iteration_02/pm_debug_02_summary.md`

Answer:
1. What are the three failure signatures and their root causes?
2. What does Fix 1 change and why is it upstream-acceptable?
3. What does Fix 2 change and why were the controls missing?
4. What does Fix 3 change and what is the ch_count anomaly?
5. What debug instrumentation was added and what will it show?
6. What is the expected outcome after applying all three fixes?
7. What still remains fail-closed after these fixes?
8. What is the recommended next human action?

---

## Task 7: Validate JSON Artifacts

```bash
python3 -m json.tool \
  AURA_KB/drivers/wcd9378/debug_iteration_02/pre_fix_state.json > /dev/null && \
  echo "pre_fix_state.json PASS"

python3 -m json.tool \
  AURA_KB/drivers/wcd9378/debug_iteration_02/fix_change_log.json > /dev/null && \
  echo "fix_change_log.json PASS"

python3 -m json.tool \
  AURA_KB/drivers/wcd9378/debug_iteration_02/fix_validation_checklist.json > /dev/null && \
  echo "fix_validation_checklist.json PASS"
```

Record in:
`AURA_KB/drivers/wcd9378/debug_iteration_02/validation.json`

---

## Task 8: Commit and Push

```bash
git add AURA_KB/drivers/wcd9378/debug_iteration_02/
git add AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/converted/
git commit -m "fix(wcd9378): add HPH DAPM path, fix ch_count, add degraded TX probe mode"
git push origin aura_upstream_learning
git status --short
```

Confirm `AURA/Makefile` is NOT staged.

---

## Success Criteria

- [ ] `pre_fix_state.json` — parse-valid, records current driver state
- [ ] `wcd9378.c` — HPH DAPM widgets + kcontrols + event callbacks added
- [ ] `wcd9378.c` — TX degraded-mode probe (non-fatal timeout) implemented
- [ ] `wcd9378-sdw.c` — ch_count computation verified/fixed
- [ ] `wcd9378.c` — `wcd9378_dump_hph_state()` added and called
- [ ] `fix_change_log.json` — parse-valid, all 3 fixes recorded
- [ ] `fix_validation_checklist.json` — parse-valid, 10 checks present
- [ ] `board_debug_commands.md` — complete step-by-step debug guide
- [ ] `pm_debug_02_summary.md` — answers all 8 questions
- [ ] `validation.json` — parse-valid, all JSON checks PASS
- [ ] No kernel source tree files modified
- [ ] `AURA/Makefile` NOT staged
- [ ] `git push origin aura_upstream_learning` succeeds
