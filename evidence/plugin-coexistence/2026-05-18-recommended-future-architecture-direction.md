# Recommended Future Architecture Direction

Run ID: `plugin-coexist-20260518T102218Z-yuhxd7`

## Direction (No Rewrite)
1. Keep single-node deterministic architecture (SQLite + in-memory bus + Docker Compose).
2. Add explicit domain partition keys in runtime metadata (task/replay/governance/event).
3. Preserve append-only global audit, but add first-class domain-scoped query views.
4. Add bounded queue fairness controls for P2 starvation mitigation (without distributed queues).
5. Add event channel scoping conventions per domain (without introducing Kafka/Redis).
6. Add plugin identity collision guardrails in registry (prevent overwrite ambiguity).
7. Keep watchdog/replay hooks as mandatory lineage layer.

## Pressure Points to Address First
- Shared websocket/system channel interference.
- P2 lag under mixed-priority coexistence.
- Retry stream state carryover across runs for reused op keys.
- Plugin registry collision overwrite behavior.

## Explicit Non-Recommendations
- No Kubernetes, Kafka, distributed queue, or microservice split in current maturity stage.
