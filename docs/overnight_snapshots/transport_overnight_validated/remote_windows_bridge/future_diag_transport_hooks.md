# Future Diag Transport Hooks

- Keep collector entrypoint at `runtime.execute(command)`.
- Add `DiagTransportAdapter` implementing `RuntimeTransportAPI`.
- Reuse TCP JSON schema fields for request correlation and evidence lineage.
- Preserve fail-closed behavior and explicit `UNKNOWN` on diag uncertainty.
- Do not infer runtime behavior from transport-level success.
