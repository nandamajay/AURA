# PM Experiment Summary: WSA884x Three-Variant Generalization

Generated: 2026-06-20

## Experiment result
- Variant A (blind): score 36.21, gate PASS.
- Variant B (relative skeleton): score 87.99, gate PASS.
- Variant C (learning-informed): score 87.99, gate PASS.

## Best method
Relative-skeleton method (Variant B) delivered the largest quality jump over blind baseline. Learning-informed method (Variant C) matched B quality while preserving risk posture.

## Did AURA generalize beyond WCD?
Yes, at medium confidence. Governance/process transfer generalized well to WSA, while behavior-specific transfer remained constrained.

## Does this validate generic rule extraction?
Partially yes. Generic rules improved safety/discipline but did not deliver additional score gain over the relative-skeleton baseline in this run.

## Continue WSA learning or move domains?
- Continue one more WSA-family run to stabilize reference-policy and anti-copy handling.
- Then move to a non-audio pilot for broader cross-domain stress testing.

## Impact on WCD9378 Monday plan
No change. WCD9378 runtime evidence collection and blocker resolution remain independent and still required.

## Runtime claim posture
No variant claims runtime playback/capture readiness.
