# AURA Architecture Canon

Date: 2026-05-18
Status: canonical definition for core separation
Scope: single-node bounded-runtime AURA

## 1) What AURA Fundamentally Is
AURA is a deterministic, governance-first, replay-auditable runtime control plane for autonomous engineering workflows under bounded operational guarantees.

In current validated form, AURA is:
- A single-node modular monolith.
- SQLite WAL based.
- Docker Compose operated.
- CLI-agent subprocess based.
- Replay-first for finalized traces.
- Governance-enforced for high-risk actions.

## 2) What AURA Fundamentally Is Not
AURA is not:
- A distributed orchestration platform.
- A multi-tenant trust-isolated plugin cloud.
- A zero-loss real-time streaming system.
- A general business workflow engine.
- A hidden-autonomy agent that can bypass governance.

## 3) Stable Architectural Layers
AURA layer stack (top to bottom):
1. Operator layer
2. Application layer
3. Domain workflow layer
4. Plugin runtime layer
5. Replay/governance layer
6. Orchestration layer
7. Core runtime layer
8. External integration edge (strictly controlled boundary)

## 4) Deterministic Invariants (Non-Negotiable)
Future plugins/workflows cannot violate:
1. Events that matter to control decisions must be persisted before external broadcast.
2. Governance transitions must remain deterministic, auditable, and conflict-resolving (no silent overwrite).
3. Finalized replay artifacts are immutable and hash-verifiable.
4. Retry lineage remains scoped and monotonic within ownership boundaries.
5. High-risk actions require explicit approval pathways.
6. Failure paths must be visible (no silent fallback success).
7. CI must hard-fail on architecture/governance/replay violations.
8. Runtime behavior classification must stay explicit: guaranteed, bounded, best-effort, out-of-scope.

## 5) Evidence-Bounded Guarantees (Current)
From current evidence:
- Governance transition conflict handling: strong in single-node transactional model.
- Finalized replay integrity: strong.
- Queue fairness, websocket delivery, replay completeness under churn: bounded.
- Plugin coexistence: bounded-safe for controlled workloads, not hard isolation.

Reference:
- `evidence/runtime-isolation/2026-05-18-bounded-runtime-isolation-stabilization-report.md`
- `evidence/endurance/2026-05-18-endurance-soak-validation-report.md`
- `docs/architecture-consolidation/06_operational_guarantees_matrix.md`
