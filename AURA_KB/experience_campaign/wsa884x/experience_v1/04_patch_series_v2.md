# Phase 4 - V2 Revision

## Change objective
Apply all v1 review feedback by reducing patch count, tightening ownership boundaries, and hardening DT/PM/SDW semantics.

## v2 patch ordering (revised)

### Patch 1
- Title: `ASoC: dt-bindings: qcom,wsa8840: add WSA884x schema`
- Changes vs v1:
  - tightened schema constraints
  - cleaned examples and compatible mapping
- Why: close DT schema gate first.

### Patch 2
- Title: `ASoC: codecs: wsa884x: add core codec driver with PM + SDW-safe base`
- Changes vs v1:
  - merged former core + PM + SDW base safeguards
  - timeout-safe runtime PM ordering integrated from start
  - explicit SDW state guards in callbacks
- Why: remove fragile staged dependency that created review churn.

### Patch 3
- Title: `ASoC: codecs: wsa884x: add controls and minimal DAPM routes`
- Changes vs v1:
  - merged controls + DAPM to keep feature ownership coherent
  - kcontrol semantics audited (`put` change-state behavior)
  - minimized route graph to functional path only
- Why: align with Mark’s scope/style expectations.

### Patch 4
- Title: `ASoC: codecs: wsa884x: small follow-up fixes from v1 feedback`
- Changes vs v1:
  - removed standalone cleanup patch
  - convert only review-requested nits into focused fix patch
- Why: preserve bisect-safety and review tractability.

## Strategy updates
- DT strategy: strict schema-first gate retained.
- PM strategy: integrated into core patch instead of late add-on.
- SoundWire strategy: callback/state correctness in core flow, not post-hoc cleanup.
- Patch split strategy: 7 -> 4 patches.

## Evidence
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/patch_submission_rules.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/runtime_pm_rules.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/rules/soundwire_rules.md`
- `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/wsa884x/20260613_222724_nandam/iteration_v2/scorecards/phase7_v2_similarity.md`
