# Reviewer Simulation - Pierre-Louis Bossart

## Expected objections
- state transitions that assume device is attached without guards.
- resume flows that sync cache before readiness/timeout checks.

## Expected nits
- redundant callback conditions in stream/update-status paths.

## Architecture concerns
- explicit lifecycle ownership between codec state and SDW transport.

## DT concerns
- limited unless DT impacts runtime transport behavior.

## PM concerns
- timeout-safe recovery and error handling.

## SoundWire concerns
- stream add/remove sequencing and port-prep transitions must be robust.
