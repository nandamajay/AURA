# Failure Containment Assessment

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Plugin Load Fault Injection
- plugin scan: `{'loaded_count': 6, 'registered_count': 5, 'registered_names': ['automation-domain-plugin', 'driver-domain-plugin', 'media-domain-plugin', 'research-domain-plugin', 'shared-domain-collision'], 'domain_counts': {'driver': 1, 'research': 1, 'media': 1, 'shared': 1, 'automation': 1}, 'overwrite_detected': True, 'collision_plugin_present': True, 'expected_packages': 7}`
- containment signal: bad plugin package did not prevent loading of healthy domain plugins.

## Watchdog Fault Pressure
- registered watches: `12`
- timeout_events: `12`
- killed_events: `8`
- timeout_by_domain: `{'driver': 3, 'media': 3, 'automation': 3, 'research': 3}`
- killed_by_domain: `{'driver': 2, 'media': 2, 'automation': 2, 'research': 2}`
- replay visibility: `{'status_counts': {'200': 12}, 'missing_replay_count': 0, 'sample': {'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-driver-0': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-driver-1': 200, 'coex-wd-task-term-plugin-coexist-20260518T102218Z-yuhxd7-driver': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-media-0': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-media-1': 200, 'coex-wd-task-term-plugin-coexist-20260518T102218Z-yuhxd7-media': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-automation-0': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-automation-1': 200, 'coex-wd-task-term-plugin-coexist-20260518T102218Z-yuhxd7-automation': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-research-0': 200, 'coex-wd-task-kill-plugin-coexist-20260518T102218Z-yuhxd7-research-1': 200, 'coex-wd-task-term-plugin-coexist-20260518T102218Z-yuhxd7-research': 200}}`

## Classification
- Proven: watchdog failure handling remained replay-visible and domain-balanced in this campaign.
- Bounded: plugin failure containment is load-time only; runtime trust boundaries remain weak.
