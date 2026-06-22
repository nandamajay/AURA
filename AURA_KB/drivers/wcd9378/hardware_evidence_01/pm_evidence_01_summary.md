# PM Evidence 01 Summary — WCD9378 TX UNATTACHED

## 1. What was confirmed by the hardware log?
- SoundWire identity is confirmed for both endpoints: `sdw:2:0:0217:0110:00:4` (RX) and `sdw:3:0:0217:0110:00:3` (TX).
- Manufacturer/part tuple is confirmed as `0x0217/0x0110`.
- Both slaves bound to `wcd9378-codec` component before probe timeout.
- RX is `Attached` while TX is `UNATTACHED` at probe time.
- Probe fails with `-110` at `snd_soc_component_probe()`, and card instantiation fails.
- A warning is present on TX controller path: `dout-ports (0) mismatch with controller (1)`.

## 2. What is the root cause of the -110 failure?
- The codec probe waits on TX `initialization_complete`, but TX is `UNATTACHED`, so completion is not signaled and timeout occurs.
- `drivers/soundwire/bus.c` shows enumeration and initialization completions are tied to slave status transitions; with TX not staying attached, probe blocks until timeout.

## 3. What was changed in A.1 and why?
- Replaced `WCD9378_CANDIDATE_*` identity macros with confirmed `WCD9378_SDW_PART_ID` and `WCD9378_SDW_COMPATIBLE` based on hardware evidence.
- Added TX `enumeration_complete` wait before `initialization_complete` in codec probe so re-attach has a deterministic wait window.
- Moved `pm_runtime_resume_and_get(dev)` before TX waits and kept runtime PM active through wait/regmap/class-H init path to reduce TX detach risk during probe window.
- Added explicit timeout error logs for TX enumeration/initialization timeouts.

## 4. What still needs board re-test?
- Re-run ELIZA EVK boot/probe and verify TX reaches `Attached` and `initialization_complete` fires.
- Re-check whether card instantiation still fails with `-110`.
- If card instantiates, run the playback/capture sequence (amixer + aplay/arecord) and capture full logs.

## 5. What remains fail-closed after this fix?
- Paging runtime validation.
- Class-H enum/base/runtime confirmation.
- LPASS PM-runtime/mclk event decision.
- Reset/re-enumeration recovery strategy.
- Playback/capture functional validation.
- Board DTS runtime finalization.

## 6. Is this ready to send as RFC to alsa-devel?
- Not for functional RFC claims yet. It is suitable only as a compile/static evidence update with explicit runtime fail-closed caveats.
- Runtime success (playback/capture/card bring-up) is still unproven until board re-test passes.
