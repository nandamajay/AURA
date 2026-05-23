# Remote Transport Protocol

## Trust boundary
- Linux AURA is authoritative governance.
- Windows serial agent is untrusted execute-only worker.

## Transport
- medium: TCP
- payload: newline-delimited JSON
- deterministic request/response correlation via `request_id`

## Request block (immutable)
- `request_id`
- `approved_commands`
- `timeout_seconds`
- `transport`
- `execution_mode`
- `request_timestamp`
- `request_integrity_sha256`

## Response block (immutable evidence)
- `request_id`
- `approved_commands`
- `timeout_seconds`
- `transport`
- `execution_mode`
- `timestamps`
- `execution_status`
- `raw_output`
- `stderr`
- `request_integrity_sha256`
- `response_integrity_sha256`

## Fail-closed behavior
- malformed request -> `rejected_malformed_request`
- integrity mismatch -> `invalid`
- timeout -> classified UNKNOWN by Linux governance
- partial response -> classified ADVISORY_ONLY by Linux governance

## Contract rule
Windows worker must execute commands exactly as received and must not perform policy decisions.
