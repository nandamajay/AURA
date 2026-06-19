# WCD9378 Evidence Request + Safe Preconversion Summary

Date: 2026-06-20  
Decision: **NO-GO remains** for full WCD9378 conversion.

## 1) What exact evidence is needed from hardware/runtime?
- SoundWire identity evidence:
  - Boot dmesg enumeration for WCD9378 RX/TX endpoints.
  - Numeric manufacturer/part/class/version/dev_num identity (dmesg/sysfs/modalias).
  - Evidence to justify final `SDW_SLAVE_ENTRY(...)` and SDW compatible string.
- SoundWire paging evidence:
  - Trace proving high-address transactions and paging path use (`sdw_fill_msg`, controller transfer path).
  - Evidence whether `pdev->prop.paging_support = true` is required.
  - Evidence whether controller changes are actually needed or not.
- Class-H evidence:
  - Register trace for HPH/Class-H enable/disable sequences.
  - Concrete address-domain proof for Class-H/flyback/HPH analog writes.
  - Evidence to decide reuse of `WCD937X` class-h path vs WCD9378-specific enum/base.
- Runtime validation:
  - Playback/headset logs and capture/AMIC1 logs with full dmesg.
  - Mute issue status with reproducible steps.
  - Register snapshots before/after reset or runtime suspend.
- Board DTS package:
  - Exact DTS/DTSI patch with reset GPIO, supplies, rx/tx devices, port mapping, pinctrl, and DAI links.

## 2) What can AURA safely prepare now?
- Vendor include/API removal inventory (planning only).
- DT property normalization map (legacy downstream names to upstream schema names).
- Kconfig/Makefile/file-structure planning.
- Regulator/reset migration plan (interface-level only).
- Banned-symbol policy and static validation rules.
- Patch ordering proposal and governance templates.

## 3) What remains blocked?
- SDW numeric identity + compatible finalization.
- SDW paging policy finalization.
- SoundWire controller patch necessity decision.
- Class-H enum/base/version behavior decisions.
- Runtime behavior claims (playback/capture/mute stability).

## 4) What should not be upstreamed?
- Board-specific DTS wiring as generic binding requirements.
- Temporary debug instrumentation/logging hacks.
- Unverified friend-note claims without reproducible evidence.
- Runtime workaround patches without root-cause evidence.

## 5) Recommended next human action
- Execute `hardware_evidence_request.md` and return all requested artifacts, with exact commands and raw logs preserved.

## 6) Recommended next AURA action after evidence arrives
1. Validate evidence completeness against `evidence_checklist.json` (P0 first).
2. Re-run blocker decisions (binding/SDW/Class-H) and update preconditions from NO-GO to GO/partial as justified.
3. If and only if P0 blockers are resolved, open a narrow, gated first conversion series (DT binding + SDW identity/paging decisions only).
