# Blind Reproduction Campaign Report

Run: `/local/mnt/workspace/AURA_V1_upstream/AURA_KB/validation/blind_reproduction_campaign/20260613_235158`

Corpus baseline: frozen Corpus v1; growth continues in parallel.

| Driver | Arch | DT | Patch | Reviewer | PM | SDW | Overall |
|---|---:|---:|---:|---:|---:|---:|---:|
| wsa883x | 46.7 | 95.0 | 76.0 | 72.0 | 92.0 | 95.0 | **75.2** |
| wsa884x | 46.7 | 95.0 | 84.0 | 52.0 | 92.0 | 95.0 | **73.8** |
| wcd938x | 58.3 | 95.0 | 92.0 | 52.0 | 70.0 | 88.0 | **74.0** |
| lpass_rx_macro | 81.8 | 95.0 | 100.0 | 46.0 | 92.0 | 80.0 | **82.7** |
| lpass_tx_macro | 90.9 | 95.0 | 100.0 | 46.0 | 92.0 | 80.0 | **84.9** |
| lpass_va_macro | 90.9 | 95.0 | 100.0 | 46.0 | 92.0 | 80.0 | **84.9** |

## Campaign averages
- Architecture similarity: 69.2%
- DT similarity: 95.0%
- Patch strategy similarity: 92.0%
- Reviewer prediction accuracy: 52.3%
- Runtime PM similarity: 88.3%
- SoundWire similarity: 86.3%
- Overall similarity: **79.2%**

## Assessment
- Result: NEEDS_IMPROVEMENT
- AURA can reconstruct maintainer-aligned technical structure strongly; reviewer prediction remains the weakest dimension where comment corpora are sparse.

## KB updates applied
- Appended campaign validation note to `drivers/wsa883x/lessons.md`
- Appended campaign validation note to `drivers/wsa884x/lessons.md`
- Appended campaign validation note to `drivers/wcd938x/lessons.md`
- Appended campaign validation note to `drivers/lpass_rx_macro/lessons.md`
- Appended campaign validation note to `drivers/lpass_tx_macro/lessons.md`
- Appended campaign validation note to `drivers/lpass_va_macro/lessons.md`
