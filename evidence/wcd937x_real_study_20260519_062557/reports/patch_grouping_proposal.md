# Patch Grouping Proposal

## Group 1: Build and Symbol Wiring
- files: `sound/soc/codecs/Kconfig`, `sound/soc/codecs/Makefile`
- goal: align WCD937x + SDW build symbol split

## Group 2: Core Codec Port
- files: `sound/soc/codecs/wcd937x.c`, `sound/soc/codecs/wcd937x.h`
- goal: codec control and DAPM behavior migration

## Group 3: SoundWire Transport Port
- files: `sound/soc/codecs/wcd937x-sdw.c`
- goal: downstream `swr_*` -> upstream `sdw_*` flow alignment

## Group 4: MBHC and Class-H Alignment
- files: `sound/soc/codecs/wcd-mbhc-v2.[ch]`, `sound/soc/codecs/wcd-clsh-v2.[ch]`
- goal: callback and power/audio event sequence alignment

## Group 5: Downstream-only Abstraction Removal
- remove/replace: `msm_cdc_*`, `wcdcal-*`, `qti-regmap-debugfs`

## Group 6: DT Binding and Integration
- files: `Documentation/devicetree/bindings/sound/qcom,wcd937x*.yaml`
- goal: binding compliance for port maps and properties

## Group 7: Validation and Governance Closure
- run checkpatch/sparse/clang/build/dt checks, then governance decision gate

Operator gate: all groups are advisory; no auto-apply.
