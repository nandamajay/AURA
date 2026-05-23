# Phase-3 Plugin Migration Notes

## Objective
Move target-specific cognition from generic runtime into explicit target plugins without destabilizing validated runtime evidence/replay/governance flows.

## What Changed
- Added explicit target plugin contract with required providers.
- Added registry-driven plugin loader and deterministic negotiation.
- Added first formal plugin (`RB3Gen2`).
- Added portable runtime orchestration layer that stays target-agnostic.

## What Did Not Change
- Existing RB3 runtime execution paths remain available.
- Existing governance enforcement logic remains unchanged.
- Existing event lineage, persistence, and replay artifacts remain unchanged.

## Migration Guidance
1. Keep existing RB3 scripts operational while incrementally adopting plugin workflow entrypoints.
2. Register each new target plugin only through registry metadata and contract validation.
3. Enforce fail-closed negotiation for low-confidence target selection.
4. Validate deterministic replay compatibility before execution authorization.
