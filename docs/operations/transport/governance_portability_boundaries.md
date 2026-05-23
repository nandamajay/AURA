# Governance Portability Boundaries

## Runtime Boundaries
- Core runtime executes in fail-closed posture by default.
- Plugin negotiation is evidence-backed and threshold-gated.
- Invalid or unsupported plugins are quarantined without core runtime mutation.
- Quarantine handling must not corrupt cognition registry state.

## Prohibited Behavior
- Autonomous patching.
- Autonomous topology rewriting.
- Autonomous mixer mutation.
- Autonomous upstream generation.

## Cross-Target Safety
- Target intelligence must remain in plugin layer.
- Core orchestration may load/unload/validate plugins but not infer target rules.
- Any cross-target uncertainty lowers confidence deterministically.
- Incompatibility yields fail-closed classification.

## Recovery Constraints
- Recovery requires explicit quarantine clear + reload.
- Recovery does not bypass replay compatibility validation.
- Governance decisions remain preserved across replay reconstruction.
