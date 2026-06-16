# Reproduction Failure Analysis

## Scope
- Campaign run: `20260613_235158`
- Drivers analyzed:
  - `wsa883x`
  - `wsa884x`
  - `wcd938x`
  - `lpass_rx_macro`
  - `lpass_tx_macro`
  - `lpass_va_macro`
- No new driver mining, no new reproduction generation.

## Why overall similarity is 79.2%
Primary contributors:
1. Architecture token mismatch for codec drivers (46.7% / 46.7% / 58.3%).
2. Reviewer-feedback prediction misses (average 52.3%) due sparse direct per-driver review corpus.
3. Scoring model weakness: SoundWire dimension penalized macro drivers where SoundWire is not a primary ownership axis.
4. Patch-splitting miss on `wsa883x` (predicted 2 patches vs actual richer staged acceptance history including controls/DAPM split and follow-ups).

## Driver-by-driver mismatch analysis

### wsa883x
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | Downstream uses `swr_driver` path while upstream is SDW-native (`sdw_driver`, `module_sdw_driver`) and explicit DAI ops (`hw_params/hw_free/set_stream/mute_stream`). | PATTERN_GAP |
| 2. File layout | Blind reconstruction was abstract and did not model exact upstream decomposition and helper placement. | KNOWLEDGE_GAP |
| 3. Probe/remove | Downstream `wsa883x_swr_probe/remove` vs upstream SDW probe lifecycle and runtime-pm gating details. | RULE_GAP |
| 4. DAPM | High-level DAPM intent matched, but event/callback-level behavior was not reconstructed at parity. | KNOWLEDGE_GAP |
| 5. Runtime PM | Basic PM predicted correctly, but exact suspend/resume + timeout robustness details underrepresented. | MAINTAINER_MODEL_GAP |
| 6. SoundWire | Lifecycle direction correct but bus abstraction migration (SWR->SDW) not explicitly encoded in reconstruction template. | PATTERN_GAP |
| 7. DT binding | Score high; no major blocker in campaign metric. | - |
| 8. Registration path | Missing explicit `snd_soc_dai_ops` parity in generated abstraction set. | RULE_GAP |
| 9. Patch splitting | Predicted 2-patch plan; actual accepted path included richer staged control/DAPM + follow-up fixes. | PATCH_STRATEGY_GAP |
| 10. Reviewer prediction | Only partially captured Mark/Pierre specifics; low confidence for Vinod/Bjorn. | MAINTAINER_MODEL_GAP |

### wsa884x
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | Same core issue as wsa883x: SWR-shaped downstream abstraction not transformed to SDW-native parity model. | PATTERN_GAP |
| 2. File layout | Generated output remained high-level; missing concrete ownership split details and exact upstream object placement. | KNOWLEDGE_GAP |
| 3. Probe/remove | SWR probe/remove assumptions leaked into blind model; upstream uses SDW-centric flow. | RULE_GAP |
| 4. DAPM | High-level graph present, not callback-semantics equivalent at line-level. | KNOWLEDGE_GAP |
| 5. Runtime PM | PM strategy predicted, but exact `pm_runtime_resume_and_get`/autosuspend sequencing parity not guaranteed. | RULE_GAP |
| 6. SoundWire | Correct directionally, but insufficiently specific transition rules and callback obligations. | PATTERN_GAP |
| 7. DT binding | Score high in campaign metric; earlier validation showed schema-fidelity risk if not constrained (compatible/supply/oneOf). | RULE_GAP |
| 8. Registration path | Missing explicit DAI ops parity in tokenized architecture model. | RULE_GAP |
| 9. Patch splitting | Better than wsa883x but still generic; did not model revision evolution nuances. | PATCH_STRATEGY_GAP |
| 10. Reviewer prediction | Major miss source due missing direct wsa884x comment transcript indexing. | MAINTAINER_MODEL_GAP |

### wcd938x
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | Partial parity only: upstream core uses explicit DAI ops (`hw_params/hw_free/set_stream`) and PM hooks not captured in blind abstraction depth. | KNOWLEDGE_GAP |
| 2. File layout | Critical: upstream is split across `wcd938x.c` + `wcd938x-sdw.c`; campaign comparison centered on single file model. | PATTERN_GAP |
| 3. Probe/remove | Platform probe/remove captured, but split transport-side probe behavior under-modeled. | PATTERN_GAP |
| 4. DAPM | Broad DAPM intent matched; fine-grain graph/control parity not reconstructed. | KNOWLEDGE_GAP |
| 5. Runtime PM | Campaign PM similarity only 70%; blind model did not capture exact PM entry/exit coverage and call-site placement. | RULE_GAP |
| 6. SoundWire | SoundWire side modeled, but split-file transport ownership and callback path completeness lagged. | PATTERN_GAP |
| 7. DT binding | Campaign score high; no major DT blocker surfaced in this pass. | - |
| 8. Registration path | `snd_soc_dai_ops` and stream callbacks present upstream; blind reconstruction was too generic. | RULE_GAP |
| 9. Patch splitting | Predicted 5 patches; near actual staged history but still not revision-accurate to accepted v9 decomposition. | PATCH_STRATEGY_GAP |
| 10. Reviewer prediction | Same corpus sparsity issue as wsa884x. | MAINTAINER_MODEL_GAP |

