# Deterministic Architecture Charter

Date: 2026-05-18

## Determinism Scope
Determinism is enforced for control-plane transitions, not for lossless transport under all pressure.

## Deterministic Guarantees (Current)
- Governance approval conflict policy is deterministic (`409` on terminal race conflict).
- Retry attempt sequence is monotonic within scoped lineage in validated campaigns.
- Replay of finalized task logs is deterministic by snapshot hash verification.
- Circuit breaker state transitions follow explicit 3-state FSM.

## Determinism Mechanisms
- Transactional serialization: `BEGIN IMMEDIATE` for approval writes.
- Explicit queue lineage metadata: dispatch sequence + fairness metadata.
- Retry lineage persistence with scope ownership.
- Event ordering metadata at WS ingest (`ingest_sequence`, duplicate markers).
- Replay hash verification on finalized snapshots.

## Bounded Determinism Areas
- Event stream completeness under reconnect storms is bounded-loss.
- Replay completeness under active churn can degrade temporarily.
- Shared queue under mixed pressure can exhibit bounded fairness lag.

## Non-Goals
- Zero-loss deterministic delivery.
- Deterministic ordering across external network failures.
- Cross-node deterministic consensus.
