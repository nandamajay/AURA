# Codec Patterns (Promoted)

## Pattern 1: Incremental codec landing (core -> controls -> DAPM/routes -> fixes)
- Confidence: HIGH_CONFIDENCE
- Problem: large monolithic codec submissions stall review cycles.
- Accepted solution: stage features across clear patches and revisions.
- Evidence drivers: `wcd938x`, `wsa883x`, `wsa884x`
- Maintainers involved: Mark Brown (explicit for wsa883x), ALSA maintainers (acceptance path)
- Acceptance rate: 3/3 codec drivers

## Pattern 2: Pair DT schema with driver enablement
- Confidence: HIGH_CONFIDENCE
- Problem: driver-only submission leaves DT contract undefined.
- Accepted solution: include YAML updates in same series.
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`
- Acceptance rate: 3/3 codec drivers
