# AURA Governance Domain Model

Date: 2026-05-18
Model: deterministic, serialized, auditable transition system

## Governance Entities
- Actor (role-bound identity)
- Action request (typed operation + risk class)
- Approval state (`pending`, `in_progress`, `passed`, `failed`)
- Policy check result
- Audit event (append-only chain-linked record)

## Governance Lifecycle
1. Request created with risk/action metadata.
2. Policy gate evaluates role/permission/charter constraints.
3. Approval transitions occur in serialized transaction path.
4. Terminal overwrite conflicts are rejected.
5. Audit event persists before completion response.

## Governance Scope Domains
- Global scope: core governance rules and charter.
- Runtime scope: task/agent/replay-related governance actions.
- Plugin/domain scope: domain-specific actions mapped into global governance model.

## Governance Guarantees (Current)
Strong:
- Deterministic conflict handling for approval transitions in single-node transactional model.
- Audit chronology integrity for append-only ledger path.

Bounded:
- Per-domain governance isolation (policy-scoped, not hard-partitioned storage model).
- Throughput under prolonged mixed contention.

## Governance Non-Goals
- Distributed consensus governance.
- Independent per-plugin governance databases.
- Hidden autonomous policy rewrite.

## Governance Discipline Requirements
- No silent policy mutation.
- No hidden fallback approvals.
- No governance bypass through direct internal calls.
- CI hard-fail checks remain mandatory for governance semantics.
