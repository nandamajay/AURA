# Upstream Success Model (v1)

## What accepted drivers have in common
- [HIGH_CONFIDENCE] All mined drivers show superseded -> accepted lifecycle in Patchwork/lore.
- [HIGH_CONFIDENCE] All mined drivers have explicit accepted commit mappings (`accepted_commits/*.md`).
- [HIGH_CONFIDENCE] All mined drivers use upstream subsystem-native objects (ASoC/SDW/platform).

## What reviewers repeatedly requested
- [MEDIUM_CONFIDENCE] ALSA control callback correctness (explicit: Mark Brown on wsa883x).
- [MEDIUM_CONFIDENCE] Runtime resume robustness under timing constraints (explicit: Pierre on wsa883x).
- [LOW_CONFIDENCE] Cross-driver textual reviewer requests are sparse due missing comment archives.

## What reviewers repeatedly rejected/flagged
- [MEDIUM_CONFIDENCE] Semantic control callback issues and unsafe PM assumptions (wsa883x explicit evidence).
- [LOW_CONFIDENCE] Broader rejection taxonomy across all drivers remains incomplete.

## Most successful patch structures
- [HIGH_CONFIDENCE] DT + driver split series with focused ownership.
- [HIGH_CONFIDENCE] Multi-patch codec bring-up (core, SDW/transport, controls, DAPM/routes).
- [HIGH_CONFIDENCE] Macro bring-up in support + DAPM/route split.

## Common reasons for v2/v3 revisions
- [MEDIUM_CONFIDENCE] Style/semantic fixes for controls.
- [MEDIUM_CONFIDENCE] DT schema tightening and variant adjustments.
- [MEDIUM_CONFIDENCE] Runtime robustness fixes.

## Quantitative view
- Drivers analyzed: 6
- Drivers with accepted commit mapping: 6/6
- Drivers with reviewer-comment transcript completeness: 1/6 full-ish, 5/6 insufficient
- Confidence impact: technical pattern confidence high, reviewer-specific confidence medium/low.
