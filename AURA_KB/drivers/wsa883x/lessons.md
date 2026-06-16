# WSA883x Lessons Learned

## Lesson 1
- Topic: kcontrol callback semantics.
- Evidence: Mark Brown feedback on v1/v2 controls series.
- Practical rule: `put` callbacks must return `1` when value changes.

## Lesson 2
- Topic: SoundWire + PM edge cases are review-critical.
- Evidence: Pierre review on resume timeout handling; subsequent fix commit.
- Practical rule: completion/timeout paths must gate regcache sync and return failures safely.

## Lesson 3
- Topic: Prefer framework-native architecture.
- Evidence: upstream converged on SDW + ASoC standard objects.
- Practical rule: avoid exposing machine-driver-specific helper contracts from codec driver unless required by subsystem design.

## Lesson 4
- Topic: Small, quick review deltas win.
- Evidence: v1 -> v2 -> v3 progression for controls/DAPM patch.
- Practical rule: submit narrowly scoped revisions tied directly to reviewer feedback.


## Blind Reproduction Campaign Validation
- Campaign run `20260613_235158` overall similarity: 75.2%.


## Failure Analysis Pass (Validated)
- Reproduction error was driven mostly by abstraction-level gaps (callback/file-layout parity), reviewer-model sparsity, and scoring-rule misfit for macro drivers.
- Key validated fix direction: driver-type-aware reconstruction/scoring plus explicit SWR->SDW and split-file pattern enforcement.
