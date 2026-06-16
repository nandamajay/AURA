# DT Patterns (Promoted)

## Pattern 1: Compatible expansion via schema + driver together
- Confidence: HIGH_CONFIDENCE
- Problem: adding SoC variants without schema updates breaks validation/review.
- Accepted solution: update `compatible` lists and driver support together.
- Evidence drivers: `wsa884x`, `wcd938x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Maintainers involved: Krzysztof Kozlowski (DT-focused trend evidence), DT maintainer path
- Acceptance rate: 5/5 with explicit YAML evidence

## Pattern 2: Iterative schema correction is normal (vN resubmissions)
- Confidence: MEDIUM_CONFIDENCE
- Evidence drivers: `wsa884x`, `wcd938x`, `lpass_va_macro`
- Acceptance rate: 3/3 where revision history is explicit
