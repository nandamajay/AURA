# Replay Portability

## Goal
Verify deterministic replay remains target-agnostic across simulated targets.

## Validation Dimensions
- Deterministic event ordering fingerprint stability.
- Governance classification preservation through replay reconstruction.
- Replay operation independent of hardware topology specifics.
- Procedural memory integrity preserved by orchestration-only operations.
- Semantic cognition replay determinism (lineage-bound semantic fingerprints).
- Semantic evidence references preserved across replay restore.
- Unified cognition correlation replay determinism (lineage + artifact graph stability).
- Confidence evolution replay consistency under identical evidence.

## Matrix Targets
- `fake_target_alpha`
- `fake_target_beta`
- `degraded_target_gamma`

## Expected Results
- Stable `deterministic_replay_fingerprint` across repeated reconstruction.
- Replay event count remains invariant for identical event stream.
- Governance labels remain in allowed set (`GOVERNED_APPROVED`, `ADVISORY_ONLY`, `FAIL_CLOSED`).
- No target-specific branching required in replay engine.
- Semantic replay trace preserves lineage and artifact references.
- Correlation replay trace preserves lineage ID, confidence state, and anomaly classification.

## Related
- `replay_lineage.md`
