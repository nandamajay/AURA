# AURA Promotion Report (v1)

## Rules promoted
- `rules/alsa_rules.md`
- `rules/dapm_rules.md`
- `rules/runtime_pm_rules.md`
- `rules/soundwire_rules.md`
- `rules/dt_binding_rules.md`
- `rules/patch_submission_rules.md`

## Patterns promoted
- `patterns/codec_patterns.md`
- `patterns/macro_patterns.md`
- `patterns/machine_driver_patterns.md`
- `patterns/soundwire_patterns.md`
- `patterns/dt_patterns.md`

## Maintainer models created/updated
- `maintainers/mark_brown.md`
- `maintainers/pierre_bossart.md`
- `maintainers/krzysztof_kozlowski.md`
- `maintainers/vinod_koul.md`
- `maintainers/bjorn_andersson.md`

## Rulebook and success model generated
- `qualcomm_audio_rulebook.md`
- `upstream_success_model.md`

## Playbooks generated
- `playbooks/upstream_codec_driver.md`
- `playbooks/upstream_macro_driver.md`
- `playbooks/upstream_machine_driver.md`
- `playbooks/upstream_soundwire_driver.md`
- `playbooks/upstream_dt_binding.md`

## Confidence levels (promoted corpus)
- HIGH_CONFIDENCE: 33
- MEDIUM_CONFIDENCE: 25
- LOW_CONFIDENCE: 4

## Knowledge-base maturity score
- 83.7 / 100
- Basis:
  - 6/6 mined drivers have architecture + patch history + lore links + accepted commits.
  - Required promotion artifacts generated.
  - Score penalized for remaining evidence gaps.

## Remaining evidence gaps
- Reviewer-comment transcript completeness is limited outside `wsa883x` (`INSUFFICIENT_EVIDENCE` in most mined drivers).
- Direct maintainer-comment evidence for `Vinod Koul` and `Bjorn Andersson` is currently insufficient.
- Machine-driver review-comment corpus remains weaker than codec/macro/soundwire corpus.
