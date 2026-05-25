# Replay Reconstruction Evidence

Date: 2026-05-19

## Requirement
Replay reconstruction must rebuild:
- snapshot root
- validation context
- governance decisions
- lineage path

Reconstruction failure must invalidate execution trust.

## Evidence
Source:
- `evidence/snapshot-runtime/2026-05-19-snapshot-runtime-evidence.json`

Observed in captured run:
- `reconstruct` endpoint status: `200`
- `reconstruct_trust_valid=true`
- reconstruction hash:
  - `51040dcdfb4b1b2302ff627098ca06a13b3d209c1f42860827ee83b68a5d5df3`

Regression coverage:
- `test_retry_lineage_is_monotonic_and_replay_failure_invalidates_trust`
  - validated replay failure path sets `replay_trust_valid=0`
  - decision outcome becomes `approved_but_replay_failed` with rejection transition

## Conclusion
Replay reconstruction is enforced as a trust boundary, not a best-effort indicator.
