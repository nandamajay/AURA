# Downstream -> Upstream API Mapping Report (WCD937x)

## Scope
- Downstream source root: `asoc/codecs/wcd937x/` (+ helper modules under `asoc/codecs` and `include/asoc`)
- Upstream baseline: `linux v6.18`
- Upstream target paths: `sound/soc/codecs/wcd937x*`, `wcd-common*`, `wcd-mbhc-v2*`, `wcd-clsh-v2*`, DT bindings

## Mapping Matrix
| Downstream API/Pattern | Upstream-compatible target pattern | Transform action | Confidence |
|---|---|---|---|
| `msm_cdc_enable_ondemand_supply`, `msm_cdc_init_supplies` | regulator framework (`regulator_bulk_*`, `devm_regulator*`) | replace Qualcomm supply helper wrappers with regulator-managed supply lifecycle | bounded |
| `msm_cdc_pinctrl_*` | gpio/pinctrl consumer (`gpiod_*`, standard pinctrl states) | migrate reset/sleep/active pin handling to upstream GPIO + pinctrl idioms | bounded |
| `swr_*` (`soc/soundwire.h`) | SoundWire upstream (`linux/soundwire/sdw*.h`, `sdw_*`) | split transport control into upstream `wcd937x-sdw.c` style path | bounded |
| `wcd_irq_*` helper | upstream IRQ handling with regmap/irqdomain patterns | align interrupt init/teardown to upstream helper usage | bounded |
| `wcd_mbhc_*` via downstream helper | upstream `wcd-mbhc-v2` | port MBHC callbacks/data wiring to upstream v2 API layout | strong-bounded |
| `wcd_clsh_*` helper | upstream `wcd-clsh-v2` | align class-H control state machine APIs | strong-bounded |
| `wcdcal-hwdep` calibration hooks | no direct upstream equivalent | isolate as non-upstreamable/private calibration path; strip from upstream submission | guaranteed-remove |
| `linux/qti-regmap-debugfs.h` and `devm_regmap_qti_debugfs_register` | upstream regmap/debugfs conventions (or remove) | remove vendor-specific debugfs registration from upstream patchset | guaranteed-remove |
| Downstream Kbuild aggregation patterns | upstream `Kconfig` + `Makefile` (`SND_SOC_WCD937X`, `SND_SOC_WCD937X_SDW`) | map object layout/config symbols to existing upstream model | strong-bounded |
| DT props `qcom,rx_swr_ch_map`, `qcom,tx_swr_ch_map` | `qcom,wcd937x*.yaml` constraints | verify/normalize property names and value shapes to upstream schema | bounded |

## Non-upstreamable or High-friction Elements
- Vendor debugfs (`qti-regmap-debugfs`) path.
- Calibration hwdep (`wcdcal-*`) path.
- Qualcomm-private helper layering (`msm_cdc_*`, bolero internal coupling).

## Evidence
- dependency graph JSON: `artifacts/dependency_graph.json`
- pattern scan log: `logs/forbidden_pattern_scan.log`
- include/symbol evidence: `logs/forbidden_pattern_scan.log`, `reports/dependency_graph_report.md`
