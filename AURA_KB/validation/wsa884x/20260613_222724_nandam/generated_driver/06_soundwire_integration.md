# SoundWire Integration (Blind v1)

## SDW ownership
- Register as `sdw_driver`.
- Use `sdw_slave_ops` for status and port prep callbacks.

## Stream lifecycle
- DAI `hw_params`: build active port config and call stream add.
- DAI `hw_free`: remove stream mapping.
- DAI `set_stream`: store runtime stream handle.

## State controls
- Track per-port enabled + prepared state.
- Validate stream state transitions before trigger/mute.
