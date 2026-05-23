# Collector Execution Examples

```python
from aura_sdk.transport import RuntimeCommandDispatcher
from aura_sdk.transport.adapters.remote_serial_transport_adapter import (
    RemoteSerialTransportAdapter,
)
from aura_sdk.transport.runtime_transport_api import CommandClassification

runtime = RuntimeCommandDispatcher(log_path="runtime_exec.jsonl")
runtime.register("remote_serial", RemoteSerialTransportAdapter(host="10.0.0.20", port=54888))

resp = runtime.execute(
    "remote_serial",
    "cat /proc/version",
    classification=CommandClassification.SAFE_READ,
    operator_approved=False,
    timeout_ms=5000,
)
print(resp.runtime_state, resp.confidence)
```

## Notes
- Collector logic remains transport-agnostic.
- SAFE_READ commands execute through registered adapter only.
- Missing endpoint connectivity must remain explicit UNKNOWN/disconnected evidence.
