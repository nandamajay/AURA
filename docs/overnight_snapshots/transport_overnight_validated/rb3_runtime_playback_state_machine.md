# RB3 Runtime Playback State Machine

## States
- `asset_selected`
- `asset_deployed`
- `mixers_applied`
- `backend_enabled`
- `pcm_active`
- `playback_running`
- `playback_completed`
- `playback_failed`
- `cleanup_completed`

## Transition discipline
- transition requires concrete evidence
- no state promotion from intent alone
- playback completion requires command success and correlated telemetry

## Fail-closed rules
- ambiguous telemetry => remain advisory state
- playback attempt without activation evidence => `playback_failed`
- cleanup success/failure is tracked explicitly
