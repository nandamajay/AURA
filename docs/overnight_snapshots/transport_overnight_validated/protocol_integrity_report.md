# Protocol Integrity Report

## Scope
- distributed runtime transport integrity checks
- static validation only
- no live device or transport execution

## Implemented controls
- request_id correlation enforcement: ENABLED
- immutable response hash validation: ENABLED
- duplicate response detection: ENABLED (`duplicate_response_detected` -> `BLOCKED`)
- out-of-order response detection: ENABLED (`out_of_order_response_detected` -> `BLOCKED`)
- malformed envelope rejection: ENABLED (`rejected_malformed_request`)
- partial-response classification: ENABLED (`PARTIAL` + `ADVISORY_ONLY`)

## Fail-closed mapping
- hash mismatch -> `INVALID`
- duplicate response -> `BLOCKED`
- replayed request_id -> `REJECTED`
- transport disconnect -> `UNKNOWN`
- oversized output -> `ADVISORY_ONLY`

## Runtime posture
- advisory-only governance preserved
- no runtime parity or merge-readiness claims
