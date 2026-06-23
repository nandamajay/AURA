# WCD9378 Debug Iteration 02 — Board Commands

## Step 1 — Check card and controls at boot

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

## Step 2 — Enable dynamic debug for targeted subsystems

```bash
# Enable all wcd9378 debug messages
echo "module snd_soc_wcd9378 +p" > /sys/kernel/debug/dynamic_debug/control

# Enable soundwire debug
echo "module snd_soc_qcom_soundwire +p" > /sys/kernel/debug/dynamic_debug/control

# Enable DAPM debug (shows widget power transitions)
echo "1" > /sys/kernel/debug/asoc/wcd9378-codec/dapm_pop_time
```

## Step 3 — Run playback with full dmesg capture

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
# HPH analog path
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

## Step 4 — Register dump after playback attempt

```bash
# Read key HPH registers via debugfs (if regmap debugfs is enabled)
cat /sys/kernel/debug/regmap/*/registers 2>/dev/null | \
  grep -E "^30[0-9a-f][0-9a-f]: " | head -40

# Or use amixer readback path in prototype
amixer -c 0 cget name='HPHL Volume'
amixer -c 0 cget name='HPHR Volume'
amixer -c 0 cget name='RX HPH Mode'
```

## Step 5 — What to send back for next iteration

Collect and share:
1. `amixer -c 0 contents` full output (before amixer sequence)
2. `dmesg` from boot to after aplay (full, not truncated)
3. `cat /sys/bus/soundwire/devices/sdw:*/status` for all slaves
4. `aplay` output with `-vv`
5. Any `HPH_STATE:` lines from dmesg
6. Any `HPHL PA:` / `HPHR PA:` lines from dmesg
