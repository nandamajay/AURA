# Future Diag Transport Hooks

- Keep collector contracts fixed at `runtime.execute(command)`.
- Implement diag adapter as `RuntimeTransportAPI` peer.
- Reuse deterministic request IDs and JSONL evidence logging.
- Preserve fail-closed and UNKNOWN classification policy.
- Do not infer runtime behavior from protocol-level success.
