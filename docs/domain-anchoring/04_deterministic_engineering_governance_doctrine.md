# Deterministic Engineering Governance Doctrine

Date: 2026-05-18
Domain: downstream-to-upstream engineering workflow

## 1) Review Authority Model
- `viewer`: observation only
- `reviewer`: review/comment level actions
- `approver`: approval/rejection authority
- `architect`: architecture/governance-level mutation authority
- `admin`: ultimate authority and emergency controls

Reference:
- `AURA/workspace/aura-sdk/src/aura_sdk/models/governance.py`

## 2) Approval Gates
Engineering workflow approvals must gate:
1. patch stage progression with risk impact
2. high-risk governance class actions
3. override operations requiring explicit justification

## 3) Escalation Paths
- escalation is explicit action (`escalate`) in approval lifecycle
- high-risk actions route through human approval gate semantics
- no silent automatic escalation

## 4) Override Permissions
- override is explicit, justification-required, and audit-visible
- override is authority action, not autonomous system behavior

## 5) Replay Integrity Protection by Governance
Governance must protect replay by blocking:
- silent replay semantic rewrites
- non-audited replay mutations
- approval shortcuts that bypass deterministic ordering

## 6) Deterministic Governance Rules for Engineering Runtime
1. transition conflicts must fail explicitly (`409`-style conflict), not merge nondeterministically.
2. terminal approval state overwrite by conflicting action is forbidden.
3. comments may append context but cannot silently alter terminal decision semantics.
4. governance events must remain replay/audit visible for engineering sign-off traceability.

## 7) Current Boundaries
Strong:
- deterministic transition serialization
- explicit role-based controls and charter endpoints

Bounded:
- per-domain governance partitioning is policy-scoped, not independently sharded.
