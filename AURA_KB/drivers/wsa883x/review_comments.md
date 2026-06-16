# WSA883x Review Comments (Evidence)

## Key Review Threads
- Patchwork `12899623` ([2/4] codec core): Pierre-Louis Bossart review.
- Patchwork `12899625` (v1 controls/DAPM): Mark Brown review.
- Patchwork `12900259` (v2 controls/DAPM): Mark Brown review.
- Patchwork `12901777` (v3 controls/DAPM): accepted by Mark Brown.

## Comment -> Outcome Matrix
1. Reviewer: Pierre-Louis Bossart
- Topic: SoundWire callback conditions and runtime resume timeout checking.
- Outcome: follow-up robustness changes; explicit timeout handling landed (`0df73e1a9f7b`).

2. Reviewer: Mark Brown
- Topic: ALSA kcontrol semantics (`put` callback must return change state).
- Outcome: revised in next versions before acceptance.

3. Reviewer: Mark Brown
- Topic: control string naming idiom (`Speaker` casing style request).
- Outcome: v2 -> v3 update; v3 accepted.

## Constraint Note
- Direct `lore.kernel.org` HTML fetch was blocked in this environment.
- Review evidence extracted via Patchwork API comment endpoints plus merged commit `Link:` tags.
