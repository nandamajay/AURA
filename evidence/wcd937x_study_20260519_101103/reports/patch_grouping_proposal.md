# Patch Grouping Proposal (Advisory)

## Group 1: Build + Kconfig Alignment
- target files: `sound/soc/codecs/Kconfig`, `sound/soc/codecs/Makefile`
- intent: align symbol/build relationships for WCD937x + SDW split
- risk: low-medium

## Group 2: Core Codec Logic Port
- target files: `sound/soc/codecs/wcd937x.c`, `sound/soc/codecs/wcd937x.h`
- intent: migrate core controls, DAPM/event flow, runtime PM usage
- risk: high

## Group 3: SoundWire Transport Port
- target files: `sound/soc/codecs/wcd937x-sdw.c`
- intent: convert downstream `swr_*` coupling to upstream `sdw_*` model
- risk: high

## Group 4: MBHC and Class-H Integration
- target files: `sound/soc/codecs/wcd-mbhc-v2.[ch]`, `sound/soc/codecs/wcd-clsh-v2.[ch]`, WCD937x integration call sites
- intent: align MBHC/CLSH callbacks and state control
- risk: high

## Group 5: Power/Reset/Pinctrl Refactor
- target files: WCD937x core + regulator/gpio call sites
- intent: remove `msm_cdc_*` helper dependencies in favor of upstream frameworks
- risk: high

## Group 6: DT Binding and DTS Consumers
- target files: `Documentation/devicetree/bindings/sound/qcom,wcd937x*.yaml` (+ affected DTS if required)
- intent: reconcile channel map + property expectations with upstream schema
- risk: medium-high

## Group 7: Vendor Hook Removal / Isolation
- remove or isolate: `qti-regmap-debugfs`, `wcdcal-hwdep` paths from upstream patchset
- risk: medium (feature parity impact)

## Group 8: Validation and Evidence Stitching
- intent: ensure each patch group has replay/audit evidence, checkpatch/sparse/build evidence, and governance decision link
- risk: medium

Operator note: all groups are advisory; no final upstream submission should occur without operator approval + full validation pass.
