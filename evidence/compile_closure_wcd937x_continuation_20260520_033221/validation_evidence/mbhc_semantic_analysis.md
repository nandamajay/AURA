# MBHC Semantic Analysis

## Structural Evidence
- Downstream `wcd_mbhc_` hits: `87`
- Upstream `wcd_mbhc_` hits: `82`
- Downstream `SND_JACK` mentions: `4`
- Upstream `SND_JACK` mentions: `6`

## Semantic Risk
- MBHC is callback and interrupt sensitive.
- Structural overlap does not prove equivalent debounce, threshold, plug-type, or button-report behavior.
- No hardware jack insertion/removal traces were captured in this pass.

## Decision
- MBHC runtime parity: `UNKNOWN`
- Jack detection proof: `NOT_PROVEN`
- Behavioral readiness: `advisory_only`

## Classification
- runtime_unverified
- escalation_required
