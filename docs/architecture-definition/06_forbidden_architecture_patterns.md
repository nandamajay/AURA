# AURA Forbidden Architecture Patterns

Date: 2026-05-18
Purpose: prevent architecture drift and complexity inflation

## Hard-Forbidden Patterns
1. Distributed escalation without evidence thresholds (Kafka/Redis streams/Kubernetes/multi-node coordination).
2. Plugin logic writing directly to governance/audit/replay persistence.
3. Hidden retries/fallbacks that are not audit-visible and replay-visible.
4. UI-triggered state mutation bypassing governance and API validation.
5. Domain/business workflow logic embedded into `aura-core`.
6. Replay finalization mutation from plugin or application layers.
7. Non-deterministic queue/retry behavior introduced without explicit bounded classification.
8. Circular cross-layer dependencies.
9. Runtime trust claims that exceed evidence (for example, "tenant isolation" without sandboxing).

## Good vs Bad Expansion Examples

### Example A: New domain plugin
Good:
- Add plugin through registry contract.
- Use `plugin_domain` and runtime-cell tagging.
- Route through existing orchestration/governance/replay APIs.

Bad:
- Plugin opens direct DB connection and writes audit/replay rows.
- Plugin implements custom queue and retry scheduler.

### Example B: New operator control surface
Good:
- Add UI endpoint through existing authenticated API and governance checks.
- Surface bounded metrics with explicit classifications.

Bad:
- Add admin-only hidden endpoint that mutates governance state without audit entry.
- Show synthetic "healthy" status while dropping bounded-loss metrics.

### Example C: External integration extension
Good:
- Add adapter at external integration edge with explicit risk typing and audit logging.
- Keep provider failures visible and bounded.

Bad:
- Add direct provider calls deep in orchestration core with silent retries and no lineage.

### Example D: Performance improvement
Good:
- Tune local queue fairness and retry scope with evidence-backed tests.

Bad:
- Introduce distributed queue infrastructure before exhausting current bounded mitigations.
