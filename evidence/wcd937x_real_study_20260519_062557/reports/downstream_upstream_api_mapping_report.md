# Downstream to Upstream API Mapping Report

## Auto-Discovered Upstream Candidate Paths
- `Documentation/devicetree/bindings/sound/qcom,wcd9335.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd934x.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd937x-sdw.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd937x.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd938x-sdw.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd938x.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd939x-sdw.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd939x.yaml`
- `Documentation/devicetree/bindings/sound/qcom,wcd93xx-common.yaml`
- `sound/soc/codecs/Kconfig`
- `sound/soc/codecs/Makefile`
- `sound/soc/codecs/wcd-clsh-v2.c`
- `sound/soc/codecs/wcd-clsh-v2.h`
- `sound/soc/codecs/wcd-common.c`
- `sound/soc/codecs/wcd-common.h`
- `sound/soc/codecs/wcd-mbhc-v2.c`
- `sound/soc/codecs/wcd-mbhc-v2.h`
- `sound/soc/codecs/wcd937x-sdw.c`
- `sound/soc/codecs/wcd937x.c`
- `sound/soc/codecs/wcd937x.h`

## Confirmed Mappings
- mapping: **wcd937x core codec file**
  - downstream pattern: `wcd_mbhc_` (hits: 87)
  - upstream pattern: `wcd_mbhc_` (hits: 82)
  - note: Both downstream and upstream candidate paths contain wcd_mbhc_* usage in codec/mbhc files.
  - sample downstream evidence: `asoc/codecs/wcd-mbhc-adc.c:32` -> `static int wcd_mbhc_get_micbias(struct wcd_mbhc *mbhc)`
  - sample upstream evidence: `sound/soc/codecs/wcd-mbhc-v2.c:36` -> `enum wcd_mbhc_adc_mux_ctl {`
- mapping: **class-H control integration**
  - downstream pattern: `wcd_clsh` (hits: 82)
  - upstream pattern: `wcd_clsh` (hits: 82)
  - note: Both sides show wcd_clsh control usage with dedicated helper files.
  - sample downstream evidence: `asoc/codecs/wcd-clsh.c:16` -> `struct wcd_clsh_cdc_info *,`
  - sample upstream evidence: `sound/soc/codecs/wcd-clsh-v2.c:12` -> `struct wcd_clsh_ctrl {`
- mapping: **runtime PM usage**
  - downstream pattern: `pm_runtime` (hits: 4)
  - upstream pattern: `pm_runtime` (hits: 34)
  - note: Both sides include/use runtime PM hooks.
  - sample downstream evidence: `asoc/codecs/wcd-mbhc-adc.c:16` -> `#include <linux/pm_runtime.h>`
  - sample upstream evidence: `sound/soc/codecs/wcd-common.c:11` -> `#include <linux/pm_runtime.h>`
- mapping: **regulator integration**
  - downstream pattern: `regulator` (hits: 84)
  - upstream pattern: `regulator` (hits: 13)
  - note: Downstream and upstream show regulator-related usage in candidate files.
  - sample downstream evidence: `asoc/codecs/msm-cdc-supply.c:12` -> `#include <linux/regulator/consumer.h>`
  - sample upstream evidence: `sound/soc/codecs/wcd-clsh-v2.c:372` -> `static void wcd_clsh_set_buck_regulator_mode(struct snd_soc_component *comp,`

## Inferred Mappings
- mapping: **SoundWire API transition**
  - downstream pattern: `swr_` (hits: 80)
  - upstream pattern: `sdw_` (hits: 81)
  - note: Downstream uses swr_* APIs; upstream candidate uses sdw_* APIs for WCD937x transport split.
  - sample downstream evidence: `asoc/codecs/wcd937x/internal.h:44` -> `struct swr_device *rx_swr_dev;`
  - sample upstream evidence: `sound/soc/codecs/wcd-common.c:13` -> `#include <linux/soundwire/sdw_type.h>`
- mapping: **pinctrl/gpio transition**
  - downstream pattern: `msm_cdc_` (hits: 83)
  - upstream pattern: `gpiod_` (hits: 6)
  - note: Downstream uses msm_cdc pinctrl helpers; upstream candidate shows gpiod-based reset handling.
  - sample downstream evidence: `asoc/codecs/msm-cdc-pinctrl.c:24` -> `struct msm_cdc_pinctrl_info {`
  - sample upstream evidence: `sound/soc/codecs/wcd937x.c:242` -> `gpiod_set_value(wcd937x->reset_gpio, 1);`
- mapping: **build symbol alignment**
  - downstream pattern: `msm_cdc_` (hits: 83)
  - upstream pattern: `SND_SOC_WCD937X` (hits: 8)
  - note: Upstream build symbols explicitly present in Kconfig/Makefile for WCD937X + SDW split.
  - sample downstream evidence: `asoc/codecs/msm-cdc-pinctrl.c:24` -> `struct msm_cdc_pinctrl_info {`
  - sample upstream evidence: `sound/soc/codecs/Kconfig:301` -> `imply SND_SOC_WCD937X_SDW`

## Unresolved Mappings
- mapping: **vendor debugfs hook**
  - downstream pattern: `qti-regmap-debugfs` (hits: 1)
  - upstream pattern: `none found`
  - note: No direct upstream qti-regmap-debugfs equivalent in candidate paths.
  - sample downstream evidence: `asoc/codecs/wcd937x/wcd937x.c:31` -> `#include <linux/qti-regmap-debugfs.h>`
- mapping: **calibration hwdep hooks**
  - downstream pattern: `wcdcal_` (hits: 29)
  - upstream pattern: `none found`
  - note: No direct upstream wcdcal hwdep equivalent in candidate paths.
  - sample downstream evidence: `asoc/codecs/wcd937x/wcd937x-mbhc.c:343` -> `hwdep_cal = wcdcal_get_fw_cal(wcd937x_mbhc->fw_data, type);`
- mapping: **msm_cdc supply wrappers**
  - downstream pattern: `msm_cdc_` (hits: 83)
  - upstream pattern: `none found`
  - note: No direct msm_cdc_* wrapper API in upstream candidates.
  - sample downstream evidence: `asoc/codecs/msm-cdc-pinctrl.c:24` -> `struct msm_cdc_pinctrl_info {`
- mapping: **wcd_irq helper parity**
  - downstream pattern: `wcd_irq_` (hits: 41)
  - upstream pattern: `none found`
  - note: No direct wcd_irq_* symbol parity located in upstream candidate paths.
  - sample downstream evidence: `asoc/codecs/wcd-irq.c:15` -> `static int wcd_map_irq(struct wcd_irq_info *irq_info, int irq)`

## Snapshot Artifacts
- `artifacts/upstream_candidate_paths.txt`
- `artifacts/upstream_candidate_sha256.txt`
- `artifacts/upstream_candidate_bundle.sha256`
- `artifacts/downstream_upstream_mapping.json`

## Unresolved Blockers
- Direct upstream equivalent for `qti-regmap-debugfs` not found in candidate set.
- Direct upstream equivalent for `wcdcal-*` hooks not found in candidate set.
- Direct upstream equivalent for `msm_cdc_*` wrapper layer not found in candidate set.

## Runtime Evidence References
- workflow_id: `28f5d02bea8699fefd6335f3f7878b39`
- `raw/runtime_lifecycle_trace.json`
- `artifacts/downstream_upstream_mapping.json`
