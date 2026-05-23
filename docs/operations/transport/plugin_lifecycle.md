# Plugin Lifecycle Documentation

## Lifecycle
1. **Register**: Add plugin metadata to registry with detection + governance constraints.
2. **Load**: Runtime loader resolves module entrypoint and validates contract.
3. **Negotiate**: Evidence-based scoring selects plugin with fail-closed thresholds.
4. **Execute Providers**: Topology/mixer/PCM/route/evidence providers run through plugin API.
5. **Validate**: Replay compatibility + governance boundary checks execute deterministically.
6. **Persist**: Negotiation, workflow metadata, and evidence lineage are persisted.
7. **Replay**: Replay compatibility is re-evaluated before deterministic reconstruction.

## Safety Rules
- No target-specific branching in generic runtime layer.
- No autonomous mutation, patching, or topology rewrite.
- Missing/ambiguous evidence lowers confidence deterministically.
- Unsupported/unknown target selection fails closed.
