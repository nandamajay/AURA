# ALSA Rules (Promoted)

## Rule 1: Use standard ASoC component/DAI registration objects
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Evidence files:
  - `drivers/wsa884x/architecture.md`
  - `drivers/wcd938x/architecture.md`
  - `drivers/lpass_rx_macro/architecture.md`
  - `drivers/lpass_tx_macro/architecture.md`
  - `drivers/lpass_va_macro/architecture.md`
- Practical rule: upstream submissions should expose `snd_soc_component_driver` + `snd_soc_dai_driver` and framework-native callbacks.

## Rule 2: Kcontrol `put` callbacks must follow ALSA return semantics
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: explicit maintainer request
- Maintainer evidence: Mark Brown review notes for WSA883x
- Evidence files:
  - `review_database/mark_brown/controls/wsa883x.md`
- Practical rule: return `1` only on value change, `0` otherwise; fix before resend.

## Rule 3: Keep initial upstream feature scope reviewable
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence drivers: all mined drivers reached acceptance via staged series and revision cycles.
- Evidence files:
  - `drivers/*/patch_history.md`
  - `accepted_commits/*.md`
