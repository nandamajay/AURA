# Transport Fail-Closed Policy (Distributed)

- If TCP connectivity fails: return explicit error with `runtime_state=disconnected`.
- If JSON payload is invalid: return explicit `invalid_request` response.
- If operator approval is missing for unsafe command: return `blocked`.
- If serial prompt is not detected in time: return `timeout` + `unknown` confidence.
- If serial connection unavailable: return `disconnected` + `unknown` confidence.
- Retries are not implicit; caller must perform controlled retry with preserved evidence.
