# RB3 Failure Reasoning (Static Validation)

- classification: `ADVISORY_ONLY`
- current_state: `playback_failed`

## Reasons
- `unresolved_routes`: No backend/frontend route mapping was extracted from DTS routing evidence.
- `missing_mixer`: No runtime mixer state change was observed while playback workflow was attempted.
- `missing_backend`: Runtime telemetry did not show backend activity during playback validation.
- `unsupported_backend`: Runtime telemetry did not show backend activity during playback validation.
- `soundwire_dependency_failure`: SoundWire-related topology markers exist but DAPM route activation was not observed.
- `invalid_pcm`: PCM runtime state did not become active for the planned playback path.
- `route_collapse`: Playback started but route activation confidence did not reach HIGH.
- `playback_not_completed`: Playback command did not complete successfully.

## Notes
- Report generated from static evidence and prior runtime snapshots only.
- No live playback command executed in this validation run.
- Advisory-only posture preserved.
