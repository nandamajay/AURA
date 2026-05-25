# Semantic Transformation Plan

## Scope
- downstream repo/branch/commit: `ssh://review-android.quicinc.com:29418/platform/vendor/qcom/opensource/audio-kernel-ar` / `audio-kernel-cmn.lnx.0.0` / `466891703077f54117390782cce636830ad8ae1c`
- upstream target baseline: `linux v6.18`
- focus: `asoc/codecs/wcd937x/*` with coupled helper integration

## Transformation Stages
1. dependency discovery
- output: `reports/dependency_graph_report.md`
- evidence: include graph + pattern coupling scan

2. API semantic alignment
- output: `reports/downstream_upstream_api_mapping_report.md`
- classification split: confirmed / inferred / unresolved

3. platform abstraction unwinding
- remove/replace downstream-only abstractions (`msm_cdc_*`, `wcdcal`, `qti-regmap-debugfs`)

4. transport layer transition
- move downstream `swr_*` flow toward upstream `sdw_*` model

5. MBHC/CLSH integration alignment
- align to upstream helper contracts (`wcd-mbhc-v2`, `wcd-clsh-v2`)

6. DT + build alignment
- validate against upstream bindings and `SND_SOC_WCD937X` build model

7. governance-gated finalization
- no autonomous apply; operator approval required

## Unresolved Blockers (Current Run)
- sparse unavailable in environment
- clang unavailable in environment
- dt schema tooling (`dt-doc-validate`) missing
- compile-scope host mismatch (`asm/types.h` include path issue)

## Workflow Binding
- advisory only until operator-approved patch generation/merge workflow
- current workflow validation status: `failed`
