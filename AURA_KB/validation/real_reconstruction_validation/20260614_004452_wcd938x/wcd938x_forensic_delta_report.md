# WCD938X Forensic Delta Report

## Major deltas: downstream vs reconstruction vs upstream
| Delta area | Downstream | AURA reconstruction | Upstream | Forensic assessment |
|---|---|---|---|---|
| Driver ownership model | Platform codec + vendor SWR slave module | Predicted split core + SDW side | Actual split core platform + SDW side | Transfer success from WSA lessons |
| Registration path | Vendor-centric component bind flow and manual orchestration | Predicted framework-native model | Upstream uses framework-native component/DAI for core + SDW component_add on SDW side | Partial success |
| SoundWire transport lifecycle | SWR device enumeration/bind, vendor APIs | Predicted SDW lifecycle callbacks | SDW slave ops + SDW driver + stream callbacks | Transfer success |
| PM ownership | Vendor sleep/resume on core plus vendor PM semantics | Predicted runtime PM emphasis | Runtime PM explicit on SDW side (`RUNTIME_PM_OPS`) | Partial success |
| DAPM/control scale | Very large WCD-specific graph and control surface | Predicted large but simplified upstream model | Large upstream graph/control model retained with family-specific behavior | Transfer gap: family complexity under-modeled |
| DT structure | Vendor DT properties and phandles | Predicted split bindings | Upstream has separate codec + sdw schemas | Transfer success |
| Review predictability | Sparse direct reviewer text in KB | Predicted via maintainer priors | Cannot fully validate due to evidence sparsity | Validation-limited, not purely model-failure |

## Objective strength classification
| Topic | Stronger design | Reason |
|---|---|---|
| SDW transport lifecycle model | UPSTREAM_BETTER | Cleaner subsystem-native ownership and API usage |
| Split core/transport file model | EQUIVALENT_DESIGN | AURA predicted same high-level structure |
| PM separation (core vs SDW side) | UPSTREAM_BETTER | Explicit, bounded PM handling for SDW endpoint lifecycle |
| DAPM/control simplification tendency | REVIEW_DRIVEN_DECISION | Upstream keeps required WCD feature scope; over-simplification would risk regressions |
| Patch decomposition | EQUIVALENT_DESIGN | AURA split is reviewable, but historical sequencing is family/review constrained |

## Evidence references
- Downstream core: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x.c:4153-4165`, `:4380-4410`, `:4753-4773`
- Downstream SWR slave: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/audio-kernel-ar/asoc/codecs/wcd938x/wcd938x-slave.c:275-304`, `:331-408`
- Upstream core: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3165-3177`, `:3273-3306`, `:3546-3556`
- Upstream SDW: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1146-1150`, `:1152-1218`, `:1259-1274`
- Upstream DT: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wcd938x.yaml:20-39`, `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wcd938x-sdw.yaml:17-44`

