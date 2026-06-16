# Pierre-Louis Bossart (SoundWire/Audio Reviewer Profile)

- Confidence: MEDIUM_CONFIDENCE
- Evidence scope: explicit review entries from `wsa883x`; additional acceptance trends from SDW drivers.

## Architecture preferences
- SDW lifecycle correctness and explicit state handling.
- Defensive runtime PM behavior around resume/attach timing.

## Common review comments
- Remove fragile/invariant conditions in callback paths.
- Validate timeout/completion before regcache sync.

## Common rejection reasons
- Runtime path assumptions not robust under race/timing scenarios.

## Preferred patterns
- SDW-native lifecycle APIs.
- Timeout-safe PM recovery.

## Evidence
- `review_database/pierre_bossart/soundwire/wsa883x.md`
- `review_database/pierre_bossart/runtime_pm/wsa883x.md`
