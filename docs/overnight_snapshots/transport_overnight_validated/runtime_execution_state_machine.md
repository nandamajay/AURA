# Runtime Execution State Machine

```
INIT
  -> CHECK_CONNECTIVITY
  -> READY
  -> CLASSIFY_COMMAND
  -> (BLOCKED | EXECUTING)
EXECUTING
  -> COMPLETED
  -> FAILED
  -> TIMEOUT
BLOCKED
  -> END
COMPLETED/FAILED/TIMEOUT
  -> END
```

## State Rules
- `BLOCKED` is terminal unless a new operator-approved request is issued.
- `FAILED` and `TIMEOUT` are terminal for the specific execution.
- `UNKNOWN` is preferred over speculative transitions.
