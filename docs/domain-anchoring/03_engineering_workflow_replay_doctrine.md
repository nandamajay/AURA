# Engineering Workflow Replay Doctrine

Date: 2026-05-18
Goal: replay integrity for engineering-runtime execution

## 1) Patch Lineage Replay
Required semantics:
- Every engineering task that mutates patch-related state must carry task/domain lineage metadata.
- Finalized replay artifacts are canonical replay evidence.

Current truth:
- replay state machine is task-centric and strong for finalized task logs
- explicit patch-to-task lineage normalization is still partial in current API layer

## 2) Validation Rerun Replay
Required semantics:
- validation reruns must be distinguishable by retry/run lineage
- rerun outputs must not overwrite prior replay evidence silently

Current truth:
- retry lineage and replay logs exist; domain-specific validation rerun correlation is bounded by current task-centric model.

## 3) Approval Ordering Replay
Required semantics:
- approval actions must replay in deterministic order and preserve conflict outcomes

Current truth:
- serialized governance transitions and audit entries provide deterministic ordering for approval decisions in single-node scope.

## 4) CI Replay Semantics
Required semantics:
- CI/review outcomes should be represented as explicit events/artifacts linked to task lineage

Current truth:
- CI parity and enforcement scripts exist; CI event materialization as first-class patch/approval-linked replay records is partial.

## 5) Audit Continuity
Required semantics:
- replay timeline and audit timeline must remain cross-referenceable
- no hidden mutation path can bypass audit continuity

Current truth:
- event persistence-before-broadcast and append-only audit chain provide continuity inside current core paths.

## 6) Retry Determinism
Required semantics:
- retries must remain monotonic and scope-owned (task/domain/op)

Current truth:
- evidence shows retry monotonicity in validated envelopes; still bounded under prolonged pressure conditions.

## 7) Replay Doctrine Rules for Engineering Domain
1. finalized replay is the only deterministic replay source for assertions.
2. mutable replay is operational telemetry, not deterministic proof.
3. patch/validation/approval decisions must be linked through task/replay/audit lineage before being treated as canonical evidence.
4. replay gaps during pressure are classified as bounded behavior, never hidden.
