# Distributed Runtime Execution

## AURA-side flow (authoritative)
`runtime.execute(command)` -> `RuntimeCommandDispatcher` -> `RemoteSerialTransportAdapter` -> governance checks (allowlist/forbidden/policy) -> immutable request block -> `RuntimeTransportClient`

## Windows-side flow (untrusted worker)
TCP request block -> `TcpRuntimeBridge` -> request structure/integrity validation -> `RuntimeSerialExecutor` execute-only -> immutable response evidence

## Governance properties
- collectors remain transport-agnostic.
- no direct COM API access from Linux AURA runtime.
- Windows side has no semantic/policy authority.
- Linux side performs response integrity verification and runtime classification.

## Classification mapping
- `timeout` -> `UNKNOWN`
- `partial_response` -> `ADVISORY_ONLY`
- response mismatch -> `INVALID` + escalation

## Truthfulness rule
No runtime parity or merge-readiness claims are permitted from transport execution alone.
