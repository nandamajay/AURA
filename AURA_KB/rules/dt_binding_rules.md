# DT Binding Rules (Promoted)

## Rule 1: Submit YAML binding updates together with driver support
- Confidence: HIGH_CONFIDENCE
- Promotion basis: 2+ drivers
- Evidence drivers: `wsa883x`, `wsa884x`, `wcd938x`, `lpass_rx_macro`, `lpass_tx_macro`, `lpass_va_macro`
- Evidence files:
  - `drivers/wsa884x/patch_history.md`
  - `drivers/wcd938x/patch_history.md`
  - `drivers/lpass_rx_macro/architecture.md`
  - `drivers/lpass_tx_macro/architecture.md`
  - `drivers/lpass_va_macro/architecture.md`

## Rule 2: DT schema constraints are mandatory for acceptance path
- Confidence: HIGH_CONFIDENCE
- Promotion basis: Linux subsystem requirement
- Evidence files:
  - `drivers/wsa884x/architecture.md` (`qcom,wsa8840.yaml`)
  - `drivers/wcd938x/architecture.md` (`qcom,wcd938x*.yaml`)
  - `drivers/lpass_*_macro/architecture.md` (`qcom,lpass-*-macro.yaml`)
