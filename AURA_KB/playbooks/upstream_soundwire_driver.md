# Playbook: Upstream SoundWire Driver (Promoted)

## Preparation
- Verify SDW driver ownership, stream lifecycle, and transport split.

## Implementation strategy
- Use `sdw_driver`, `sdw_slave_ops`, and SDW stream add/remove APIs.

## Patch series structure
1. SDW transport/core ownership patch
2. Stream lifecycle and callback fixes
3. Runtime PM robustness patches

## Review expectations
- SDW lifecycle must be race-safe and explicit.
- PM resume paths must guard timeout/attachment transitions.

## Validation checklist
- [ ] hw_params/hw_free stream lifecycle
- [ ] status/update callbacks
- [ ] suspend/resume timeout handling

## Submission checklist
- [ ] soundwire and PM paths tested together
- Confidence: HIGH_CONFIDENCE
