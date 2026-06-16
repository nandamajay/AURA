# Generalization Assessment (WSA883x -> WCD938x)

## 1. Which lessons transferred successfully
- SDW-native transport ownership generalizes.
- Core/transport split expectation generalizes.
- DT split model (codec + sdw endpoint bindings) generalizes.

Evidence:
- WSA baseline deltas: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstruction_vs_upstream_delta.md:19-24`
- WCD upstream evidence: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x-sdw.c:1146-1150`, `:1264-1274`, `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/Documentation/devicetree/bindings/sound/qcom,wcd938x-sdw.yaml:17-44`

## 2. Which lessons failed to transfer
- WSA-style DAPM simplification heuristics do not fully transfer to WCD938x family complexity.
- Reviewer prediction confidence does not transfer due to sparse direct `wcd938x` review text.

Evidence:
- WCD DAPM/control scale: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:2588`, `:2644`
- Review evidence gap: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd938x/review_comments.md:3-4`

## 3. Family-specific vs Qualcomm-audio-wide rules
Qualcomm-audio-wide:
- SDW-native transport lifecycle ownership
- Framework-native registration preference
- Runtime PM robustness expectation

Likely family-specific:
- Degree of early DAPM/control minimization
- Patch decomposition granularity for codec with MBHC/jack-heavy behavior

Evidence:
- WSA validated lessons: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/validated_learning_extraction.md:7-14`
- WCD structural complexity: `/local/mnt/workspace/AURA_V1_upstream/track_b_corpora/linux-next/sound/soc/codecs/wcd938x.c:3152-3177`, `:2588-2644`

## 4. Scores
- Reconstruction readiness score: **81/100**
- Reviewer-survival score: **63/100**
- Architecture maturity score: **79/100**

Score rationale:
- Architecture and reconstruction improved over prior blind campaign baseline (74.0 overall) but remain below WSA883x real-validation level.
  - Baseline evidence: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/blind_reproduction_campaign/20260613_235158/wcd938x/05_similarity_scorecard.md:5-11`
- Reviewer score constrained by direct evidence gaps.

## 5. Final determination
Can AURA generalize beyond WSA-family drivers?

**PARTIALLY**

Supporting evidence:
- Successful transfer on architecture primitives (SDW ownership, split model, DT structure).
- Incomplete transfer on family-specific control/DAPM complexity and reviewer prediction robustness due to sparse direct review evidence.

