# WCD9378 Blocker Burndown 01 — PM Summary

Generated: 2026-06-20 (audit-only, no source modifications)

## 1. Which blockers are now resolved?
- `RESOLVED_READY_FOR_CONVERSION`:
  - Upstream property replacements are clear for reset/phandles/port-mapping/micbias (`qcom,wcd93xx-common.yaml`, `qcom,wcd937x-sdw.yaml`, `wcd937x.c`).
  - Paging requirement is evidenced for WCD9378, and upstream Linux SDW core already supports paging (`bus.c`, `sdw.h`).
  - Downstream SDCA interrupt register usage is clearly identified (`wcd9378.c`, `wcd9378-regmap.c`).

## 2. Which blockers remain fail-closed?
- SDW identity values proposed in notes (`SDW_SLAVE_ENTRY(0x0217, 0x110, 0)` and `sdw20217011000`) are unproven.
- Fallback compatible chain for `qcom,wcd9378-codec` vs `qcom,wcd9370/9375-codec` remains unproven.
- `qcom,swr-tx-port-params` upstream strategy (new binding vs conversion/removal) remains unproven.
- Class-H base/version strategy for WCD9378 remains unproven (fixed `0x3000` path vs WCD9378 address domain).

## 3. Can WCD9378 conversion start?
- **NO-GO** for full conversion start.
- Reason: blocking `FAIL_CLOSED` and `MISSING` items remain in SDW identity and Class-H decision paths.

## 4. If yes, what exact first patch series is allowed?
- Limited pre-conversion prep only:
  1. Binding prep patch draft for `qcom,wcd9378-codec` in `qcom,wcd937x.yaml` (without fallback assertion).
  2. DTS cleanup plan replacing legacy downstream DT properties with upstream schema properties.
  3. No SDW ID or Class-H behavior patch until blocked evidence is obtained.

## 5. If no, what exact evidence is still missing?
- Hardware-enumerated SDW identity for WCD9378 (numeric part-id and OF compatible mapping).
- Runtime proof for paging behavior under upstream Linux SDW stack using WCD9378 high-address register accesses.
- Runtime/reg trace proving whether WCD9378 can reuse existing `WCD937X` Class-H variant or needs dedicated handling.
- Deterministic mapping/evidence for `qcom,swr-tx-port-params` necessity.

## 6. Which friend-note claims were helpful?
- Helpful as hypotheses only:
  - Paging concern was directionally useful; source evidence confirmed paging is relevant.
  - Concern around SDW runtime robustness motivated checking upstream `qcom.c` and `bus.c` retry/IRQ paths.

## 7. Which friend-note claims are dangerous or unverified?
- Dangerous/unverified:
  - Forcing `0x110` / `sdw20217011000` without evidence.
  - Claiming mandatory `qcom.c` core patches before reproducing a real upstream failure.
  - Claiming dynamic Class-H analog base change without proof from runtime traces and shared-module analysis.

## 8. What should be asked from hardware/runtime validation next?
1. Capture SoundWire enumeration logs identifying WCD9378 part-id/compatible mapping.
2. Validate register reads/writes above `0xffff` with paging enabled in upstream-style flow.
3. Capture Class-H related register transactions during HPH/EAR path enable/disable.
4. Provide reproducible playback/capture/mute test logs tied to exact DTS and kernel commit.
