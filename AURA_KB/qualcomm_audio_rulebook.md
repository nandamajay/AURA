# Qualcomm Audio Rulebook (v1)

## ALSA
- [HIGH_CONFIDENCE] Use standard ASoC component/DAI registration objects (`rules/alsa_rules.md`).
- [MEDIUM_CONFIDENCE] Enforce kcontrol callback semantics before resend (`rules/alsa_rules.md`).

## DAPM
- [HIGH_CONFIDENCE] Include explicit DAPM widgets/routes in accepted series (`rules/dapm_rules.md`).
- [MEDIUM_CONFIDENCE] Stage DAPM growth incrementally across revisions.

## Runtime PM
- [MEDIUM_CONFIDENCE] Integrate runtime PM for codec/macro drivers.
- [MEDIUM_CONFIDENCE] Ensure resume timeout safety before cache sync.

## SoundWire
- [HIGH_CONFIDENCE] Prefer SDW-native lifecycle APIs and ownership model.
- [MEDIUM_CONFIDENCE] Split transport/core responsibilities cleanly.

## DT Bindings
- [HIGH_CONFIDENCE] Pair YAML binding updates with driver support.
- [HIGH_CONFIDENCE] Treat schema constraints as merge-gate requirements.

## Machine Drivers
- [MEDIUM_CONFIDENCE] Keep board policy outside codec core where possible.
- [LOW_CONFIDENCE] Direct machine-driver review comment corpus is incomplete.

## Codec Drivers
- [HIGH_CONFIDENCE] Land core first, then controls/DAPM/routes, then focused fixes.

## Patch Submission
- [HIGH_CONFIDENCE] Expect vN iterations; superseded states are normal.
- [HIGH_CONFIDENCE] Split by ownership boundary (DT/core/transport/features).
- [HIGH_CONFIDENCE] Track final merges via Patchwork `commit_ref`.

## Review Handling
- [MEDIUM_CONFIDENCE] Address each review point with tight, auditable deltas.
- [LOW_CONFIDENCE] For maintainers without comment corpus, avoid overfitting assumptions.

## Acceptance Strategies
- [HIGH_CONFIDENCE] Demonstrate upstream framework alignment early.
- [MEDIUM_CONFIDENCE] Keep first accepted series minimal; follow with explicit fixups.
