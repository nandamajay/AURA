# Playbook: Upstream Macro Driver (Promoted)

## Preparation
- Confirm macro driver object model in both trees and DT macro binding coverage.

## Implementation strategy
- Reuse platform-macro architecture; avoid introducing new vendor orchestration layers.

## Patch series structure
1. Macro support patch
2. DAPM/routes patch
3. Variant/clock follow-ups

## Review expectations
- ASoC maintainers expect framework-native macro registration and clean DAPM graph.

## Validation checklist
- [ ] probe/remove paths
- [ ] DAI ops + DAPM widgets/routes
- [ ] DT compatible coverage per SoC
- [ ] runtime PM paths

## Submission checklist
- [ ] patch split remains ownership-clean
- [ ] accepted commit mapping captured
- Confidence: HIGH_CONFIDENCE
