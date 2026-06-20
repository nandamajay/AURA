# PM Learning Summary: WCD938x LA vs LE Audit

Generated: 2026-06-20  
Mode: learning-only, no conversion, no runtime claim

## PM verdict on usefulness
- **High usefulness** for architectural and API transformation rules.
- **No direct blocker closure** for WCD9378 runtime-sensitive items (SDW ID, paging proof, Class-H base/version, playback/capture validation).

## Top 10 reusable lessons (LE-centric)
1. Use aggregate codec + SDW child split instead of monolithic vendor flow.
2. Bind/unbind with component master and device links for rx/tx ordering.
3. Initialize SDW regmap in tx path and begin cache-only pre-attach.
4. Sync regcache on SDW attach and runtime resume.
5. Use runtime PM autosuspend on aggregate + SDW children.
6. Use reset-gpios with gpiod, not vendor pinctrl state APIs.
7. Use regulator bulk enable APIs, not vendor supply policy wrappers.
8. Integrate MBHC through `wcd-mbhc-v2` shared API.
9. Integrate Class-H through `wcd-clsh-v2` shared state controller.
10. Keep Kconfig/Makefile split symbols for core/SDW codec integration.

## Top 10 things not to copy from LA
1. Vendor includes (`msm-cdc*`, bolero internals, qti debugfs, hwdep).
2. LA debugfs peek/poke/regdump slave interfaces.
3. String-based SWR identity model (`wcd938x-slave`) for LE SDW.
4. Parent platform callback coupling (`handle`, `update_wcd_event`, notifier hooks).
5. Vendor reset wrappers (`msm_cdc_pinctrl_select_*`).
6. Vendor supply orchestration (`msm_cdc_*supply*`).
7. LA-only DT property names (`qcom,wcd-rst-gpio-node`, `qcom,rx-slave`, etc.).
8. Custom IRQ wrapper stack in place of regmap-irq/threaded IRQ.
9. External-module Kbuild environment assumptions.
10. Runtime timing/retry heuristics treated as universal truth.

## Direct WCD9378 implications
- Improved now: conversion architecture choices, DT normalization direction, API mapping quality expectations, and fail-closed discipline.
- Unchanged blockers: SDW numeric identity, paging runtime proof, Class-H base/version decision, runtime playback/capture/mute evidence, board DTS finalization.
- Evidence sources:
  - `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/pm_datasheet_delta_summary.md`
  - `AURA_KB/drivers/wcd9378/blocker_burndown_01_datasheet_delta/conversion_gate_preconditions_delta.json`
  - `AURA_KB/drivers/wcd9378/evidence_request_01/evidence_checklist.json`

## Should WCD939x be audited next?
- **Yes (recommended)**.
- Reason: WCD939x is a nearby LE codec family member and likely strengthens reusable LE pattern coverage for PM/lifecycle/DT/SDW decisions without forcing WCD9378 runtime assumptions.

## AURA tooling/gate improvements suggested
1. Add explicit LA->LE DT property migration checks (legacy property detector).
2. Add vendor-API symbol banlist specific to Qualcomm audio downstream stacks.
3. Add mandatory runtime-evidence gate labels for SDW identity/paging/Class-H base decisions.
4. Add DAPM-topology anti-copy heuristic (name-only cloning detection).
5. Add report section that separates structural reuse from runtime validation status.

## Final PM stance
- This audit materially improves conversion intelligence.
- It does **not** authorize WCD9378 runtime claims or conversion blocker closure.
