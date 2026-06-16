# DAPM Rules (Promoted)

## Rule 1: Upstream codec/macro series must provide explicit DAPM widgets and routes
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence drivers: `wcd938x`, `wsa883x`, `wsa884x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Evidence files:
  - `drivers/wcd938x/patch_history.md` (accepted DAPM/routing patches)
  - `drivers/lpass_rx_macro/patch_history.md`
  - `drivers/lpass_tx_macro/patch_history.md`
  - `drivers/lpass_va_macro/patch_history.md`

## Rule 2: Keep DAPM graph additions minimal in initial series, then iterate
- Confidence: MEDIUM_CONFIDENCE
- Promotion basis: 2+ drivers + observed superseded->accepted loops
- Evidence files:
  - `drivers/wsa884x/patch_history.md`
  - `drivers/wcd938x/patch_history.md`
  - `multi_driver_evidence_report.md`

## Refinement Note (2026-06-14)
- Family-sensitivity: DAPM minimization applies differently by codec family.
- Validated evidence: `wcd938x` upstream keeps a materially larger control/DAPM surface than `wsa883x` despite using framework-native ASoC patterns.
- Action: treat DAPM simplification as a tuning heuristic, not a hard universal rule.
- Evidence files:
  - `validation/real_reconstruction_validation/20260614_002943_wsa883x/reconstruction_vs_upstream_delta.md`
  - `validation/real_reconstruction_validation/20260614_004452_wcd938x/wcd938x_forensic_delta_report.md`
