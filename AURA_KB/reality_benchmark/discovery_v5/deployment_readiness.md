# Deployment Readiness

## Operational estimates
- operational discovered-rule precision: 0.00%
- expected real-world FDR: 100.00%
- expected autonomous promotion rate: 3.00%
- discovered-rule FDR 95% CI: [43.85%, 100.00%]

## Safety decision
- Discovery_V4 cannot safely promote knowledge without human review.

## Mandatory human oversight
- Mandatory manual audit packet signoff for each `discovered_rule`.
- Mandatory adjudication queue for every `undecided_discovery`.
- Mandatory dual-review for reviewer-specific and low-transfer claims.
- Mandatory periodic calibration/FDR monitoring and freeze on threshold breach.
