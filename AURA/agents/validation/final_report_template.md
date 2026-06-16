# Final Validation Report Template

## Context
- DUT:
- Kernel baseline commit:
- Kernel candidate commit:
- Date/time:
- Tester:

## Evidence Scope
- Item #1: Power benefit
- Item #2: Runtime PM stability
- Item #3: Functional regression matrix
- Item #4: Clock correctness

## Run Metadata
- Baseline logs directory:
- Candidate logs directory:
- Tracefs/debugfs availability:
- Stress command used:

## Results Summary
Status values:
- PASS
- FAIL
- INVALID_DATA (missing or insufficient evidence; treated as non-pass)

| Item | Status | Key Metric | Threshold | Notes |
|---|---|---|---|---|
| ITEM1_POWER |  |  |  |  |
| ITEM2_RUNTIME_PM |  |  |  |  |
| ITEM3_REGRESSION |  |  |  |  |
| ITEM4_CLOCK |  |  |  |  |

## Evidence Quality Gates
- Runtime PM summary present in both baseline and candidate: YES/NO
- Runtime PM suspend/resume evidence observed (>0 events) in both runs: YES/NO
- Clock trace present in both baseline and candidate: YES/NO
- Clock enable/disable evidence observed (>0 events) in both runs: YES/NO
- Missing evidence encountered: YES/NO (if YES, overall cannot be PASS)

## Detailed Findings

### Item #1 Power
- Sensors evaluated:
- Baseline mean/p95:
- Candidate mean/p95:
- Delta:
- Pass/Fail rationale:

### Item #2 Runtime PM Stability
- WARN/OOPS/BUG/Call Trace counts:
- PM suspend/resume event counts:
- Evidence validity:
- Failure incidents:
- Pass/Fail rationale:

### Item #3 Functional Regression
- Matrix file used:
- Failed rows (if any):
- Pass/Fail rationale:

### Item #4 Clock Correctness
- Clock balance violations:
- Suspect clocks:
- Ordering anomalies observed:
- Evidence validity:
- Pass/Fail rationale:

## Upstream Acceptance Decision Input
- REQUIRED_FOR_UPSTREAM items met: YES/NO
- Remaining blockers:
- Recommendation:
