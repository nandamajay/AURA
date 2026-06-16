# Reviewer Simulation - Mark Brown

## Expected objections
- kcontrol `put` callbacks that do not return change semantics.
- unnecessary naming/style deviations in user-visible controls.

## Expected nits
- overly broad patch scope mixing controls + PM + bus logic.

## Architecture concerns
- codec core should remain framework-native and concise.

## DT concerns
- defer to DT reviewers, but expects clean split and consistency.

## PM concerns
- PM paths must not regress audio stability.

## SoundWire concerns
- expects idiomatic integration via subsystem APIs.
