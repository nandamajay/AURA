# Runtime Command Dispatcher

This document describes the dispatcher behavior. The implementation lives in:
- `AURA/workspace/aura-sdk/src/aura_sdk/transport/runtime_command_dispatcher.py`

## Behavior
- Routes commands to a registered transport adapter by name.
- Logs every response in JSONL when a log path is configured.
- Returns `unknown` when transport is not registered.
