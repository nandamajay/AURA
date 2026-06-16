# Macro Patterns (Promoted)

## Pattern 1: Split macro enablement and route/widget expansion
- Confidence: HIGH_CONFIDENCE
- Problem: macro drivers include heavy audio graph and policy logic.
- Accepted solution: core support patch + DAPM/routes patch in same revisioned series.
- Evidence drivers: `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Maintainers involved: ALSA maintainer path (Mark Brown routing in headers)
- Acceptance rate: 3/3 macro drivers

## Pattern 2: Reuse platform-driver macro architecture across LPASS variants
- Confidence: MEDIUM_CONFIDENCE
- Problem: per-SoC divergence can fragment macro code.
- Accepted solution: common macro driver structure with DT compatible expansion.
- Evidence drivers: `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Acceptance rate: 3/3 macro drivers
