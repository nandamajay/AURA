# AURA Future-Safe Evolution Rules

Date: 2026-05-18
Intent: controlled evolution without deterministic regression

## Scaling Trigger Policy (Definition Only)
Infrastructure escalation is justified only when all conditions hold:
1. Repeated high-severity evidence across at least 3 independent campaigns.
2. Failures exceed declared controlled-workload bounds after local mitigations.
3. Replay semantics can be preserved or strengthened.
4. Governance semantics remain deterministic and auditable.
5. Complexity increase is justified by measurable correctness gains.

## Trigger Candidates (Not Implemented)
- Persistent queue loss beyond bounded policy controls.
- Replay finalization integrity limits from single-node durability constraints.
- Governance latency/throughput collapse under sustained validated load.
- Mandatory mixed-trust plugin requirements that exceed current bounded model.

## Mandatory Pre-Escalation Checklist
1. Baseline evidence artifact set captured.
2. Mitigation attempts in current architecture documented and exhausted.
3. Determinism regression tests prepared.
4. Governance and replay delta impact analysis prepared.
5. Rollback strategy documented.

## Evolution Guardrails
- Preserve single-node deterministic simplicity unless thresholds are exceeded.
- Preserve replay lineage as first-class invariant.
- Preserve governance chronology visibility.
- Preserve bounded guarantee classification discipline.

## Explicitly Deferred Domains
- Multi-node replay and governance.
- Distributed message buses.
- Runtime sandbox container-per-plugin models.

These remain deferred until trigger policy is satisfied.
