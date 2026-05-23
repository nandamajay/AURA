# Bounded Execution Policy

- Mode: `READ_FIRST_NON_DESTRUCTIVE`
- Timeout source: request timeout, fallback to agent config timeout.
- Read loop bound: hard timeout + max capture bytes (`128 KiB` default).
- Command classification: `SAFE_READ` or `REQUIRES_OPERATOR_APPROVAL`.
- Approval gate: commands requiring approval are blocked when `operator_approved=false`.
- Retry model: `fail_closed` (no uncontrolled retries).
- Unknown handling: if prompt detection or connectivity is uncertain, classify `UNKNOWN` and stop.
