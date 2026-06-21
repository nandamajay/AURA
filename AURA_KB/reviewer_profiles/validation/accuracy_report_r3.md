# Reviewer Profile Validation Accuracy Report (R3)

Generated: 2026-06-21T14:18:19Z

Terminology:
- LA = downstream / Linux Android
- LE = upstream / Linux Embedded

## Validation Set (Fixed from R2)
- Accepted cases: 5
- Rejected/changes-requested cases: 5
- Accepted series IDs: 713662, 858471, 651180, 716373, 873172
- Rejected series IDs: 751628, 410777, 757519, 504081, 507031

## Weighted Scoring Results
- Blocking threshold used: 2.0
- Precision: 0.62
- Recall: 1.00
- False positives on accepted: 3
- False negatives on rejected: 0
- Precision target >= 0.60: YES
- Recall target >= 0.60: YES

## R3 Model Notes
- Subsystem/vendor tokens are moved to subsystem_context and contribute zero score.
- Case scoring uses weighted threshold on objection-classified comments only.
- Vinod Koul question-as-objection rules are enabled for rejected/changes-requested series.

