# Collector Execution Examples

```python
from aura_sdk.transport import RuntimeCommandDispatcher
from aura_sdk.transport.adapters.remote_serial_transport_adapter import (
    RemoteSerialTransportAdapter,
)
from aura_sdk.transport.runtime_transport_api import CommandClassification

runtime = RuntimeCommandDispatcher(log_path="remote_runtime_exec.jsonl")
runtime.register("remote_serial", RemoteSerialTransportAdapter(host="10.0.0.20", port=54888))

response = runtime.execute(
    "remote_serial",
    "uname -a",
    classification=CommandClassification.SAFE_READ,
    operator_approved=False,
    timeout_ms=10000,
)
print(response.runtime_state, response.confidence)
```

- Collectors interact only with dispatcher `execute`.
- No direct COM port access from collector logic.
