# Transport Timeout Policy

## Default Timeouts (ms)
- `execute`: 10,000
- `check_connectivity`: 5,000
- `collect_environment_metadata`: 5,000
- `push_file` / `pull_file`: 10,000
- `capture_stream`: 10,000 (must be explicitly authorized)

## Rules
- Timeouts are mandatory for every execution.
- Timeout events produce `runtime_state=timeout` and `confidence=unknown`.
- No silent retries are permitted.
- Transport adapters may tighten timeouts for safety.
