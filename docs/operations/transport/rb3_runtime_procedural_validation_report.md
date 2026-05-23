# RB3 Runtime Procedural Validation

- execution_mode: `live_controlled`
- current_state: `cleanup_completed`
- final_classification: `ADVISORY_ONLY`
- process_success: `True`
- evidence_success: `True`
- audible_human_validation: `unknown`
- route_activation_confidence: `MEDIUM`
- playback_completion: `True`
- wav_duration_seconds: `25.0`
- playback_runtime_seconds: `25.902215`
- playback_duration_match: `True`
- soundwire_activity: `False`
- regression_detected: `True`
- regression_severity: `MEDIUM`
- topology_state: `INFERRED`
- topology_confidence: `0.565`
- agentization_state: `topology_validated`

## Failure Reasons
- `missing_mixer`: No runtime mixer state change was observed while playback workflow was attempted.
- `missing_backend`: Runtime telemetry did not show backend activity during playback validation.
- `unsupported_backend`: Runtime telemetry did not show backend activity during playback validation.
- `soundwire_dependency_failure`: SoundWire-related topology markers exist but DAPM route activation was not observed.
- `invalid_pcm`: PCM runtime state did not become active for the planned playback path.
- `route_collapse`: Playback started but route activation confidence did not reach HIGH.

## Missing Evidence
- none

## Governance
- windows remains execute-only
- linux remains cognition authority
- write operations require governed_write_approved
- fail-closed classification preserved
