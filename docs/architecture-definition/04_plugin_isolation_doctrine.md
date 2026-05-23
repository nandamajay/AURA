# AURA Plugin Runtime-Cell Isolation Doctrine

Date: 2026-05-18
Status: bounded logical isolation, not hard sandbox isolation

## Isolation Rules

### 1) Governance scope
- Each plugin/domain workflow action must map to explicit governance scope metadata.
- Plugin code cannot mutate governance transition rules.
- Cross-domain governance effects must occur only through explicit approval actions.

### 2) Replay namespace boundaries
- Replay lineage is task-scoped with domain/runtime-cell metadata.
- Finalized replay cannot be rewritten by plugin logic.
- Namespace mismatch must remain observable and classified.

### 3) Audit boundaries
- Audit ledger remains globally append-only.
- Plugin/domain tags are required for attribution.
- Plugins cannot bypass or rewrite audit chain entries.

### 4) Retry boundaries
- Retry lineage must be domain/run/op scoped.
- Retry ownership cannot carry across domain boundaries.
- Retry metadata must remain replay-visible.

### 5) Queue ownership
- Global queue policy is owned by orchestrator.
- Plugins can request priority but cannot own queue scheduling policy.
- Fairness overrides remain orchestrator-governed and observable.

### 6) Event ownership
- Event publication ownership stays with core orchestrator/event subsystem.
- Domain channels may be scoped, but transport reliability remains bounded.
- Plugins must not create hidden side channels for control-plane state changes.

### 7) Failure containment
- Plugin failures must be contained to task/plugin scope where possible.
- Load-time failures must not crash control-plane baseline.
- Failure impact must remain auditable and replay-referenced.

### 8) Runtime trust assumptions
- Plugins are cooperative bounded actors, not fully trusted isolated tenants.
- Mixed-trust plugin claims are invalid under current architecture.

## Safe / Bounded / Unsafe Coexistence Conditions
Safe (current evidence):
- Replay namespace bleed detection.
- Governance cross-contamination checks.
- Retry-order interaction contamination checks.

Bounded:
- Queue starvation pressure sensitivity.
- Shared channel interference under load.
- Shared replay-buffer pressure.
- Cross-domain watchdog and drift effects.

Unsafe for claims:
- Hard tenant isolation.
- Plugin trust sandbox guarantees.

Evidence:
- `evidence/runtime-isolation/2026-05-18-bounded-runtime-isolation-stabilization-report.md`
- `evidence/runtime-isolation/2026-05-18-coexistence-delta-report.md`
