# AURA Runtime Trust Model

Date: 2026-05-18
Model type: bounded trust with deterministic enforcement

## Trust Zones
1. Trusted deterministic kernel:
- Orchestration engine
- Replay finalization and integrity checks
- Governance transition enforcement
- Audit persistence

2. Bounded extension zone:
- Plugin runtime and domain workflows operating through contracts

3. Untrusted/variable edge:
- External integrations (LLM providers, future external systems)
- Live transport channels (WS/SSE)

## Trust Assumptions
- Single-node transactional semantics are available.
- Governance gates remain active and non-bypassable through official APIs.
- Replay finalization remains immutable and hash-verifiable.
- Event delivery can be bounded-loss under pressure and is treated as such.

## Failure Containment Rules
- Plugin load/runtime failures are containable at bounded levels but not hard-sandbox isolated.
- External integration failures must not mutate governance/replay state silently.
- Retry logic must preserve ownership lineage and not bleed across scopes.
- WAL contention failures must fail visibly with explicit error surface.

## Deterministic Safety Envelope
Inside envelope (stronger confidence):
- Finalized replay integrity
- Governance transition determinism
- Audit chronology append-only integrity

Bounded envelope:
- Queue fairness under sustained mixed pressure
- WS/SSE completeness under reconnect storms
- Replay completeness while system is actively mutating under pressure

Outside envelope:
- Hard plugin sandbox isolation
- Distributed durability and consensus behavior
- Multi-node replay/governance guarantees

## Evidence Anchors
- `evidence/endurance/2026-05-18-endurance-soak-validation-report.md`
- `evidence/runtime-isolation/2026-05-18-runtime-isolation-confidence-summary.json`
