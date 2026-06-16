# Phase 3 - Reviewer Simulation (v1)

## Patch-by-patch simulated outcome

| Patch | Mark Brown | Pierre Bossart | Krzysztof | Vinod Koul | Bjorn Andersson | Result |
|---|---|---|---|---|---|---|
| 1 DT binding | REQUEST_CHANGES | - | REQUEST_CHANGES | - | - | REQUEST_CHANGES |
| 2 core codec | REQUEST_CHANGES | - | - | - | - | REQUEST_CHANGES |
| 3 DAPM/routes | REQUEST_CHANGES | - | - | - | - | REQUEST_CHANGES |
| 4 controls | REQUEST_CHANGES | - | - | - | - | REQUEST_CHANGES |
| 5 runtime PM | REQUEST_CHANGES | REQUEST_CHANGES | - | - | - | REQUEST_CHANGES |
| 6 SoundWire | REQUEST_CHANGES | REQUEST_CHANGES | REQUEST_CHANGES | REQUEST_CHANGES | - | REQUEST_CHANGES |
| 7 cleanup | REJECT (fold) | - | - | - | - | REJECT |

## Rejections / hard blockers

### Patch 7 rejected
- Exact root cause: standalone cleanup patch lacks ownership value and harms bisect/review focus.
- Violated rule: patch split by logical ownership.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md`
- Violated pattern: codec series should be binding/core/features/fixes, not trailing cosmetic patch.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/playbooks/upstream_codec_driver.md`
- Violated maintainer preference: focused reviewable deltas.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/mark_brown.md`

## Request-changes root causes

### DT patch (Patch 1)
- Root cause: expected schema strictness likely under-specified in v1.
- Violated rule: DT schema constraints mandatory.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/dt_binding_rules.md`
- Maintainer preference: DT hygiene and consistency.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/krzysztof_kozlowski.md`

### Control patch (Patch 4)
- Root cause: risk of kcontrol `put` semantics/style nits.
- Violated rule: ALSA put callback semantics.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/alsa_rules.md`
- Maintainer preference: Mark Brown control semantics/style.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/mark_brown.md`

### Runtime PM patch (Patch 5)
- Root cause: timeout-safe ordering likely requested.
- Violated rule: timeout-safe resume path.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`
- Maintainer preference: PM robustness around attach/resume.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/maintainers/pierre_bossart.md`

### SoundWire patch (Patch 6)
- Root cause: stream/callback ownership and state-guard correctness.
- Violated rule: generic SDW lifecycle and clean ownership boundaries.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
- Violated pattern: move common SDW runtime allocations to proper layer when requested.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/reviewer_evidence_database.md`
- Maintainer preferences: Pierre/Krzysztof/Vinod SoundWire modeling focus.
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/pierre_bossart_acceptance_model.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/krzysztof_acceptance_model.md`
  - `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/review_campaign/20260614_092103_reviewer_evidence_acquisition/vinod_koul_acceptance_model.md`

## v1 campaign metrics (experience metrics)
- Review-survival probability (series-level): 58%
- Reviewer confidence (weighted): 71/100
- Acceptance probability at v1: 35%
- Evidence basis:
  - wsa884x v1 patch-split weakness and maintainer similarity trend:
    `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/wsa884x/20260613_222724_nandam/scorecards/phase5_similarity_v1.md`
