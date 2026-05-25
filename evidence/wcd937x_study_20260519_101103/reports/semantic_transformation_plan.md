# Semantic Transformation Plan (Bounded)

## Objective
Transform downstream WCD937x logic toward upstream-compatible implementation while preserving provenance, replay lineage, and operator governance.

## Preconditions (immutable)
- downstream commit: `a89e32cf75ed4ef166c39caa1b39d8ec3818a633`
- upstream baseline: `v6.18` (`7d0a66e4bb9081d75c82ec4957c50034cb0ea449`)
- source intake/workflow anchors: `6f817915bdc0cb628815128b1b03cc68` / `d285331f26c70c20ac81f9ed3b273279`

## Planned Transformation Steps
1. Normalize build wiring:
- align downstream object grouping with upstream `SND_SOC_WCD937X` + `SND_SOC_WCD937X_SDW` split.

2. Transport boundary conversion:
- move downstream `swr_*` flows toward upstream `sdw_*` split (`wcd937x.c` vs `wcd937x-sdw.c`).

3. Power/reset conversion:
- replace `msm_cdc_*` supply/pinctrl helpers with regulator/gpiod/runtime PM flow.

4. MBHC + CLSH alignment:
- remap downstream helper callbacks to upstream `wcd-mbhc-v2` and `wcd-clsh-v2` idioms.

5. Vendor hook removal:
- remove `qti-regmap-debugfs` and `wcdcal-hwdep` from upstream-bound patch groups.

6. DT/schema reconciliation:
- validate/adjust codec and SoundWire bindings against `qcom,wcd937x*.yaml`.

7. Validation + governance gating:
- checkpatch/sparse/clang/build/DT checks before final governance approval.

## Explicitly Deferred (not in this phase)
- autonomous learning/self-training
- auto-generated final upstream patch submission
- hidden retries or auto-approval bypass

## Current Outcome
- Plan generated and governance-approved in bounded mode.
- Validation status remains `failed` due missing toolchain components in execution environment.

## Evidence
- runtime lifecycle trace: `raw/runtime_lifecycle_trace.json`
- validation runs DB export: `raw/validation_runs_rows.json`
