# Patch Submission Rules (Promoted)

## Rule 1: Expect superseded revisions before acceptance
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence drivers: all 6 mined drivers
- Evidence files:
  - `drivers/*/patch_history.md`
  - `multi_driver_evidence_report.md`

## Rule 2: Split series by logical ownership (binding/core/feature blocks)
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence:
  - WSA884x: 2-patch DT+codec sequence across v1-v4 (`drivers/wsa884x/patch_history.md`)
  - WCD938x: multi-patch split for DT/core/SDW/controls/DAPM/routes (`drivers/wcd938x/patch_history.md`)
  - LPASS macros: support + DAPM route patch split (`drivers/lpass_*_macro/patch_history.md`)

## Rule 3: Track accepted commits via Patchwork `commit_ref`
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence files:
  - `accepted_commits/wsa883x.md`
  - `accepted_commits/wsa884x.md`
  - `accepted_commits/wcd938x.md`
  - `accepted_commits/lpass_rx_macro.md`
  - `accepted_commits/lpass_tx_macro.md`
  - `accepted_commits/lpass_va_macro.md`
