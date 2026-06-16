# WCD938X Validated Lessons

## Transfer validation against WSA883x forensic lessons
| WSA883x lesson | Transfer result on WCD938x | Classification | Evidence |
|---|---|---|---|
| Prefer SDW-native lifecycle over vendor SWR runtime path | Transferred successfully | QUALCOMM_AUDIO_WIDE | Upstream SDW driver+ops: `/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1146-1150`, `:1264-1274` |
| Favor framework-native registration and bounded ownership | Partially transferred | QUALCOMM_AUDIO_WIDE | Core aligns: `/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3165-3177`, `:3546-3556`; downstream complexity remains larger |
| Runtime PM robustness expectations matter | Partially transferred | QUALCOMM_AUDIO_WIDE | SDW runtime PM: `/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1233-1261`; direct review text evidence missing |
| DAPM minimalism in first cut | Failed to fully transfer | FAMILY_SPECIFIC (WSA-biased) | WCD family retains wide DAPM/control scope: `/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:2588`, `:2644` |
| Reviewer prediction from maintainer priors is sufficient | Failed to transfer strongly | FAMILY_SPECIFIC_EVIDENCE_GAP | `wcd938x` review comment extraction is insufficient: `/AURA_KB/drivers/wcd938x/review_comments.md:3-4` |

## KB update actions (validated only)
1. RULE_REFINEMENT: mark `DAPM minimal initial series` as family-sensitive (works better for WSA than WCD938x).
2. RULE_REFINEMENT: preserve Qualcomm-wide SDW-native lifecycle rule.
3. MAINTAINER_MODEL_UPDATE: enforce evidence-threshold gating for reviewer simulation confidence on drivers with sparse review text.

No additional rule promotion from `wcd938x` reviewer specifics due to `INSUFFICIENT_EVIDENCE`.

