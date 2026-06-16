# Qualcomm Audio Upstreaming Corpus Report

Generated: 2026-06-13 22:43:07

## 1. Total drivers discovered
- 66

## 2. Total upstreamed drivers
- 31

## 3. Total downstream-only drivers
- 18

## 4. Family coverage
- 7 families modeled (`families/`)

## 5. Maintainer coverage
- 5 maintainer models present (`maintainers/`)

## 6. Pattern coverage
- 5 primary pattern libraries present (`patterns/`)

## 7. Knowledge gaps
- Direct review-comment corpus is still sparse for many non-wsa883x drivers.
- Several downstream codecs (aqt1000, qmp1000, rouleur, bolero stack) lack clear upstream equivalents in current corpus.
- Downstream machine-driver board variants remain largely downstream-only and need deeper functional mapping.

## 8. Confidence score
- 82/100

## 9. Corpus maturity score
- 88/100

## 10. Readiness assessment
- PARTIAL_CORPUS

## Promotion Rule Check
- Inventory completed: YES
- Family models completed: YES
- Upstream corpus completed: YES (indexed profiles exist)
- Maintainer models completed: YES
- Success model completed: YES (`upstream_success_model.md`)
- Corpus maturity >= 90: NO
- At least 5 upstreamed drivers indexed: YES (12)

Gate result: real conversion remains blocked by corpus maturity threshold.
