# Plugin Coexistence Report

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`
Artifact: `AURA/data/outputs/runtime_discovery/plugin_coexistence_plugin-coexist-20260518T102218Z-yuhxd7.json`
Window: `2026-05-18T10:22:18.761265+00:00` -> `2026-05-18T10:23:51.722712+00:00`

## Scope
- Controlled synthetic multi-domain coexistence validation.
- No architecture rewrite, no infra escalation.

## Workloads
- Domains: `driver`, `media`, `automation`, `research`
- Tasks created: `56`
- Task completion: all domains reached `completed=14/14`
- Replay final status: all domains `200=14/14`, `integrity_ok=14/14`

## Before/After Coexistence State
- Queue before: `{'P0_critical': 0, 'P1_normal': 0, 'P2_background': 0, 'running': 0, 'completed_today': 630, 'failed_today': 0}`
- Queue after: `{'P0_critical': 0, 'P1_normal': 0, 'P2_background': 0, 'running': 0, 'completed_today': 686, 'failed_today': 0}`
- Audit delta rows: `794`
- Audit delta mismatch: `0`

## Observed Domain Start-Lag (Queue Pressure Signal)
- `driver`: p50=0.349s, p95=0.64s, max=0.673s
- `media`: p50=1.163s, p95=1.621s, max=1.644s
- `automation`: p50=16.77s, p95=17.539s, max=17.604s
- `research`: p50=0.858s, p95=1.21s, max=2.323s

## Key Findings
- Replay namespace boundary: `namespace_mismatch_count=0` with full task-log coverage (`56/56`).
- Governance phase1 isolation held: non-target pending remained `12` for media/automation/research before phase2 contention.
- Websocket/SSE cross-domain visibility is high under shared-channel mode (`foreign_ratio ~0.75`).
- Background domain (`automation`/P2) showed materially higher queue lag (p95 `17.539s`) than other domains (<= `1.621s`).
- Retry normalization remained monotonic but showed run-to-run carryover (`[4,5,6]`), indicating shared retry-state continuity for same op keys.
- Watchdog events were balanced across domains and replay-visible (`missing_replay_count=0`).
- CI governance/replay/architecture hard-fail checks remained passing (`passed=True`, `exit_code=0`).

## Safe / Bounded / Unsafe Conditions
### Safe
- `replay_namespace_bleed`
- `governance_cross_contamination`
### Bounded
- `audit_chronology_mixing`
- `shared_replay_buffer_pressure`
- `watchdog_cross_domain_effects`
- `plugin_failure_containment`
- `plugin_induced_operational_drift`
### Unsafe
- `queue_starvation_between_plugins`
- `websocket_event_interference`
- `retry_order_interaction`

## Truthful Conclusion
- Coexistence is viable for controlled internal workloads only with explicit acceptance of shared-channel interference and P2 lag sensitivity.
- Current runtime does not provide strong plugin isolation guarantees.
