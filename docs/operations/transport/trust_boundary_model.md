# Trust Boundary Model

## Boundary definition
- Trusted zone: Linux AURA governance layer.
- Untrusted zone: Windows serial execution worker and remote transport path.

## Trusted zone responsibilities
- validate requested command against allowlist
- detect forbidden patterns
- enforce execution mode policy
- emit approved request block
- verify response integrity and request correlation
- classify runtime status (UNKNOWN/ADVISORY/ESCALATION)

## Untrusted zone responsibilities
- parse immutable request
- reject malformed request
- execute approved command list exactly
- return raw evidence only

## Explicit non-responsibilities (untrusted zone)
- no command approval
- no policy override
- no semantic interpretation
- no merge-readiness output

## Fail-closed rules
- malformed request -> reject
- response integrity mismatch -> INVALID
- timeout -> UNKNOWN
- partial response -> ADVISORY_ONLY

## Evidence model
- append-only worker evidence log
- request_id correlation
- request integrity hash + response integrity hash
- deterministic timestamps preserved end-to-end
