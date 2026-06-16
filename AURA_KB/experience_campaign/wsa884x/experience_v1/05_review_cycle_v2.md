# Phase 5 - Second Review Round Simulation (v2)

## Patch-level outcome

| Patch | Mark Brown | Pierre Bossart | Krzysztof | Vinod Koul | Bjorn Andersson | Result |
|---|---|---|---|---|---|---|
| 1 DT schema | ACCEPT | - | ACCEPT | - | - | ACCEPT |
| 2 core + PM + SDW base | REQUEST_CHANGES (minor scope wording) | ACCEPT | REQUEST_CHANGES (minor DT reference wording) | REQUEST_CHANGES (low-confidence SDW nit) | - | REQUEST_CHANGES |
| 3 controls + minimal DAPM | ACCEPT | - | - | - | - | ACCEPT |
| 4 focused follow-up fixes | ACCEPT | ACCEPT | ACCEPT | ACCEPT | - | ACCEPT |

## Delta vs v1
- Review-survival probability: 58% -> 83% (**+25**)
- Reviewer confidence: 71/100 -> 79/100 (**+8**)
- Acceptance probability at current revision: 35% -> 72% (**+37**)

## Why improved
1. Removed patch-structure anti-pattern (standalone cleanup patch).
2. PM and SDW correctness moved into core design, reducing late review objections.
3. Controls/DAPM bundle made ownership clearer and easier to review.

## Remaining risk
- Non-primary reviewer predictions still limited by evidence confidence (especially Bjorn; Vinod low-volume).
- Evidence:
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/bjorn_acceptance_model.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/vinod_koul_acceptance_model.md`
