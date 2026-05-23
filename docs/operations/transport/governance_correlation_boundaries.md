# Governance Correlation Boundaries

## Allowed Actions
- correlate
- classify
- infer
- recommend
- replay
- quarantine

## Forbidden Actions
- fabricate evidence
- fabricate causality
- auto patch
- auto modify runtime
- override governance

## Fail-Closed Requirements
- governance violations are classified as `FAIL_CLOSED`
- anomaly correlation must preserve governance lineage
- plugin capability inconsistencies must not bypass governance restrictions
