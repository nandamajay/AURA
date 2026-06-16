# Reconstruction vs Upstream Delta - wsa883x

## Metric Scorecard
| Metric | Score | Basis |
|---|---:|---|
| Architecture similarity | 89% | Correctly predicted SDW-native driver + component/DAI model; missed some reset/hwmon details |
| File layout similarity | 84% | Predicted single codec + binding path correctly; patch granularity differed from historical evolution |
| DT similarity | 94% | Correctly predicted SoundWire compatible and port mapping evolution; minor ordering/detail differences |
| DAPM similarity | 87% | Correctly predicted explicit DAPM/controls; downstream SWR mixer-specific behavior over-predicted |
| Runtime PM similarity | 90% | Correctly predicted autosuspend/runtime callbacks; historical timeout fix came as follow-up |
| SoundWire similarity | 91% | Correctly predicted transition from vendor SWR calls to generic SDW stream lifecycle |
| Patch-series similarity | 86% | Predicted a clean 6-patch series; real accepted path used 4-patch start + revision loops and follow-ups |
| Reviewer prediction similarity | 78% | High accuracy for Mark/Pierre themes; limited direct evidence for Vinod/Bjorn/Krzysztof comments |
| Overall similarity | **87.4%** | Arithmetic mean of the above |

## Delta Matrix (Predicted vs Actual)
| Area | Reconstructed (blind) | Actual upstream | Delta class | Evidence |
|---|---|---|---|---|
| Bus model | Convert `swr_driver` to generic SDW | `module_sdw_driver`, `sdw_driver`, `sdw_slave_ops` | Match | Downstream `.../wsa883x.c:2208-2231`; Upstream `.../wsa883x.c:1126-1129`, `:1717-1728` |
| Registration | devm component + static DAI | `devm_snd_soc_register_component` + static `wsa883x_dais[]` | Match | Upstream `.../wsa883x.c:1412-1426`, `:1674-1677` |
| DAPM topology | Minimal graph + controls | Minimal graph (`IN`,`SPKR`) + port switch controls | Partial | Upstream `.../wsa883x.c:1301-1325`; Downstream has extra SWR DAC mixer `.../wsa883x.c:1256-1269` |
| Port mapping ownership | Move from machine helper to DT/control-driven | DT property parse + per-port controls | Match | Downstream exported helper `.../wsa883x.c:1271-1296`; Upstream DT parse `.../wsa883x.c:1635-1637`, controls `:1313-1320` |
| PM strategy | runtime PM autosuspend | runtime PM autosuspend + regcache callbacks | Match | Upstream `.../wsa883x.c:1668-1672`, `:1686-1708` |
| Reset/GPIO model | Shared reset support expected | reset controller with fallback to powerdown gpio | Partial | Upstream `.../wsa883x.c:1579-1593`; binding `.../qcom,wsa883x.yaml:28-35`, `:60-64` |
| Probe footprint | Leaner probe than downstream | Lean probe: regulator/reset/regmap/pm/component/hwmon | Partial | Downstream probe heavy `.../wsa883x.c:1780-2054`; upstream lean `.../wsa883x.c:1598-1683` |
| IRQ handling | Prefer SDW/core callbacks over vendor IRQ stack | upstream avoids downstream `wcd_irq_*` stack | Match | Downstream `.../wsa883x.c:1881-1939`; upstream lacks equivalent custom IRQ block |
| Machine coupling | Remove board-specific exported API coupling | no upstream equivalent exported machine helper | Match | Downstream exports and machine use `.../wsa883x.c:1271-1296`, `/audio_machine.c:2209` |

## Why Similarity Is Not >= 90%
1. Historical patch-shape mismatch: real series iterated controls patch through v1/v2/v3 before acceptance.
2. Reviewer model sparsity for non-primary reviewers (Vinod/Bjorn/Krzysztof direct comment evidence limited).
3. Blind reconstruction slightly over-specified PM/SDW details in initial patch partitioning versus historical order.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wsa883x.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa883x/review_comments.md`