### lpass_rx_macro
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | Good parity overall; primary gap was missing explicit upstream `snd_soc_component_driver` emphasis in token set comparison. | RULE_GAP |
| 2. File layout | Layout parity acceptable; detailed helper/function ownership remained approximate. | KNOWLEDGE_GAP |
| 3. Probe/remove | Directionally correct; component_probe vs platform_probe role split insufficiently explicit in blind docs. | RULE_GAP |
| 4. DAPM | Major flow aligned; detailed widget-route differences not audited in blind reconstruction. | KNOWLEDGE_GAP |
| 5. Runtime PM | Strong parity (92%) but no exact suspend/resume sequence audit in generated artifacts. | KNOWLEDGE_GAP |
| 6. SoundWire | Macro driver penalized by campaign SoundWire metric although SoundWire is non-primary here. | RULE_GAP |
| 7. DT binding | High score; no major mismatch from campaign metric. | - |
| 8. Registration path | Missing component-driver explicitness in reconstruction template. | RULE_GAP |
| 9. Patch splitting | Matched well (100%). | - |
| 10. Reviewer prediction | Low (46%) mostly due generic reviewer template and sparse macro-specific review corpus. | MAINTAINER_MODEL_GAP |

### lpass_tx_macro
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | High parity; residual mismatch from missing explicit `snd_soc_component_driver` in blind token model. | RULE_GAP |
| 2. File layout | Good at macro level; helper-placement and SoC-variant handling not reconstructed in depth. | KNOWLEDGE_GAP |
| 3. Probe/remove | Correct directionally; component-probe layering under-documented in blind artifacts. | RULE_GAP |
| 4. DAPM | Largely aligned, but detailed route/control deltas not captured. | KNOWLEDGE_GAP |
| 5. Runtime PM | Strong metric but no call-order parity validation in blind reconstruction docs. | KNOWLEDGE_GAP |
| 6. SoundWire | Penalized by non-applicable metric axis in current campaign weighting. | RULE_GAP |
| 7. DT binding | High score. | - |
| 8. Registration path | Component registration nuance underrepresented. | RULE_GAP |
| 9. Patch splitting | Matched (100%). | - |
| 10. Reviewer prediction | Low due generic template + sparse direct macro comment index. | MAINTAINER_MODEL_GAP |

### lpass_va_macro
| Area | Mismatch | Gap Class |
|---|---|---|
| 1. Architecture | High parity; residual mismatch from component-driver explicitness gap in blind model. | RULE_GAP |
| 2. File layout | Good at top level; limited detail on helper/variant-specific layout. | KNOWLEDGE_GAP |
| 3. Probe/remove | Directionally matched but component-vs-platform callback layering under-documented. | RULE_GAP |
| 4. DAPM | Broad alignment with remaining fine-grain route/control gaps. | KNOWLEDGE_GAP |
| 5. Runtime PM | Strong score; exact runtime callback ordering not reconstructed. | KNOWLEDGE_GAP |
| 6. SoundWire | Penalized by non-applicable metric dimension. | RULE_GAP |
| 7. DT binding | High score. | - |
| 8. Registration path | Component registration detail underrepresented. | RULE_GAP |
| 9. Patch splitting | Matched (100%). | - |
| 10. Reviewer prediction | Low due sparse direct review corpus for macro driver. | MAINTAINER_MODEL_GAP |

## Cross-driver root-cause summary
| Root Cause | Evidence | Gap Class |
|---|---|---|
| SWR->SDW transformation logic was under-specified for codec families. | `wsa883x/wsa884x` architecture 46.7%. | PATTERN_GAP |
| Reconstruction templates were too abstract (token-level, not callback-level). | Missing explicit DAI ops and component-path parity in multiple drivers. | KNOWLEDGE_GAP |
| Scoring rule penalized non-SoundWire macro drivers on SoundWire axis. | Macro drivers fixed at 80% SoundWire despite non-primary relevance. | RULE_GAP |
| Reviewer model not driver-specific enough due sparse comment corpus. | Average reviewer accuracy 52.3%. | MAINTAINER_MODEL_GAP |
| Patch strategy underfit for wsa883x historical series shape. | Patch similarity 76% only for wsa883x. | PATCH_STRATEGY_GAP |
