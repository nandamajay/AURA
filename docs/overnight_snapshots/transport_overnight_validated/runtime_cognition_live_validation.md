# Runtime Cognition Live Validation

- probe_request_id: `9e689263-cf0d-423d-97d0-193d5379526f`
- probe_classification: `ADVISORY_ONLY`
- target_primary_environment: `Embedded Linux`
- supports_getprop: `UNSUPPORTED`
- adaptive_planning_mode: `EMBEDDED_LINUX`
- adaptive_selected_commands: `cat /proc/version, cat /proc/asound/cards`
- adaptive_classification: `CAPTURE_READY`
- proof_planner_avoids_getprop_when_unsupported: `True`

## Notes
- Unsupported commands are preserved as raw evidence and classified advisory/unknown fail-closed.
- No runtime parity, behavioral equivalence, or merge-readiness claims are made.
