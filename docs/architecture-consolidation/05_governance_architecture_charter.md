# Governance Architecture Charter

Date: 2026-05-18

## Governance Model
Governance combines:
- RBAC role/permission checks
- High-risk action approval gating
- Self-modification prohibition checks
- Append-only audit ledger

## Approval Lifecycle
1. Request exists in `pending`.
2. Action attempts use serialized transition (`BEGIN IMMEDIATE`).
3. Terminal status transitions are single-writer deterministic.
4. Conflicting terminal overwrite attempts return conflict (`409`).
5. Audit row is written in same transaction path.

## Deterministic Transition Rules
- No terminal overwrite to a new terminal state.
- Idempotent repeat of same status is allowed.
- Comment actions merge without changing status.

## Governance Replay Visibility
- Approval changes write before/after state to audit.
- Event/audit chronology is preserved with chain-hash ledger.
- Governance enforcement outcomes are CI-validated.

## Durability Limits
- Governance semantics are strong for single-node transactional execution.
- Global audit stream is intentionally mixed chronologically across domains.
- Per-domain governance isolation is policy-scoped, not schema-hard partitioned.

## CI Governance Enforcement
Hard-fail suite includes governance stabilization tests and architecture/replay checks via:
- `.github/workflows/architecture-compliance.yml`
