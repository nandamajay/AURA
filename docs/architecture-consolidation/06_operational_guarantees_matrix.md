# Operational Guarantees Matrix

Date: 2026-05-18

Classification scale:
1. Guaranteed
2. Strong but bounded
3. Best effort
4. Experimental
5. Out of scope

| Domain | Classification | Current Basis | Notes |
|---|---|---|---|
| Finalized replay integrity | 1 Guaranteed | snapshot/output hash checks | deterministic for finalized task logs |
| Governance transition conflict handling | 1 Guaranteed | serialized approval transitions | terminal overwrite race blocked |
| Audit append-only chronology integrity | 1 Guaranteed | audit mismatch observed 0 in campaigns | chronology is global, not per-domain isolated |
| Retry ordering semantics | 2 Strong but bounded | monotonic `[1,2,3]` in reruns | bounded to scoped keys and tested pressure envelope |
| Queue fairness across domains | 2 Strong but bounded | unsafe->bounded improvement, fairness overrides active | lag can still rise under mixed bursts |
| WebSocket/SSE delivery completeness | 3 Best effort | reconnect/drop metrics non-zero | delivery is observable and bounded-loss |
| Replay completeness under active churn | 2 Strong but bounded | coverage floor observed 0.929 | finalized replay remains strong |
| WAL write success under forced lock pressure | 3 Best effort | contention campaign failures under exclusive locks | deterministic failure behavior; resilience bounded |
| Plugin coexistence fault containment | 2 Strong but bounded | load-time containment proven | no hard trust sandbox |
| Runtime cell hard isolation | 5 Out of scope | only boundary preparation/tagging exists | no process/sandbox isolation by design |
| Multi-node replay/governance | 5 Out of scope | single-node architecture | prohibited in current phase |
| Full multi-tenant safety | 5 Out of scope | bounded coexistence only | not claimed |
