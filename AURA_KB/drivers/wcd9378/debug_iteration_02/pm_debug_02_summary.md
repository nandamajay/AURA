# WCD9378 Debug Iteration 02 - PM Summary

1. Three failure signatures and root causes
- Signature 1: TX SoundWire slave (`sdw:3:...:3`) remains `UNATTACHED`; root cause is runtime attach/enumeration not completing on TX bus.
- Signature 2: HPH controls missing in ALSA (`Cannot find element`); root cause was no HPH kcontrols/widgets/routes in the prototype component registration.
- Signature 3: SWR CMD errors during playback (`qcom_swrm_irq_handler ... CMD error`); root cause chain is incomplete HPH path enablement plus suspicious `ch_count` derivation in SDW hw_params.

2. Fix 1 change and upstream acceptability
- Probe now keeps TX as non-fatal degraded mode when TX remains `UNATTACHED` after timeout, tracked via `tx_slave_ready`.
- TX-dependent capture paths are gated on `tx_slave_ready` rather than forcing full probe failure.
- This follows the upstream pattern of avoiding hard-fail for optional/deferred sub-path readiness while preserving explicit logs.

3. Fix 2 change and why controls were missing
- Added HPH-oriented kcontrols, HPH DAPM widgets, and explicit HPH routes into the component driver registration.
- Controls were missing because only a minimal endpoint stub was previously registered, without analog HPH control/widget graph entries.

4. Fix 3 change and ch_count anomaly
- `wcd9378_sdw_hw_params()` now computes per-port channel count with `hweight_long(ch_mask)` and sums into total `ch_count`.
- Prior logic initialized `ch_count` to 1 and incremented in a set-bit loop, which can overcount (e.g., stereo mask `0x3` leading to `3`).

5. Added debug instrumentation and what it shows
- Probe logs now print `tx_slave_ready` and registered DAPM/kcontrol counts.
- SDW hw_params logs now print stream/rate/ch_mask/ch_count plus per-port mapping.
- HPH/CLSH event callbacks now print PRE/POST power events.
- `wcd9378_dump_hph_state()` dumps key HPH-related register snapshots at probe and HPH enable entry.

6. Expected outcome after applying all three fixes
- Card probe should continue in RX-only degraded mode even when TX stays unattached.
- HPH mixer controls should appear in `amixer`.
- Playback debug should produce actionable PA/CLSH/HPH-state traces and corrected channel-count logs.
- No playback/capture success is claimed until board retest confirms.

7. Remaining fail-closed items
- TX attach root cause and final TX runtime recovery remain unresolved.
- Final hardware-accurate HPH register semantics remain to be validated on board.
- MBHC/capture full readiness remains gated on TX attach.
- End-to-end playback quality and SWR CMD-error elimination remain pending runtime evidence.

8. Recommended next human action
- Reboot with this build, run `board_debug_commands.md`, and share full `amixer -c 0 contents`, full `dmesg` (boot through aplay), all `sdw:* /status`, and `aplay -vv` output for the next targeted iteration.
