# Transport Execution Contract

## Purpose
Provide a transport-agnostic, fail-closed execution contract for runtime collectors.

## Core Rules
- Collectors must call `runtime.execute(command)` only.
- Transport adapters decide how commands run (adb/serial/ssh/local).
- Commands are classified before execution.
- `REQUIRES_OPERATOR_APPROVAL` commands MUST NOT execute without explicit approval.
- Fail closed when behavior is uncertain.

## Required Request Fields
- `command`
- `timeout_ms`
- `classification` (`safe_read` or `requires_operator_approval`)
- `operator_approved` (boolean)

## Required Response Fields
- `transport`
- `command`
- `exit_code`
- `stdout`
- `stderr`
- `timestamp`
- `duration_ms`
- `runtime_state`
- `confidence`

## Runtime State Semantics
- `unknown`: execution not possible or ambiguous
- `blocked`: command refused due to governance
- `executed`: command completed
- `failed`: command executed but returned non-zero
- `timeout`: execution exceeded timeout
- `disconnected`: transport not connected

## Confidence Semantics
- `unknown`: no verified runtime visibility
- `connected`: transport reachable
- `partial_connectivity`: transport reachable with limitations
- `transport_ready`: transport responding to commands
- `capture_ready`: command executed with output
- `advisory_only`: output captured but not certified
- `escalation_required`: operator review required

## Governance Guard
No merge readiness or runtime parity claim can be derived from transport output alone.
