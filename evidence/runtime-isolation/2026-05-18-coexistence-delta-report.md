# Coexistence Delta Report

Comparison windows:
- Baseline: `plugin_coexistence_plugin-coexist-20260518T102218Z-yuhxd7.json`
- Final: `plugin_coexistence_plugin-coexist-20260518T111458Z-zj26wp.json`

## Delta Summary
- `websocket_event_interference`: `unsafe -> bounded` (foreign_ratio `~0.75 -> 0.0`)
- `retry_order_interaction`: `unsafe -> safe` (`[4,5,6] -> [1,2,3]`)
- `queue_starvation_between_plugins`: `unsafe -> bounded`
- `replay_namespace_bleed`: remained `safe`
- `governance_cross_contamination`: remained `safe`
- `shared_replay_buffer_pressure`: remained `bounded`

## Queue Fairness Shift
- Automation p95 lag: `17.539s -> 15.899s`
- Automation fairness overrides: `0 -> 14` (from queue isolation metrics)

## Interference Shift
- Per-domain collectors:
  - baseline: each watcher saw mostly foreign traffic (`foreign_ratio ~0.75`)
  - final: each watcher saw own-domain traffic only (`foreign_ratio 0.0`)

## Retry Lineage Shift
- baseline retry attempts observed: `[4,5,6]`
- final retry attempts observed: `[1,2,3]`
- final scoped retry keys include domain/run/op ownership.

## Remaining Bounds
- Queue lag can still rise under mixed high-pressure windows.
- Replay buffer remains bounded-loss under pressure, now with explicit accounting.
