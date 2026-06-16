# Reviewer Prediction Accuracy - wsa883x

## Predicted vs Actual
| Reviewer | Predicted focus | Actual evidence found | Accuracy | Notes |
|---|---|---|---:|---|
| Mark Brown | kcontrol semantics, control naming/style, patch scope | Explicit evidence: `put` callback return semantics, enum naming/style; v2->v3 acceptance | 90% | Strong direct evidence from review DB |
| Pierre-Louis Bossart | SoundWire lifecycle correctness, runtime PM/resume robustness | Explicit evidence: update callback condition discussion + runtime resume timeout safety request | 88% | Strong direct evidence |
| Krzysztof Kozlowski | DT schema strictness and binding hygiene | Partial/direct evidence sparse for this driver; DT evolution exists in accepted commits | 55% | Marked partial evidence |
| Vinod Koul | SoundWire transport nits | INSUFFICIENT_EVIDENCE for direct per-comment extraction in this driver | 35% | Predicted based on maintainer model, not direct driver thread evidence |
| Bjorn Andersson | Qualcomm integration/DT concerns | INSUFFICIENT_EVIDENCE for direct per-comment extraction in this driver | 30% | Predicted from role patterns only |

## Aggregate Reviewer Prediction Similarity
- Weighted reviewer prediction similarity: **78%**

Weighting used:
- High-evidence reviewers (Mark, Pierre): 35% each
- Lower-evidence reviewers (Krzysztof, Vinod, Bjorn): 10% each

## Evidence Index
- Review DB:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/soundwire/wsa883x.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/krzysztof_kozlowski/dt/wsa883x.md`
- Lore/patch evolution:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/lore_links/wsa883x.md`

