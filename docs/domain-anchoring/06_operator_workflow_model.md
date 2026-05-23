# Operator Workflow Model (Engineering Runtime)

Date: 2026-05-18

## 1) Operator Role in Engineering Runtime
Operator is the accountable control authority, not a passive observer.

## 2) Domain-Aligned Operator Workflow
1. Intake oversight
- inspect incoming downstream intake tasks and domain tags

2. Transformation oversight
- monitor transformation task progression and failure surfaces

3. Validation oversight
- inspect validation/simulation outcomes and bounded-risk conditions

4. Governance oversight
- inspect approval state transitions and conflict outcomes

5. Replay inspection
- verify finalized replay hashes for decision-critical tasks

6. Intervention and recovery
- cancel/intervene/override/rollback when required

7. Evidence closure
- confirm audit continuity and evidence completeness before approvals

## 3) Operator Control Surfaces (Current)
- runtime overview and domain pressure
- replay inspector (`/tasks/{task_id}/replay`, `/replay/state`)
- governance timeline and audit views
- charter intervention endpoints

## 4) Operator Non-Delegable Actions
- final release/approval of high-risk transitions
- acceptance of bounded behavior risk
- override with responsibility statement

## 5) Operator Failure Doctrine
If evidence is incomplete/inconsistent:
- do not claim success
- keep status bounded/blocked
- request rerun or intervention
- preserve lineage for post-incident replay
