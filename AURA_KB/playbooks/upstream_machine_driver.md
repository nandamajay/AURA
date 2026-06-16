# Playbook: Upstream Machine Driver (Promoted, Limited Evidence)

## Preparation
- Extract board-specific routing, clock, and channel-map policy from codec code.

## Implementation strategy
- Keep codec generic; represent board policy in machine + DT.

## Patch series structure
1. Machine-driver routing changes
2. DT wiring changes
3. Minimal codec hooks only if strictly required

## Review expectations
- Avoid embedding board policy into codec core.
- Keep series narrow and testable.

## Validation checklist
- [ ] FE/BE links validated
- [ ] DAPM machine routes validated
- [ ] codec generic behavior preserved

## Submission checklist
- [ ] no board constants leaked into codec core
- Confidence: MEDIUM_CONFIDENCE (direct machine-review corpus incomplete)
