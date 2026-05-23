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
- Autonomous semantic patch authoring.
- Autonomous DTS rewrite proposals.
- Autonomous driver mutation proposals.
- Fabricated evidence.
- Fabricated causality.
- Runtime mutation from correlation inference.

## Cross-Target Safety
- Target intelligence must remain in plugin layer.
- Core orchestration may load/unload/validate plugins but not infer target rules.
- Any cross-target uncertainty lowers confidence deterministically.
- Incompatibility yields fail-closed classification.

## Recovery Constraints
- Recovery requires explicit quarantine clear + reload.
- Recovery does not bypass replay compatibility validation.
- Governance decisions remain preserved across replay reconstruction.

## Semantic Governance Boundaries
- Allowed semantic actions: analyze, classify, correlate, fingerprint, replay, recommend.
- Forbidden semantic actions: generate final patches, rewrite DTS, mutate drivers, fabricate compatibility.
- Semantic cognition must remain evidence-backed and lineage-linked.

## Correlation Governance Boundaries
- Allowed correlation actions: correlate, classify, infer, recommend, replay, quarantine.
- Forbidden correlation actions: fabricate evidence, fabricate causality, auto patch, auto modify runtime, override governance.
- Correlation anomaly handling must preserve fail-closed posture and plugin isolation.
