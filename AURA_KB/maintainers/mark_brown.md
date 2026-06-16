# Mark Brown (ASoC Maintainer Profile)

- Confidence: MEDIUM_CONFIDENCE
- Evidence scope: explicit reviewer comments mainly from `wsa883x`; broader maintainership inferred from routing/acceptance.

## Architecture preferences
- Framework-native ASoC component/DAI/control behavior.
- Focused, reviewable patch deltas.

## Common review comments
- Kcontrol semantic correctness (`put` return behavior).
- Control naming/style quality.

## Common rejection reasons
- ALSA control semantic violations.
- Unclear or overly mixed patch scope.

## Patch split expectations
- Smaller revisions directly addressing prior comments.

## Evidence
- `review_database/mark_brown/controls/wsa883x.md`
- `review_database/mark_brown/patch_structure/wsa883x.md`
