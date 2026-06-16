# Playbook: Upstream Codec Driver (Promoted)

## Preparation
- Collect downstream/upstream codec core evidence, DT bindings, accepted commit refs.
- Ensure component/DAI objects and control semantics are aligned.

## Implementation strategy
- Stage codec as: core registration -> controls -> DAPM/routes -> fixes.
- Keep board policy out of codec where possible.

## Patch series structure
1. DT binding patch
2. Codec core patch
3. Controls/DAPM/routes patches
4. Focused robustness fixes

## Review expectations
- Mark Brown: control semantics and style.
- Pierre: runtime/SDW safety where applicable.
- Krzysztof/DT path: schema correctness.

## Validation checklist
- [ ] kcontrol return semantics
- [ ] DAPM route sanity
- [ ] PM suspend/resume safety
- [ ] DT schema validation
- [ ] Patchwork accepted-state tracking

## Submission checklist
- [ ] lore links indexed
- [ ] accepted commit refs indexed
- [ ] unresolved comments addressed in next revision
- Confidence: HIGH_CONFIDENCE
