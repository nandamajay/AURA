# Reviewer Survival Playbook

## Quantitative survival model (review-only campaign)
Baseline from current KB:
- Current reviewer-survival score: **63/100**
  - Evidence: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_004452_wcd938x/wcd938x_reviewer_prediction_report.md:16-21`

Model (if architecture is already correct):
- `S = 0.35 * CommentEvidence + 0.25 * PatchDecomposition + 0.20 * MaintainerRuleCompliance + 0.20 * IterationDiscipline`

Where:
- `CommentEvidence`: direct reviewer-comment availability and topical mapping.
- `PatchDecomposition`: ownership-clean split and revision clarity.
- `MaintainerRuleCompliance`: kcontrol semantics, PM safety, DT hygiene.
- `IterationDiscipline`: speed/precision of v1->vN fixes and follow-up handling.

## Current factor estimates (evidence-backed)
| Factor | Current score | Evidence |
|---|---:|---|
| CommentEvidence | 35 | Direct comment text mostly only for wsa883x; others insufficient |
| PatchDecomposition | 82 | Multi-driver evidence of logical splitting and accepted commit chains |
| MaintainerRuleCompliance | 78 | Clear rules exist for Mark/Pierre paths and DT/PM patterns |
| IterationDiscipline | 70 | Superseded->accepted behavior captured across drivers |

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/multi_driver_evidence_report.md:5-10`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md:1-28`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/mark_brown/controls/wsa883x.md:4-12`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_database/pierre_bossart/runtime_pm/wsa883x.md:4-6`

## Survival actions (evidence-backed only)
1. Apply mandatory pre-submit semantic gates:
   - kcontrol `put` return semantics
   - runtime PM timeout-safety in resume-sensitive paths
2. Keep first series ownership-clean:
   - binding/core/feature/fix split
3. Enforce evidence-thresholded reviewer simulation:
   - if direct comment evidence missing, classify prediction confidence as LOW and avoid over-fitting maintainer behavior
4. Treat DAPM minimization as family-sensitive:
   - WSA: often helps early acceptance
   - WCD: preserve required larger feature/control surface

## Projected reviewer-survival improvement
- Current: **63/100**
- Projected after campaign playbook adoption: **74/100**

Projection rationale:
- +6 from stricter maintainer-rule compliance gates (Mark/Pierre rules)
- +3 from family-sensitive patch/decomposition handling
- +2 from confidence-thresholding to reduce false reviewer predictions

Constraint:
- Ceiling limited by comment-evidence sparsity until more direct review threads are indexed.

## Is reviewer-survival now the primary blocker?
**YES**

Reason:
- Architecture, DT, and SoundWire modeling have stronger demonstrated capability than reviewer-survival prediction quality.
- Remaining failure mode is review convergence uncertainty, especially where direct comment evidence is sparse.

Evidence:
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstruction_vs_upstream_delta.md:6-14`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_004452_wcd938x/wcd938x_similarity_report.md:6-14`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/real_reconstruction_validation/20260614_004452_wcd938x/wcd938x_reviewer_prediction_report.md:16-21`

