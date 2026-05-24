# ARCHITECTURE_DECISION_LOG

## ADR-P1-001 Runtime Truth Precedence
- Decision: Runtime evidence artifacts override static assumptions in governance decisions.
- Status: Accepted

## ADR-P1-002 Fail-Closed Governance
- Decision: Promotion is blocked when confidence, lineage, or integrity is uncertain.
- Status: Accepted

## ADR-P1-003 Deterministic Replay Persistence
- Decision: Runtime and governance reasoning persist deterministic fingerprints and lineage references.
- Status: Accepted

## ADR-P1-004 Contract-First Runtime API
- Decision: Dashboard/runtime APIs consume typed contracts instead of raw filesystem JSON assumptions.
- Status: Accepted

## ADR-P1-005 Environment Gating
- Decision: Python >=3.12 is mandatory for production backend runtime parity.
- Status: Accepted (current host blocker remains)

## ADR-P1-006 No Synthetic Runtime Payloads for Onboarding
- Decision: Hardware onboarding prep is schema/boundary only; no mock runtime payload commits.
- Status: Accepted
