# Malformed Protocol Test Report

## Test mode
- static test execution only
- no live runtime commands

## Cases covered
- malformed request envelope rejection (`missing_fields`, invalid integrity)
- oversized command batch rejection (`max_command_count_exceeded`)
- response integrity mismatch detection (`response_integrity_mismatch`)
- replay-protection hook presence checks (duplicate/out-of-order/replayed request IDs)

## Evidence
- test file: `AURA/workspace/aura-sdk/tests/test_distributed_runtime_transport_static.py`
- execution: `python3 -m pytest tests/test_distributed_runtime_transport_static.py -q`
- result: `4 passed`

## Classification
- static protocol validation: PASSED
- runtime observability: UNKNOWN (not executed)
- posture: ADVISORY_ONLY
