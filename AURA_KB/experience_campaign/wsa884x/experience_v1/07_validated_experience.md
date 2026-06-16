# Phase 7 - Validated Experience Extraction

Only lessons validated within this campaign flow (v1 -> v2 simulation with existing KB evidence) are listed.

## Lesson 1
- Source phase: Phase 3 -> Phase 4
- Lesson: eliminate standalone cleanup patches in initial series; fold into ownership patches.
- Supporting evidence:
  - v1 rejection reason in `03_review_cycle_v1.md`
  - patch split rule: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md`
- Confidence: HIGH
- Applicable families: WSA, WCD, LPASS macros (patch-structure rule is cross-family)

## Lesson 2
- Source phase: Phase 3 -> Phase 5
- Lesson: PM + SDW safety integrated in core patch survives better than deferred late patches.
- Supporting evidence:
  - v1 PM/SDW request-change concentration in `03_review_cycle_v1.md`
  - v2 acceptance improvement in `05_review_cycle_v2.md`
  - reviewer models:
    `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/pierre_bossart_acceptance_model.md`
- Confidence: MEDIUM-HIGH
- Applicable families: WSA and SoundWire-dependent codec/macro paths

## Lesson 3
- Source phase: Phase 2 -> Phase 5
- Lesson: controls and minimal DAPM in one ownership patch reduce review noise versus separated micro-patches.
- Supporting evidence:
  - v1 had two separate feature patches (`02_patch_series_v1.md`)
  - v2 merged and improved survival (`05_review_cycle_v2.md`)
  - DAPM + ALSA rules: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/dapm_rules.md`, `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/alsa_rules.md`
- Confidence: MEDIUM
- Applicable families: WSA-family codecs; `INSUFFICIENT_EVIDENCE` for broad WCD generalization in this campaign alone.

## KB update performed
- Appended experience-validated lessons section to:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wsa884x/lessons.md`
