# Executor Contract

## Contract purpose
Define strict behavior of untrusted Windows execution worker.

## Required input
- `request_id`
- `approved_commands` (list)
- `timeout_seconds`
- `transport`
- `execution_mode`
- `request_timestamp`
- `request_integrity_sha256`

## Required worker behavior
- validate protocol structure only
- reject malformed request
- execute each approved command exactly as provided
- capture raw output and stderr
- return deterministic timestamps
- produce execution status per request block

## Prohibited worker behavior
- policy decisions
- command rewriting decisions
- command approval logic
- semantic/runtime interpretation
- merge-readiness statements

## Required output fields
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

## Failure handling
- malformed request -> `rejected_malformed_request`
- command timeout -> `timeout`
- incomplete evidence -> `partial_response`
- disconnected transport -> `transport_disconnected`
