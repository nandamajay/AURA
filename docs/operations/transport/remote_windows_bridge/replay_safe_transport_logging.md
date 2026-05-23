# Replay-Safe Transport Logging

- Agent writes append-only JSONL evidence.
- Dispatcher may write append-only JSONL execution traces.
- Required replay fields:
- `request_id`
- `command`
- `timestamp`
- `duration_ms`
- `runtime_state`
- `confidence`
- `transport`
- `classification`
- `notes.request_order`

## Replay Constraints
- Preserve failed and timeout responses as first-class evidence.
- Never delete prior entries during continuation passes.
- Unknown states remain unknown in replay reconstruction.
