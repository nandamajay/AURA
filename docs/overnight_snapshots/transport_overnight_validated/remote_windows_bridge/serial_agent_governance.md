# Serial Agent Governance

## Invariants
- COM access is owned only by `windows_serial_agent.py`.
- Collectors never access COM ports directly.
- Runtime evidence is persisted as immutable JSONL entries.
- Transport failures are explicit and never suppressed.
- Prompt uncertainty forces fail-closed behavior.

## Safety gates
- Unsafe commands require explicit operator approval.
- Runtime mutations are outside default allowed scope.
- Disconnect and timeout states are preserved as evidence.

## Trust model
- Output trust level depends on observed runtime response only.
- Missing runtime observability is classified `UNKNOWN`.
