# Reviewer Profile Validation Accuracy Report (R2)

Generated: 2026-06-21T12:41:10Z

Terminology:
- LA = downstream / Linux Android
- LE = upstream / Linux Embedded

## Validation Set
- Accepted cases: 5
- Rejected/changes-requested cases: 5
- Accepted series IDs: 713662, 858471, 651180, 716373, 873172
- Rejected series IDs: 751628, 410777, 757519, 504081, 507031

## Metrics
- Precision: 0.29
- Recall: 0.40
- False positives on accepted: 5
- False negatives on rejected: 3
- Precision target >= 0.60: NO
- Recall target >= 0.70: NO

## Recommended Tuning Actions
1. Expand reviewer coverage where confidence remains below HIGH.
2. Add reviewer-specific phrase normalization for objection detection.
3. Increase explicit false-positive suppression for acceptance/changelog-only threads.
