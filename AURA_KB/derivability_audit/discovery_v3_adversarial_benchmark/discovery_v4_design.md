# Discovery_V4 Design (Borderline Abstention)

## Formal abstention mechanism
For each candidate with V2 base prediction `discovered_rule`, compute:
`novelty_confidence`, `derivability_confidence`, `causal_confidence`, `transfer_confidence`, and `overall_discovery_confidence`.

`overall_discovery_confidence = geometric_mean( novelty^0.25, derivability^0.30, causal^0.25, transfer^0.20 )`

Decision rule at threshold `T`:
- if V2 base class != discovered: keep V2 class (`copied_rule` or `generalized_rule`)
- if V2 base class == discovered and overall_discovery_confidence < T: `undecided_discovery`
- else: `discovered_rule`

## Outcome space
- `copied_rule`
- `generalized_rule`
- `discovered_rule`
- `undecided_discovery`

## Threshold sweep
- Evaluated thresholds from `0.50` to `0.99` on the 200-item adversarial benchmark.
- Curves and per-threshold metrics are in `abstention_curve.json`.
