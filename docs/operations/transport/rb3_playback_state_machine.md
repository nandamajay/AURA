# RB3 Playback State Machine

Playback is modeled as subsystem activation workflow, not command execution.

## States
1. `INTENT_VALIDATED`
2. `OVERLAY_RESOLVED`
3. `PCM_RESOLVED`
4. `ASSET_SELECTED`
5. `ASSET_STAGED`
6. `ASSET_DEPLOYED`
7. `ROUTE_ACTIVATED`
8. `PLAYBACK_EXECUTED`
9. `TELEMETRY_CORRELATED`
10. `COMPLETED`

## Transition policy
- Every transition requires evidence.
- Missing evidence keeps state machine in advisory state.
- `COMPLETED` is allowed only with playback completion + high-confidence route activation evidence.

## Fail-closed behavior
- unresolved overlay -> stay before route activation
- unresolved PCM -> no playback execution approval
- missing telemetry correlation -> no completion claim
