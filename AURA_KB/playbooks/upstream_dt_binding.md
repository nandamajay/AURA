# Playbook: Upstream DT Binding (Promoted)

## Preparation
- Map every driver-visible DT property to schema and code consumption points.

## Implementation strategy
- Submit strict YAML constraints with examples that match real driver behavior.

## Patch series structure
1. Binding schema patch
2. Driver consumption patch
3. Variant extension follow-ups

## Review expectations
- Binding clarity, consistency, and accurate compatible/property modeling.

## Validation checklist
- [ ] `dtbs_check` clean
- [ ] required/optional split justified
- [ ] examples compile and match code

## Submission checklist
- [ ] lore links and accepted commits tracked
- Confidence: HIGH_CONFIDENCE
