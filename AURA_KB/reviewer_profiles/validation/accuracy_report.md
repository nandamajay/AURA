# Reviewer Profile Validation Accuracy Report

Generated: 2026-06-21

## Validation Set
- Accepted patches/series: 3
- Rejected/changes-requested patches/series: 1

## Per-Reviewer Precision/Recall
- Krzysztof Kozlowski: precision=0.00, recall=0.00, FP=1, FN=0
- Mark Brown: precision=0.50, recall=1.00, FP=1, FN=0

## Overall
- Precision: 0.33
- Recall: 1.00
- False positives on accepted patches: 2
- False negatives on rejected patches: 0

## Confidence Assessment
- Scores are bounded by profile confidence level and validation sample size.
- LOW_CONFIDENCE and INSUFFICIENT_DATA profiles should remain advisory.

## Recommended Tuning Actions
1. Increase reviewer thread coverage where confidence is below HIGH.
2. Improve objection-pattern normalization to reduce false positives.
3. Add subsystem-specific lexical parsers for dt-bindings and SoundWire.
