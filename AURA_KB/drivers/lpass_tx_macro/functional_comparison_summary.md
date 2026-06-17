# TX Blind Conversion Functional Comparison
## Verdict
- Overall verdict: **PARTIALLY_ALIGNED** (69.27%)
- Improvement over VA: **REGRESSED** (average delta -7.13 points)
- Blind assumptions: 5 correct, 4 wrong/unvalidated

## Per-Category Scores
| Category | Upstream | Converted | Match | Verdict |
|---|---:|---:|---:|---|
| KERNEL_API_CALLS | 55 | 58 | 72.73% | PARTIALLY_ALIGNED |
| LIFECYCLE_STRUCTURE | 30 | 30 | 70.0% | PARTIALLY_ALIGNED |
| DAPM_TOPOLOGY | 163 | 282 | 75.68% | PARTIALLY_ALIGNED |
| REGISTER_ACCESS | 167 | 70 | 27.54% | DIVERGENT |
| CLOCK_POWER | 10 | 9 | 80.0% | ALIGNED |
| SOC_DATA_MODEL | 17 | 16 | 78.21% | PARTIALLY_ALIGNED |
| REGMAP_OWNERSHIP | 6 | 3 | 50.0% | PARTIALLY_ALIGNED |
| VENDOR_COUPLING | 0 | 0 | 100.0% | ALIGNED |

## VA Baseline vs TX
| Metric | VA | TX | Delta | Trend |
|---|---:|---:|---:|---|
| line_similarity | 40.23% | 27.94% | -12.29 | regressed |
| function_match | 57.14% | 63.33% | 6.19 | improved |
| register_defines | 68.29% | 27.54% | -40.75 | regressed |
| dapm | 64.47% | 75.68% | 11.21 | improved |
| runtime_pm | 100.0% | 100.0% | 0.0 | same |

## Top Lessons Applied Correctly
- **REGMAP_OWNERSHIP**: Blind TX conversion owns its MMIO regmap with devm_regmap_init_mmio.
- **SOC_DATA_MODEL**: Blind TX conversion added of_device_get_match_data and per-compatible data.
- **DAPM_TOPOLOGY**: Blind TX conversion reduced downstream DAPM topology instead of preserving all vendor widgets/routes.
- **VENDOR_COUPLING**: Vendor lpass-cdc/clk-rsc/Kconfig/property coupling was removed.
- **RUNTIME_PM**: Runtime PM callbacks are present and wired.

## Top Remaining Conversion Gaps
- **CLOCK_POWER**: Missing upstream clock resources: npl
- **REGMAP_OWNERSHIP**: Regmap config lacks upstream readable/writeable/volatile callbacks: readable_reg, volatile_reg, writeable_reg
- **SOC_DATA_MODEL**: Missing upstream compatible: qcom,sc7280-lpass-tx-macro
- **SOC_DATA_MODEL**: Missing upstream compatible: qcom,sc8280xp-lpass-tx-macro
- **SOC_DATA_MODEL**: Missing upstream compatible: qcom,sm6115-lpass-tx-macro

## New TX Lessons
- SWR/SMIC fanout is materially larger in TX than VA Rule: Topology reduction must understand mux fanout limits and not only delete named vendor controls.
- Cross-macro CSR references can remain after local prefix normalization Rule: Register extraction must classify cross-macro register ownership before blind localizing defines.
- Compatible string inference is high-risk blind work Rule: Do not invent SoC compatibles without binding/corpus evidence; create placeholders only as governed assumptions.
- Clock-provider detection needs binding evidence Rule: Search binding/property evidence for clock-output-names before deciding provider role.
- Function renaming should be staged after semantic removals Rule: Broad prefix cleanup should be last and audited for external ABI/ops-table references.
