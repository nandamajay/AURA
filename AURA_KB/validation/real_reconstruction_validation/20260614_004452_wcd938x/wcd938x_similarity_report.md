# WCD938X Similarity Report

## Scorecard
| Metric | Score | Basis |
|---|---:|---|
| Architecture similarity | 76% | Correctly predicted core+SDW split, but under-modeled WCD938x-specific complexity and vendor->upstream control flow details |
| File layout similarity | 88% | Correctly predicted split files (`wcd938x.c` + `wcd938x-sdw.c`) and DT dual-schema model |
| DT similarity | 93% | Correct split between codec and SDW endpoint bindings, with port mapping semantics aligned |
| DAPM/Controls similarity | 74% | Predicted large graph presence but not full family-specific scope and control granularity |
| Runtime PM similarity | 82% | Correct PM direction on SDW side; partial mismatch on downstream-vs-upstream PM ownership details |
| SoundWire similarity | 90% | Correctly predicted SDW-native transport model and separate SDW driver ownership |
| Patch-series similarity | 86% | Predicted split largely matches upstream family shape; historical review-loop details still imperfect |
| Reviewer prediction similarity | 57% | Evidence-limited reviewer corpus for this driver (`INSUFFICIENT_EVIDENCE` for direct comment extraction) |
| Overall similarity | **80.8%** | Arithmetic mean |

## WSA883X vs WCD938X (comparison)
| Metric | WSA883x | WCD938x | Delta |
|---|---:|---:|---:|
| Architecture | 89% | 76% | -13 |
| DT | 94% | 93% | -1 |
| SoundWire | 91% | 90% | -1 |
| Patch-series | 86% | 86% | 0 |
| Reviewer prediction | 78% | 57% | -21 |
| Overall | 87.4% | 80.8% | -6.6 |

WSA baseline source:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstruction_vs_upstream_delta.md:6-14`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reviewer_prediction_accuracy.md:12-14`

WCD prior baseline source:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/blind_reproduction_campaign/20260613_235158/wcd938x/05_similarity_scorecard.md:5-11`

