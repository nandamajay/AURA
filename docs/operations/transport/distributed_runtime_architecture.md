# Distributed Runtime Architecture

## Objective
Refactor distributed runtime into a strict trust-boundary model where Linux AURA is authoritative and Windows acts as an untrusted execution worker.

## Architecture
AURA Runtime (Linux, authoritative)
-> RuntimeCommandDispatcher
-> RemoteSerialTransportAdapter (governance authority)
-> RuntimeTransportClient (TCP JSON)
-> WindowsSerialAgent (untrusted worker)
-> RuntimeSerialExecutor (execute-only)
-> COM Port
-> RB3/Kodiak Target

## Linux-side authority
- command approval
- allowlist enforcement
- forbidden pattern detection
- runtime policy enforcement
- semantic/runtime classification
- evidence interpretation
- merge-readiness governance decisions

## Windows-side untrusted worker role
- receive immutable approved request block
- execute commands exactly as received
- capture raw output and stderr
- return immutable raw evidence payload
- no policy interpretation
- no semantic classification
- no command mutation decisions

## Safety posture
- default mode: governed read-only execution
- fail-closed on malformed protocol, integrity mismatch, timeout ambiguity
- preserve UNKNOWN and advisory outcomes when evidence is incomplete

## Truthfulness boundary
Compile success or transport connectivity does not imply runtime parity, behavioral equivalence, or merge readiness.
