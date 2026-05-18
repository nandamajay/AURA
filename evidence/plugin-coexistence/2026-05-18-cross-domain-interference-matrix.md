# Cross-Domain Interference Matrix

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

- `replay_namespace_bleed`: safe | value=0
- `governance_cross_contamination`: safe | value=0
- `audit_chronology_mixing`: bounded | value=52 (Global append-only audit is intentionally mixed by time across domains.)
- `queue_starvation_between_plugins`: unsafe | value=True
- `websocket_event_interference`: unsafe | value=0.751
- `retry_order_interaction`: unsafe | value=['driver', 'media', 'automation', 'research']
- `shared_replay_buffer_pressure`: bounded | value=1028
- `watchdog_cross_domain_effects`: bounded | value=False
- `plugin_failure_containment`: bounded | value=True (Plugin load failures did not prevent task queue activity, but no hard runtime isolation exists.)
- `plugin_induced_operational_drift`: bounded | value=12

## Event Interference Evidence
- Broadcast calls: `1028`
- Duplicate drops: `16`
- WS recipients min/max: `0/0`
- watcher `driver`: total=1012, own=253, foreign=759, foreign_ratio=0.75
- watcher `media`: total=380, own=95, foreign=285, foreign_ratio=0.75
- watcher `automation`: total=1012, own=253, foreign=759, foreign_ratio=0.75
- watcher `research`: total=382, own=95, foreign=287, foreign_ratio=0.751
