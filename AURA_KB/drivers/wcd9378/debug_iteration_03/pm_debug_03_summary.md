# WCD9378 Debug Iteration 03 - PM Summary

1. Two bugs and exact log evidence
- Bug 1 (register mapping): log shows `ASoC error (-16)` at `soc_component_read_no_lock()` for `0x000030ef`, `0x000030c9`, `0x000030ca`, `0x000030e4`, followed by `HPH_STATE ... =0xf0` sentinel values.
- Bug 2 (DAPM route): log shows `Control not supported for path HPHL PGA -> [Switch] -> HPHL` and `HPHR PGA -> [Switch] -> HPHR`, then `failed to instantiate card -22`.

2. Why register addresses were wrong
- Wrong aliasing: control macros in `wcd9378.h` were mapped to status-register macros (`WCD9378_EAR_STATUS_REG_1`, `WCD9378_HPH_L_STATUS`, `WCD9378_HPH_R_STATUS`, `WCD9378_HPH_SURGE_HPHLR_SURGE_STATUS`) instead of true control-register addresses derived from downstream `wcd9378-registers.h` via `WCD9378_REG()`.

3. Why DAPM route was wrong
- Widget-type mismatch: `HPHL`/`HPHR` are `SND_SOC_DAPM_OUT_DRV_E` (no mixer kcontrol), so using route control name `"Switch"` is invalid. OUT_DRV sink routes must use `NULL` control.

4. Expected outcome after both fixes
- Static expectation: card no longer fails route parsing with `-EINVAL/-22`, and HPH state reads target control-register addresses (`0x1009`, `0x10d9`, `0x1414`, `0x144e`) instead of prior status aliases.
- Runtime remains to be confirmed on board logs.

5. Next likely failure to expect
- TX SoundWire slave may still remain `UNATTACHED`, so TX/capture path and MBHC-related behavior can still stay degraded even if playback card instantiation is fixed.

6. Fail-closed items that remain
- TX attach root cause/resolution remains runtime-dependent.
- Playback success and SWR CMD-error elimination are still pending board evidence.
- No claim of full playback/capture readiness is made from this static fix set.
