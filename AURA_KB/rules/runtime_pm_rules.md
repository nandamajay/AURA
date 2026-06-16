# Runtime PM Rules (Promoted)

## Rule 1: Runtime PM integration is expected in codec/macro drivers
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: 2+ drivers + subsystem requirement
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Evidence files:
  - `drivers/*/architecture.md` (runtime PM presence)

## Rule 2: Resume path must be timeout-safe before cache sync
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: explicit maintainer/reviewer request
- Evidence files:
  - `review_database/pierre_bossart/runtime_pm/wsa883x.md`
  - `accepted_commits/wsa883x.md` (timeout handling follow-up)
