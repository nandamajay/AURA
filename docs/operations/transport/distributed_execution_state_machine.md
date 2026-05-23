# Distributed Execution State Machine

## States
- `APPROVED`
- `EXECUTING`
- `COMPLETED`
- `PARTIAL`
- `TIMEOUT`
- `INVALID`
- `REJECTED`
- `UNKNOWN`

## Transitions
- `APPROVED -> EXECUTING`
- `EXECUTING -> COMPLETED` on valid full response
- `EXECUTING -> PARTIAL` on partial response or oversized output
- `EXECUTING -> TIMEOUT` on timeout status
- `EXECUTING -> UNKNOWN` on transport disconnect
- `EXECUTING -> INVALID` on hash mismatch / malformed envelope / sequence mismatch
- `APPROVED -> REJECTED` on replayed request_id or request rejection before execution

## Governance notes
- `BLOCKED` is a fail-closed transport runtime state for duplicate or out-of-order responses.
- semantic/behavioral claims are prohibited at this layer.
